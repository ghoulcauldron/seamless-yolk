#!/usr/bin/env python3
"""
build_image_manifests.py
Scans a capsule's asset folders (ghosts, editorials, swatches)
and produces manifests/images_manifest.jsonl with accessory tagging
and CPI extraction for both apparel and accessories.

Usage:
    python scripts/build_image_manifests.py --capsule S126 [--dry-run]
"""

import argparse
import json
import pathlib
import re
import datetime

# ---------------------------------------------------------------------
#  Regex definitions
# ---------------------------------------------------------------------

# CPI pattern: captures style number (3–5 digits) and 6-digit color code.
# Handles prefixes like S126-, F125-, F325-, etc.
CPI_PATTERN = re.compile(
    r"(?:[FS]\d{3}|[A-Z]{2}\d{2})[-_]?(\d{3,5}).*?(\d{6})"
)

# Accessory patterns: style ranges, fabric prefixes, literal matches.
ACCESSORY_PATTERNS = [
    re.compile(r"\b7\d{3}\b"),        # style numbers in 7000 range
    re.compile(r"\bLLC\d+\b", re.I),  # fabric prefix LLC
    re.compile(r"\bACC\b", re.I),     # literal ACC marker
    re.compile(r"ACCESSORY", re.I),   # literal word
]

# ---------------------------------------------------------------------
#  Helper functions
# ---------------------------------------------------------------------

def extract_cpi(filename: str) -> str | None:
    """Extract CPI (style-colorcode) from filename."""
    m = CPI_PATTERN.search(filename)
    if m:
        style, color = m.group(1), m.group(2)
        return f"{style}-{color}"
    return None


def is_accessory_name(filename: str) -> bool:
    """Return True if filename matches accessory heuristics."""
    name = filename.upper()
    return any(p.search(name) for p in ACCESSORY_PATTERNS)


# ---------------------------------------------------------------------
#  Builder
# ---------------------------------------------------------------------

def build_manifest(capsule: str, dry_run: bool = False):
    base = pathlib.Path(f"capsules/{capsule}/assets")
    out_dir = base.parent / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "images_manifest.jsonl"

    manifest = []
    scanned = 0
    anomalies = []

    for kind in ["ghosts", "editorials", "swatches"]:
        folder = base / kind
        if not folder.exists():
            continue

        for file in sorted(folder.glob("*")):
            if not file.is_file():
                continue

            scanned += 1
            fname = file.name

            accessory = is_accessory_name(fname)

            cpi = extract_cpi(fname)
            
            if not cpi:
                anomalies.append({
                    "filename": fname,
                    "asset_type": kind,
                    "reason": "CPI not detected",
                    "is_accessory": accessory
                })


            manifest.append({
                "capsule": capsule,
                "cpi": cpi,
                "asset_type": kind,
                "filename": fname,
                "source_dir": str(file.parent),
                "is_accessory": accessory,
                "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            })

    # Diagnostics
    total = len(manifest)
    with_cpi = sum(1 for r in manifest if r["cpi"])
    without_cpi = total - with_cpi
    accessories = sum(1 for r in manifest if r["is_accessory"])

    if dry_run:
        print(json.dumps(manifest[:5], indent=2))
        print(f"\n🧩 {total} assets scanned | "
              f"{with_cpi} CPIs matched | "
              f"{without_cpi} missing | "
              f"{accessories} accessories tagged.")
        return

    with open(out_path, "w", encoding="utf-8") as fh:
        for row in manifest:
            fh.write(json.dumps(row) + "\n")

    print(f"✅ {total} assets indexed for {capsule} → {out_path}")
    print(f"📊 Summary: {with_cpi} CPIs matched | {without_cpi} missing | "
          f"{accessories} accessories tagged.")
    if scanned == 0:
        print("⚠️  No files found; check asset folder paths.")
    if anomalies:
        anomaly_path = out_dir / "anomalies.jsonl"
        with open(anomaly_path, "w", encoding="utf-8") as f:
            for a in anomalies:
                f.write(json.dumps(a) + "\n")
        print(f"⚠️  {len(anomalies)} anomalies logged → {anomaly_path}")

# ---------------------------------------------------------------------
#  CLI entry
# ---------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    build_manifest(args.capsule, dry_run=args.dry_run)