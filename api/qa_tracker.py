#!/usr/bin/env python3
"""
qa_tracker.py
Pulls data for all products in a capsule and generates a CSV tracker
to check for completeness of key data points.

NOW INCLUDES:
- Validation of tags against a "source of truth" CSV.
- Validation of 'FLAT_IMAGES' (pos 1) against Shopify "Content > Files".
- Validation of 'ON_MODEL_IMAGES' (pos 2+) against Shopify "Content > Files".
"""

import csv
import argparse
import pandas as pd
# import re  <-- REMOVED (unused)
from shopify_client import ShopifyClient

def find_internal_id(tags, capsule_tag):
    """
    Finds the tag that matches the 'S126-...' internal ID format.
    """
    prefix = f"{capsule_tag}-"
    for tag in tags:
        if tag.startswith(prefix) and ' ' in tag: # Look for the tag with spaces
            return tag
    return None

# --- UPDATED FUNCTION ---
def load_truth_map(source_csv_path, quiet: bool = False): # <-- UPDATED
    """
    Loads the "source of truth" CSV (e.g., poc_shopify_import_ready_...csv)
    and builds a dictionary mapping product handles to their expected tags,
    flat image, and on-model images.
    """
    if not quiet: # <-- UPDATED
        print(f"Loading source of truth from '{source_csv_path}'...")
    try:
        df = pd.read_csv(source_csv_path, dtype=str)
        
        # Ensure 'Image Position' is numeric for sorting, errors -> NaT/NaN
        df['Image Position'] = pd.to_numeric(df['Image Position'], errors='coerce')
        df['Image Src'] = df['Image Src'].astype(str) # Ensure Image Src is string
        
        truth_map = {}

        for handle, group in df.groupby('Handle'):
            handle = str(handle).strip()
            if not handle:
                continue

            # Initialize entry for this handle
            truth_map[handle] = {
                'tags': set(),
                'flat_image': None,
                'on_model_images': []
            }

            # 1. Find parent row to get TAGS
            parent_row = group[group['Title'].notna() & (group['Title'] != '')]
            if not parent_row.empty:
                tags_str = parent_row.iloc[0].get('Tags')
                if pd.notna(tags_str) and tags_str.strip():
                    truth_map[handle]['tags'] = {
                        tag.strip() for tag in tags_str.split(',') if tag.strip()
                    }

            # 2. Find all images, sort by position
            images_group = group[
                group['Image Src'].notna() & (group['Image Src'] != '') & (group['Image Src'].str.startswith('http'))
            ].sort_values(by='Image Position')

            for _, image_row in images_group.iterrows():
                image_src = image_row['Image Src']
                
                # --- NEW: Clean URL to get filename ---
                # Strip query params (?v=...) just in case
                if '?' in image_src:
                    image_src = image_src.split('?')[0]
                
                filename = image_src.split('/')[-1] # Get filename.jpg from URL
                # --- END NEW ---
                
                if not filename:
                    continue

                position = image_row['Image Position']
                
                if position == 1:
                    truth_map[handle]['flat_image'] = filename
                elif position > 1:
                    truth_map[handle]['on_model_images'].append(filename)

        if not quiet: # <-- UPDATED
            print(f"  > Built truth map for {len(truth_map)} product handles.")
        return truth_map

    except FileNotFoundError:
        print(f"❌ FAILED to load source CSV: File not found at '{source_csv_path}'")
        return None
    except Exception as e:
        print(f"❌ FAILED to parse source CSV: {e}")
        return None
# --- END UPDATED FUNCTION ---


