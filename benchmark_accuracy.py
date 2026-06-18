#!/usr/bin/env python3
"""
Accuracy benchmark for the OTP extractor.

Runs find_otp_with_candidates() over every image in data/, compares the
predicted OTP against a hand-labelled ground truth (read visually from each
image's green "OTP" arrow), and writes per-image results + summary metrics to
a timestamped log file.

    python benchmark_accuracy.py
"""

import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

from extract_otp import find_otp_with_candidates

DATA_DIR = Path(__file__).parent / "data"
LOG_PATH = Path(__file__).parent / "accuracy_report.log"

# Ground truth: the code the green "OTP" arrow points to in each image.
# Labelled by visual inspection. Two are marked uncertain (see notes).
GROUND_TRUTH = {
    "14d0a720-282e-4111-b673-d9006b9d3b07.png": "017509",
    "8c6ba2a1-3b1d-4bb2-bc56-c884187db2bc.png": "047637",
    "da9fedbc-dac8-4ccc-ae8d-992e2c30318d.png": "470696",   # faint leading digit, uncertain
    "otp(1).png": "753050",
    "otp.png": "313776",
    "otp_test_1.png": "416673",
    "otp_test_2.png": "824269",
    "otp_test_3.png": "992440",   # trailing 0 stylized as italic 'o'
    "otp_test_4.png": "768608",
    "otp_test_5.png": "879962",
    "WhatsApp Image 2026-05-30 at 9.55.08 PM.jpeg": "753050",
}

NOTES = {
    "da9fedbc-dac8-4ccc-ae8d-992e2c30318d.png": "ground-truth uncertain (faint leading digit)",
    "otp_test_3.png": "true trailing 0 is stylized as italic 'o'",
}


def run():
    lines = []
    def log(s=""):
        lines.append(s)

    log("=" * 78)
    log("OTP EXTRACTOR — ACCURACY BENCHMARK")
    log(f"Run at:  {datetime.now().isoformat(timespec='seconds')}")
    log(f"Data:    {DATA_DIR}")
    log(f"Images:  {len(GROUND_TRUTH)}")
    log("=" * 78)
    log()

    results = []
    for name, truth in GROUND_TRUTH.items():
        path = DATA_DIR / name
        rec = {"name": name, "truth": truth, "pred": None,
               "candidates": [], "ms": 0.0, "status": "", "match": False,
               "error": None}
        if not path.exists():
            rec["status"] = "MISSING FILE"
            results.append(rec)
            continue
        try:
            img = Image.open(path)
            started = time.perf_counter()
            out = find_otp_with_candidates(img)
            rec["ms"] = (time.perf_counter() - started) * 1000
            rec["pred"] = out["otp"]
            rec["candidates"] = out["candidates"]
        except Exception as e:  # noqa: BLE001
            rec["error"] = str(e)
            rec["status"] = "ERROR"
            results.append(rec)
            continue

        if rec["pred"] is None:
            rec["status"] = "NO DETECTION"
        elif rec["pred"] == truth:
            rec["status"] = "CORRECT"
            rec["match"] = True
        else:
            # was the truth even among the candidates the OCR saw?
            seen = truth in rec["candidates"]
            rec["status"] = "WRONG PICK" if seen else "WRONG (truth not OCR'd)"
        results.append(rec)

    # ---- per-image detail ----
    log("PER-IMAGE RESULTS")
    log("-" * 78)
    for r in results:
        log(f"File:        {r['name']}")
        log(f"  Expected:  {r['truth']}")
        log(f"  Predicted: {r['pred']}")
        log(f"  Status:    {r['status']}    ({r['ms']:.0f} ms)")
        if r["candidates"]:
            log(f"  Candidates seen: {', '.join(r['candidates'])}")
        if r["error"]:
            log(f"  Error:     {r['error']}")
        if r["name"] in NOTES:
            log(f"  Note:      {NOTES[r['name']]}")
        log()

    # ---- metrics ----
    total = len(results)
    correct = sum(1 for r in results if r["match"])
    detected = sum(1 for r in results if r["pred"] is not None)
    errored = sum(1 for r in results if r["status"] == "ERROR")
    truth_in_cands = sum(1 for r in results if r["truth"] in r["candidates"])
    times = [r["ms"] for r in results if r["pred"] is not None]
    avg_ms = sum(times) / len(times) if times else 0.0

    log("=" * 78)
    log("SUMMARY METRICS")
    log("-" * 78)
    log(f"  Total images:                 {total}")
    log(f"  Exact-match accuracy:         {correct}/{total} = {correct/total*100:.1f}%")
    log(f"  Detection rate (any code):    {detected}/{total} = {detected/total*100:.1f}%")
    if detected:
        log(f"  Precision when it answers:    {correct}/{detected} = {correct/detected*100:.1f}%")
    log(f"  Truth present in OCR output:  {truth_in_cands}/{total} = {truth_in_cands/total*100:.1f}%")
    log(f"      (ceiling: best the selection heuristic could reach with this OCR)")
    log(f"  Errors / crashes:             {errored}")
    log(f"  Avg time per image:           {avg_ms:.0f} ms")
    log("=" * 78)

    # breakdown by status
    log()
    log("STATUS BREAKDOWN")
    log("-" * 78)
    from collections import Counter
    for status, n in Counter(r["status"] for r in results).most_common():
        log(f"  {status:28s} {n}")
    log("=" * 78)

    report = "\n".join(lines) + "\n"
    LOG_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nLog written to: {LOG_PATH}")


if __name__ == "__main__":
    run()
