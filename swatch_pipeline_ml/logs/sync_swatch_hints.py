#!/usr/bin/env python3
"""
sync_swatch_hints.py
Reads swatch_hints.json → adds unseen garment types to garment_config.json.
"""

import argparse, json, pathlib

def main(capsule: str, dry_run=False):
    base = pathlib.Path(f"capsules/{capsule}")
    hints = json.load(open(base/"logs/swatch_hints.json"))
    cfg_path = base/"config/garment_config.json"
    cfg = json.load(open(cfg_path))
    existing = set(cfg["garments"].keys())
    new_types = {}
    for entry in hints.get("entries", []):
        gtype = entry.get("garment_type")
        if gtype and gtype not in existing:
            new_types[gtype] = {
                "default_hint": {"left_ratio": 0.35, "top_ratio": 0.35},
                "notes": "Auto-learned from swatch hints"
            }
    if new_types:
        cfg["garments"].update(new_types)
        major, minor = map(int, cfg["version"].split("."))
        cfg["version"] = f"{major}.{minor+1}"
        if not dry_run:
            json.dump(cfg, open(cfg_path, "w"), indent=2)
        print(f"🆕 Added {len(new_types)} garment types: {', '.join(new_types)}")
    else:
        print("No new garment types found.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    main(a.capsule, a.dry_run)
