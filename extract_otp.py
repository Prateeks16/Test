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
import shutil


def _configure_tesseract() -> None:
    """Point pytesseract at the tesseract binary.

    On Linux/macOS the binary is normally on PATH (apt/brew). On Windows the
    official installer does NOT add it to PATH, so resolve it explicitly:
    honour a TESSERACT_CMD override, else probe the standard install dirs.
    """
    if shutil.which("tesseract"):
        return  # already on PATH, nothing to do

    import os

    candidates = []
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd:
        candidates.append(env_cmd)
    candidates += [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for path in candidates:
        if path and Path(path).is_file():
            pytesseract.pytesseract.tesseract_cmd = path
            return


_configure_tesseract()

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


def _find_arrow_anchor(img: Image.Image) -> dict | None:
    """Locate the green "OTP" arrow badge by colour.

    Returns {"cx","cy","x","y","w","h"} for the badge, or None when no
    sufficiently large green region is present. The badge is a solid green shape
    on the left, on the same row as the real code — a far more reliable marker
    than OCR'ing the white "OTP" text, which Tesseract mangles into noise
    ("fore", "im", ...).
    """
    arr = np.array(img.convert("RGB"))
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (40, 80, 80), (85, 255, 255))
    mask[:, img.width // 2:] = 0  # the arrow lives in the left half
    n, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))  # largest blob (skip background)
    if stats[idx, cv2.CC_STAT_AREA] < 300:  # too small to be the badge
        return None
    x, y, w, h = (int(stats[idx, cv2.CC_STAT_LEFT]), int(stats[idx, cv2.CC_STAT_TOP]),
                  int(stats[idx, cv2.CC_STAT_WIDTH]), int(stats[idx, cv2.CC_STAT_HEIGHT]))
    cx, cy = centroids[idx]
    return {"cx": float(cx), "cy": float(cy), "x": x, "y": y, "w": w, "h": h}


_DIGITS_ONLY = "-c tessedit_char_whitelist=0123456789"


def _arrow_band_tokens(img: Image.Image, arrow: dict) -> list:
    """OCR a horizontal strip at the arrow's row and return digit tokens.

    Isolating the OTP row drops the decoy rows above/below, which lets Tesseract
    read codes the full-image pass misses. Runs several PSM modes with a digit
    whitelist (forces letter-shaped glyphs like an italic 'o' to read as '0') and
    unions the results; selection's longest-on-row rule then votes the winner.
    Token cy is pinned to the arrow row so selection treats these as on-row.
    """
    cy = arrow["cy"]
    pad = max(int(arrow["h"] * 1.6), 48)
    top = max(0, int(cy - pad))
    bot = min(img.height, int(cy + pad))
    proc = _preprocess(img.crop((0, top, img.width, bot)))  # 2x upscaled, binarised

    # Mix a faithful read (no whitelist) with digit-forced reads across PSM modes.
    # Tagged by source so selection can vote by agreement across config *types*,
    # not raw pass count (3 PSM agreeing on one misread shouldn't outvote a
    # faithful read).
    passes = [("band_norm", "--psm 11"),
              ("band_wl", f"--psm 7 {_DIGITS_ONLY}"),
              ("band_wl", f"--psm 11 {_DIGITS_ONLY}"),
              ("band_wl", f"--psm 6 {_DIGITS_ONLY}")]
    tokens = []
    for src, cfg in passes:
        for t in _ocr_tokens(proc, config=cfg):
            t["x"] //= 2
            t["cx"] //= 2
            t["cy"] = int(cy)
            t["src"] = src
            tokens.append(t)
    return tokens


