from __future__ import annotations

import uuid
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from . import db


bp = Blueprint("web", __name__)


def allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in current_app.config["ALLOWED_EXTENSIONS"]
    )


def serialize_job(job) -> dict:
    return {key: job[key] for key in job.keys()}


@bp.get("/")
def index():
    return render_template(
        "index.html",
        jobs=db.list_jobs(limit=8),
        counts=db.job_counts(),
    )


@bp.post("/upload")
def upload():
    if "file" not in request.files:
        flash("Choose an audio or video file to upload.", "error")
        return redirect(url_for("web.index"))

    uploaded = request.files["file"]
    if not uploaded.filename:
        flash("Choose an audio or video file to upload.", "error")
        return redirect(url_for("web.index"))

    if not allowed_file(uploaded.filename):
        extensions = ", ".join(sorted(current_app.config["ALLOWED_EXTENSIONS"]))
        flash(f"Unsupported file type. Allowed: {extensions}", "error")
        return redirect(url_for("web.index"))

    original_name = Path(uploaded.filename).name
    safe_name = secure_filename(original_name) or "audio"
    path = Path(safe_name)
    job_id = uuid.uuid4().hex[:12]
    stored_name = f"{path.stem}_{job_id}{path.suffix.lower()}"
    stored_path = Path(current_app.config["UPLOAD_DIR"]) / stored_name
    uploaded.save(stored_path)

    db.create_job(
        {
            "id": job_id,
            "original_name": original_name,
            "stored_path": str(stored_path),
            "model": current_app.config["WHISPER_MODEL"],
        }
    )
    flash(f"{original_name} has been queued for transcription.", "success")
    return redirect(url_for("web.job_detail", job_id=job_id))


@bp.get("/jobs")
def jobs():
    return render_template("jobs.html", jobs=db.list_jobs(limit=250))


@bp.get("/jobs/<job_id>")
def job_detail(job_id: str):
    job = db.get_job(job_id)
    if job is None:
        abort(404)
    return render_template("job_detail.html", job=job)


@bp.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = db.get_job(job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(serialize_job(job))


@bp.get("/download/<job_id>/<kind>")
def download(job_id: str, kind: str):
    job = db.get_job(job_id)
    if job is None:
        abort(404)

    column = {
        "transcript": "transcript_path",
        "timestamped": "timestamped_path",
    }.get(kind)
    if column is None:
        abort(404)

    path_value = job[column]
    if not path_value:
        abort(404)
    path = Path(path_value)
    if not path.exists():
        abort(404)

    stem = secure_filename(Path(job["original_name"]).stem) or "transcript"
    suffix = "transcript" if kind == "transcript" else "timestamped"
    return send_file(
        path,
        as_attachment=True,
        download_name=f"{stem}_{suffix}.txt",
        mimetype="text/plain; charset=utf-8",
    )


@bp.get("/settings")
def settings():
    config = current_app.config
    return render_template(
        "settings.html",
        settings={
            "Version": current_app.config.get("APP_VERSION", "0.1.0"),
            "Whisper model": config["WHISPER_MODEL"],
            "Device": config["WHISPER_DEVICE"],
            "Compute type": config["WHISPER_COMPUTE_TYPE"],
            "Beam size": config["WHISPER_BEAM_SIZE"],
            "VAD filter": config["WHISPER_VAD_FILTER"],
            "Word timestamps": config["WHISPER_WORD_TIMESTAMPS"],
            "Data directory": str(config["DATA_DIR"]),
            "Maximum upload": f"{config['MAX_CONTENT_LENGTH'] // 1024 // 1024} MB",
            "Listen address": f"{config['HOST']}:{config['PORT']}",
        },
    )


@bp.get("/health")
def health():
    counts = db.job_counts()
    return jsonify(
        {
            "status": "ok",
            "app": "WhisperDesk",
            "version": current_app.config.get("APP_VERSION", "0.1.0"),
            "model": current_app.config["WHISPER_MODEL"],
            "device": current_app.config["WHISPER_DEVICE"],
            "jobs": counts,
        }
    )
