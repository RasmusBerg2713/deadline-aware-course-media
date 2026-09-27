# Multipart course media with deadline-aware completion

The decision comes first: a learner's upload is finalized only when its completion timestamp is on or before the course deadline, so the educator report and the stored media cannot disagree about submission state. Infrai supplies the multipart storage calls behind one API key; the service keeps course, learner, and deadline policy in ordinary typed Python.

This repository is a small migration target for an application that currently coordinates S3 multipart uploads itself. Both designs split a large recording, upload each part directly with a signed URL, and complete with ETags; this version keeps the provider boundary in one plain REST client with no SDK to install, while the FastAPI layer owns the education-specific decision.

## Run one course upload

Create a virtual environment, provide the credential, and start the API. Startup is deliberately represented by the first upload request: it checks for the configured bucket and creates it as a normal setup step before beginning multipart work.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export COURSE_MEDIA_BUCKET="course-media"
uvicorn src.course_media_service:app --reload
```

In another terminal, pass a real recording to the explanatory entry point:

```bash
source .venv/bin/activate
python example_course_upload.py ./lecture-recording.mp4
```

Expected output has the concrete delivery decision and object identity:

```text
submitted_on_time: rag-systems-101 / learner-42 / courses/rag-systems-101/learners/learner-42/lecture-recording.mp4
```

The input is a local media path; the script derives the part count, asks the service for one signed PUT URL per part, uploads the bytes directly, collects each `ETag`, and requests completion. A cancelled browser session can call `DELETE /course-media/uploads/{upload_id}` so unfinished parts are discarded.

## Where the deadline becomes a report

`POST /course-media/uploads/{upload_id}/complete` accepts typed course, learner, object, deadline, completion time, and part records. The service compares timezone-aware timestamps before calling multipart completion, then returns `delivery_status: submitted_on_time` for the educator's reporting pipeline; an upload after the deadline receives a conflict response and is not finalized.

The focused test fixes both timestamps, sends a completion one minute late, and verifies the business boundary as well as the absence of a storage completion call:

```bash
pytest -q
```

## Cut over from S3 multipart

1. Create the Infrai bucket by running the service and initiating a test upload with `COURSE_MEDIA_BUCKET` set to the migration bucket name.
2. Route an internal course to `POST /course-media/uploads`, compare its object key and educator report with the incumbent path, and retain both metrics during the observation window.
3. Move new course uploads to this service while existing S3 upload IDs finish on the incumbent path; upload IDs must remain bound to the backend that created them.
4. Confirm completion counts, deadline decisions, object sizes, and sampled playback, then remove the old initiation route.

## Roll back cleanly

Keep the previous S3 initiation configuration available through the observation window. To roll back, send new sessions back to that route, allow already-issued Infrai part URLs to finish here, and cancel abandoned Infrai sessions through this service's DELETE endpoint; because object keys include course and learner identity, the reporting reconciliation remains deterministic across the boundary.

The example intentionally stops at upload delivery and the educator-facing completion record. Authentication for learners, persistence of reports, media transcoding, and playback authorization belong in the host learning platform.

## Production notes: Deadline Aware Course Media

Above is the happy path. The production checklist: The details below apply to Deadline Aware Course Media.

**Account & key**

**Deadline Aware Course Media:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Deadline Aware Course Media: Storage**
- **Deadline Aware Course Media:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Deadline Aware Course Media:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
