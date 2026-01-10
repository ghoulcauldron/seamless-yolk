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


def seed_state(preflight_data: dict, capsule: str) -> dict:
    products_state = {}

    for product in preflight_data.get("products", []):
        handle = product["handle"]

        state_entry = {
            "handle": handle,
            "product_id": product.get("product_id"),
            "cpi": product.get("cpi"),
            "product_type": "ACCESSORY" if product.get("is_accessory") else "RTW",
            "is_accessory": bool(product.get("is_accessory")),

            "preflight": {
                "status": product.get("status"),
                "image_status": product.get("image_status"),
                "errors": product.get("errors", []),
                "warnings": product.get("warnings", []),
            },

            "import": {
                "eligible": not product.get("ws_buy", False),
                "imported": False,
                "imported_at": None,
                "import_source": None,
                "anomaly_accepted": False,
            },

            "images": {
                "expected": {
                    "count": product.get("total_images"),
                    "max_position": product.get("total_images"),
                },
                "last_enriched_at": None,
            },

            "promotion": {
                "stage": "PRE_FLIGHT",
                "locked": False,
                "last_transition_at": None,
            },

            "overrides": {
                "manual_go": False,
                "notes": "",
            },
        }

        # Default deny-all allowed_actions (will be selectively opened below)
        state_entry["allowed_actions"] = {
            "metafield_write": False,
            "image_upsert": False,
            "collection_write": False,
            "include_in_import_csv": False,
            "size_guide_write": False,
        }

        preflight_status = state_entry["preflight"]["status"]
        image_status = state_entry["preflight"]["image_status"]

        state_entry["allowed_actions"].update({
            "metafield_write": preflight_status == "GO",
            "image_upsert": (
                preflight_status == "GO"
                and image_status in {"IMAGE_READY", "IMAGE_MINIMAL"}
            ),
            "collection_write": True,
            "include_in_import_csv": preflight_status in {"GO", "NO-GO"},
            "size_guide_write": True,
        })

        products_state[handle] = state_entry

    return {
        "capsule": capsule,
        "schema_version": "1.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "products": products_state,
    }

def derive_allowed_actions(record: dict) -> dict:
    stage = record["promotion"]["stage"]
    locked = record["promotion"]["locked"]
    manual_go = record["overrides"]["manual_go"]

    if locked:
        return {
            "metafield_write": False,
            "image_upsert": False,
            "collection_write": False,
            "size_guide_write": False,
        }

    if stage == "IMPORTED":
        return {
            "metafield_write": True,
            "image_upsert": manual_go,   # anomalies require override
            "collection_write": True,
            "size_guide_write": True,
        }

    return {
        "metafield_write": False,
        "image_upsert": False,
        "collection_write": True,
        "size_guide_write": True,
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
        json.dump(state_data, f, indent=2)

    print(f"✅ product_state.json written to: {output_path}")
    print(f"   Products seeded: {len(state_data['products'])}")


if __name__ == "__main__":
    main()