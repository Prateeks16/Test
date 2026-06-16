#!/usr/bin/env python3
"""
Extract an OTP digit code from an image or PDF.

Usage:
    python extract_otp.py path/to/image.jpg
    python extract_otp.py path/to/image.jpg --crop x,y,w,h
    python extract_otp.py --pdf path/to/email.pdf

System requirement: tesseract-ocr binary must be installed.
    apt-get install -y tesseract-ocr
"""

import io
import re
import sys
import argparse
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

DIGIT_RE = re.compile(r"^\d{4,8}$")
LABEL_RE = re.compile(r"OTP|CODE|PASS|VERIF|PIN", re.IGNORECASE)


def _ocr_tokens(img: Image.Image, config: str = "--psm 11") -> list:
    """Run tesseract and return non-empty tokens with position info."""
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config=config)
    tokens = []
    for i in range(len(d["text"])):
        text = d["text"][i].strip()
        if not text:
            continue
        cx = d["left"][i] + d["width"][i] // 2
        cy = d["top"][i] + d["height"][i] // 2
        tokens.append({"text": text, "cx": cx, "cy": cy,
                       "x": d["left"][i], "conf": d["conf"][i]})
    return tokens


def _preprocess(img: Image.Image) -> Image.Image:
    """Grayscale → 2x upscale → denoise → Otsu threshold."""
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    arr = cv2.resize(arr, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    arr = cv2.fastNlMeansDenoising(arr, h=10)
    _, arr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(arr)


def _select_otp(tokens: list, img_width: int) -> str | None:
    """Pick the most likely OTP from OCR token list."""
    digits = [t for t in tokens if DIGIT_RE.match(t["text"])]
    if not digits:
        return None
    if len(digits) == 1:
        return digits[0]["text"]

    # Find a label token (e.g. "OTP" text or ">" arrow) in the left half of the image.
    labels = [t for t in tokens
              if (LABEL_RE.search(t["text"]) or ">" in t["text"])
              and t["x"] < img_width // 2]

    if labels:
        label = min(labels, key=lambda l: l["cx"])  # leftmost
        def score(c):
            dx = c["cx"] - label["cx"]
            dy = c["cy"] - label["cy"]
            dist = (dx ** 2 + dy ** 2) ** 0.5
            # Prefer candidates to the right on the same row (arrow direction)
            if dx > 0 and abs(dy) < 30:
                dist *= 0.5
            return dist
        return min(digits, key=score)["text"]

    # Fallback: topmost candidate (smallest y)
    return min(digits, key=lambda c: c["cy"])["text"]


def find_otp_in_image(img: Image.Image) -> str | None:
    """
    Attempt to extract an OTP from a PIL image.
    Tries raw OCR first; falls back to preprocessed if no digits found.
    """
    img_rgb = img.convert("RGB")
    W = img_rgb.width

    # Primary: raw image OCR
    tokens = _ocr_tokens(img_rgb)
    otp = _select_otp(tokens, W)
    if otp:
        return otp

    # Fallback: preprocessed (helps with grainy/low-contrast images)
    proc = _preprocess(img_rgb)
    tokens = _ocr_tokens(proc)
    # Preprocessed is 2x upscaled; halve x coords for label-position check
    for t in tokens:
        t["x"] //= 2
        t["cx"] //= 2
        t["cy"] //= 2
    return _select_otp(tokens, W)


def extract_otp(image_path: str, crop: tuple = None) -> str | None:
    """Extract OTP from an image file. crop=(x, y, w, h) to restrict the region."""
    img = Image.open(image_path).convert("RGB")
    if crop:
        x, y, w, h = crop
        img = img.crop((x, y, x + w, y + h))
    return find_otp_in_image(img)


def extract_otp_from_pdf(pdf_path: str, crop: tuple = None) -> str | None:
    """Extract embedded images from a PDF and return the first OTP found."""
    import fitz
    doc = fitz.open(str(pdf_path))
    images = []
    for page in doc:
        for xref in [img[0] for img in page.get_images(full=True)]:
            raw = doc.extract_image(xref)
            img = Image.open(io.BytesIO(raw["image"])).convert("RGB")
            if img.width >= 50 and img.height >= 50:
                images.append((img.width * img.height, img))
    images.sort(reverse=True)  # largest first
    for _, img in images:
        if crop:
            x, y, w, h = crop
            img = img.crop((x, y, x + w, y + h))
        otp = find_otp_in_image(img)
        if otp:
            return otp
    return None


def main():
    parser = argparse.ArgumentParser(description="Extract OTP from an image or PDF.")
    parser.add_argument("image", nargs="?", help="Path to image file")
    parser.add_argument("--pdf", metavar="PATH", help="Path to PDF (scans embedded images)")
    parser.add_argument("--crop", metavar="X,Y,W,H",
                        help="Restrict OCR to this region, e.g. --crop 100,0,150,60")
    args = parser.parse_args()

    if not args.image and not args.pdf:
        parser.error("provide an image path or --pdf PATH")

    crop = tuple(int(v) for v in args.crop.split(",")) if args.crop else None

    if args.pdf:
        otp = extract_otp_from_pdf(args.pdf, crop=crop)
    else:
        otp = extract_otp(args.image, crop=crop)

    if otp:
        print(otp)
    else:
        print("No OTP found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