def _select_otp(tokens: list, img_width: int, label_anchor: tuple | None = None) -> str | None:
    """Pick the most likely OTP from OCR token list.

    label_anchor=(cx, cy) is the OTP marker position (e.g. the green arrow) when
    known from colour detection; the code nearest and to its right is preferred.
    Falls back to a text label ("OTP"/arrow), then to the topmost digit group.
    """
    digits = [t for t in tokens if DIGIT_RE.match(t["text"])]
    if not digits:
        return None
    if len(digits) == 1:
        return digits[0]["text"]

    label = None
    if label_anchor is not None:
        label = {"cx": label_anchor[0], "cy": label_anchor[1]}
    else:
        # Find a label token (e.g. "OTP" text or ">" arrow) in the left half.
        labels = [t for t in tokens
                  if (LABEL_RE.search(t["text"]) or ">" in t["text"])
                  and t["x"] < img_width // 2]
        if labels:
            label = min(labels, key=lambda l: l["cx"])  # leftmost

    if label:
        # Vote by distinct source (full / band-normal / band-whitelist): a code
        # agreed on by independent config types is more trustworthy than one a
        # single config repeats. Breaks "824269" (full) vs "324269" (whitelist)
        # and "768608" (2 sources) vs "768603" (1) cleanly.
        src_votes = {}
        for d in digits:
            src_votes.setdefault(d["text"], set()).add(d.get("src", "full"))

        def score(c):
            dx = c["cx"] - label["cx"]
            dy = c["cy"] - label["cy"]
            dist = (dx ** 2 + dy ** 2) ** 0.5
            on_row = dx > 0 and abs(dy) < 30  # to the right, same row (arrow direction)
            if not on_row:
                return (1, 0, 0, 0, dist)
            # On-row rank: longest first (full code beats a fragment like "3440"),
            # then most agreed-on across sources, then prefer the faithful full
            # pass over a band-only read, then nearest.
            full_first = 0 if "full" in src_votes[c["text"]] else 1
            return (0, -len(c["text"]), -len(src_votes[c["text"]]), full_first, dist)
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
    arrow = _find_arrow_anchor(img_rgb)
    anchor = (arrow["cx"], arrow["cy"]) if arrow else None

    # Primary: raw image OCR, plus an OCR of just the arrow's row (drops decoy
    # rows, recovers codes the full-image pass garbles).
    tokens = _ocr_tokens(img_rgb)
    for t in tokens:
        t["src"] = "full"
    if arrow:
        tokens = tokens + _arrow_band_tokens(img_rgb, arrow)
    otp = _select_otp(tokens, W, label_anchor=anchor)
    if otp:
        return otp

    # Fallback: preprocessed full image (helps grainy/low-contrast images)
    proc = _preprocess(img_rgb)
    tokens = _ocr_tokens(proc)
    # Preprocessed is 2x upscaled; halve x coords for label-position check
    for t in tokens:
        t["x"] //= 2
        t["cx"] //= 2
        t["cy"] //= 2
    return _select_otp(tokens, W, label_anchor=anchor)


def find_otp_with_candidates(img: Image.Image) -> dict:
    """Like find_otp_in_image, but also report the candidates considered.

    Returns {"otp": str|None, "candidates": [str, ...]} where candidates is the
    de-duplicated list of 4-8 digit groups the OCR pass saw (decoys + the pick),
    in reading order. Used by the web UI to show what was rejected and why the
    pick is trustworthy.
    """
    img_rgb = img.convert("RGB")
    W = img_rgb.width
    arrow = _find_arrow_anchor(img_rgb)
    anchor = (arrow["cx"], arrow["cy"]) if arrow else None

    tokens = _ocr_tokens(img_rgb)
    for t in tokens:
        t["src"] = "full"
    if arrow:
        tokens = tokens + _arrow_band_tokens(img_rgb, arrow)
    otp = _select_otp(tokens, W, label_anchor=anchor)
    if not otp:
        # Fallback pass mirrors find_otp_in_image; candidates come from whichever
        # pass actually produced the answer.
        proc = _preprocess(img_rgb)
        tokens = _ocr_tokens(proc)
        for t in tokens:
            t["x"] //= 2
            t["cx"] //= 2
            t["cy"] //= 2
        otp = _select_otp(tokens, W, label_anchor=anchor)

    candidates = []
    for t in tokens:
        if DIGIT_RE.match(t["text"]) and t["text"] not in candidates:
            candidates.append(t["text"])
    return {"otp": otp, "candidates": candidates}


def _unique_digits(tokens: list) -> list:
    out = []
    for t in tokens:
        if DIGIT_RE.match(t["text"]) and t["text"] not in out:
            out.append(t["text"])
    return out


def inspect_image(img: Image.Image) -> dict:
    """Run the pipeline with each stage exposed for visualisation.

    Returns the arrow location, the crop-band region, and the prediction +
    candidates for the FULL image and the CROPPED row independently, plus the
    final merged result. Used by the Inspector dashboard to show how cropping
    changes the prediction.
    """
    img_rgb = img.convert("RGB")
    W, H = img_rgb.width, img_rgb.height
    arrow = _find_arrow_anchor(img_rgb)
    anchor = (arrow["cx"], arrow["cy"]) if arrow else None

    # Stage A — predict on the full image alone (no band help)
    full_tokens = _ocr_tokens(img_rgb)
    full = {"otp": _select_otp(full_tokens, W, label_anchor=anchor),
            "candidates": _unique_digits(full_tokens)}

    # Stage B — predict on the cropped arrow-row band alone
    band, cropped = None, {"otp": None, "candidates": []}
    if arrow:
        cy, pad = arrow["cy"], max(int(arrow["h"] * 1.6), 48)
        band = {"top": max(0, int(cy - pad)), "bottom": min(H, int(cy + pad)),
                "left": 0, "right": W}
        band_tokens = _arrow_band_tokens(img_rgb, arrow)
        cropped = {"otp": _select_otp(band_tokens, W, label_anchor=anchor),
                   "candidates": _unique_digits(band_tokens)}

    # Stage C — the real merged result the app uses
    final = find_otp_with_candidates(img_rgb)

    return {"width": W, "height": H, "arrow": arrow, "band": band,
            "full": full, "cropped": cropped, "final": final}


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


def extract_otp_from_pdf_with_candidates(pdf_path: str, crop: tuple = None) -> dict:
    """PDF variant of find_otp_with_candidates. Returns the first image's hit
    (with its candidates), else the candidates from the last image scanned."""
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
    result = {"otp": None, "candidates": []}
    for _, img in images:
        if crop:
            x, y, w, h = crop
            img = img.crop((x, y, x + w, y + h))
        result = find_otp_with_candidates(img)
        if result["otp"]:
            return result
    return result


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
