#!/usr/bin/env python3
"""
smart_collections.py
Creates smart collections for each unique style_tag in the capsule.
This script checks for existing collections by title and will not
create duplicates. The collection title will be the tag itself (e.g., 'style_My_Sweater').

Usage:
    python scripts/smart_collections.py --capsule S126 [--dry-run]
    python scripts/smart_collections.py --capsule S126 --styles style_Harold_Sweater style_Askania_Coat
"""

import argparse
import pandas as pd
import pathlib
import json
from api.shopify_client import ShopifyClient

def extract_unique_style_tags(csv_path: pathlib.Path) -> set:
    """
    Extracts all unique, non-blank tags starting with 'style_' from the 'Tags' column.
    """
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"❌ Error: File not found at {csv_path}")
        return set()
    except Exception as e:
        print(f"❌ Error reading CSV {csv_path}: {e}")
        return set()
        
    tags = set()
    # Use .get() for safety, default to empty list if 'Tags' column is missing
    for taglist in df.get("Tags", []):
        if not isinstance(taglist, str):
            continue
        for tag in taglist.split(","):
            t = tag.strip()
            if t.startswith("style_") and t != "style_": # Ensure tag is not just 'style_'
                tags.add(t)
    return tags

def load_authorized_styles_from_state(capsule: str) -> dict:
    """
    Load capsule product_state JSON from:
    capsules/{capsule}/state/product_state_{capsule}.json

    Return:
        { style_tag: [handle1, handle2, ...] }

    A style is authorized if at least one product with that style tag
    has allowed_actions.collection_write == true.
    """
    state_path = pathlib.Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    if not state_path.exists():
        print(f"❌ Warning: State file not found at {state_path}")
        return {}

    try:
        with open(state_path, "r") as f:
            product_state = json.load(f)
    except Exception as e:
        print(f"❌ Error loading state JSON: {e}")
        return {}

    products = product_state.get("products", {})
    authorized: dict[str, list[str]] = {}

    for handle, product in products.items():
        if not isinstance(product, dict):
            print(f"[WARN] product_state entry for '{handle}' is not a dict — skipping")
            continue

        allowed_actions = product.get("allowed_actions")
        if not isinstance(allowed_actions, dict):
            continue

        if allowed_actions.get("collection_write") is not True:
            continue

        tags = product.get("tags", [])
        if not isinstance(tags, list):
            continue

        for tag in tags:
            if isinstance(tag, str) and tag.startswith("style_") and tag != "style_":
                authorized.setdefault(tag, []).append(handle)

    return authorized

def main(
    capsule: str,
    source_csv: str,
    dry_run: bool = False,
    styles: list | None = None,
):
    """
    Main function to process and create smart collections.
    """
    capsule_dir = pathlib.Path(f"capsules/{capsule}")
    csv_path = pathlib.Path(source_csv)

    if not csv_path.exists():
        print(f"❌ FileNotFoundError: Missing source CSV: {csv_path}")
        return

    # Load styles from the enriched CSV for this capsule
    styles_from_csv = extract_unique_style_tags(csv_path)

    if styles:
        print(f"--- Filtering for {len(styles)} specific style(s) provided via --styles ---")
        # Ensure provided styles are sets for intersection
        styles_to_create = styles_from_csv.intersection(set(styles))
        if not styles_to_create:
            print(f"No matching styles found from your list: {styles}")
            return
    else:
        styles_to_create = styles_from_csv

    if not styles_to_create:
        print("No style tags found in CSV. Exiting.")
        return

    print(f"Found {len(styles_to_create)} unique style tags to process.")

    authorized_style_map = load_authorized_styles_from_state(capsule)

    print("[STATE_AUDIT] style authorization summary")
    for style in sorted(styles_to_create):
        handles = authorized_style_map.get(style, [])
        if handles:
            print(
                f"[STYLE_ALLOW] {style} | authorized_by={len(handles)} | handles={handles}"
            )
        else:
            print(
                f"[STYLE_SKIP] {style} | authorized_by=0 | reason=no product with allowed_actions.collection_write == true"
            )

    print(f"Authorized styles from state: {len(authorized_style_map)}")

    unauthorized = sorted(set(styles_to_create) - set(authorized_style_map))
    for style in unauthorized:
        print(f"[SKIP] {style} | no products authorize collection_write=true in product_state")

    if not authorized_style_map:
        print("⏭ No styles authorized for collection creation.")
        return

    client = ShopifyClient()
    
    # Fetch all existing titles *before* the loop for an efficient single check
    try:
        print("Fetching all existing smart collection titles from Shopify...")
        existing_titles = client.get_all_smart_collection_titles()
        print(f"  > Found {len(existing_titles)} existing collection titles.")
    except Exception as e:
        print(f"❌ FAILED to fetch existing collections: {e}")
        print("Aborting to prevent potential duplicate creation.")
        return
    
    api_results = [] # Use this list for logging
    
    for style_tag, handles in sorted(authorized_style_map.items()):
        print(f"[ALLOW] {style_tag} | authorized by {len(handles)} product(s): {', '.join(handles)}")

        # Check if a collection with this exact title already exists
        if style_tag in existing_titles:
            print(f"[NOOP] {style_tag} | collection already exists on Shopify")
            continue # Skip to the next style_tag

        if dry_run:
            print(f"[dry-run] Would create smart collection '{style_tag}'")
            continue

        print(f"[CREATE] {style_tag} | creating smart collection")
        try:
            # Create the collection where title and tag are identical
            resp = client.create_smart_collection(title=style_tag, tag=style_tag)
            api_results.append({"tag": style_tag, "status": "created", "response": resp})
            print(f"[CREATE] {style_tag} | created successfully")
        except Exception as e:
            print(f"    ❌ FAILED to create '{style_tag}': {e}")
            api_results.append({"tag": style_tag, "status": "failed", "response": {"error": str(e)}})

    # --- This is the end of the only loop ---
    # The erroneous second loop has been removed.

    # --- Log the results of the API calls ---
    if api_results or dry_run: # Save log if we did anything
        log_path = capsule_dir / "outputs/api_jobs" / f"collections_{capsule}.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(log_path, "w") as f:
                json.dump(api_results, f, indent=2)
            print(f"\n🗂  Collections log saved to → {log_path}")
        except Exception as e:
            print(f"\n❌ Error saving log file: {e}")
    else:
        print("\nNo new collections were created (all may have existed already).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create smart collections based on style tags.")
    parser.add_argument(
        '--capsule',
        required=True,
        help='Capsule name (e.g., "S126") used to locate product state.'
    )
    parser.add_argument(
        '--source-csv',
        required=True,
        help=(
            'Path to a Shopify-exported CSV representing current live products. '
            'Used for style discovery only.'
        )
    )
    parser.add_argument('--dry-run', action='store_true', help='Run script without creating collections.')
    parser.add_argument('--styles', nargs='+', help='(Optional) A list of specific style_TAGS to process.')
    
    args = parser.parse_args()

    main(
        capsule=args.capsule,
        source_csv=args.source_csv,
        dry_run=args.dry_run,
        styles=args.styles,
    )