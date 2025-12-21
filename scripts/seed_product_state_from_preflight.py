

#!/usr/bin/env python3

"""
Seed product_state.json from a preflight JSON output.

This script is intentionally simple and deterministic.
It performs a one-way transform:
    preflight → product_state

No Shopify logic, no enrichment, no validation re-computation.
"""

import json
import argparse
from datetime import datetime
from pathlib import Path


def derive_allowed_actions(preflight_entry: dict) -> dict:
    """
    Determine allowed actions based strictly on preflight findings.
    Client overrides can be applied later by editing the state file.
    """
    status = preflight_entry.get("status")
    ws_buy = preflight_entry.get("ws_buy", False)
    image_status = preflight_entry.get("image_status")

    include_in_import = not ws_buy

    image_upsert_allowed = (
        include_in_import and image_status in {"IMAGE_READY", "IMAGE_MINIMAL"}
    )

    metafield_write_allowed = include_in_import
    collection_write_allowed = include_in_import

    return {
        "include_in_import_csv": include_in_import,
        "image_upsert": image_upsert_allowed,
        "metafield_write": metafield_write_allowed,
        "collection_write": collection_write_allowed,
    }


def seed_state(preflight_data: dict, capsule: str) -> dict:
    products_state = {}

    for product in preflight_data.get("products", []):
        handle = product["handle"]

        state_entry = {
            "cpi": product.get("cpi"),
            "product_type": "ACCESSORY" if product.get("is_accessory") else "RTW",
            "preflight_status": product.get("status"),
            "preflight_errors": product.get("errors", []),
            "preflight_warnings": product.get("warnings", []),
            "ws_buy": product.get("ws_buy", False),
            "image_state": product.get("image_status"),
            "details_ready": product.get("details_ready", False),
            "body_ready": product.get("body_status") == "BODY_WRITE_OK",
            "client_recommendation": product.get("client_recommendation"),
            "allowed_actions": derive_allowed_actions(product),
            "current_stage": "PREFLIGHT_COMPLETE",
        }

        products_state[handle] = state_entry

    return {
        "schema_version": "1.0",
        "capsule": capsule,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "generated_from": "preflight",
        "products": products_state,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Seed product_state.json from a preflight JSON file"
    )
    parser.add_argument(
        "--preflight",
        required=True,
        help="Path to preflight JSON (e.g. preflight_S226_internal_*.json)",
    )
    parser.add_argument(
        "--capsule",
        required=True,
        help="Capsule code (e.g. S226)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for product_state.json",
    )

    args = parser.parse_args()

    preflight_path = Path(args.preflight)
    output_path = Path(args.output)

    if not preflight_path.exists():
        raise FileNotFoundError(f"Preflight file not found: {preflight_path}")

    with preflight_path.open("r", encoding="utf-8") as f:
        preflight_data = json.load(f)

    state_data = seed_state(preflight_data, args.capsule)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2, sort_keys=True)

    print(f"✅ product_state.json written to: {output_path}")
    print(f"   Products seeded: {len(state_data['products'])}")


if __name__ == "__main__":
    main()