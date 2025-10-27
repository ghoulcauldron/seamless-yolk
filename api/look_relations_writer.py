#!/usr/bin/env python3
"""
look_relations_writer.py
Populates altuzarra.look_products (multi-product metafield) from look_relations.json.

Usage:
    python api/look_relations_writer.py --capsule S126 [--dry-run]
"""

import argparse
import json
import pathlib
import re  # <-- ADDED IMPORT
import sys  # <-- ADDED IMPORT

# --- FIX for ModuleNotFoundError ---
# Add the project's root directory to the Python path.
project_root = pathlib.Path(__file__).parent.parent
sys.path.append(str(project_root))
# --- END FIX ---

from shopify_client import ShopifyClient

# --- HELPER FUNCTIONS (from build_product_map.py) ---
CPI_PATTERN_FROM_PRODUCT_ID = re.compile(r"(\d{3,5})\s+[A-Z0-9]+\s+(\d{6})")

def extract_cpi_from_product_id(product_id: str) -> str | None:
    """Converts a full Product ID (from shotlist) into a CPI (e.g., '1008-000182')."""
    if not product_id:
        return None
    match = CPI_PATTERN_FROM_PRODUCT_ID.search(product_id)
    if match:
        style, color = match.groups()
        return f"{style}-{color}"
    return None
# --- END HELPER FUNCTIONS ---


# ---------------------------------------------------------------------
def load_relations(capsule: str) -> dict:
    path = pathlib.Path(f"capsules/{capsule}/manifests/look_relations.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing look_relations.json for {capsule}")
    with open(path, 'r') as f:
        return json.load(f)

def load_product_map(capsule: str) -> dict:
    path = pathlib.Path(f"capsules/{capsule}/manifests/product_map.json")
    if not path.exists():
        raise FileNotFoundError("product_map.json missing (CPI → Product GID mapping).")
    with open(path, 'r') as f:
        return json.load(f)

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
            "value": json.dumps(product_gids) # Value must be a JSON string of GIDs
        }]
    }
    return client.graphql(mutation, variables)

# ---------------------------------------------------------------------
def main(capsule: str, dry_run: bool = False):
    relations = load_relations(capsule)
    prod_map = load_product_map(capsule) # This is {CPI: GID}
    client = ShopifyClient()

    jobs, skipped = [], []
    looks = relations.get("looks", {})
    
    print(f"Processing {len(looks)} looks for capsule {capsule}...")

    for look_name, payload in looks.items():
        
        # 1. Get raw "Product ID" strings from the JSON
        hero_product_id_str = payload.get("hero_product")
        related_product_id_strs = payload.get("product_ids", [])

        # 2. Convert raw strings to CPIs
        hero_cpi = extract_cpi_from_product_id(hero_product_id_str)
        
        # 3. Look up GIDs using the product map
        hero_gid = prod_map.get(hero_cpi)

        if not hero_gid:
            print(f"  > ⚠️  SKIPPING {look_name}: Hero product CPI '{hero_cpi}' not found in product_map.json.")
            skipped.append(look_name)
            continue
        
        if not related_product_id_strs:
            print(f"  > ⚠️  SKIPPING {look_name}: No related products listed.")
            skipped.append(look_name)
            continue
            
        # 4. Convert all related product strings to GIDs
        related_gids = []
        for prod_id_str in related_product_id_strs:
            cpi = extract_cpi_from_product_id(prod_id_str)
            gid = prod_map.get(cpi)
            if gid:
                related_gids.append(gid)
            else:
                print(f"  > Warning for {look_name}: Related product CPI '{cpi}' not found in map. Will be excluded.")

        # 5. Remove self-reference
        # The hero product GID should not be in the list of related products.
        final_related_gids = [gid for gid in related_gids if gid != hero_gid]

        if not final_related_gids:
            print(f"  > ⚠️  SKIPPING {look_name}: No valid related products to link.")
            skipped.append(look_name)
            continue

        if dry_run:
            print(f"[dry-run] Would set 'look_products' for {look_name} ({hero_cpi}):")
            print(f"          - Hero GID: {hero_gid}")
            print(f"          - Related GIDs: {json.dumps(final_related_gids)}")
            continue

        try:
            resp = set_multi_product_metafield(client, hero_gid, final_related_gids)
            jobs.append({
                "look": look_name,
                "hero_product_cpi": hero_cpi,
                "hero_product_gid": hero_gid,
                "related_gids": final_related_gids,
                "response": resp
            })
            print(f"✅ {look_name}: Linked {len(final_related_gids)} look_products to {hero_cpi}")
        except Exception as e:
            print(f"  > ❌ FAILED for {look_name}: {e}")
            skipped.append(look_name)


    log_path = pathlib.Path(f"capsules/{capsule}/outputs/api_jobs/look_relations_{capsule}.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"jobs": jobs, "skipped": skipped}, open(log_path, "w"), indent=2)
    print(f"\n🗂  Log → {log_path}")
    print(f"--- Complete: {len(jobs)} looks processed, {len(skipped)} looks skipped. ---")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(args.capsule, args.dry_run)