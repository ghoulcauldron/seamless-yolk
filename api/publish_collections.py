#!/usr/bin/env python3
"""
publish_collections.py

Finds a specific list of smart collections by their title and ensures they
are published to both the "Online Store" and "Point of Sale" channels.
Performs a case-insensitive and underscore-insensitive match.

Usage:
    # Dry run to see what would be published
    python scripts/publish_collections.py --dry-run
    
    # Live run to publish all collections in the list
    python scripts/publish_collections.py
    
    # Target a single collection for debugging or live run
    python scripts/publish_collections.py --style "Style_Harold Sweater"
"""

import argparse
import time
from api.shopify_client import ShopifyClient

def normalize_title(title: str) -> str:
    """Helper function to normalize titles for comparison.
    Converts to lowercase, replaces underscores with spaces, 
    squashes multiple spaces, and strips whitespace.
    """
    if not isinstance(title, str):
        return ""
    # "Style_Harold Sweater" -> "style harold sweater"
    # "style_harold_sweater" -> "style harold sweater"
    # "Style Harold Sweater" -> "style harold sweater"
    return " ".join(title.lower().replace("_", " ").split())

def load_authorized_styles_from_state(capsule: str) -> set[str]:
    """
    Load capsule product_state JSON and return a set of style tags
    authorized for collection publication.

    A style is authorized if at least one product with that style tag
    has allowed_actions.collection_write == true.
    """
    import json
    import pathlib

    state_path = pathlib.Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    if not state_path.exists():
        print(f"❌ Error: State file not found at {state_path}")
        return set()

    with open(state_path, "r") as f:
        state = json.load(f)

    products = state.get("products", {})
    authorized_styles = set()

    for product in products.values():
        if not isinstance(product, dict):
            continue

        allowed = product.get("allowed_actions", {})
        if allowed.get("collection_write") is not True:
            continue

        for tag in product.get("tags", []):
            if isinstance(tag, str) and tag.startswith("style_") and tag != "style_":
                authorized_styles.add(tag)

    return authorized_styles

