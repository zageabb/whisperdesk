from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

    DATA_DIR = Path(
        os.getenv(
            "WHISPERDESK_DATA_DIR",
            str(Path.home() / ".local" / "share" / "whisperdesk"),
        )
    ).expanduser()
    UPLOAD_DIR = DATA_DIR / "uploads"
    TRANSCRIPT_DIR = DATA_DIR / "transcripts"
    DATABASE_PATH = DATA_DIR / "whisperdesk.db"

    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
    WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
    WHISPER_VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    WHISPER_WORD_TIMESTAMPS = os.getenv(
        "WHISPER_WORD_TIMESTAMPS", "true"
    ).lower() in {"1", "true", "yes", "on"}

    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "4096")) * 1024 * 1024
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5070"))

    ALLOWED_EXTENSIONS = {
        "mp3",
        "wav",
        "m4a",
        "mp4",
        "mov",
        "mkv",
        "webm",
        "flac",
        "ogg",
        "aac",
        "opus",
        "mpeg",
        "mpg",
    }
