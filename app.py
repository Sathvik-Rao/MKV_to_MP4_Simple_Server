from flask import (
    Flask,
    request,
    redirect,
    url_for,
    render_template_string,
    session,
    send_file,
    after_this_request,
    jsonify,
)
from werkzeug.utils import secure_filename
import json
import threading
import time
import re
import os
import subprocess
import uuid
from dotenv import load_dotenv

load_dotenv()

# Create Flask app and load config from environment (with sensible defaults)
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY_MKV2MP4", "supersecretkey")

# ---------------- CONFIG ----------------

# Directories (namespaced)
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER_MKV2MP4", "uploads")
OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER_MKV2MP4", "outputs")

# Auth (namespaced)
USERNAME = os.getenv("USERNAME_MKV2MP4", "admin")
PASSWORD = os.getenv("PASSWORD_MKV2MP4", "password123")

# Max upload size (bytes). Default 5 GB (namespaced)
app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("MAX_CONTENT_LENGTH_MKV2MP4", 5 * 1024 * 1024 * 1024)
)

# Auto-create folders on startup
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ---------------- LOGIN PAGE ----------------

login_page = """
<style>
    :root{--bg:#f6f8fb;--card:#ffffff;--accent:#2563eb;--muted:#6b7280;--success:#16a34a}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:var(--bg)}
    .card{background:var(--card);padding:28px;border-radius:12px;box-shadow:0 8px 30px rgba(16,24,40,0.08);width:380px}
    h2{margin:0 0 8px 0;font-size:20px}
    .muted{color:var(--muted);font-size:13px;margin-bottom:14px}
    input[type=text],input[type=password]{width:100%;padding:10px 12px;border:1px solid #e6e9ef;border-radius:8px;margin-bottom:12px;box-sizing:border-box;display:block}
    button{background:var(--accent);color:#fff;padding:10px 14px;border-radius:8px;border:0;cursor:pointer;width:100%}
    .footer{margin-top:12px;text-align:center;color:var(--muted);font-size:12px}
</style>
<div class="card">
    <h2>Sign in</h2>
    <form method="post">
        <input type="text" name="username" placeholder="Username" required autofocus>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Sign in</button>
    </form>
</div>
"""


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if (
            request.form["username"] == USERNAME
            and request.form["password"] == PASSWORD
        ):
            session["logged_in"] = True
            return redirect(url_for("convert"))
        return "Invalid credentials"
    return render_template_string(login_page)


# ---------------- CONVERSION PAGE ----------------

