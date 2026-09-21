from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated, Any, Callable, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .infrai_storage import Infrai, InfraiError


class StartCourseUpload(BaseModel):
    course_id: str = Field(min_length=1, max_length=80)
    learner_id: str = Field(min_length=1, max_length=80)
    media_name: str = Field(min_length=1, max_length=180)
    part_count: int = Field(ge=1, le=10_000)
    deadline: datetime


class UploadPart(BaseModel):
    part_number: int
    upload_url: str


class UploadSession(BaseModel):
    upload_id: str
    object_key: str
    deadline: datetime
    parts: list[UploadPart]


class CompletedPart(BaseModel):
    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1)


class FinishCourseUpload(BaseModel):
    course_id: str
    learner_id: str
    object_key: str
    deadline: datetime
    completed_at: datetime
    parts: list[CompletedPart] = Field(min_length=1)


class EducatorReport(BaseModel):
    course_id: str
    learner_id: str
    object_key: str
    delivery_status: Literal["submitted_on_time"]
    completed_at: datetime
    storage_result: dict[str, Any]


def submitted_on_time(deadline: datetime, completed_at: datetime) -> bool:
    if deadline.tzinfo is None or completed_at.tzinfo is None:
        raise ValueError("deadline and completed_at must include a timezone")
    return completed_at <= deadline


@lru_cache
def get_infrai() -> Infrai:
    return Infrai.from_environment()


InfraiDependency = Annotated[Infrai, Depends(get_infrai)]
app = FastAPI(title="Course media delivery")


def _as_http_error(error: InfraiError) -> HTTPException:
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return HTTPException(status_code=status, detail={"code": error.code, "error": error.detail})


@app.post("/course-media/uploads", response_model=UploadSession)
def start_upload(request: StartCourseUpload, infrai: InfraiDependency) -> UploadSession:
    bucket = os.environ.get("COURSE_MEDIA_BUCKET", "course-media")
    object_key = f"courses/{request.course_id}/learners/{request.learner_id}/{request.media_name}"
    try:
        bucket_record = infrai.storage.bucket.get(bucket)
        if not bucket_record.get("found", True):
            infrai.storage.bucket.create(bucket)
        created = infrai.storage.multipart.create(bucket, object_key)
        upload_id = str(created["upload_id"])
        parts = [
            UploadPart(
                part_number=number,
                upload_url=str(infrai.storage.multipart.presign_part(upload_id, number)["url"]),
            )
            for number in range(1, request.part_count + 1)
        ]
    except InfraiError as error:
        raise _as_http_error(error) from error
    return UploadSession(
        upload_id=upload_id,
        object_key=object_key,
        deadline=request.deadline,
        parts=parts,
    )


@app.post("/course-media/uploads/{upload_id}/complete", response_model=EducatorReport)
def finish_upload(
    upload_id: str,
    request: FinishCourseUpload,
    infrai: InfraiDependency,
) -> EducatorReport:
    if not submitted_on_time(request.deadline, request.completed_at):
        raise HTTPException(status_code=409, detail="submission arrived after the learner deadline")
    try:
        result = infrai.storage.multipart.complete(
            upload_id,
            [part.model_dump() for part in request.parts],
        )
    except InfraiError as error:
        raise _as_http_error(error) from error
    return EducatorReport(
        course_id=request.course_id,
        learner_id=request.learner_id,
        object_key=request.object_key,
        delivery_status="submitted_on_time",
        completed_at=request.completed_at,
        storage_result=result,
    )


@app.delete("/course-media/uploads/{upload_id}")
def cancel_upload(upload_id: str, infrai: InfraiDependency) -> dict[str, str]:
    try:
        infrai.storage.multipart.abort(upload_id)
    except InfraiError as error:
        raise _as_http_error(error) from error
    return {"upload_id": upload_id, "status": "cancelled"}
