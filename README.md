# OTP Extractor

Automation that reads a One-Time-Password (OTP) out of an image or PDF using
OCR. Built to slot into an email pipeline: when an OTP email arrives with a
screenshot/PDF, this reads the code automatically — no manual typing.

## Features

- Extracts the OTP from a noisy image even when several decoy numbers are
  present, by locating the **OTP** label/arrow and picking the nearest code.
- Reads codes straight from a PDF (pulls embedded images via PyMuPDF).
- Optional `--crop x,y,w,h` override for fixed-layout screenshots.
- Clean web UI for drag-and-drop testing and visualisation.

## Setup

### Windows

1. Download and run the **Tesseract installer** from the UB Mannheim build:
   https://github.com/UB-Mannheim/tesseract/wiki
   (accept the default install path — the script detects it automatically)

2. Install Python dependencies:
   ```cmd
   pip install -r requirements.txt
   ```

### Linux / macOS

```bash
# macOS
brew install tesseract

# Ubuntu / Debian
sudo apt-get install -y tesseract-ocr

# Python dependencies
pip install -r requirements.txt
```

## Usage

### Command line

```bash
python extract_otp.py path/to/image.jpg          # image -> prints OTP
python extract_otp.py --pdf path/to/email.pdf    # PDF  -> prints OTP
python extract_otp.py image.jpg --crop 100,10,110,50
```

Prints the OTP to stdout (exit 0), or `No OTP found` to stderr (exit 1) — easy
to capture from a shell pipeline or `subprocess`.

### Web UI

```bash
python app.py
# open http://localhost:5000
```

![UI preview](docs/ui_preview.png)

## How it works

1. Run OCR (`pytesseract`, sparse-text mode) over the image.
2. Collect every 4–8 digit candidate.
3. Find the **OTP** / arrow label and pick the digit group nearest to it
   (with a rightward / same-row bias to follow the arrow).
4. Fall back to the single / top-most candidate, or a preprocessed
   (grayscale → upscale → denoise → threshold) pass for low-contrast images.

## Project layout

```
extract_otp.py        Core extraction logic + CLI
app.py                Flask web UI
templates/index.html  Front-end
tests/fixtures/       Sample OTP image and Gmail PDF
docs/ui_preview.png   UI screenshot
```
