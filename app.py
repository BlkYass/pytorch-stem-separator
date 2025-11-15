import os
import uuid
import shutil
import subprocess
from pathlib import Path

from flask import (
    Flask, request, render_template_string,
    send_from_directory, redirect, url_for, flash
)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
RESULTS_DIR = BASE_DIR / "results"

UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

MODEL_NAME = "htdemucs_ft"  # the model you confirmed works

app = Flask(__name__)
app.secret_key = "dev-debug-key"  # needed for flash()


# ------------------------------------------------------------------
# HTML Template
# ------------------------------------------------------------------
TEMPLATE = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>Vocal Separator (Debug Mode)</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; }
        .box { padding: 1rem; border: 1px solid #ccc; border-radius: 8px; }
        audio { width: 100%; margin-top: 0.5rem; }
        .error { color: red; }
    </style>
</head>
<body>
<h1>🎤 Vocal Separator (Demucs)</h1>
<div class="box">
    <form method="post" action="{{ url_for('separate') }}" enctype="multipart/form-data">
        <p>Upload audio file:</p>
        <input type="file" name="file" accept="audio/*" required>
        <p><button type="submit">Separate</button></p>
    </form>

    {% if messages %}
        <ul class="error">
        {% for m in messages %}
            <li>{{ m }}</li>
        {% endfor %}
        </ul>
    {% endif %}
</div>

{% if vocals_url or instrumental_url %}
    <h2>Results</h2>
    <div class="box">
        {% if vocals_url %}
            <h3>Vocals</h3>
            <audio controls src="{{ vocals_url }}"></audio>
            <p><a href="{{ vocals_url }}" download>Download vocals</a></p>
        {% endif %}
        {% if instrumental_url %}
            <h3>Instrumental</h3>
            <audio controls src="{{ instrumental_url }}"></audio>
            <p><a href="{{ instrumental_url }}" download>Download instrumental</a></p>
        {% endif %}
    </div>
{% endif %}
</body>
</html>
"""


# ------------------------------------------------------------------
# DEMUCS Debug Wrapper
# ------------------------------------------------------------------
def run_demucs_debug(input_path: Path):
    """
    Runs Demucs exactly with your working flags.
    Prints FULL stdout to help debugging.
    """

    job_id = uuid.uuid4().hex
    job_dir = RESULTS_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    out_root = job_dir / "raw"
    out_root.mkdir(exist_ok=True)

    cmd = [
        "demucs",
        "--two-stems", "vocals",
        "-n", MODEL_NAME,
        "--shifts", "0",
        "--overlap", "0.05",
        "--jobs", "1",
        "--mp3",
        "--out", str(out_root),
        str(input_path),
    ]

    print("\n=================== DEMUCS COMMAND ===================")
    print(" ".join(cmd))
    print("=======================================================\n")

    # Run the command and capture ALL output
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print("===== DEMUCS OUTPUT START =====")
    print(process.stdout)
    print("===== DEMUCS OUTPUT END =====\n")

    if process.returncode != 0:
        raise RuntimeError(
            f"Demucs error (exit code {process.returncode}). "
            f"See above output."
        )

    # Locate output folder
    base = input_path.stem
    model_dir = out_root / MODEL_NAME / base

    if not model_dir.is_dir():
        # fallback: search recursively
        found = None
        for root, dirs, _ in os.walk(out_root):
            for d in dirs:
                if d == base:
                    found = Path(root) / d
                    break
        if not found:
            raise RuntimeError("Could not locate Demucs output folder.")
        model_dir = found

    print("Located Demucs output folder:", model_dir)

    # Pick vocal / instrumental
    vocals = None
    inst = None

    for fn in os.listdir(model_dir):
        low = fn.lower()
        full = model_dir / fn
        if "vocals" in low and not low.startswith("no_"):
            vocals = full
        if "no_vocals" in low or "accompaniment" in low or "other" in low:
            inst = full

    if not vocals or not inst:
        raise RuntimeError("Could not find vocals/instrumental files.")

    # Copy to root of job_dir
    vocals_out = job_dir / f"{base}_vocals{vocals.suffix}"
    inst_out = job_dir / f"{base}_instrumental{inst.suffix}"

    shutil.copy2(vocals, vocals_out)
    shutil.copy2(inst, inst_out)

    print("Saved vocals to:", vocals_out)
    print("Saved instrumental to:", inst_out)
    print("------------------------------------------------------\n")

    return vocals_out, inst_out


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.get("/")
def index():
    return render_template_string(TEMPLATE, messages=None)


@app.post("/separate")
def separate():
    file = request.files.get("file")
    if not file:
        flash("No file uploaded.")
        return redirect(url_for("index"))

    filename = file.filename
    ext = Path(filename).suffix
    upload_name = f"{uuid.uuid4().hex}{ext}"
    upload_path = UPLOAD_DIR / upload_name
    file.save(upload_path)

    print("\n========== NEW REQUEST ==========")
    print("Uploaded file saved to:", upload_path)

    try:
        vocals, inst = run_demucs_debug(upload_path)
    except Exception as e:
        print("ERROR:", e)
        flash(str(e))
        return redirect(url_for("index"))

    # Build URLs
    vocals_rel = vocals.relative_to(RESULTS_DIR)
    inst_rel = inst.relative_to(RESULTS_DIR)

    return render_template_string(
        TEMPLATE,
        vocals_url=url_for("serve_results", path=str(vocals_rel)),
        instrumental_url=url_for("serve_results", path=str(inst_rel)),
        messages=None,
    )


@app.route("/results/<path:path>")
def serve_results(path):
    return send_from_directory(RESULTS_DIR, path, as_attachment=False)


# ------------------------------------------------------------------
# DEBUG MODE SERVER
# ------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"Flask debug server running → http://127.0.0.1:{port}")
    print("Debug mode enabled. All errors will show in the terminal.\n")
    app.run(host="0.0.0.0", port=port, debug=True)