convert_page = """
<style>
    :root{--bg:#f6f8fb;--card:#fff;--accent:#2563eb;--muted:#6b7280}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;background:var(--bg);margin:0;padding:24px}
    .container{max-width:760px;margin:28px auto}
    .card{background:var(--card);padding:22px;border-radius:12px;box-shadow:0 8px 30px rgba(16,24,40,0.06)}
    h2{margin:0 0 8px 0}
    p.muted{color:var(--muted);margin-top:0}
    .drop{display:block;width:100%;min-height:78px;border:2px dashed #e6e9ef;border-radius:10px;padding:20px;text-align:center;color:var(--muted);cursor:pointer;box-sizing:border-box}
    .drop.dragover{background:#f0f6ff;border-color:var(--accent);color:var(--accent)}
    .row{display:flex;gap:12px;align-items:center;margin-top:12px}
    .modes{display:flex;gap:8px;flex-wrap:wrap}
    .mode{padding:8px 10px;border-radius:8px;border:1px solid #e6e9ef;background:#fbfdff}
    .mode input{margin-right:8px}
    .actions{display:flex;gap:8px;margin-top:16px}
    .btn{background:var(--accent);color:#fff;padding:10px 14px;border-radius:8px;border:0;cursor:pointer}
    .btn.ghost{background:#fff;color:var(--accent);border:1px solid #e6e9ef}
    .logout{float:right;font-size:14px}
    .logout.btn.ghost{padding:6px 10px;border-radius:8px;background:#fff;color:var(--muted);border:1px solid #e6e9ef}
    .fileinfo{margin-top:10px;color:var(--muted);font-size:13px;display:block}
</style>
<div class="container">
    <button class="logout btn ghost" type="button" onclick="window.location='/logout'">Logout</button>
    <div class="card">
        <h2>MKV to MP4</h2>
        <p class="muted">Drop an MKV file here or click to select. Choose a processing mode and click Convert.</p>

        <form method="post" enctype="multipart/form-data" id="uploadForm">
            <label id="drop" class="drop">Drop file here or click to select<input id="fileinput" type="file" name="video" accept=".mkv" style="display:none" required></label>
            <div class="fileinfo" id="fileinfo">No file selected</div>

            <div style="margin-top:14px">
                <div style="font-weight:600;margin-bottom:6px">Mode</div>
                <div class="modes">
                    <label class="mode"><input type="radio" name="mode" value="auto" checked>Auto (remux, fallback to convert)</label>
                    <label class="mode"><input type="radio" name="mode" value="remux">Remux only (fastest when compatible)</label>
                    <label class="mode"><input type="radio" name="mode" value="remux_audio">Remux video + Audio convert (fixes audio issues)</label>
                    <label class="mode"><input type="radio" name="mode" value="convert">Convert (full re-encode)</label>
                </div>
            </div>

            <div class="actions">
                <button class="btn" type="submit">Convert</button>
                <button class="btn ghost" type="button" id="clearBtn">Clear</button>
            </div>
        </form>
    </div>
    <div style="text-align:center;margin-top:12px;color:var(--muted);font-size:13px">Output files are removed after download.</div>
</div>

<script>
const drop = document.getElementById('drop');
const input = document.getElementById('fileinput');
const info = document.getElementById('fileinfo');
input.addEventListener('change', ()=>{ info.innerText = input.files[0]?.name || 'No file selected'; });
['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('dragover')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('dragover')}));
drop.addEventListener('drop', ev=>{ if(ev.dataTransfer.files && ev.dataTransfer.files.length){ input.files = ev.dataTransfer.files; info.innerText = input.files[0].name; } });
document.getElementById('uploadForm').addEventListener('submit', ()=>{ if(!input.files.length){ alert('Please select an MKV file to upload'); return false; } return true; });
document.getElementById('clearBtn').addEventListener('click', ()=>{ input.value=''; info.innerText='No file selected'; });
</script>
"""


@app.route("/convert", methods=["GET", "POST"])
def convert():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        file = request.files.get("video")

        if not file or not file.filename.lower().endswith(".mkv"):
            return "Only MKV files are allowed", 400

        uid = str(uuid.uuid4())
        input_path = os.path.join(UPLOAD_FOLDER, uid + ".mkv")
        output_path = os.path.join(OUTPUT_FOLDER, uid + ".mp4")

        # Sanitize and persist the original filename so it can be used for download
        original_filename = secure_filename(os.path.basename(file.filename))
        file.save(input_path)
        # Selected mode (auto, remux, remux_audio, convert)
        mode = request.form.get("mode", "auto")

        # Save metadata to disk so the filename and mode persist across restarts
        meta_path = os.path.join(OUTPUT_FOLDER, uid + ".json")
        try:
            with open(meta_path, "w", encoding="utf-8") as mf:
                json.dump({"original_filename": original_filename, "mode": mode}, mf)
        except Exception:
            app.logger.exception("Failed to write metadata file")

        # Record original filename in in-memory progress so UI can display it immediately
        with progress_lock:
            progress.setdefault(uid, {})
            progress[uid].update({"original_filename": original_filename})
        # Start conversion in background and redirect to progress page
        start_background_conversion(uid, input_path, output_path, mode=mode)
        # The progress page view function is named `progress_page_view`.
        # Use that endpoint name when building the URL to avoid BuildError.
        return redirect(url_for("progress_page_view", uid=uid))

    return render_template_string(convert_page)


# ---------------- LOGOUT ----------------


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT_MKV2MP4", 5000)))


# ---------------- PROGRESS TRACKING ----------------

progress = {}
progress_lock = threading.Lock()

# Track running conversions so they can be cancelled
conversions = {}
conversions_lock = threading.Lock()

CONCURRENT_CONVERSIONS = int(os.getenv("CONCURRENT_CONVERSIONS_MKV2MP4", 1))
conversion_semaphore = threading.BoundedSemaphore(CONCURRENT_CONVERSIONS)


def _time_str_to_seconds(time_str: str) -> float:
    parts = time_str.split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    return float(parts[0])


