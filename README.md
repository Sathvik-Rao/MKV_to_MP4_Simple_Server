# MKV to MP4 Simple Server

This small Flask app accepts MKV uploads and remuxes/converts them to MP4 using `ffmpeg`.

<div align="center">
    <img src="https://github.com/user-attachments/assets/c77d24fb-b5e8-4c8e-9f86-9753a23bfc99" alt="login" width="360" height="300" />
    <img src="https://github.com/user-attachments/assets/16fa883a-1020-4e66-90e2-89bf8481b911" alt="conversion mode" width="360" height="300" />
    <img src="https://github.com/user-attachments/assets/1f8e4250-2ccd-4600-aa16-1688eb8da309" alt="conversion" width="360" height="300" />
</div>

**Configuration**

Copy `.env.example` to `.env` and set any values you need (the `.env` file is ignored by git).

Run the app directly with values from `.env` loaded by `python-dotenv`.

Environment variables are namespaced with the `_MKV2MP4` suffix to avoid collisions (for example `USERNAME_MKV2MP4`, `PASSWORD_MKV2MP4`, `PORT_MKV2MP4`).

Quick start with Docker Compose:

Build and run the service (uses the bundled `docker-compose.yml`):

```bash
docker-compose up --build -d
```

The service will be available on port `5000` by default and `ffmpeg` is already bundled into the Docker image.

Notes:

- `ffmpeg` is installed inside the image; no additional host setup is required.
- The app runs with Gunicorn. The default login is `admin` / `password123`.

  - The default login values are set in `.env.example` under `USERNAME_MKV2MP4` / `PASSWORD_MKV2MP4`.
  - Configurable Gunicorn runtime options are available via environment variables in `docker-compose.yml`:
    - `GUNICORN_TIMEOUT_MKV2MP4` - increase if uploads or conversions take a long time (default 3600s).
    - `GUNICORN_WORKER_CLASS_MKV2MP4` - worker class (default `gthread`).
    - `GUNICORN_THREADS_MKV2MP4` - threads per worker (default `4`).
    - `CONCURRENT_CONVERSIONS_MKV2MP4` - how many simultaneous `ffmpeg` conversions to allow (default `1`).

  Recommendation: for memory-constrained environments keep `CONCURRENT_CONVERSIONS_MKV2MP4` at `1` and increase `GUNICORN_TIMEOUT_MKV2MP4` to a value large enough for uploads + conversion. Also consider giving the container more RAM (Docker Desktop resource settings) to avoid OOM kills.

## Running locally

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell on Windows
# Or on macOS / Linux:
# source .venv/bin/activate
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

3. Install `ffmpeg`/`ffprobe` (must be on your PATH). For example:

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Windows: download from https://ffmpeg.org and add to PATH
```

4. Copy `.env.example` to `.env` and adjust any settings (optional), then run:

```bash
python app.py
```

> Note: `python app.py` runs the Flask development server which is simple and cross-platform for local testing. The project uses Gunicorn inside the Docker image for a more robust, production-ready server. Gunicorn is not supported on native Windows (it requires a Unix-like environment such as WSL), so using `python app.py` is the easiest local option on Windows.

If you prefer to run a Gunicorn server locally on macOS/Linux or inside WSL, you can use the same command the Docker image uses:

```bash
gunicorn -w 1 -b 0.0.0.0:5000 --timeout 3600 --worker-class gthread --threads 4 app:app
```

5. Open `http://localhost:5000` in your browser. After uploading an MKV you'll be redirected to a progress page. You can also poll the status programmatically at `/progress/<uid>` (JSON) and download when finished at `/download/<uid>`.

## Conversion modes

The web UI now offers four processing modes when you upload an MKV:

- **Auto** (default): Attempts a fast remux (copying streams) and falls back to a full re-encode if that fails.
- **Remux only**: Only attempts a fast remux (very quick if it works). If remuxing fails the conversion stops with an error.
- **Remux video + re-encode audio**: Copies the video stream but re-encodes audio to `AAC` (recommended if you see audio stuttering after remuxing).
- **Convert**: Forces a full re-encode (video + audio), which is slower but most compatible.

If you're seeing audio stuttering after remuxing, try **Remux video + re-encode audio** - it fixes most audio compatibility problems while keeping the conversion fast.
