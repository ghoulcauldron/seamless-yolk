#!/usr/bin/env python3
"""
look_relations_writer.py
Populates altuzarra.look_products (multi-product metafield) from look_relations.json.

Usage:
    python api/look_relations_writer.py --capsule S126 [--dry-run]
"""

import argparse, json, pathlib
from shopify_client import ShopifyClient

# ---------------------------------------------------------------------
def load_relations(capsule: str) -> dict:
    path = pathlib.Path(f"capsules/{capsule}/manifests/look_relations.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing look_relations.json for {capsule}")
    return json.load(open(path))

def load_product_map(capsule: str) -> dict:
    path = pathlib.Path(f"capsules/{capsule}/manifests/product_map.json")
    if not path.exists():
        raise FileNotFoundError("product_map.json missing (CPI → Product GID mapping).")
    return json.load(open(path))

# ---------------------------------------------------------------------
def set_multi_product_metafield(client, owner_gid: str, product_gids: list[str]):
    """Write the multi-product metafield."""
    mutation = """
    mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        metafields { key namespace type value }
        userErrors { field message }
      }
    }"""
    variables = {
        "metafields": [{
            "ownerId": owner_gid,
            "namespace": "altuzarra",
            "key": "look_products",
            "type": "list.product_reference",
            "value": json.dumps(product_gids)
        }]
    }
    return client.graphql(mutation, variables)

# ---------------------------------------------------------------------
def main(capsule: str, dry_run: bool = False):
    relations = load_relations(capsule)
    prod_map = load_product_map(capsule)
    client = ShopifyClient()

    jobs, skipped = [], []
    looks = relations.get("looks", {})
    for look_name, payload in looks.items():
        hero_gid = payload.get("hero_product")
        product_ids = payload.get("product_ids", [])

        if not hero_gid or not product_ids:
            skipped.append(look_name)
            continue

        # remove self-reference
        related = [gid for gid in product_ids if gid != hero_gid]

        if not related:
            skipped.append(look_name)
            continue

        if dry_run:
            print(f"[dry-run] Would set look_products for {look_name} → {len(related)} items")
            continue

        resp = set_multi_product_metafield(client, hero_gid, related)
        jobs.append({
            "look": look_name,
            "hero_product": hero_gid,
            "related_count": len(related),
            "response": resp
        })
        print(f"✅ {look_name}: linked {len(related)} look_products")

    log_path = pathlib.Path(f"capsules/{capsule}/outputs/api_jobs/look_relations_{capsule}.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"jobs": jobs, "skipped": skipped}, open(log_path, "w"), indent=2)
    print(f"🗂  Log → {log_path}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(args.capsule, dry_run=args.dry_run)
