#!/usr/bin/env python3
"""
list_style_collections.py

Fetches all smart collection titles from Shopify and generates a CSV report
of all collections whose titles begin with "style". This is used to
identify and review potentially duplicate collections.

Usage:
    python scripts/list_style_collections.py --capsule S126
"""

import argparse
import pandas as pd
import pathlib
from shopify_client import ShopifyClient

def main(capsule: str, output_filename: str):
    """
    Fetches collection titles, filters for 'style' titles, and saves to CSV.
    """
    output_dir = pathlib.Path(f"capsules/{capsule}/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename

    client = ShopifyClient()
    found_collection_titles = []
    
    print("Fetching all smart collection titles from Shopify (this may take a moment)...")
    try:
        # Use the correct method name found in smart_collections.py
        all_titles = client.get_all_smart_collection_titles()
    except AttributeError:
        print("❌ Error: 'ShopifyClient' object has no attribute 'get_all_smart_collection_titles'.")
        print("Please check your 'shopify_client.py' file.")
        return
    except Exception as e:
        print(f"❌ Error: Could not fetch collections from ShopifyClient: {e}")
        return

    print(f"  > Fetched {len(all_titles)} total collection titles.")
    print("Filtering for collections with titles starting with 'style'...")

    for title in all_titles:
        if not isinstance(title, str):
            continue
            
        # Check if title starts with 'style' (case-insensitive)
        if title.lower().startswith('style'):
            found_collection_titles.append({
                'Title': title,
            })

    if not found_collection_titles:
        print("✅ No collections found with a title starting with 'style'.")
        return

    print(f"  > Found {len(found_collection_titles)} matching collections.")
    
    # Create and save the report
    df = pd.DataFrame(found_collection_titles)
    # Sort alphabetically, case-insensitive
    df.sort_values(by='Title', ascending=True, key=lambda col: col.str.lower(), inplace=True)
    
    try:
        df.to_csv(output_path, index=False)
        print(f"\n✅ Successfully saved report to: {output_path}")
        print("This file contains all 'style' collection titles for client review.")
    except Exception as e:
        print(f"\n❌ Error saving CSV file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find and report on all smart collections with 'style' in the title.")
    parser.add_argument('--capsule', required=True, help='Capsule name (e.g., "S126") to define the output directory.')
    parser.add_argument(
        '--output-file',
        default="style_collections_report.csv",
        help='Filename for the output report (default: style_collections_report.csv).'
    )
    
    args = parser.parse_args()
    main(capsule=args.capsule, output_filename=args.output_file)