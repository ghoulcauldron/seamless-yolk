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
from shopify_client import ShopifyClient

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

def main(capsule: str, dry_run: bool = False, styles: list | None = None):
    """
    Main function to process and create smart collections.
    """
    capsule_dir = pathlib.Path(f"capsules/{capsule}")
    csv_path = capsule_dir / "outputs/poc_shopify_import_enriched.csv"
    
    if not csv_path.exists():
        print(f"❌ FileNotFoundError: Missing enriched CSV: {csv_path}")
        print("Please run the 'enrich_shopify_import.py' script first.")
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
    
    for style_tag in sorted(list(styles_to_create)):
        
        # Check if a collection with this exact title already exists
        if style_tag in existing_titles:
            print(f"  > Skipping '{style_tag}': Collection already exists.")
            continue # Skip to the next style_tag

        if dry_run:
            print(f"[dry-run] Would create smart collection '{style_tag}'")
            continue

        print(f"  > Creating smart collection '{style_tag}'...")
        try:
            # Create the collection where title and tag are identical
            resp = client.create_smart_collection(title=style_tag, tag=style_tag)
            api_results.append({"tag": style_tag, "status": "created", "response": resp})
            print(f"    ✅ Created.")
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
    parser.add_argument('--capsule', required=True, help='Capsule name (e.g., "S126") to find input CSV.')
    parser.add_argument('--dry-run', action='store_true', help='Run script without creating collections.')
    parser.add_argument('--styles', nargs='+', help='(Optional) A list of specific style_TAGS to process.')
    
    args = parser.parse_args()

    main(capsule=args.capsule, dry_run=args.dry_run, styles=args.styles)