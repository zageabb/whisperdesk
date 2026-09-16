# WhisperDesk

WhisperDesk is a local-first Flask web application for uploading audio/video files to an Ubuntu server and transcribing them with Faster-Whisper.

**Current version: v0.1.0**

## What it does

- Upload audio or video through a browser
- Queue transcription work so long jobs do not block the upload request
- Run Faster-Whisper locally on the server
- Automatically detect spoken language
- Use VAD filtering to reduce silence
- Generate a clean UTF-8 transcript
- Generate a timestamped UTF-8 transcript
- Keep transcription job history in SQLite
- Recover an interrupted processing job after application restart
- Download the generated transcript files through the browser
- Expose a `/health` endpoint for deployment monitoring

The initial architecture deliberately keeps transcription separate from LLM reasoning:

```text
Audio / video
     |
     v
Faster-Whisper
     |
     +--> Plain transcript
     |
     +--> Timestamped transcript
     |
     v
Future: Ollama analysis / summaries / actions
```

## Repository structure

```text
whisperdesk/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── transcriber.py
│   ├── web.py
│   ├── static/
│   │   └── css/
│   │       └── app.css
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── job_detail.html
│       ├── jobs.html
│       └── settings.html
├── deploy/
│   └── whisperdesk.service
├── tests/
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
└── start.sh
```

## Ubuntu installation

### 1. Clone the repository

```bash
cd ~
git clone https://github.com/zageabb/whisperdesk.git
cd whisperdesk
```

### 2. Reuse the existing Whisper environment

If Faster-Whisper has already been installed at `~/whisper-env`, reuse it:

```bash
source ~/whisper-env/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This adds Flask, Gunicorn and the other app dependencies to the same environment. It will not reinstall the Whisper model if the model is already present in the local model cache.

If `~/whisper-env` does not exist, create a dedicated environment instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure the application

```bash
cp .env.example .env
nano .env
```

For a CPU-only server, the defaults are appropriate:

```dotenv
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
HOST=0.0.0.0
PORT=5070
```

Change `SECRET_KEY` to a long random value.

The default persistent data directory is:

```text
~/.local/share/whisperdesk
```

It contains:

```text
uploads/
transcripts/
whisperdesk.db
```

Keeping this outside the repository prevents normal Git deployments from replacing application data.

## Run manually

Make the launcher executable once:

```bash
chmod +x start.sh
```

Then run:

```bash
./start.sh
```

`start.sh` checks for Python in this order:

1. `WHISPERDESK_PYTHON` if explicitly configured
2. `~/whisper-env/bin/python`
3. `.venv/bin/python`

The default browser address is:

```text
http://SERVER-IP:5070
```

Health check:

```text
http://SERVER-IP:5070/health
```

## First transcription

1. Open WhisperDesk in a browser.
2. Select an audio or video file.
3. Click **Upload and transcribe**.
4. The file is written to the persistent upload directory.
5. The job is added to SQLite as `queued`.
6. The background worker changes it to `processing` and lazily loads `large-v3`.
7. The first use of a model may download model files into the normal local Hugging Face cache.
8. When complete, download either the plain or timestamped transcript.

## Supported file extensions

- MP3
- WAV
- M4A
- MP4
- MOV
- MKV
- WebM
- FLAC
- OGG
- AAC
- Opus
- MPEG / MPG

Faster-Whisper uses PyAV for media decoding, so a separate system FFmpeg installation is not required for the normal supported path.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Network bind address |
| `PORT` | `5070` | Web port |
| `WHISPER_MODEL` | `large-v3` | Faster-Whisper model |
| `WHISPER_DEVICE` | `cpu` | `cpu` or supported GPU mode |
| `WHISPER_COMPUTE_TYPE` | `int8` | Compute type used by CTranslate2 |
| `WHISPER_BEAM_SIZE` | `5` | Transcription beam size |
| `WHISPER_VAD_FILTER` | `true` | Voice activity detection |
| `WHISPER_WORD_TIMESTAMPS` | `true` | Request word timing information |
| `MAX_UPLOAD_MB` | `4096` | Maximum browser upload size |
| `WHISPERDESK_DATA_DIR` | `~/.local/share/whisperdesk` | Durable application data |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Production / systemd

WhisperDesk is designed to run with **one Gunicorn worker and multiple threads** in v0.1.0. The transcription queue is persisted in SQLite and serviced by the worker's background transcription thread.

A user-level systemd template is provided at:

```text
deploy/whisperdesk.service
```

Assuming the repo is cloned to `~/whisperdesk`:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/whisperdesk.service ~/.config/systemd/user/whisperdesk.service
systemctl --user daemon-reload
systemctl --user enable --now whisperdesk
systemctl --user status whisperdesk
```

Logs:

```bash
journalctl --user -u whisperdesk -f
```

Restart after an update:

```bash
systemctl --user restart whisperdesk
```

## Updating

```bash
cd ~/whisperdesk
git pull
source ~/whisper-env/bin/activate
pip install -r requirements.txt
systemctl --user restart whisperdesk
```

The persistent transcription data is stored outside the Git checkout by default.

## Development

For local development:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The built-in Flask development server is intended only for development. `start.sh` uses Gunicorn for the Ubuntu service path.

## Roadmap

Likely next stages:

- Transcript preview in the browser
- Optional deletion/retention controls for uploaded media
- Ollama analysis after transcription
- Meeting summaries and action extraction
- Speaker diarisation
- SRT/VTT subtitle export
- API endpoints for programmatic uploads and retrieval
- Batch uploads
- Search across previous transcripts

## Security notes

WhisperDesk v0.1.0 is designed primarily for a trusted local network. It validates upload extensions, uses generated stored filenames, and keeps runtime files outside the Git repository. If exposed beyond a trusted LAN, add authentication and HTTPS/reverse-proxy controls before use.
