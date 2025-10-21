#!/usr/bin/env python3
"""
qa_tracker.py
Pulls data for all products in a capsule and generates a CSV tracker
to check for completeness of key data points.
"""

import csv
import argparse
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

def main(capsule, output_file):
    client = ShopifyClient()
    products = client.get_products_for_qa(capsule)

    if not products:
        print(f"No products found for capsule '{capsule}'. Exiting.")
        return

    # These headers map to your client's tracker file:
    # Internal ID -> The 'S126-...' tag
    # FLAT_IMAGES -> Standard product images (product.images)
    # DESCRIPTION -> product.bodyHtml
    # TAGS -> product.tags
    # SWATCH -> altuzarra.swatch_image metafield
    # DETAILS -> altuzarra.details metafield
    # LOOK_IMAGE -> altuzarra.look_image metafield (Covers both 'ON MODEL' and 'GET THE LOOK')
    
    headers = [
        'Internal ID',
        'FLAT_IMAGES',
        'DESCRIPTION',
        'TAGS',
        'SWATCH',
        'DETAILS',
        'LOOK_IMAGE'
    ]
    
    csv_data = [headers]
    print(f"Processing {len(products)} products to build QA report...")

    for product in products:
        # Find the internal ID tag (e.g., "S126-2012...")
        internal_id = find_internal_id(product['tags'], capsule) or product['handle']
        
        # --- Perform all checks ---
        
        # 1. FLAT_IMAGES: Check if the main product.images has at least one entry.
        flat_images_check = "x" if product['images']['edges'] else ""
        
        # 2. DESCRIPTION: Check if bodyHtml is not empty.
        desc_check = "x" if product['bodyHtml'] and product['bodyHtml'].strip() else ""
        
        # 3. TAGS: Check for more than one tag (assumes capsule tag is always present).
        tags_check = "x" if len(product['tags']) > 1 else ""
        
        # 4. SWATCH: Check if the metafield exists and has a value.
        swatch_check = "x" if product['swatch_metafield'] and product['swatch_metafield']['value'] else ""
        
        # 5. DETAILS: Check if the metafield exists and has a value.
        details_check = "x" if product['details_metafield'] and product['details_metafield']['value'] else ""
        
        # 6. LOOK_IMAGE: Check if the metafield exists and has a value.
        #    This covers your 'ON MODEL IMAGES' and 'GET THE LOOK IMAGE' points.
        look_image_check = "x" if product['look_image_metafield'] and product['look_image_metafield']['value'] else ""

        # Append the row for the CSV
        csv_data.append([
            internal_id,
            flat_images_check,
            desc_check,
            tags_check,
            swatch_check,
            details_check,
            look_image_check
        ])

    # Write the final CSV file
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)
        print(f"✅ QA tracker report successfully saved to '{output_file}'")
    except Exception as e:
        print(f"❌ FAILED to write CSV file: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a QA tracker CSV for a Shopify capsule launch.")
    parser.add_argument('--capsule', required=True, help='Capsule tag to query (e.g., "S126").')
    parser.add_argument('--output', default='qa_tracker_report.csv', help='Name of the output CSV file (default: qa_tracker_report.csv).')
    
    args = parser.parse_args()
    main(capsule=args.capsule, output_file=args.output)