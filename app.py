#!/usr/bin/env python3
"""
Web UI for the OTP extraction automation.

Run:
    pip install -r requirements.txt
    python app.py
    # open http://localhost:5000
"""

import io
import time
import tempfile
from pathlib import Path

from flask import Flask, request, jsonify
from PIL import Image

from extract_otp import (find_otp_with_candidates, extract_otp_from_pdf_with_candidates,
                         inspect_image)

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload cap

# Allow the API to be called from a separately-hosted frontend (e.g. Vercel).
# Graceful: local dev still runs if flask-cors isn't installed.
try:
    from flask_cors import CORS
    CORS(app, resources={r"/extract": {"origins": "*"}, r"/inspect": {"origins": "*"}})
except ImportError:
    pass


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    if "file" not in request.files or request.files["file"].filename == "":
        return jsonify(error="No file uploaded"), 400

    f = request.files["file"]
    name = f.filename.lower()
    data = f.read()

    crop = None
    if request.form.get("crop"):
        try:
            crop = tuple(int(v) for v in request.form["crop"].split(","))
            if len(crop) != 4:
                raise ValueError
        except ValueError:
            return jsonify(error="Crop must be x,y,w,h"), 400

    started = time.perf_counter()
    try:
        if name.endswith(".pdf"):
            # delete=False + manual unlink: on Windows NamedTemporaryFile holds an
            # exclusive lock, so PyMuPDF can't open the path while the handle is open.
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            try:
                tmp.write(data)
                tmp.close()
                result = extract_otp_from_pdf_with_candidates(tmp.name, crop=crop)
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        else:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            if crop:
                x, y, w, h = crop
                img = img.crop((x, y, x + w, y + h))
            result = find_otp_with_candidates(img)
    except Exception as e:  # noqa: BLE001 - surface any decode/OCR error to the UI
        msg = str(e)
        if "tesseract" in msg.lower() or "not installed" in msg.lower():
            msg = (
                "Tesseract OCR is not installed or not found. "
                "Windows: download the installer from "
                "https://github.com/UB-Mannheim/tesseract/wiki "
                "and install it, then restart the server. "
                "Linux: sudo apt-get install -y tesseract-ocr"
            )
        return jsonify(error=msg), 500

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    otp = result["otp"]
    candidates = result["candidates"]
    if otp:
        rejected = [c for c in candidates if c != otp]
        return jsonify(otp=otp, candidates=candidates, rejected=rejected, ms=elapsed_ms)
    return jsonify(error="No OTP found in the image", candidates=candidates, ms=elapsed_ms), 404


@app.route("/inspect", methods=["POST"])
def inspect():
    """Run the pipeline with each stage exposed (full vs cropped-row prediction)
    for the Inspector dashboard. Images only — PDFs aren't visualised."""
    if "file" not in request.files or request.files["file"].filename == "":
        return jsonify(error="No file uploaded"), 400

    f = request.files["file"]
    if f.filename.lower().endswith(".pdf"):
        return jsonify(error="Inspector works on images, not PDFs"), 400

    started = time.perf_counter()
    try:
        img = Image.open(io.BytesIO(f.read())).convert("RGB")
        stages = inspect_image(img)
    except Exception as e:  # noqa: BLE001
        return jsonify(error=f"Could not process file: {e}"), 500

    stages["ms"] = round((time.perf_counter() - started) * 1000)
    return jsonify(stages)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
