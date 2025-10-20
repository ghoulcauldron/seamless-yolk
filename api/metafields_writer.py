#!/usr/bin/env python3
"""
metafields_writer.py
Uploads swatch + look images (if any) from images_manifest.jsonl
and sets the corresponding product metafields.

Usage:
    python api/metafields_writer.py --capsule S126 [--dry-run]
"""

import argparse, json, pathlib
from shopify_client import ShopifyClient

def load_manifest(capsule: str):
    manifest_path = pathlib.Path(f"capsules/{capsule}/manifests/images_manifest.jsonl")
    records = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    return [r for r in records if r["asset_type"] in ("swatch", "editorials")]

def load_product_map(capsule: str):
    # Simple lookup table {CPI: product_gid}; fill in from export or mapping file later.
    mapping_path = pathlib.Path(f"capsules/{capsule}/manifests/product_map.json")
    if not mapping_path.exists():
        raise FileNotFoundError("product_map.json missing (CPI → Product GID mapping).")
    return json.load(open(mapping_path))

def main(capsule: str, dry_run: bool = False):
    client = ShopifyClient()
    manifest = load_manifest(capsule)
    prod_map = load_product_map(capsule)

    jobs = []
    for row in manifest:
        cpi = row["cpi"]
        if not cpi or cpi not in prod_map:
            continue
        product_gid = prod_map[cpi]
        alt = f"{row['asset_type'].capitalize()} - {cpi}"
        url_placeholder = f"https://example.com/{row['filename']}"  # Replace when CDN URL known
        if dry_run:
            print(f"Would upload {row['filename']} for {cpi}")
            continue

        # Upload + wait
        file_gid = client.upload_file(url_placeholder, alt)
        try:
            ready_url = client.wait_for_file_ready(file_gid)
        except TimeoutError:
            print(f"⚠️ File not ready in time for {row['filename']}")
            continue

        # Assign metafield
        key = "swatch_image" if row["asset_type"] == "swatch" else "look_image"
        if row.get("is_accessory") and key == "look_image":
            # Accessories skip look_image
            continue

        resp = client.set_product_metafield(product_gid, key, file_gid)
        jobs.append({
            "cpi": cpi,
            "product_gid": product_gid,
            "file_gid": file_gid,
            "key": key
        })
        print(f"✅ Linked {row['filename']} → {key} for {cpi}")

    log_path = pathlib.Path(f"capsules/{capsule}/outputs/api_jobs/metafields_{capsule}.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(jobs, open(log_path, "w"), indent=2)
    print(f"🗂  Log written to {log_path}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(args.capsule, dry_run=args.dry_run)
