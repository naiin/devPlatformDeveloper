from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from platform_app.config import settings
from platform_app.db import Job, engine, session
from platform_app.domain import Operation
from platform_app.queue import redis_client

app = FastAPI(title="DevPlatform Jobs", version="1.0.0", root_path=settings().root_path)
DB = Annotated[Session, Depends(session)]


class JobRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    operation: Operation = Operation.uppercase


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    text: str
    operation: str
    status: str
    result: str | None
    error: str | None
    attempts: int
    created_at: datetime


@app.get("/health/live")
def live():
    return {"status": "ok", "version": settings().app_version}


@app.get("/health/ready")
def ready():
    try:
        with engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        redis_client().ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Dependencies unavailable") from exc
    return {"status": "ready", "version": settings().app_version}


@app.post("/jobs", response_model=JobResponse, status_code=202)
def submit(payload: JobRequest, db: DB):
    # PostgreSQL is the durable outbox. The worker publishes queued rows into
    # Redis; accepting a job never depends on Redis being available.
    job = Job(text=payload.text, operation=payload.operation.value)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@app.get("/jobs", response_model=list[JobResponse])
def list_jobs(db: DB, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    return list(db.scalars(select(Job).order_by(Job.created_at.desc(), Job.id).limit(limit)))


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: DB):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
