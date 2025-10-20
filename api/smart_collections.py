#!/usr/bin/env python3
"""
smart_collections.py
Creates smart collections for each unique style_tag in the capsule.

Usage:
    python api/smart_collections.py --capsule S126 [--dry-run]
"""

import argparse, pandas as pd, pathlib
from shopify_client import ShopifyClient

def extract_unique_style_tags(csv_path: pathlib.Path):
    df = pd.read_csv(csv_path)
    tags = set()
    for taglist in df.get("Tags", []):
        if not isinstance(taglist, str):
            continue
        for tag in taglist.split(","):
            t = tag.strip()
            if t.startswith("style_"):
                tags.add(t)
    return sorted(tags)

def main(capsule: str, dry_run: bool = False):
    csv_path = pathlib.Path(f"capsules/{capsule}/outputs/poc_shopify_import_enriched.csv")
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing enriched CSV: {csv_path}")

    tags = extract_unique_style_tags(csv_path)
    client = ShopifyClient()
    created = []

    for tag in tags:
        title = tag.replace("style_", "style_").replace("_", " ").title()
        if dry_run:
            print(f"Would create smart collection: {title} ({tag})")
            continue
        resp = client.create_smart_collection(title, tag)
        created.append(resp)
        print(f"✅ Created collection for {tag}")

    log_path = pathlib.Path(f"capsules/{capsule}/outputs/api_jobs/collections_{capsule}.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    json.dump(created, open(log_path, "w"), indent=2)
    print(f"🗂  Collections log → {log_path}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(args.capsule, dry_run=args.dry_run)
