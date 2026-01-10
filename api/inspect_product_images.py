"""
inspect_product_images.py

READ-ONLY diagnostic utility.

Purpose:
- Inspect Shopify product media for hero candidates
- Compare Shopify reality vs local manifest expectations
- Surface cases where:
    * Shopify has hero images
    * Manifest does NOT include editorial/hero images
- Emit structured JSON for downstream state seeding

This script MUST NOT:
- Upload files
- Write metafields
- Mutate product_state.json

Usage:
  python -m api.inspect_product_images --capsule S226
  python -m api.inspect_product_images --capsule S226 --cpis 4015-000172 6007-000479
"""

import argparse
import json
from typing import Dict, List

from api.shopify_client import ShopifyClient
from pathlib import Path

def load_product_state(capsule: str) -> dict:
    path = Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing product state file: {path}")
    return json.loads(path.read_text())

def resolve_handle_from_cpi(products: dict, cpi: str) -> str | None:
    """
    Resolve product handle from CPI using product_state["products"].
    """
    for handle, record in products.items():
        if not isinstance(record, dict):
            continue
        if record.get("cpi") == cpi:
            return handle
    return None

def get_product_by_gid(shopify: ShopifyClient, product_gid: str) -> dict | None:
    query = """
    query getProductById($id: ID!) {
      product(id: $id) {
        id
        media(first: 20) {
          edges {
            node {
              __typename
              id
              ... on MediaImage {
                image {
                  originalSrc
                }
              }
            }
          }
        }
      }
    }
    """
    resp = shopify.graphql(query, {"id": product_gid})
    return resp.get("data", {}).get("product")

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", required=True)
    parser.add_argument(
        "--cpis",
        nargs="*",
        help="Optional list of CPIs to inspect (defaults to all in state)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    return parser.parse_args()

def is_hero_candidate(media: Dict, idx: int) -> bool:
    """
    Heuristic for hero images.
    Conservative by design.

    Rules:
    - Media type must be MediaImage
    - Filename includes 'hero'
    - OR image appears early in media order (idx <= 1)
    """
    if media.get("__typename") != "MediaImage":
        return False

    image = media.get("image") or {}
    filename = (image.get("originalSrc") or "").lower()

    if "hero" in filename:
        return True

    if idx <= 1:
        return True

    return False


def inspect_product(shopify: ShopifyClient, cpi: str, product_gid: str) -> Dict:
    """
    Inspect a single product's Shopify media by product_gid.
    """
    product = get_product_by_gid(shopify, product_gid)
    if not product:
        return {
            "cpi": cpi,
            "product_gid": product_gid,
            "shopify": {
                "status": "PRODUCT_NOT_FOUND"
            }
        }

    media_edges = (
        product.get("media", {})
        .get("edges", [])
    )

    media = [edge["node"] for edge in media_edges]

    hero_candidates = []
    for idx, m in enumerate(media):
        if is_hero_candidate(m, idx):
            hero_candidates.append({
                "media_gid": m["id"],
                "position": idx,
                "filename": m.get("image", {}).get("originalSrc"),
            })

    return {
        "cpi": cpi,
        "product_gid": product_gid,
        "shopify": {
            "media_count": len(media),
            "hero_candidates": hero_candidates,
        }
    }


def main():
    args = parse_args()

    state = load_product_state(args.capsule)
    products = state.get("products", {})
    if not isinstance(products, dict):
        raise RuntimeError("Invalid product_state schema: expected top-level 'products' map")

    if args.cpis:
        cpis = args.cpis
    else:
        cpis = sorted({
            record["cpi"]
            for record in products.values()
            if isinstance(record, dict) and record.get("cpi")
        })

    shopify = ShopifyClient()

    results: List[Dict] = []

    for cpi in cpis:
        handle = resolve_handle_from_cpi(products, cpi)
        if not handle:
            results.append({
                "cpi": cpi,
                "error": "HANDLE_NOT_FOUND_IN_STATE",
            })
            continue

        record = products.get(handle, {})
        if not isinstance(record, dict):
            results.append({
                "cpi": cpi,
                "handle": handle,
                "error": "INVALID_RECORD_IN_STATE",
            })
            continue

        product_gid = record.get("product_gid")
        if not product_gid:
            results.append({
                "cpi": cpi,
                "handle": handle,
                "error": "PRODUCT_GID_MISSING_IN_STATE",
            })
            continue

        inspection = inspect_product(shopify, cpi, product_gid)

        images = record.get("images", {}) if isinstance(record, dict) else {}
        expected = images.get("expected", {}) if isinstance(images, dict) else {}

        # Editorial images must be explicitly declared; image counts alone are insufficient
        assets = record.get("assets", {}) if isinstance(record, dict) else {}
        look_images = assets.get("look_images", [])
        manifest_has_editorial = bool(look_images)

        inspection["handle"] = handle
        inspection["manifest"] = {
            "has_editorial": manifest_has_editorial
        }

        if inspection.get("shopify", {}).get("status") == "PRODUCT_NOT_FOUND":
            inspection["assessment"] = "PRODUCT_NOT_FOUND"
        elif inspection.get("shopify", {}).get("hero_candidates") and not manifest_has_editorial:
            inspection["assessment"] = "SHOPIFY_HAS_HERO_MANIFEST_MISSING"
        else:
            inspection["assessment"] = "OK"

        results.append(inspection)

    if args.pretty:
        print(json.dumps(results, indent=2))
    else:
        print(json.dumps(results))


if __name__ == "__main__":
    main()