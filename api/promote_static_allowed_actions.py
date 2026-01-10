#!/usr/bin/env python3
"""
promote_static_allowed_actions.py

One-time / repeat-safe normalizer.

Purpose:
- Retroactively promote static allowed_actions that should never be gated
- Align legacy product_state files with the current architecture guarantees

Specifically:
- allowed_actions.collection_write = true
- allowed_actions.size_guide_write = true

Eligibility:
- Any product that exists in product_state (i.e. has a CPI entry)
- SKIP products are left untouched

This script:
- Does NOT inspect Shopify
- Does NOT infer assets
- Does NOT touch metafield_write or image_upsert
- Is idempotent and safe to re-run

Usage:
  python -m api.promote_static_allowed_actions --capsule S226
"""

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def load_product_state(capsule: str) -> dict:
    path = Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing product state file: {path}")
    return json.loads(path.read_text())


def write_product_state(capsule: str, state: dict):
    path = Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def is_skip_product(product: dict) -> bool:
    """
    Define SKIP semantics centrally so this script
    does not accidentally override intentional exclusions.
    """
    stage = product.get("promotion", {}).get("stage")
    return stage == "SKIP"


def promote_actions(product: dict) -> bool:
    """
    Promote static allowed_actions.
    Returns True if any change was made.
    """
    allowed = product.setdefault("allowed_actions", {})
    changed = False

    if allowed.get("collection_write") is not True:
        allowed["collection_write"] = True
        changed = True

    if allowed.get("size_guide_write") is not True:
        allowed["size_guide_write"] = True
        changed = True

    if changed:
        product.setdefault("audit", {}).setdefault("static_action_promotions", []).append({
            "script": "promote_static_allowed_actions",
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "actions": ["collection_write", "size_guide_write"],
        })

    return changed


def main(capsule: str):
    state = load_product_state(capsule)
    products = state.get("products", {})

    promoted = 0
    skipped = 0

    for handle, product in products.items():
        if is_skip_product(product):
            skipped += 1
            continue

        if promote_actions(product):
            promoted += 1

    write_product_state(capsule, state)

    print(f"Static allowed_actions promotion complete for capsule {capsule}")
    print(f"  ✅ Promoted: {promoted}")
    print(f"  ⏭  Skipped (SKIP stage): {skipped}")
    print(f"  📄 State updated: capsules/{capsule}/state/product_state_{capsule}.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Promote static allowed_actions in product_state."
    )
    parser.add_argument(
        "--capsule",
        required=True,
        help="Capsule name (e.g. S226)"
    )

    args = parser.parse_args()
    main(capsule=args.capsule)