

"""
sync_product_gids.py

One-time (or repeatable) synchronization utility.

Purpose:
- Inject canonical Shopify product GIDs into product_state_{capsule}.json
- Source of truth: capsules/{capsule}/manifests/product_map.json
- Target: capsules/{capsule}/state/product_state_{capsule}.json

This script:
- Does NOT call Shopify
- Does NOT mutate anything except product_state
- Is safe to re-run

Usage:
  python -m api.sync_product_gids --capsule S226
"""

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return json.loads(path.read_text())


def main(capsule: str) -> None:
    product_map_path = Path("capsules") / capsule / "manifests" / "product_map.json"
    state_path = Path("capsules") / capsule / "state" / f"product_state_{capsule}.json"

    product_map = load_json(product_map_path)
    state = load_json(state_path)

    products = state.get("products", {})
    updated = 0
    missing = []

    for handle, product in products.items():
        cpi = product.get("cpi")
        if not cpi:
            continue

        product_gid = product_map.get(cpi)
        if not product_gid:
            missing.append(cpi)
            continue

        # Inject at top level for now (explicit and simple)
        product["product_gid"] = product_gid
        updated += 1

    state_path.write_text(json.dumps(state, indent=2))

    print(f"[sync_product_gids] Capsule {capsule}")
    print(f"  Injected product_gid for {updated} products")

    if missing:
        print(f"  ⚠️ Missing product_gid for {len(missing)} CPIs:")
        for cpi in sorted(set(missing)):
            print(f"    - {cpi}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", required=True)
    args = parser.parse_args()

    main(args.capsule)