def start_background_conversion(uid, input_path, output_path, mode="auto"):
    # Ensure we don't clobber metadata like original filename set at upload time
    with progress_lock:
        progress.setdefault(uid, {})
        progress[uid].update({"status": "queued", "percent": 0, "message": "Queued"})

    cancel_event = threading.Event()
    with conversions_lock:
        conversions[uid] = {"proc": None, "cancel": cancel_event}

    def _run():
        try:
            with progress_lock:
                progress[uid].update(
                    {
                        "status": "waiting",
                        "percent": 0,
                        "message": "Waiting for conversion slot",
                    }
                )

            app.logger.info(
                "%s: waiting for conversion slot (concurrency=%s)",
                uid,
                CONCURRENT_CONVERSIONS,
            )
            # Acquire slot, but abort quickly if cancelled before we get one
            acquired_slot = False
            while not acquired_slot:
                if cancel_event.is_set():
                    with progress_lock:
                        progress[uid].update(
                            {"status": "cancelled", "message": "Cancelled before start"}
                        )
                    return
                conversion_semaphore.acquire()
                acquired_slot = True
            app.logger.info("%s: acquired conversion slot", uid)

            # Record selected mode and update status messages
            with progress_lock:
                progress[uid].update({"mode": mode})

            # Branch behavior depending on selected mode
            if mode == "remux":
                with progress_lock:
                    progress[uid].update(
                        {
                            "status": "remuxing",
                            "percent": 0,
                            "message": "Remuxing (copy)",
                        }
                    )
                remux_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    input_path,
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    output_path,
                ]
                app.logger.info("%s: starting remux (fast copy)", uid)
                remux_proc = subprocess.Popen(
                    remux_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
                with conversions_lock:
                    conversions[uid]["proc"] = remux_proc

                while True:
                    if cancel_event.is_set():
                        try:
                            remux_proc.kill()
                        except Exception:
                            pass
                        with progress_lock:
                            progress[uid].update(
                                {"status": "cancelled", "message": "Cancelled"}
                            )
                        return
                    if remux_proc.poll() is not None:
                        break
                    time.sleep(0.1)

                if remux_proc.returncode == 0:
                    app.logger.info("%s: remux succeeded", uid)
                    with progress_lock:
                        progress[uid].update(
                            {
                                "status": "done",
                                "percent": 100,
                                "message": "Remuxed",
                                "output": output_path,
                            }
                        )
                    try:
                        os.remove(input_path)
                    except Exception:
                        pass
                    return
                else:
                    app.logger.info("%s: remux failed (remux-only mode)", uid)
                    with progress_lock:
                        progress[uid].update(
                            {"status": "error", "message": "Remux failed"}
                        )
                    return

            # remux_audio: copy video, re-encode audio to AAC
            if mode == "remux_audio":
                with progress_lock:
                    progress[uid].update(
                        {
                            "status": "remuxing",
                            "percent": 0,
                            "message": "Remuxing (video copy, audio -> AAC)",
                        }
                    )
                remux_audio_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    input_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    output_path,
                ]
                app.logger.info("%s: starting remux (video copy, audio->AAC)", uid)
                remux_proc = subprocess.Popen(
                    remux_audio_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
                with conversions_lock:
                    conversions[uid]["proc"] = remux_proc

                while True:
                    if cancel_event.is_set():
                        try:
                            remux_proc.kill()
                        except Exception:
                            pass
                        with progress_lock:
                            progress[uid].update(
                                {"status": "cancelled", "message": "Cancelled"}
                            )
                        return
                    if remux_proc.poll() is not None:
                        break
                    time.sleep(0.1)

                if remux_proc.returncode == 0:
                    app.logger.info("%s: remux+audio succeeded", uid)
                    with progress_lock:
                        progress[uid].update(
                            {
                                "status": "done",
                                "percent": 100,
                                "message": "Remuxed (audio re-encoded)",
                                "output": output_path,
                            }
                        )
                    try:
                        os.remove(input_path)
                    except Exception:
                        pass
                    return
                else:
                    app.logger.info(
                        "%s: remux+audio failed, falling back to re-encode", uid
                    )

            # If mode == 'convert' skip remux attempts and go straight to re-encode
            if mode == "convert":
                with progress_lock:
                    progress[uid].update(
                        {
                            "status": "converting",
                            "percent": 0,
                            "message": "Converting (full re-encode)",
                        }
                    )
            else:
                # mode == 'auto' (or fall-through from remux_audio failure)
                with progress_lock:
                    progress[uid].update(
                        {
                            "status": "converting",
                            "percent": 0,
                            "message": "Converting (fallback)",
                        }
                    )

            # Full re-encode
            with progress_lock:
                progress[uid].update(
                    {"status": "converting", "percent": 0, "message": "Converting"}
                )

            # Obtain duration via ffprobe
            duration = None
            try:
                ffprobe_cmd = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    input_path,
                ]
                res = subprocess.run(
                    ffprobe_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                duration = float(res.stdout.strip()) if res.stdout else None
            except Exception:
                duration = None

            convert_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                input_path,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                output_path,
            ]
            app.logger.info("%s: starting full re-encode", uid)
            proc = subprocess.Popen(
                convert_cmd, stderr=subprocess.PIPE, universal_newlines=True
            )
            with conversions_lock:
                conversions[uid]["proc"] = proc

            time_re = re.compile(r"time=\s*(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)")

            for line in proc.stderr:
                m = time_re.search(line)
                if m:
                    t = m.group(1)
                    secs = _time_str_to_seconds(t)
                    if duration:
                        pct = min(100, max(0, int((secs / duration) * 100)))
                        with progress_lock:
                            progress[uid].update(
                                {"percent": pct, "message": f"Converting ({pct}%)"}
                            )
                    else:
                        with progress_lock:
                            progress[uid].update(
                                {
                                    "percent": None,
                                    "message": f"Converting (elapsed {t})",
                                }
                            )

                # Check for cancellation while reading stderr
                with conversions_lock:
                    if (
                        conversions.get(uid, {}).get("cancel")
                        and conversions[uid]["cancel"].is_set()
                    ):
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        with progress_lock:
                            progress[uid].update(
                                {"status": "cancelled", "message": "Cancelled"}
                            )
                        return

            proc.wait()

            if proc.returncode == 0:
                with progress_lock:
                    progress[uid].update(
                        {
                            "status": "done",
                            "percent": 100,
                            "message": "Completed",
                            "output": output_path,
                        }
                    )
            else:
                with progress_lock:
                    progress[uid].update(
                        {
                            "status": "error",
                            "message": f"FFmpeg failed ({proc.returncode})",
                        }
                    )

        except Exception as e:
            with progress_lock:
                progress[uid].update({"status": "error", "message": str(e)})
        finally:
            try:
                conversion_semaphore.release()
            except Exception:
                pass
            with conversions_lock:
                try:
                    del conversions[uid]
                except Exception:
                    pass
            try:
                os.remove(input_path)
            except Exception:
                pass
            app.logger.info("%s: conversion slot released", uid)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


