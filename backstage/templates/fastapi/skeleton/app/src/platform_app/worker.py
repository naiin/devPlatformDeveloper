import logging
import signal
import socket
import time
from datetime import UTC, datetime, timedelta

from redis.exceptions import ResponseError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from platform_app.config import settings
from platform_app.db import Job, engine
from platform_app.domain import Operation, transform
from platform_app.queue import redis_client

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, consumer: str | None = None, *, reclaim_idle_ms: int | None = None):
        self.config = settings()
        self.redis = redis_client()
        self.consumer = consumer or socket.gethostname()
        self.reclaim_idle_ms = (
            self.config.reclaim_idle_ms if reclaim_idle_ms is None else reclaim_idle_ms
        )

    def ensure_group(self):
        try:
            self.redis.xgroup_create(
                self.config.stream, self.config.consumer_group, id="0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def dispatch(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.config.outbox_retry_seconds)
        count = 0
        with Session(engine()) as db, db.begin():
            rows = db.scalars(
                select(Job)
                .where(
                    Job.status == "queued",
                    or_(Job.enqueued_at.is_(None), Job.enqueued_at < cutoff),
                )
                .order_by(Job.created_at)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            for job in rows:
                self.redis.xadd(self.config.stream, {"job_id": job.id})
                job.enqueued_at = datetime.now(UTC)
                count += 1
        # If publishing or committing fails, the DB rolls back. Duplicate Redis
        # entries are safe; the processing transaction locks/deduplicates jobs.
        return count

    def process(self, message_id: str, fields: dict) -> None:
        with Session(engine()) as db, db.begin():
            job = db.scalar(select(Job).where(Job.id == fields["job_id"]).with_for_update())
            if job is not None and job.status not in {"completed", "failed"}:
                job.attempts += 1
                try:
                    job.result = transform(job.text, Operation(job.operation))
                    job.status = "completed"
                except ValueError as exc:
                    job.status = "failed"
                    job.error = str(exc)
        # A crash after this commit leaves a pending Redis message. Reclaiming
        # it reads the terminal DB state and ACKs without applying effects twice.
        self.redis.xack(self.config.stream, self.config.consumer_group, message_id)
        self.redis.xdel(self.config.stream, message_id)

    def cycle(self, *, block_ms: int = 1000) -> int:
        self.ensure_group()
        self.dispatch()
        claimed = self.redis.xautoclaim(
            self.config.stream,
            self.config.consumer_group,
            self.consumer,
            self.reclaim_idle_ms,
            "0-0",
            count=10,
        )[1]
        messages = list(claimed)
        if not messages:
            batches = self.redis.xreadgroup(
                self.config.consumer_group,
                self.consumer,
                {self.config.stream: ">"},
                count=10,
                block=block_ms,
            )
            messages = [entry for _, entries in batches for entry in entries]
        for message_id, fields in messages:
            self.process(message_id, fields)
        self.redis.set(f"platform:worker:{self.consumer}:heartbeat", str(time.time()), ex=30)
        return len(messages)


def main():
    logging.basicConfig(level=logging.INFO)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker = Worker()
    while not stopping:
        try:
            worker.cycle()
        except Exception:
            log.exception("Worker cycle failed; durable jobs will be retried")
            time.sleep(2)


if __name__ == "__main__":
    main()
