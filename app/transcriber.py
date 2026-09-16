from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

from . import db


log = logging.getLogger(__name__)
_worker_lock = threading.Lock()
_worker: "TranscriptionWorker | None" = None


def format_timestamp(seconds: float | None) -> str:
    seconds = max(float(seconds or 0.0), 0.0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


class TranscriptionWorker(threading.Thread):
    def __init__(self, config: dict[str, Any]):
        super().__init__(name="whisperdesk-transcriber", daemon=True)
        self.config = config
        self.database_path = Path(config["DATABASE_PATH"])
        self.transcript_dir = Path(config["TRANSCRIPT_DIR"])
        self.model: WhisperModel | None = None
        self.stop_event = threading.Event()

    def get_model(self) -> WhisperModel:
        if self.model is None:
            log.info(
                "Loading Whisper model=%s device=%s compute_type=%s",
                self.config["WHISPER_MODEL"],
                self.config["WHISPER_DEVICE"],
                self.config["WHISPER_COMPUTE_TYPE"],
            )
            self.model = WhisperModel(
                self.config["WHISPER_MODEL"],
                device=self.config["WHISPER_DEVICE"],
                compute_type=self.config["WHISPER_COMPUTE_TYPE"],
            )
        return self.model

    def run(self) -> None:
        log.info("Transcription worker started")
        while not self.stop_event.is_set():
            job = db.claim_next_job(self.database_path)
            if job is None:
                self.stop_event.wait(1.0)
                continue
            self.process_job(job)

    def process_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        source = Path(job["stored_path"])
        try:
            if not source.exists():
                raise FileNotFoundError(f"Uploaded file no longer exists: {source}")

            self.transcript_dir.mkdir(parents=True, exist_ok=True)
            safe_stem = source.stem.rsplit("_", 1)[0] or "transcript"
            plain_path = self.transcript_dir / f"{safe_stem}_{job_id}_transcript.txt"
            timestamped_path = self.transcript_dir / f"{safe_stem}_{job_id}_timestamped.txt"
            partial_plain_path = plain_path.with_suffix(".partial.txt")
            partial_timestamped_path = timestamped_path.with_suffix(".partial.txt")
            resume_at = max(float(job.get("progress_seconds") or 0), 0.0)

            model = self.get_model()
            segments, info = model.transcribe(
                str(source),
                language=job.get("language"),
                beam_size=self.config["WHISPER_BEAM_SIZE"],
                vad_filter=self.config["WHISPER_VAD_FILTER"],
                word_timestamps=self.config["WHISPER_WORD_TIMESTAMPS"],
                clip_timestamps=[max(0.0, resume_at - 1.0)],
            )
            duration = getattr(info, "duration", None)
            language = getattr(info, "language", None)
            header = (
                f"WhisperDesk transcript\n"
                f"Source: {job['original_name']}\n"
                f"Model: {job['model']}\n"
                f"Language: {language or 'unknown'}\n\n"
            )
            if resume_at <= 0 or not partial_plain_path.exists():
                partial_plain_path.write_text(header, encoding="utf-8")
                partial_timestamped_path.write_text(header, encoding="utf-8")
                resume_at = 0.0

            db.update_progress(
                self.database_path,
                job_id,
                language=language,
                duration_seconds=float(duration) if duration is not None else None,
                progress_seconds=resume_at,
                partial_transcript_path=str(partial_plain_path),
                partial_timestamped_path=str(partial_timestamped_path),
            )

            with partial_plain_path.open("a", encoding="utf-8") as plain_file, partial_timestamped_path.open(
                "a", encoding="utf-8"
            ) as timestamped_file:
                for segment in segments:
                    if float(segment.end) <= resume_at:
                        continue
                    text = segment.text.strip()
                    if not text:
                        continue
                    plain_file.write(text + "\n")
                    timestamped_file.write(
                        f"[{format_timestamp(segment.start)} --> "
                        f"{format_timestamp(segment.end)}] {text}\n"
                    )
                    plain_file.flush()
                    timestamped_file.flush()
                    progress = float(segment.end)
                    db.update_progress(
                        self.database_path,
                        job_id,
                        language=language,
                        duration_seconds=float(duration) if duration is not None else None,
                        progress_seconds=progress,
                        partial_transcript_path=str(partial_plain_path),
                        partial_timestamped_path=str(partial_timestamped_path),
                    )

            os.replace(partial_plain_path, plain_path)
            os.replace(partial_timestamped_path, timestamped_path)
            db.complete_job(
                self.database_path,
                job_id,
                language=getattr(info, "language", None),
                duration_seconds=float(duration) if duration is not None else None,
                transcript_path=str(plain_path),
                timestamped_path=str(timestamped_path),
            )
            log.info("Completed transcription job %s", job_id)
        except Exception as exc:  # noqa: BLE001 - worker must record job failures
            log.exception("Transcription job %s failed", job_id)
            db.fail_job(self.database_path, job_id, str(exc))


def start_worker(config: dict[str, Any]) -> TranscriptionWorker:
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return _worker
        db.recover_interrupted_jobs(config["DATABASE_PATH"])
        _worker = TranscriptionWorker(config)
        _worker.start()
        return _worker
