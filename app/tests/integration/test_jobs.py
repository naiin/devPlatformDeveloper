from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy.orm import Session

from platform_app.db import Job, engine
from platform_app.queue import redis_client
from platform_app.worker import Worker

pytestmark = pytest.mark.integration


def submit(client, text="durable job", operation="uppercase"):
    response = client.post("/jobs", json={"text": text, "operation": operation})
    assert response.status_code == 202
    return response.json()


def test_job_round_trip_and_persistence(client):
    job = submit(client)
    assert job["status"] == "queued"
    assert Worker("test").cycle(block_ms=1) == 1
    response = client.get("/jobs/" + job["id"])
    assert response.json()["result"] == "DURABLE JOB"
    assert response.json()["status"] == "completed"
    # A new database connection reads persisted state, independent of API/worker memory.
    engine().dispose()
    with Session(engine()) as db:
        assert db.get(Job, job["id"]).result == "DURABLE JOB"


def test_reverse_and_listing(client):
    job = submit(client, "abc", "reverse")
    Worker("test").cycle(block_ms=1)
    assert client.get("/jobs").json()[0]["result"] == "cba"
    assert client.get("/jobs/" + job["id"]).json()["attempts"] == 1


@pytest.mark.parametrize(
    "payload", [{"text": ""}, {"text": "x", "operation": "exec"}, {"text": "x" * 10_001}]
)
def test_input_validation(client, payload):
    assert client.post("/jobs", json=payload).status_code == 422


def test_unknown_job_and_limit(client):
    assert client.get("/jobs/missing").status_code == 404
    assert client.get("/jobs?limit=0").status_code == 422
    assert client.get("/jobs?limit=101").status_code == 422


def test_queue_outage_does_not_lose_accepted_job(client):
    job = submit(client)
    worker = Worker("test")
    with patch.object(worker.redis, "xadd", side_effect=ConnectionError("outage")):
        with pytest.raises(ConnectionError):
            worker.dispatch()
    with Session(engine()) as db:
        row = db.get(Job, job["id"])
        assert row.status == "queued"
        assert row.enqueued_at is None
    worker.cycle(block_ms=1)
    assert client.get("/jobs/" + job["id"]).json()["status"] == "completed"


def test_redelivery_after_commit_before_ack_is_idempotent(client):
    job = submit(client)
    first = Worker("first", reclaim_idle_ms=0)
    with patch.object(first.redis, "xack", side_effect=ConnectionError("crash before ack")):
        with pytest.raises(ConnectionError):
            first.cycle(block_ms=1)
    assert client.get("/jobs/" + job["id"]).json()["status"] == "completed"
    second = Worker("second", reclaim_idle_ms=0)
    assert second.cycle(block_ms=1) == 1
    result = client.get("/jobs/" + job["id"]).json()
    assert result["attempts"] == 1
    assert second.redis.xpending(second.config.stream, second.config.consumer_group)["pending"] == 0


def test_redis_data_loss_recovered_from_outbox(client):
    job = submit(client)
    worker = Worker("test")
    worker.dispatch()
    redis_client().flushdb()
    worker.config = worker.config.model_copy(update={"outbox_retry_seconds": 0})
    worker.cycle(block_ms=1)
    assert client.get("/jobs/" + job["id"]).json()["status"] == "completed"


def test_readiness_reports_dependency_outage(client):
    assert client.get("/health/ready").status_code == 200
    with patch("platform_app.api.redis_client") as redis:
        redis.return_value.ping.side_effect = ConnectionError("down")
        assert client.get("/health/ready").status_code == 503
    assert client.get("/health/live").status_code == 200