@app.route("/progress/<uid>")
def progress_api(uid):
    # Require login to fetch progress
    if not session.get("logged_in"):
        return jsonify({"status": "unauthorized", "message": "Login required"}), 401

    with progress_lock:
        data = progress.get(
            uid, {"status": "unknown", "percent": 0, "message": "Not found"}
        )

    # If original filename not in memory, try to load from disk metadata
    meta_path = os.path.join(OUTPUT_FOLDER, uid + ".json")
    if (not data.get("original_filename")) and os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            data.setdefault("original_filename", meta.get("original_filename"))
        except Exception:
            pass

    return jsonify(data)


@app.route("/cancel/<uid>", methods=["POST"])
def cancel_conversion(uid):
    if not session.get("logged_in"):
        return jsonify({"status": "unauthorized", "message": "Login required"}), 401
    # Signal cancellation to the background worker and kill ffmpeg if running
    with conversions_lock:
        conv = conversions.get(uid)
    if not conv:
        return (
            jsonify(
                {
                    "status": "not_found",
                    "message": "Conversion not found or already finished",
                }
            ),
            404,
        )

    conv["cancel"].set()
    proc = conv.get("proc")
    if proc:
        try:
            proc.kill()
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

    # Remove files if present
    in_path = os.path.join(UPLOAD_FOLDER, uid + ".mkv")
    out_path = os.path.join(OUTPUT_FOLDER, uid + ".mp4")
    try:
        if os.path.exists(in_path):
            os.remove(in_path)
    except Exception:
        pass
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass

    # Remove metadata file if present
    meta_path = os.path.join(OUTPUT_FOLDER, uid + ".json")
    try:
        if os.path.exists(meta_path):
            os.remove(meta_path)
    except Exception:
        pass

    with progress_lock:
        progress.setdefault(uid, {})
        progress[uid].update({"status": "cancelled", "message": "Cancelled by user"})

    return jsonify({"status": "cancelled", "message": "Cancellation requested"})


