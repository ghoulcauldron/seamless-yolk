#!/usr/bin/env python3
"""
delete_style_collections.py

Finds and deletes a specific list of "pretty" smart collections that were
created in error (e.g., "Style Harold Sweater" with a space).

Usage:
    python scripts/delete_style_collections.py [--dry-run]
"""

import argparse
import pathlib
import time
from shopify_client import ShopifyClient

# List of exact, case-sensitive "pretty" titles to be deleted
TITLES_TO_DELETE = [
    "Style Abstract Buckle Belt",
    "Style Arlie Top",
    "Style Astley Jacket",
    "Style Baker Dress",
    "Style Banks Top",
    "Style Bean Skinny Belt",
    "Style Birdy Dress",
    "Style Buchanan Sweater",
    "Style Carrol Dress",
    "Style Chika Top",
    "Style Classic Buckle Belt",
    "Style Claudia Dress",
    "Style Conroy Jacket",
    "Style Dash Pant",
    "Style E/W Mini Tote",
    "Style Elongated Studded Buckle Belt",
    "Style Elton Skirt",
    "Style Fenice Jacket",
    "Style Floyd Dress",
    "Style Hamilton Sweater",
    "Style Hank Skirt",
    "Style Harold Sweater",
    "Style Hayden Jacket",
    "Style Jazmina Dress",
    "Style Kaplan Dress",
    "Style Katrin Dress",
    "Style Kiera Dress",
    "Style Linnie Skirt",
    "Style Llewellyn Jacket",
    "Style Loquette Belt",
    "Style Mack Skirt",
    "Style Marian Dress",
    "Style Marty Sweater",
    "Style Meyer Dress",
    "Style Noor Dress",
    "Style Oates Sweater",
    "Style Organic Buckle Belt",
    "Style Origami Bag",
    "Style Origami Bag Mini",
    "Style Origami Baguette",
    "Style Orrie Dress",
    "Style Penny Dress",
    "Style Pogo Sweater",
    "Style Putney Sweater",
    "Style Satterly Top",
    "Style Sayle Sweater",
    "Style Sleary Top",
    "Style Small Tote",
    "Style Square Buckle Belt",
    "Style Tate Sweater",
    "Style Taylor Sweater",
    "Style Thea Sweater",
    "Style Todd Pant",
    "Style Toro Sweater",
    "Style Ty Sweater",
    "Style Varda Skirt",
    "Style Western Boho Belt",
    "Style Xl Tote"
]


def main(dry_run: bool):
    """
    Fetches all smart collections, finds matches from the list, and deletes them.
    """
    
    # Use a set for efficient lookup
    titles_to_delete_set = set(TITLES_TO_DELETE)
    
    client = ShopifyClient()
    collections_to_delete = []
    
    print("Fetching all smart collections from Shopify (this may take a moment)...")
    try:
        # --- ASSUMPTION 1 ---
        # Assumes your client has a method 'get_all_smart_collections'
        # that returns a list of collection dicts, e.g., [{'id': 123, 'title': '...'}, ...]
        all_collections = client.get_all_smart_collections()
        
        if all_collections is None:
             print("❌ Error: 'get_all_smart_collections' returned None. Client setup might be incorrect.")
             return

    except AttributeError:
        print("❌ Error: 'ShopifyClient' object has no attribute 'get_all_smart_collections'.")
        print("Please add this method to your shopify_client.py")
        return
    except Exception as e:
        print(f"❌ Error: Could not fetch collections from ShopifyClient: {e}")
        return

    print(f"  > Fetched {len(all_collections)} total collections.")
    print(f"Searching for {len(titles_to_delete_set)} specific titles to delete...")

    # Find collections that match the titles to be deleted
    for collection in all_collections:
        title = collection.get('title')
        if title in titles_to_delete_set:
            collections_to_delete.append({
                'title': title,
                'id': collection.get('id')
            })

    if not collections_to_delete:
        print("\n✅ No matching collections found to delete.")
        return

    print(f"\nFound {len(collections_to_delete)} collections to delete:")
    
    for collection in collections_to_delete:
        title = collection['title']
        col_id = collection['id']
        
        if dry_run:
            print(f"[dry-run] Would DELETE collection: '{title}' (ID: {col_id})")
            continue
            
        print(f"  > Deleting '{title}' (ID: {col_id})...")
        try:
            # --- ASSUMPTION 2 ---
            # Assumes your client has a method 'delete_smart_collection'
            # that takes a collection ID as an argument.
            client.delete_smart_collection(col_id)
            print(f"    ✅ Deleted.")
            
            # Add a small delay to avoid rate limiting
            time.sleep(0.5) 
            
        except AttributeError:
            print("❌ Error: 'ShopifyClient' object has no attribute 'delete_smart_collection'.")
            print("Please add this method to your shopify_client.py. Aborting.")
            return # Stop the script if the method is missing
        except Exception as e:
            print(f"    ❌ FAILED to delete '{title}' (ID: {col_id}): {e}")

    print("\nDeletion process complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find and delete erroneous 'pretty' style collections.")
    parser.add_argument('--dry-run', action='store_true', help='Run script without actually deleting anything.')
    
    args = parser.parse_args()

    if not args.dry_run:
        print("--- WARNING: This is NOT a dry run. ---")
        print(f"This script will permanently delete {len(TITLES_TO_DELETE)} collections if found.")
        confirm = input("Are you absolutely sure you want to continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborting.")
            exit()
            
    main(dry_run=args.dry_run)