def main(capsule: str, dry_run: bool, target_style: str | None):
    """
    Fetches collections, checks their publication status, and publishes
    to 'Online Store' and 'Point of Sale' if not already published.
    """
    
    client = ShopifyClient()
    
    # --- Step 1: Get Publication GIDs for "Online Store" and "Point of Sale" ---
    print("Fetching Publication Channel IDs...")
    try:
        publication_ids = client.get_publication_ids(names=["Online Store", "Point of Sale"])
    except AttributeError:
        print("❌ Error: 'ShopifyClient' object missing 'get_publication_ids'.")
        print("Please ensure 'shopify_client.py' has this method.")
        return
    except Exception as e:
        print(f"❌ Error fetching publication IDs: {e}")
        return

    # Check if we found the required channels
    online_store_id = publication_ids.get("Online Store")
    pos_id = publication_ids.get("Point of Sale")
    
    if not online_store_id:
        print("❌ Error: Could not find Publication ID for 'Online Store'. Aborting.")
        return
    if not pos_id:
        print("❌ Error: Could not find Publication ID for 'Point of Sale'. Aborting.")
        return
        
    print(f"  > Found 'Online Store': {online_store_id}")
    print(f"  > Found 'Point of Sale': {pos_id}")
    

    # --- Step 2: Get all Smart Collections and their current publications ---
    print("Fetching all smart collections and their publication status...")
    try:
        all_collections = client.get_all_smart_collections_with_publication_status(
            store_pub_id=online_store_id,
            pos_pub_id=pos_id
        )
    except AttributeError:
        print("❌ Error: 'ShopifyClient' object missing 'get_all_smart_collections_with_publication_status'.")
        print("Please ensure 'shopify_client.py' has this new method.")
        return
    except Exception as e:
        print(f"❌ Error fetching collections: {e}")
        return
        
    print(f"  > Fetched {len(all_collections)} total collections.")
    
    # --- Step 3: Determine which collections to process ---
    
    # Create a lookup map of {normalized_title: full_collection_object}
    all_collections_map = {
        normalize_title(c.get('title', '')): c
        for c in all_collections
    }

    authorized_styles = load_authorized_styles_from_state(capsule)

    if not authorized_styles:
        print("⏭ No authorized styles found in product_state. Nothing to publish.")
        return

    print(f"\n[STATE_AUDIT] {len(authorized_styles)} style(s) authorized for publication")

    # Normalize authorized styles for lookup
    normalized_authorized = {
        normalize_title(style): style for style in authorized_styles
    }

    collections_to_process = []

    if target_style:
        normalized_target = normalize_title(target_style)
        print(f"\n--- Targeting single style: '{target_style}' ---")

        collection = all_collections_map.get(normalized_target)
        if not collection:
            print(f"❌ Error: No Shopify collection found for '{normalized_target}'")
            return

        if normalized_target not in normalized_authorized:
            print(f"⏭ Skipping '{target_style}': not authorized in product_state")
            return

        collections_to_process.append(collection)

    else:
        for norm_title, collection in all_collections_map.items():
            if norm_title in normalized_authorized:
                collections_to_process.append(collection)

    if not collections_to_process:
        print("⏭ No matching Shopify collections found for authorized styles.")
        return

    # --- Step 4: Process and Publish ---
    print(f"\nProcessing {len(collections_to_process)} found collections...")
    for collection in collections_to_process:
        title = collection['title']
        col_id = collection['id']
        
        is_on_store = collection.get('isPublishedOnStore', False)
        is_on_pos = collection.get('isPublishedOnPOS', False)
        
        if is_on_store and is_on_pos:
            print(f"[NOOP] {title} | capsule={capsule} | already published")
            continue
            
        # Build the list of *only* the publications to add
        publications_to_add = []
        channels_to_add_names = []
        
        if not is_on_store:
            publications_to_add.append({"publicationId": online_store_id})
            channels_to_add_names.append("Online Store")
        if not is_on_pos:
            publications_to_add.append({"publicationId": pos_id})
            channels_to_add_names.append("Point of Sale")
        
        if not publications_to_add:
            print(f"[NOOP] {title} | capsule={capsule} | no publications to add (logic error)")
            continue
        
        channels_str = " and ".join(channels_to_add_names)
            
        if dry_run:
            print(f"[dry-run] [PUBLISH] {title} | capsule={capsule} | would publish to: {channels_str}")
            continue
            
        print(f"[PUBLISH] Publishing '{title}' | capsule={capsule} | to: {channels_str}...")
        try:
            # Pass the pub IDs for verification
            client.publish_collection(col_id, publications_to_add, online_store_id, pos_id) 
            print(f"    ✅ Published.")
            time.sleep(0.5) 
            
        except AttributeError:
            print("❌ Error: 'ShopifyClient' object has no attribute 'publish_collection'.")
            print("Please ensure 'shopify_client.py' has this method. Aborting.")
            return
        except Exception as e:
            print(f"    ❌ FAILED to publish '{title}' (ID: {col_id}): {e}")

    print("\nPublication check complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check and publish smart collections to Online Store and POS.")
    parser.add_argument('--dry-run', action='store_true', help='Run script without actually publishing anything.')
    parser.add_argument('--style', help='(Optional) Run for a single, specific collection title.')
    parser.add_argument(
        '--capsule',
        required=True,
        help='Capsule name (e.g., "S226") used to load product_state.'
    )
    
    args = parser.parse_args()

    if not args.dry_run:
        print("--- WARNING: This is NOT a dry run. ---")
        print("This script will publish collections to the Online Store and POS.")
        confirm = input("Are you sure you want to continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborting.")
            exit()
            
    main(capsule=args.capsule, dry_run=args.dry_run, target_style=args.style)