from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx


PART_BYTES = 8 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload one learner video through the local service")
    parser.add_argument("media", type=Path)
    parser.add_argument("--service", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    size = args.media.stat().st_size
    part_count = max(1, (size + PART_BYTES - 1) // PART_BYTES)
    now = datetime.now(timezone.utc)
    start_body = {
        "course_id": "rag-systems-101",
        "learner_id": "learner-42",
        "media_name": args.media.name,
        "part_count": part_count,
        "deadline": (now + timedelta(hours=1)).isoformat(),
    }

    with httpx.Client(timeout=120.0) as client:
        started = client.post(f"{args.service}/course-media/uploads", json=start_body)
        started.raise_for_status()
        session = started.json()
        completed_parts = []
        with args.media.open("rb") as media:
            for part in session["parts"]:
                response = client.put(part["upload_url"], content=media.read(PART_BYTES))
                response.raise_for_status()
                completed_parts.append(
                    {"part_number": part["part_number"], "etag": response.headers["ETag"]}
                )

        report_body = {
            "course_id": start_body["course_id"],
            "learner_id": start_body["learner_id"],
            "object_key": session["object_key"],
            "deadline": session["deadline"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "parts": completed_parts,
        }
        finished = client.post(
            f"{args.service}/course-media/uploads/{session['upload_id']}/complete",
            json=report_body,
        )
        finished.raise_for_status()
        report = finished.json()
        print(
            f"{report['delivery_status']}: {report['course_id']} / "
            f"{report['learner_id']} / {report['object_key']}"
        )


if __name__ == "__main__":
    main()
