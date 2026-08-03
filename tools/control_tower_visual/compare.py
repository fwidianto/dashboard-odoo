from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance

PIXEL_THRESHOLD = 12
MAX_CHANGED_RATIO = 0.005


def compare_image(baseline_path: Path, current_path: Path, diff_path: Path) -> tuple[float, str]:
    baseline = Image.open(baseline_path).convert("RGB")
    current = Image.open(current_path).convert("RGB")
    if baseline.size != current.size:
        return 1.0, f"SIZE_MISMATCH baseline={baseline.size} current={current.size}"

    difference = ImageChops.difference(baseline, current)
    pixels = list(difference.getdata())
    changed = sum(1 for pixel in pixels if max(pixel) > PIXEL_THRESHOLD)
    ratio = changed / max(len(pixels), 1)

    if changed:
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        ImageEnhance.Contrast(difference).enhance(4.0).save(diff_path)
    return ratio, "PASS" if ratio <= MAX_CHANGED_RATIO else "DIFF"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare current Control Tower screenshots to approved baselines.")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--diff", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    baseline_root = args.baseline.resolve()
    current_root = args.current.resolve()
    diff_root = args.diff.resolve()
    report_path = args.report.resolve()

    rows: list[tuple[str, str, float, str]] = []
    failed = False
    for baseline_path in sorted(baseline_root.rglob("*.png")):
        relative = baseline_path.relative_to(baseline_root)
        current_path = current_root / relative
        if not current_path.exists():
            rows.append((str(relative), "MISSING", 1.0, "Current screenshot missing"))
            failed = True
            continue
        ratio, status = compare_image(baseline_path, current_path, diff_root / relative)
        rows.append((str(relative), status, ratio, ""))
        failed = failed or status != "PASS"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Control Tower Visual Regression Report",
        "",
        f"Pixel threshold: {PIXEL_THRESHOLD}",
        f"Maximum changed-pixel ratio: {MAX_CHANGED_RATIO:.3%}",
        "",
        "| Screenshot | Status | Changed pixels | Note |",
        "|---|---:|---:|---|",
    ]
    for screenshot, status, ratio, note in rows:
        lines.append(f"| `{screenshot}` | {status} | {ratio:.3%} | {note} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(report_path.read_text(encoding="utf-8"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
