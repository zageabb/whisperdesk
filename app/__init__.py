from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, request, url_for

from . import db
from .config import Config
from .transcriber import start_worker


__version__ = "0.1.1"


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["APP_VERSION"] = __version__

    if test_config:
        app.config.update(test_config)

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    for key in ("DATA_DIR", "UPLOAD_DIR", "TRANSCRIPT_DIR"):
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)

    db.init_schema(app.config["DATABASE_PATH"])
    app.teardown_appcontext(db.close_db)

    from .web import bp

    app.register_blueprint(bp)

    @app.errorhandler(413)
    def too_large(_error):
        max_mb = app.config["MAX_CONTENT_LENGTH"] // 1024 // 1024
        message = f"The selected file is larger than the {max_mb} MB upload limit."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "error": message}), 413
        flash(message, "error")
        return redirect(request.referrer or url_for("web.index"))

    @app.context_processor
    def inject_app_meta():
        return {
            "app_name": "WhisperDesk",
            "app_version": __version__,
        }

    if app.config.get("START_TRANSCRIPTION_WORKER", True):
        start_worker(dict(app.config))

    return app
