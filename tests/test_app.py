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
    assert payload["version"] == "0.1.0"
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
