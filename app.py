#!/usr/bin/env python3
"""
Web UI for the OTP extraction automation.

Run:
    pip install -r requirements.txt
    python app.py
    # open http://localhost:5000
"""

import io
import tempfile
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from PIL import Image

from extract_otp import find_otp_in_image, extract_otp_from_pdf

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload cap


@app.route("/")
def index():
    return render_template("index.html")


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

    try:
        if name.endswith(".pdf"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(data)
                tmp.flush()
                otp = extract_otp_from_pdf(tmp.name, crop=crop)
        else:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            if crop:
                x, y, w, h = crop
                img = img.crop((x, y, x + w, y + h))
            otp = find_otp_in_image(img)
    except Exception as e:
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

    if otp:
        return jsonify(otp=otp)
    return jsonify(error="No OTP found in the image"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
