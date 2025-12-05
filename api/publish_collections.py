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
from shopify_client import ShopifyClient

# The list of 59 collection titles to check and publish
# The exact casing/underscores here do not matter, as they will be normalized
TITLES_TO_PUBLISH = [
    "Style_Abstract Buckle Belt", "Style_Arlie Top", "Style_Astley Jacket",
    "Style_Baker Dress", "Style_Banks Top", "Style_Bean Skinny Belt",
    "Style_Birdy Dress", "Style_Buchanan Sweater", "Style_Carrol Dress",
    "Style_Chika Top", "Style_Classic Buckle Belt", "Style_Claudia Dress",
    "Style_Conroy Jacket", "Style_Dash Pant", "Style_E/W Mini Tote",
    "Style_Elongated Studded Buckle Belt", "Style_Elton Skirt", "Style_Fenice Jacket",
    "Style_Floyd Dress", "Style_Hamilton Sweater", "Style_Hank Skirt",
    "Style_Harold Sweater", "Style_Hayden Jacket", "Style_Jazmina Dress",
    "Style_Kaplan Dress", "Style_Katrin Dress", "Style_Kiera Dress",
    "Style_Linnie Skirt", "Style_Llewellyn Jacket", "Style_Loquette Belt",
    "Style_Mack Skirt", "Style_Marian Dress", "Style_Marty Sweater",
    "Style_Meyer Dress", "Style_Noor Dress", "Style_Oates Sweater",
    "Style_Organic Buckle Belt", "Style_Origami Bag", "Style_Origami Bag Mini",
    "Style_Origami Baguette", "Style_Orrie Dress", "Style_Penny Dress",
    "Style_Pogo Sweater", "Style_Putney Sweater", "Style_Satterly Top",
    "Style_Sayle Sweater", "Style_Sleary Top", "Style_Small Tote",
    "Style_Square Buckle Belt", "Style_Tate Sweater", "Style_Taylor Sweater",
    "Style_Thea Sweater", "Style_Todd Pant", "Style_Toro Sweater",
    "Style_Ty Sweater", "Style_Varda Skirt", "Style_Western Boho Belt",
    "Style_Xl Tote"
]

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


def main(dry_run: bool, target_style: str | None):
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

    collections_to_process = []
    
    if target_style:
        # Normalize the single target style for lookup
        normalized_target = normalize_title(target_style)
        print(f"\n--- Targeting single style: '{target_style}' (Normalized: '{normalized_target}') ---")
        
        found_collection = all_collections_map.get(normalized_target)
        if found_collection:
            collections_to_process.append(found_collection)
        else:
            print(f"❌ Error: Could not find collection matching '{normalized_target}'")
            return
    else:
        # Normalize the master list of titles to find
        normalized_titles_to_find = {normalize_title(t) for t in TITLES_TO_PUBLISH}
        print(f"\n--- Checking {len(normalized_titles_to_find)} normalized collections from list ---")

        found_titles_normalized = set()
        
        # Look up each normalized target title in our map
        for normalized_title in normalized_titles_to_find:
            collection = all_collections_map.get(normalized_title)
            if collection:
                collections_to_process.append(collection)
                found_titles_normalized.add(normalized_title)
        
        # Log which ones weren't found
        missing_titles_normalized = normalized_titles_to_find - found_titles_normalized
        if missing_titles_normalized:
            print(f"⚠️  Warning: Could not find {len(missing_titles_normalized)} collections (normalized titles shown):")
            for title in sorted(list(missing_titles_normalized)):
                print(f"  - {title}")

    # --- Step 4: Process and Publish ---
    print(f"\nProcessing {len(collections_to_process)} found collections...")
    for collection in collections_to_process:
        title = collection['title']
        col_id = collection['id']
        
        # --- THIS BLOCK HAS BEEN REMOVED ---
        # status = collection.get('status')
        # if status != 'ACTIVE':
        #     print(f"⚠️  Skipping '{title}': Collection status is '{status}', not 'ACTIVE'. ...")
        #     continue
        # --- END REMOVAL ---
        
        is_on_store = collection.get('isPublishedOnStore', False)
        is_on_pos = collection.get('isPublishedOnPOS', False)
        
        if is_on_store and is_on_pos:
            print(f"✅ Skipping '{title}': Already published to both channels.")
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
            print(f"✅ Skipping '{title}': Logic error, no publications to add.")
            continue
        
        channels_str = " and ".join(channels_to_add_names)
            
        if dry_run:
            print(f"[dry-run] Would publish '{title}' (ID: {col_id}) to: {channels_str}")
            continue
            
        print(f"  > Publishing '{title}' (ID: {col_id}) to: {channels_str}...")
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
    
    args = parser.parse_args()

    if not args.dry_run:
        print("--- WARNING: This is NOT a dry run. ---")
        print("This script will publish collections to the Online Store and POS.")
        confirm = input("Are you sure you want to continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborting.")
            exit()
            
    main(dry_run=args.dry_run, target_style=args.style)