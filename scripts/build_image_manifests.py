#!/usr/bin/env python3
"""
build_image_manifests.py
Scans a capsule's asset folders (ghosts, editorials, swatches)
and produces manifests/images_manifest.jsonl with accessory tagging.

Usage:
    python scripts/build_image_manifests.py --capsule S126 [--dry-run]
"""

import argparse, json, pathlib, re, datetime

# ---------------------------------------------------------------------
#  Heuristics
# ---------------------------------------------------------------------
ACCESSORY_PATTERNS = [
    re.compile(r"\b7\d{3}\b"),        # style numbers in 7000 range
    re.compile(r"\bLLC\d+\b", re.I),  # fabric/prefix LLC
    re.compile(r"\bACC\b", re.I),     # literal ACC marker
    re.compile(r"ACCESSORY", re.I),
]

# extract capsule, style, colorcode from filenames like:
# S126-3019 BSP031 418102 IVORY_FINAL_ghost_0543.jpg
CPI_PATTERN = re.compile(r"(S\d{3})[-_ ]?(\d{4})[ _-]+.*?(\d{6})")


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

    for kind in ["ghosts", "editorials", "swatches"]:
        folder = base / kind
        if not folder.exists():
            continue

        for file in sorted(folder.glob("*")):
            if not file.is_file():
                continue

            scanned += 1
            fname = file.name
            # Try to extract CPI
            m = CPI_PATTERN.search(fname)
            cpi = f"{m.group(2)}-{m.group(3)}" if m else None

            # Accessory tagging
            accessory = is_accessory_name(fname)

            manifest.append({
                "capsule": capsule,
                "cpi": cpi,
                "asset_type": kind,
                "filename": fname,
                "source_dir": str(file.parent),
                "is_accessory": accessory,
                "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            })

    if dry_run:
        print(json.dumps(manifest[:5], indent=2))
        print(f"🧩 {len(manifest)} assets would be written (dry-run).")
        return

    with open(out_path, "w", encoding="utf-8") as fh:
        for row in manifest:
            fh.write(json.dumps(row) + "\n")

    print(f"✅ {len(manifest)} assets indexed for {capsule} → {out_path}")
    if scanned == 0:
        print("⚠️  No files found; check asset folder paths.")


# ---------------------------------------------------------------------
#  CLI entry
# ---------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    build_manifest(args.capsule, dry_run=args.dry_run)