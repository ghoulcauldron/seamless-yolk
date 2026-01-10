#!/usr/bin/env python3
"""
size_guide_writer.py

Attaches the correct Size Guide Page to a product's 'altuzarra.size_guide_page'
metafield based on the product's 'productType'.

Filters the product list based on a provided --capsule tag and a
--source-csv file (Shopify-exported CSV used only for handle discovery).
"""

import argparse
import json
import pandas as pd
import pathlib
import re
from api.shopify_client import ShopifyClient
from utils.state_gate import StateGate

def load_authorized_products_from_state(capsule: str) -> dict:
    """Load authorized products from state file for the capsule.

    Returns a dict of {handle: product_state_dict}
    where allowed_actions.size_guide_write == True.
    """
    state_file = pathlib.Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    if not state_file.exists():
        print(f"Error: State file not found at {state_file}")
        exit(1)

    with open(state_file, 'r') as f:
        state_data = json.load(f)

    products = state_data.get("products", {})
    if not isinstance(products, dict):
        print(f"Error: Invalid state schema — 'products' missing or malformed")
        exit(1)

    authorized = {}
    for handle, product_state in products.items():
        if not isinstance(product_state, dict):
            continue

        allowed = product_state.get("allowed_actions", {})
        if allowed.get("size_guide_write") is True:
            authorized[handle] = product_state

    return authorized

def extract_handles_from_csv(csv_path: pathlib.Path) -> set[str]:
    """Extract unique non-null handles from the CSV's 'Handle' column."""
    try:
        df = pd.read_csv(csv_path)
        if 'Handle' not in df.columns:
            print(f"Error: CSV file must contain a 'Handle' column.")
            exit(1)
        handles = set(df['Handle'].dropna().unique())
        return handles
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_path}")
        exit(1)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        exit(1)

def main(capsule: str, source_csv: str, dry_run: bool = False):
    client = ShopifyClient()

    # Load authorized products from state
    authorized_products = load_authorized_products_from_state(capsule)
    authorized_handles = set(authorized_products.keys())

    # Load handles from CSV
    csv_handles = extract_handles_from_csv(pathlib.Path(source_csv))

    # Audit authorization
    print("[STATE_AUDIT] size_guide authorization summary")
    for handle in csv_handles:
        if handle in authorized_handles:
            print(f"[SIZE_GUIDE_ALLOW] {handle}")
        else:
            print(f"[SIZE_GUIDE_SKIP] {handle} | reason=allowed_actions.size_guide_write != true")

    # Intersection of handles to process
    handles_to_process = csv_handles.intersection(authorized_handles)

    # Fetch all products for the capsule
    all_capsule_products = client.get_products_with_type(capsule)

    # Build handle-to-product map
    product_map = {p['handle']: p for p in all_capsule_products}

    # Get all available Size Guide Pages
    size_guide_map = client.get_size_guide_pages_map()
    if not size_guide_map:
        print("No size guide pages found on Shopify. Exiting.")
        return

    success_count = 0
    fail_count = 0

    for handle in handles_to_process:
        product = product_map.get(handle)
        if not product:
            # Product not found in Shopify for this handle; skip silently
            continue

        product_type = product.get('productType')
        product_gid = product.get('id')

        page_gid = size_guide_map.get(product_type)
        if not page_gid:
            print(f"[NOOP] {handle} | no size guide page for productType={product_type}")
            continue

        if dry_run:
            print(f"[ATTACH] {handle} | page={page_gid}")
            success_count += 1
        else:
            try:
                client.set_product_metafield(
                    product_gid=product_gid,
                    key="size_guide_page",
                    value_gid=page_gid,
                    namespace="altuzarra",
                    field_type="page_reference"
                )
                print(f"[ATTACH] {handle} | page={page_gid}")
                success_count += 1
            except Exception as e:
                print(f"[ERROR] {handle} | {e}")
                fail_count += 1

    print("--- Size Guide Attachment Complete ---")
    print(f"✅ Success: {success_count} products")
    print(f"❌ Failed/Skipped: {fail_count} products")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Attach Size Guide pages to products via metafields.")
    parser.add_argument('--capsule', required=True, help='Capsule name (e.g., "S126") to query products.')
    parser.add_argument('--source-csv', required=True, help='Path to the Shopify-exported CSV for handle discovery.')
    parser.add_argument('--dry-run', action='store_true', help='Run script without making any API changes.')

    args = parser.parse_args()
    main(capsule=args.capsule, source_csv=args.source_csv, dry_run=args.dry_run)