@app.route("/clear/<uid>", methods=["POST"])
def clear_conversion(uid):
    """Delete output, metadata and progress entry. Cancel running conversion if present."""
    if not session.get("logged_in"):
        return jsonify({"status": "unauthorized", "message": "Login required"}), 401

    # Cancel running conversion if any
    with conversions_lock:
        conv = conversions.get(uid)
    if conv:
        conv.get("cancel").set()
        proc = conv.get("proc")
        if proc:
            try:
                proc.kill()
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass

    # Remove files and metadata
    in_path = os.path.join(UPLOAD_FOLDER, uid + ".mkv")
    out_path = os.path.join(OUTPUT_FOLDER, uid + ".mp4")
    meta_path = os.path.join(OUTPUT_FOLDER, uid + ".json")
    try:
        if os.path.exists(in_path):
            os.remove(in_path)
    except Exception:
        pass
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass
    try:
        if os.path.exists(meta_path):
            os.remove(meta_path)
    except Exception:
        pass

    with progress_lock:
        try:
            del progress[uid]
        except Exception:
            # If not present, that's fine
            pass

    return jsonify({"status": "cleared", "message": "Resources removed"})


progress_page = """
<style>
    :root{--bg:#f6f8fb;--card:#fff;--accent:#2563eb;--muted:#6b7280;--danger:#dc2626;--success:#16a34a}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;background:var(--bg);margin:0;padding:24px}
    .container{max-width:760px;margin:28px auto}
    .card{background:var(--card);padding:22px;border-radius:12px;box-shadow:0 8px 30px rgba(16,24,40,0.06)}
    .status{display:flex;align-items:center;justify-content:space-between;gap:12px}
    .title{font-weight:700}
    .muted{color:var(--muted)}
    .barwrap{width:100%;background:#eef2ff;border-radius:8px;height:18px;margin-top:12px;overflow:hidden}
    .bar{height:100%;width:0%;background:linear-gradient(90deg,var(--accent),#34a853);transition:width 300ms ease}
    .badge{padding:6px 10px;border-radius:999px;font-size:13px;color:#fff}
    .badge.queued{background:#64748b}
    .badge.waiting{background:#f59e0b}
    .badge.converting{background:#2563eb}
    .badge.done{background:var(--success)}
    .actions{margin-top:14px;display:flex;gap:8px}
    .btn{padding:8px 12px;border-radius:8px;border:0;cursor:pointer}
    .btn.primary{background:var(--accent);color:#fff}
    .btn.ghost{background:#fff;border:1px solid #e6e9ef}
</style>
<div class="container">
    <div class="card">
        <div class="status">
            <div>
                <div class="title">Conversion Status</div>
                <div class="muted" id="meta">Starting...</div>
            </div>
            <div id="status" class="badge queued">Starting</div>
        </div>

        <div class="barwrap"><div id="bar" class="bar"></div></div>
        <div style="margin-top:10px;display:flex;justify-content:space-between;align-items:center">
            <div class="muted" id="details"></div>
            <div id="percent" class="muted">0%</div>
        </div>

        <div class="actions" id="actions"></div>
        <div style="margin-top:10px;color:var(--muted);font-size:13px" id="download"></div>
    </div>
</div>

<script>
const uid = "__UID__";
let downloaded=false;
async function poll(){
    const r = await fetch('/progress/'+uid);
    const j = await r.json();
    const bar = document.getElementById('bar');
    const status = document.getElementById('status');
    const meta = document.getElementById('meta');
    const details = document.getElementById('details');
    const pct = document.getElementById('percent');
    const dl = document.getElementById('download');
    const actions = document.getElementById('actions');

    let modeStr = j.mode ? (' ['+j.mode+']') : '';
    meta.innerText = (j.message || '') + modeStr;
    details.innerText = (j.original_filename || '')

    // Set status badge
    status.className = 'badge ' + (j.status||'queued');
    status.innerText = (j.status||'');

    if(j.percent===null){
        pct.innerText = '';
        bar.style.width = '12%';
    } else {
        pct.innerText = (j.percent||0) + '%';
        bar.style.width = (j.percent||0) + '%';
    }

    // Actions and download
    actions.innerHTML = '';
    dl.innerHTML = '';
    if(j.status === 'done'){
            const original = j.original_filename || 'converted.mkv';
            const fname = original.replace(/\.mkv$/i, '.mp4');
            dl.innerHTML = '<a id="downloadlink" href="/download/'+uid+'">Download ' + fname.replace(/</g, '&lt;') + '</a>';
            const clearBtn = document.createElement('button'); clearBtn.className='btn ghost'; clearBtn.innerText='Clear';
            clearBtn.onclick = async ()=>{ clearBtn.disabled=true; const resp = await fetch('/clear/'+uid,{method:'POST'}); if(resp.ok){ dl.innerText='Cleared'; actions.innerHTML=''; } else { clearBtn.disabled=false; meta.innerText='Clear failed' } }
            const homeBtn = document.createElement('button'); homeBtn.className='btn primary'; homeBtn.innerText='Home'; homeBtn.onclick = ()=> window.location.href='/convert';
            actions.appendChild(clearBtn); actions.appendChild(homeBtn);
            const dlLink = document.getElementById('downloadlink'); if(dlLink){ dlLink.addEventListener('click', ()=> downloaded=true); }
            window.addEventListener('beforeunload', ()=>{ try{ if(!downloaded) navigator.sendBeacon('/clear/'+uid); }catch(e){} });
    } else if(j.status === 'error'){
            dl.innerText = 'Error: ' + (j.message||'')
    } else if(j.status === 'cancelled'){
            dl.innerText = 'Cancelled'
    } else {
            // allow cancel
            const cancelBtn = document.createElement('button'); cancelBtn.className='btn ghost'; cancelBtn.innerText='Cancel';
            cancelBtn.onclick = async ()=>{ cancelBtn.disabled=true; const resp = await fetch('/cancel/'+uid,{method:'POST'}); if(resp.ok){ const d = await resp.json(); meta.innerText = d.message || ''; actions.innerHTML=''; } else { cancelBtn.disabled=false; meta.innerText='Cancel failed' } }
            actions.appendChild(cancelBtn);
            setTimeout(poll, 1000);
    }
}
poll();
</script>
"""


