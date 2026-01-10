#!/usr/bin/env python3
"""
promote_state_swatches_to_manifest.py

Promotes state-adopted swatch assets into images_manifest.jsonl.

This is the ONLY mechanism by which locally-created or
Shopify-adopted swatches become publishable assets.

NO Shopify calls.
NO uploads.
Append-only.
"""

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

def load_product_state(capsule: str) -> dict:
    path = Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing product state: {path}")
    return json.loads(path.read_text())

def load_existing_manifest(manifest_path: Path) -> set:
    """
    Returns a set of (cpi, asset_type, filename) already present.
    Used for dedupe.
    """
    existing = set()
    if not manifest_path.exists():
        return existing

    for line in manifest_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cpi = row.get("cpi")
        asset_type = row.get("asset_type")
        if "filename" in row:
            filename = row["filename"]
        elif "file_path" in row:
            filename = Path(row["file_path"]).name
        else:
            filename = None
        existing.add((
            cpi,
            asset_type,
            filename,
        ))
    return existing

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", required=True)
    parser.add_argument("--cpis", nargs="*", help="Optional CPI scope")
    args = parser.parse_args()

    capsule = args.capsule
    scope_cpis = set(args.cpis or [])

    state = load_product_state(capsule)
    products = state.get("products", {})

    manifest_path = Path(f"capsules/{capsule}/manifests/images_manifest.jsonl")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    existing_rows = load_existing_manifest(manifest_path)

    now = datetime.now(timezone.utc).isoformat()

    appended = 0
    skipped = 0

    with manifest_path.open("a", encoding="utf-8") as mf:
        for handle, product in products.items():
            cpi = product.get("cpi")
            if not cpi:
                continue
            if scope_cpis and cpi not in scope_cpis:
                continue

            swatch = product.get("assets", {}).get("swatch")
            if not swatch:
                skipped += 1
                continue

            file_path = swatch.get("file_path")
            if not file_path:
                skipped += 1
                continue

            file_path = str(Path(file_path))
            if not Path(file_path).exists():
                print(f"[SKIP] {cpi} | swatch file missing on disk")
                skipped += 1
                continue

            filename = Path(file_path).name
            source_dir = str(Path(file_path).parent)

            dedupe_key = (cpi, "swatches", filename)
            if dedupe_key in existing_rows:
                print(f"[SKIP] {cpi} | swatch already in manifest")
                skipped += 1
                continue

            row = {
                "capsule": capsule,
                "cpi": cpi,
                "asset_type": "swatches",
                "filename": filename,
                "source_dir": source_dir,
                "is_accessory": bool(product.get("is_accessory", False)),
                "created_at": now,
            }

            mf.write(json.dumps(row) + "\n")
            appended += 1
            print(f"[PROMOTED] {cpi} swatch → manifest")

    print(f"\n✔ Swatches promoted: {appended}")
    print(f"⏭ Skipped: {skipped}")

if __name__ == "__main__":
    main()