def main(capsule, output_file, truth_map, quiet: bool = False): # <-- UPDATED
    client = ShopifyClient()
    
    # --- UPDATED: Get all files from Shopify Content > Files ---
    if not quiet: # <-- UPDATED
        print("Fetching all uploaded files from Shopify Content > Files...")
    try:
        # Call the REAL function from shopify_client.py
        files_gid_map = client.get_staged_uploads_map()
        
        # Get a set of the *keys* (the filenames) for fast lookup
        uploaded_files_set = set(files_gid_map.keys())
        
        if not quiet: # <-- UPDATED
            print(f"  > Found {len(uploaded_files_set)} files in Content > Files.")
    except Exception as e:
        print(f"❌ FAILED to get Shopify files list: {e}")
        print("    Image checks (FLAT_IMAGES, ON_MODEL_IMAGES) will be skipped.")
        uploaded_files_set = set() # Use an empty set to fail all checks
    # --- END UPDATED ---

    products = client.get_products_for_qa(capsule)

    if not products:
        print(f"No products found for capsule '{capsule}'. Exiting.")
        return

    # --- UPDATED HEADERS ---
    headers = [
        'Internal ID',
        'FLAT_IMAGES',
        'ON_MODEL_IMAGES', # <-- NEW COLUMN
        'DESCRIPTION',
        'TAGS',
        'SWATCH',
        'DETAILS',
        'LOOK_IMAGE'
    ]
    # --- END UPDATED HEADERS ---
    
    csv_data = [headers]
    if not quiet: # <-- UPDATED
        print(f"Processing {len(products)} products to build QA report...")
    
    handles_not_in_source = 0

    for product in products:
        internal_id = find_internal_id(product['tags'], capsule) or product['handle']
        handle = product['handle']
        
        # --- Perform all checks ---
        
        # Get the "source of truth" for this product
        product_truth = truth_map.get(handle)
        
        # Initialize checks
        flat_images_check = ""
        on_model_images_check = ""
        tags_check = ""
        
        if product_truth:
            # --- 1. FLAT_IMAGES Check ---
            expected_flat_image = product_truth.get('flat_image')
            if expected_flat_image:
                # Check against the set of filenames
                if expected_flat_image in uploaded_files_set:
                    flat_images_check = "x"

            # --- 2. ON_MODEL_IMAGES Check ---
            expected_model_images = product_truth.get('on_model_images', [])
            if expected_model_images: # Only check if list is not empty
                all_model_images_found = all(
                    # Check against the set of filenames
                    img in uploaded_files_set for img in expected_model_images
                )
                if all_model_images_found:
                    on_model_images_check = "x"

            # --- 3. TAGS Check ---
            live_tags_set = set(product['tags'])
            expected_tags_set = product_truth.get('tags', set())
            if expected_tags_set.issubset(live_tags_set):
                tags_check = "x"
        
        else:
            handles_not_in_source += 1
            # All truth-based checks remain ""

        # --- Other checks (from API response) ---
        
        # 4. DESCRIPTION: Check if bodyHtml is not empty.
        desc_check = "x" if product['bodyHtml'] and product['bodyHtml'].strip() else ""
        
        # 5. SWATCH: Check if the metafield exists and has a value.
        swatch_check = "x" if product['swatch_metafield'] and product['swatch_metafield']['value'] else ""
        
        # 6. DETAILS: Check if the metafield exists and has a value.
        details_check = "x" if product['details_metafield'] and product['details_metafield']['value'] else ""
        
        # 7. LOOK_IMAGE: Check if the metafield exists and has a value.
        look_image_check = "x" if product['look_image_metafield'] and product['look_image_metafield']['value'] else ""

        # Append the row for the CSV
        csv_data.append([
            internal_id,
            flat_images_check,
            on_model_images_check, # <-- NEW COLUMN
            desc_check,
            tags_check,
            swatch_check,
            details_check,
            look_image_check
        ])

    # This warning is important, so it stays
    if handles_not_in_source > 0:
        print(f"  > Warning: {handles_not_in_source} products found on Shopify (for capsule '{capsule}') were NOT present in the source CSV.")
        
    # Write the final CSV file
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)
        # The final success message also stays
        print(f"✅ QA tracker report successfully saved to '{output_file}'")
    except Exception as e:
        print(f"❌ FAILED to write CSV file: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a QA tracker CSV for a Shopify capsule launch.")
    parser.add_argument('--capsule', required=True, help='Capsule tag to query (e.g., "S126").')
    parser.add_argument('--source-csv', required=True, help='Path to the "source of truth" CSV (e.g., poc_shopify_import_ready_....csv) for tag and image validation.')
    parser.add_argument('--output', default='qa_tracker_report.csv', help='Name of the output CSV file (default: qa_tracker_report.csv).')
    
    # --- NEW ARGUMENT ---
    parser.add_argument('-q', '--quiet', action='store_true', help='Run the script with minimal console output.')
    
    args = parser.parse_args()
    
    # Load the truth map first
    tag_truth_map = load_truth_map(args.source_csv, quiet=args.quiet) # <-- UPDATED
    
    if tag_truth_map is not None:
        main(capsule=args.capsule, output_file=args.output, truth_map=tag_truth_map, quiet=args.quiet) # <-- UPDATED
    else:
        print("Exiting due to failure in loading the source CSV.")