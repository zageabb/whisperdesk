from __future__ import annotations

import io

from app import create_app


def make_app(tmp_path):
    data_dir = tmp_path / "data"
    return create_app(
        {
            "TESTING": True,
            "START_TRANSCRIPTION_WORKER": False,
            "DATA_DIR": data_dir,
            "UPLOAD_DIR": data_dir / "uploads",
            "TRANSCRIPT_DIR": data_dir / "transcripts",
            "DATABASE_PATH": data_dir / "whisperdesk.db",
            "MAX_CONTENT_LENGTH": 10 * 1024 * 1024,
        }
    )


def test_health(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["app"] == "WhisperDesk"
    assert payload["version"] == "0.2.0"
    assert payload["jobs"]["queued"] == 0


def test_upload_creates_queued_job(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake audio"), "meeting.mp3")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"meeting.mp3" in response.data
    assert b"queued" in response.data

    with app.app_context():
        from app import db

        jobs = db.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["original_name"] == "meeting.mp3"
        assert jobs[0]["status"] == "queued"


def test_async_upload_returns_job_url(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake audio"), "meeting.mp3")},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["filename"] == "meeting.mp3"
    assert payload["job_id"]
    assert payload["redirect_url"].endswith(payload["job_id"])


def test_rejects_unsupported_extension(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"not media"), "notes.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Unsupported file type" in response.data


def test_async_rejects_unsupported_extension(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"not media"), "notes.txt")},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Unsupported file type" in payload["error"]


def test_job_api_exposes_transcription_progress(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake audio"), "meeting.mp3")},
        content_type="multipart/form-data",
    )

    with app.app_context():
        from app import db

        job = db.list_jobs()[0]
        partial = tmp_path / "data" / "transcripts" / "meeting.partial.txt"
        partial.write_text("Partial transcript\n", encoding="utf-8")
        db.update_progress(
            app.config["DATABASE_PATH"],
            job["id"],
            language="en",
            duration_seconds=120.0,
            progress_seconds=30.0,
            partial_transcript_path=str(partial),
            partial_timestamped_path=str(partial),
        )
        job_id = job["id"]

    payload = client.get(f"/api/jobs/{job_id}").get_json()
    assert payload["progress_seconds"] == 30.0
    assert payload["duration_seconds"] == 120.0
    assert payload["partial_transcript_path"] == str(partial)

    response = client.get(f"/download/{job_id}/partial-transcript")
    assert response.status_code == 200
    assert response.data == b"Partial transcript\n"


def test_segments_api_returns_recent_timestamped_lines(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake audio"), "meeting.mp3")},
        content_type="multipart/form-data",
    )
    with app.app_context():
        from app import db

        job = db.list_jobs()[0]
        partial = tmp_path / "data" / "transcripts" / "meeting.partial.txt"
        partial.write_text(
            "WhisperDesk transcript\n\n[00:00:00.000 --> 00:00:03.000] Hello\n",
            encoding="utf-8",
        )
        db.update_progress(
            app.config["DATABASE_PATH"], job["id"], language="en",
            duration_seconds=60.0, progress_seconds=3.0,
            partial_transcript_path=str(partial),
            partial_timestamped_path=str(partial),
        )
        job_id = job["id"]

    payload = client.get(f"/api/jobs/{job_id}/segments").get_json()
    assert payload["segments"] == ["[00:00:00.000 --> 00:00:03.000] Hello"]