@app.route("/progress_page/<uid>")
def progress_page_view(uid):
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template_string(progress_page.replace("__UID__", uid))


@app.route("/download/<uid>")
def download(uid):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    with progress_lock:
        info = progress.get(uid)

    # If not found in memory, check metadata on disk
    meta_path = os.path.join(OUTPUT_FOLDER, uid + ".json")
    if not info or info.get("status") != "done" or not info.get("output"):
        # If progress dict is missing but output file exists, allow download only if metadata confirms
        out_path = os.path.join(OUTPUT_FOLDER, uid + ".mp4")
        if os.path.exists(out_path) and os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                info = {
                    "status": "done",
                    "output": out_path,
                    "original_filename": meta.get("original_filename"),
                }
            except Exception:
                info = None

    if not info or info.get("status") != "done" or not info.get("output"):
        return "File not ready", 404

    output_path = info["output"]

    @after_this_request
    def cleanup(response):
        try:
            os.remove(output_path)
        except Exception:
            pass
        # Remove associated metadata file too
        try:
            meta_path = os.path.join(OUTPUT_FOLDER, uid + ".json")
            if os.path.exists(meta_path):
                os.remove(meta_path)
        except Exception:
            pass
        with progress_lock:
            try:
                del progress[uid]
            except Exception:
                pass
        return response

    # Use original filename (change extension to .mp4)
    orig = info.get("original_filename") or "converted.mkv"
    name_root, _ext = os.path.splitext(orig)
    safe_name = secure_filename(name_root) + ".mp4"

    return send_file(output_path, as_attachment=True, download_name=safe_name)
