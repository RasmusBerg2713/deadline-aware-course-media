from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.course_media_service import app, get_infrai


class RecordingMultipart:
    def __init__(self) -> None:
        self.completed = False

    def complete(self, upload_id: str, parts: list[dict[str, object]]) -> dict[str, object]:
        self.completed = True
        return {"key": "course.mp4", "size_bytes": 12}


class FakeInfrai:
    def __init__(self) -> None:
        self.storage = type("Storage", (), {})()
        self.storage.multipart = RecordingMultipart()


def test_late_submission_is_rejected_before_storage_completion() -> None:
    fake = FakeInfrai()
    app.dependency_overrides[get_infrai] = lambda: fake
    request = {
        "course_id": "agents-201",
        "learner_id": "learner-7",
        "object_key": "courses/agents-201/learners/learner-7/demo.mp4",
        "deadline": datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc).isoformat(),
        "completed_at": datetime(2026, 9, 11, 9, 1, tzinfo=timezone.utc).isoformat(),
        "parts": [{"part_number": 1, "etag": "etag-1"}],
    }

    try:
        response = TestClient(app).post(
            "/course-media/uploads/upload-123/complete",
            json=request,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "submission arrived after the learner deadline"
    assert fake.storage.multipart.completed is False
