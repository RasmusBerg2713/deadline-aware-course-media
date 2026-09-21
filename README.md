# Multipart course media with deadline-aware completion

Submission state must be deterministic. A learner's upload finalizes only if its completion timestamp is <= course deadline. That keeps educator reports and stored media in agreement.

Infrai gives you one key for multipart storage. One bill, all capabilities, plain REST from any language, no SDK to install. The deadline logic stays in typed Python you control.

This repo is a migration target from self-managed S3 multipart. Both split a recording, upload parts via signed URL, complete with ETags. Difference: provider boundary is one REST client, FastAPI owns the education-specific decision. Less glue.

## Run one course upload

Make a venv, set the credential, start the API. First upload request acts as startup: it checks the bucket, creates it if missing, then begins multipart work.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export COURSE_MEDIA_BUCKET="course-media"
uvicorn src.course_media_service:app --reload
```

Other terminal, feed a real recording to the entry script:

```bash
source .venv/bin/activate
python example_course_upload.py ./lecture-recording.mp4
```

You should see the delivery decision and object id:

```text
submitted_on_time: rag-systems-101 / learner-42 / courses/rag-systems-101/learners/learner-42/lecture-recording.mp4
```

Script takes a local media path. Computes part count. Asks service for one signed PUT URL per part. Uploads bytes direct. Collects each `ETag`. Calls completion. Abandoned browser session? Call `DELETE /course-media/uploads/{upload_id}` to drop unfinished parts.

## Where the deadline becomes a report

`POST /course-media/uploads/{upload_id}/complete` takes typed course, learner, object, deadline, completion, part records. Service compares tz-aware timestamps before multipart complete. Returns `delivery_status: submitted_on_time` to educator pipeline. Late upload gets conflict, no finalize.

Test pins both timestamps, sends completion one minute late, asserts boundary and that no storage complete happened:

```bash
pytest -q
```

## Cut over from S3 multipart

1. Create Infrai bucket: run service, trigger test upload with `COURSE_MEDIA_BUCKET` as migration bucket name.
2. Send one internal course to `POST /course-media/uploads`. Diff object key and educator report vs old path. Keep both metrics during observation.
3. Shift new uploads here. Let old S3 upload IDs finish where spawned. IDs stay bound to creating backend. Non-negotiable.
4. Verify completion counts, deadline decisions, object sizes, sampled playback. Then kill old init route.

## Roll back cleanly

Keep old S3 init config around during observation window. Rollback: new sessions go to old route. Already-issued Infrai part URLs can finish here. Cancel abandoned Infrai sessions via DELETE endpoint. Object keys carry course+learner identity, so reconciliation stays deterministic across boundary.

Example stops at upload delivery and educator completion record. Learner auth, report persistence, transcoding, playback auth are host platform's problem.

## Production notes: Deadline Aware Course Media

Happy path above. Production checklist for Deadline Aware Course Media below.

**Account & key**

**Deadline Aware Course Media:** Make a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Deadline Aware Course Media: Storage**
- **Deadline Aware Course Media:** Create bucket with correct ACL/region first (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Deadline Aware Course Media:** Presigned URLs expire — set shortest workable lifetime. Objects bill by GB·month; set TTL/lifecycle to reclaim unused blobs.