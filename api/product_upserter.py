#!/usr/bin/env python3
"""
product_upserter.py

Performs targeted "upsert" operations (tags, images, metafields) for
Shopify products, using a source CSV (from pre_upload_images.py)
as the "source of truth".

This script reads FINAL SHOPIFY CDN URLs from the source CSV.
"""

import argparse
import pandas as pd
import re
import sys
import json
import pathlib
from shopify_client import ShopifyClient

def load_source_data(source_csv_path: str) -> dict:
    """
    Loads the "source of truth" CSV (which contains final Shopify URLs).
    Returns a map of {handle: data}.
    """
    print(f"Loading source of truth from '{source_csv_path}'...")
    
    # 1. Load Source CSV
    try:
        df = pd.read_csv(source_csv_path, dtype=str)
        # Fill NA in key columns to prevent errors
        df['Image Position'] = pd.to_numeric(df['Image Position'], errors='coerce').fillna(999)
        df['Image Src'] = df['Image Src'].fillna('')
        df['Tags'] = df['Tags'].fillna('')
        df['Details (product.metafields.altuzarra.details)'] = df['Details (product.metafields.altuzarra.details)'].fillna('')
        
        source_data_map = {}

        for handle, group in df.groupby('Handle'):
            handle = str(handle).strip()
            if not handle:
                continue
            
            # Get the "parent" row which contains non-image data
            parent_row_series = group[group['Title'].notna() & (group['Title'] != '')]
            if parent_row_series.empty:
                continue
            parent_row = parent_row_series.iloc[0]
            
            tags_str = parent_row.get('Tags', '')
            tags_list = sorted([tag.strip() for tag in tags_str.split(',') if tag.strip()])
            
            details_str = parent_row.get('Details (product.metafields.altuzarra.details)', '')
            
            capsule_tag = None
            for tag in tags_list:
                if re.match(r'^[A-Z]\d{3}$', tag):
                    capsule_tag = tag
                    break
            
            # --- THIS IS THE KEY CHANGE ---
            # Get the final, correct Shopify URLs directly from the CSV.
            image_urls = []
            # Filter for rows that have image URLs and sort them
            images_group = group[group['Image Src'].str.startswith('http')].sort_values(by='Image Position')
            
            for _, image_row in images_group.iterrows():
                # Get the full URL and strip any query params
                url = image_row['Image Src'].split('?')[0]
                image_urls.append(url)
            # --- END CHANGE ---

            source_data_map[handle] = {
                'handle': handle,
                'capsule': capsule_tag,
                'tags': tags_list,
                'details': details_str,
                'images': image_urls # This is now a list of final CDN URLs
            }
            
        print(f"  > Loaded data for {len(source_data_map)} product handles from CSV.")
        return source_data_map

    except FileNotFoundError:
        print(f"❌ FAILED to load source CSV: File not found at '{source_csv_path}'", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ FAILED to parse source CSV: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(description="Perform targeted upserts to Shopify products.")
    parser.add_argument('--source-csv', required=True, help='Path to the "source of truth" CSV (e.g., import_ready_alpha.csv).')
    
    # --- Targeting Arguments ---
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument('--capsule', help='Capsule tag to process all products for (e.g., "S126").')
    target_group.add_argument('--handles', nargs='+', help='One or more specific product handles to update.')
    
    # --- Action Arguments ---
    parser.add_argument('--update-images', action='store_true', help='Update the product images (replaces all).')
    parser.add_argument('--update-tags', action='store_true', help='Update the product tags.')
    parser.add_argument('--update-details', action='store_true', help='Update the "altuzarra.details" metafield.')
    
    # --- Control Arguments ---
    parser.add_argument('--dry-run', action='store_true', help='Simulate actions without making API writes.')
    parser.add_argument('--verbose', action='store_true', help='Enable detailed logging from the Shopify client.')
    
    args = parser.parse_args()

    # --- Argument Validation ---
    if not (args.update_images or args.update_tags or args.update_details):
        print("❌ Error: You must specify at least one action: --update-images, --update-tags, or --update-details.", file=sys.stderr)
        parser.print_help()
        return

    # --- 1. Load Source of Truth Data ---
    source_data = load_source_data(args.source_csv)
    if source_data is None:
        return

    # --- 2. Determine Handles to Process ---
    handles_to_process = []
    if args.handles:
        handles_to_process = args.handles
        # Verify handles exist in the source CSV
        for handle in handles_to_process:
            if handle not in source_data:
                print(f"⚠️  Warning: Handle '{handle}' not found in source CSV. Will be skipped.")
    
    elif args.capsule:
        # Filter source data by capsule
        handles_to_process = [
            handle for handle, data in source_data.items()
            if data['capsule'] == args.capsule
        ]
        if not handles_to_process:
            print(f"No products found in source CSV for capsule '{args.capsule}'.")
            return

    print(f"\nFound {len(handles_to_process)} products to process.")
            
    # --- 3. Initialize Client & Get Shopify Product GIDs ---
    client = ShopifyClient()
    
    shop_capsule_tag = args.capsule
    if not shop_capsule_tag:
        # If user specified --handles, find the capsule from the first valid handle
        first_valid_handle = next((h for h in args.handles if h in source_data), None)
        if first_valid_handle:
            shop_capsule_tag = source_data[first_valid_handle]['capsule']
    
    if not shop_capsule_tag:
        print("❌ Error: Could not determine a capsule tag to query Shopify. Exiting.", file=sys.stderr)
        return

    print(f"Fetching Shopify product data for capsule '{shop_capsule_tag}'...")
    
    try:
        product_data_map = client.get_products_for_upsert(shop_capsule_tag, verbose=args.verbose)
    except AttributeError as e:
        print(f"❌ Error: `ShopifyClient` is missing a required function: {e}", file=sys.stderr)
        return
    except Exception as e:
        print(f"❌ Error fetching Shopify data: {e}", file=sys.stderr)
        return

    # --- 4. Process Each Product ---
    for handle in handles_to_process:
        print(f"\n--- Processing: {handle} ---")
        
        source_product_data = source_data.get(handle)
        shop_product_data = product_data_map.get(handle)
        
        if not source_product_data:
            print("  > ⚠️  Skipped: Not found in source CSV.")
            continue
        if not shop_product_data:
            print(f"  > ⚠️  Skipped: Not found in Shopify under capsule tag '{shop_capsule_tag}'.")
            continue
            
        product_gid = shop_product_data['gid']
        existing_media_gids = shop_product_data['media_gids']
        
        if args.verbose:
            print(f"  > Shopify GID: {product_gid}")
        
        # --- Build Update Payloads ---
        product_update_payload = {"id": product_gid}
        has_core_update = False
        
        if args.update_tags:
            tags_list = source_product_data['tags']
            product_update_payload['tags'] = tags_list
            print(f"  > 🏷️  Will update tags to: {', '.join(tags_list[:3])}...")
            has_core_update = True

        if args.update_details:
            details_str = source_product_data['details']
            print(f"  > 📝 Will update details to: {details_str[:50]}...")
            
        # --- 5. Execute API Calls ---
        try:
            # --- A: Core Product Updates (Tags) ---
            if has_core_update:
                client.update_product(product_update_payload, args.dry_run, verbose=args.verbose)
            
            # --- B: Metafield Updates (Details) ---
            if args.update_details:
                client.set_string_metafield(
                    owner_gid=product_gid,
                    namespace="altuzarra",
                    key="details",
                    value=details_str,
                    dry_run=args.dry_run,
                    verbose=args.verbose
                )
            
            # --- C: Image Updates ---
            if args.update_images:
                # Get the list of Shopify CDN URLs from our source data
                image_urls_to_create = source_product_data['images']
                
                print(f"  > 🖼️  Will replace {len(existing_media_gids)} media items with {len(image_urls_to_create)} new images...")

                # 1. Delete all old media
                if existing_media_gids:
                    client.delete_product_media(product_gid, existing_media_gids, args.dry_run, verbose=args.verbose)
                
                # 2. Create new media from the final Shopify URLs
                if image_urls_to_create:
                    # We can do this in one batch call, as the URLs are already on Shopify
                    client.create_product_media(product_gid, image_urls_to_create, args.dry_run, verbose=args.verbose)
                else:
                    print(f"  > ℹ️  No images listed in source CSV for this product.")
            
            if args.dry_run:
                print(f"  > ✅ [DRY RUN] Simulated updates for {handle}.")
            else:
                print(f"  > ✅ Successfully updated {handle}.")

        except AttributeError as e:
            print(f"  > ❌ FAILED: Your `ShopifyClient` is missing a required function: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  > ❌ FAILED: An API error occurred: {e}", file=sys.stderr)

    print("\n--- Process Complete ---")

if __name__ == "__main__":
    main()