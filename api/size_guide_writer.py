#!/usr/bin/env python3
"""
size_guide_writer.py

Attaches the correct Size Guide Page to a product's 'altuzarra.size_guide_page'
metafield based on the product's 'productType'.

Filters the product list based on a provided --capsule tag and a
--from-csv file (e.g., poc_shopify_import_ready.csv).
"""

import argparse
import json
import pandas as pd
import pathlib
import re
from shopify_client import ShopifyClient

# --- HELPER FUNCTIONS (Copied from build_product_map.py) ---

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

# --- CSV CPI Extractor ---

def load_cpis_from_csv(csv_path: str) -> set:
    """Reads a Shopify import CSV, extracts CPIs from the 'Tags' column."""
    print(f"Loading and extracting CPIs from '{csv_path}'...")
    cpis = set()
    try:
        df = pd.read_csv(csv_path, low_memory=False)
        if 'Tags' not in df.columns:
            print(f"Error: CSV file must contain a 'Tags' column.")
            exit(1)
        
        # Get all unique tag strings from the 'Tags' column
        unique_tag_strings = df['Tags'].dropna().unique()
        
        for tag_string in unique_tag_strings:
            # Split the comma-separated tag string into a list
            tags_list = [tag.strip() for tag in tag_string.split(',')]
            
            # Find the full product ID (e.g., "S126 1008...")
            product_id_tag = extract_product_id_from_tags(tags_list)
            
            # Extract the CPI (e.g., "1008-000182")
            cpi = extract_cpi_from_product_id(product_id_tag)
            
            if cpi:
                cpis.add(cpi)
        
        print(f"Found {len(cpis)} unique CPIs in CSV.")
        return cpis
        
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}")
        exit(1)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        exit(1)

def load_product_map(capsule: str) -> dict:
    """Loads the product_map.json file and returns the {CPI: GID} map."""
    map_file = pathlib.Path(f"capsules/{capsule}/product_map.json")
    if not map_file.exists():
        # Fallback to the manifests directory
        map_file = pathlib.Path(f"capsules/{capsule}/manifests/product_map.json")
        if not map_file.exists():
            print(f"Error: product_map.json not found for capsule {capsule} at {map_file}")
            print("Please run the product_map_builder.py script first.")
            exit(1)
        
    with open(map_file, 'r') as f:
        return json.load(f)

def main(capsule: str, from_csv: str, dry_run: bool = False):
    client = ShopifyClient()

    # 1. Get all available Size Guide Pages
    size_guide_map = client.get_size_guide_pages_map()
    if not size_guide_map:
        print("No size guide pages found on Shopify. Exiting.")
        return

    # 2. Get all products for the capsule
    all_capsule_products = client.get_products_with_type(capsule)

    # 3. Get the list of CPIs we actually want to process from the CSV
    target_cpis = load_cpis_from_csv(from_csv)
    
    # 4. Load the CPI-to-GID map
    product_gid_map = load_product_map(capsule) # This is {CPI: GID}

    # 5. Filter the products:
    #    - Map target CPIs to target GIDs
    #    - Filter the all_capsule_products list to only these GIDs
    
    target_product_gids = set()
    for cpi in target_cpis:
        gid = product_gid_map.get(cpi)
        if gid:
            target_product_gids.add(gid)
        else:
            print(f"  > Warning: CPI {cpi} from CSV not found in product_map.json. Skipping.")

    products_to_process = [
        p for p in all_capsule_products if p['id'] in target_product_gids
    ]

    print(f"--- Processing {len(products_to_process)} products from the CSV ---")
    
    success_count = 0
    fail_count = 0
    
    for product in products_to_process:
        product_gid = product['id']
        product_type = product['productType']
        handle = product['handle']

        if not product_type:
            print(f"  > ⚠️  SKIPPING '{handle}': Product has no 'Type'.")
            fail_count += 1
            continue

        # Find the matching page GID
        page_gid = size_guide_map.get(product_type)

        if not page_gid:
            print(f"  > ⚠️  SKIPPING '{handle}': No size guide page found for type '{product_type}'.")
            fail_count += 1
            continue

        # We have a match, let's set the metafield
        if dry_run:
            print(f"[dry-run] Would attach '{product_type}' guide ({page_gid}) to '{handle}' ({product_gid}).")
            success_count += 1
        else:
            try:
                print(f"  > Attaching '{product_type}' guide to '{handle}'...")
                client.set_product_metafield(
                    product_gid=product_gid,
                    key="size_guide_page",
                    value_gid=page_gid,
                    namespace="altuzarra",
                    field_type="page_reference"
                )
                success_count += 1
            except Exception as e:
                print(f"  > ❌ FAILED for '{handle}': {e}")
                fail_count += 1
    
    print("--- Size Guide Attachment Complete ---")
    print(f"✅ Success: {success_count} products")
    print(f"❌ Failed/Skipped: {fail_count} products")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Attach Size Guide pages to products via metafields.")
    parser.add_argument('--capsule', required=True, help='Capsule name (e.g., "S126") to query products.')
    parser.add_argument('--from-csv', required=True, help='Path to the Shopify import CSV (e.g., "poc_shopify_import_ready.csv") to filter products.')
    parser.add_argument('--dry-run', action='store_true', help='Run script without making any API changes.')
    
    args = parser.parse_args()
    main(capsule=args.capsule, from_csv=args.from_csv, dry_run=args.dry_run)