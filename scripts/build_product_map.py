import json
import pathlib
import argparse
import re
import sys

# --- FIX for ModuleNotFoundError ---
# Add the project's root directory to the Python path.
# This allows the script to find the 'api' module.
project_root = pathlib.Path(__file__).parent.parent
sys.path.append(str(project_root))

from api.shopify_client import ShopifyClient

# Re-use the robust regex and helper functions from our enrichment script
CPI_PATTERN_FROM_PRODUCT_ID = re.compile(r"(\d{3,5})\s+[A-Z0-9]+\s+(\d{6})")

def extract_product_id_from_tags(tags: list) -> str | None:
    """Extracts the full Product ID from a list of Shopify tags."""
    if not isinstance(tags, list):
        return None
    for tag in tags:
        tag = tag.strip()
        # A Product ID tag reliably has multiple space-separated parts.
        if tag.count(' ') >= 2:
            return tag
    return None

def extract_cpi_from_product_id(product_id: str) -> str | None:
    """Converts a full Product ID into a CPI (e.g., '1008-000182')."""
    if not product_id:
        return None
    match = CPI_PATTERN_FROM_PRODUCT_ID.search(product_id)
    if match:
        style, color = match.groups()
        return f"{style}-{color}"
    return None

def main(capsule: str, dry_run: bool = False):
    """
    Builds the product_map.json (CPI -> Admin GID) by querying the Shopify API
    for products with a specific tag.
    """
    client = ShopifyClient()
    product_map = {}
    
    # The capsule code (e.g., "S126") is used as the tag to query.
    tag_to_query = capsule
    
    # Fetch all products from Shopify with the specified tag
    products = client.get_products_by_tag(tag_to_query)

    if not products:
        print(f"⚠️  Warning: No products found in Shopify with the tag '{tag_to_query}'. Cannot build map.")
        return

    for product in products:
        full_product_id = extract_product_id_from_tags(product.get('tags', []))
        cpi = extract_cpi_from_product_id(full_product_id)
        
        gid = product.get("id")

        if cpi and gid:
            product_map[cpi] = gid

    if dry_run:
        print("\n[dry-run] --- Product Map Preview ---")
        # Show a sample of the map that would be created
        sample_map = dict(list(product_map.items())[:5])
        print(json.dumps(sample_map, indent=2))
        print(f"\n[dry-run] Would build product_map.json with {len(product_map)} entries.")
        if not product_map:
            print("⚠️  Warning: The map is empty. Check if products have the correct tags in Shopify.")
        return

    out_path = pathlib.Path(f"capsules/{capsule}/manifests/product_map.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w") as f:
        json.dump(product_map, f, indent=2)
        
    print(f"✅ product_map.json built with {len(product_map)} entries → {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build CPI-to-GID map by querying the Shopify API.")
    parser.add_argument("--capsule", required=True, help="The capsule code (e.g., S126), used as the tag to query products.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without writing the map file.")
    args = parser.parse_args()
    main(args.capsule, args.dry_run)