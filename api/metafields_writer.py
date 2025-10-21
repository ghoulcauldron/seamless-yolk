#!/usr/bin/env python3
"""
metafields_writer.py
Uploads swatch + look images (if any) from images_manifest.jsonl
and sets the corresponding product metafields.

Usage:
    python api/metafields_writer.py --capsule S126 [--dry-run]
    python api/metafields_writer.py --capsule S126 --debug-cpi 1008-000182
"""

import argparse, json, pathlib, re
from shopify_client import ShopifyClient

def load_manifest(capsule: str):
    manifest_path = pathlib.Path(f"capsules/{capsule}/manifests/images_manifest.jsonl")
    records = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    # This script's scope is only swatches and editorials (for look_image)
    return [r for r in records if r["asset_type"] in ("swatches", "editorials")]

def load_product_map(capsule: str):
    mapping_path = pathlib.Path(f"capsules/{capsule}/manifests/product_map.json")
    if not mapping_path.exists():
        raise FileNotFoundError("product_map.json missing (CPI → Product GID mapping).")
    return json.load(open(mapping_path))

def main(capsule: str, dry_run: bool = False, debug_cpi: str = None, cpis: list | None = None):
    CDN_PREFIX = 'https://cdn.shopify.com/s/files/1/0148/9561/2004/files/'
    client = ShopifyClient()
    
    if debug_cpi:
        print(f"--- Running in DEBUG mode for CPI: {debug_cpi} ---")
        manifest = [r for r in load_manifest(capsule) if r.get('cpi') == debug_cpi]
        if not manifest:
            print(f"❌ No swatch or editorial assets found in manifest for CPI {debug_cpi}.")
            return
    else:
        manifest = load_manifest(capsule)

    prod_map = load_product_map(capsule)

    # Always fetch existing files to provide an accurate simulation.
    existing_files_map = client.get_staged_uploads_map()
    if dry_run or debug_cpi:
        print("[run mode] The script will now check against the list of existing files.")

    if cpis:
        print(f"--- Running in CPI filter mode for {len(cpis)} CPI(s) ---")
        # Filter the product_data_map to only include items from the --cpis list
        product_data_map = {cpi: data for cpi, data in product_data_map.items() if cpi in cpis}
        if not product_data_map:
            print("No matching CPIs found from your list. Exiting.")
            return

    if debug_cpi:
        print("\n--- Full Existing Files Map (first 10 items for brevity) ---")
        print(json.dumps(dict(list(existing_files_map.items())[:10]), indent=2))
        print("--------------------------------------------------\n")

    jobs = []
    for row in manifest:
        cpi = row["cpi"]
        if not cpi or cpi not in prod_map:
            continue
        product_gid = prod_map[cpi]
        
        asset_type = row["asset_type"]
        key = None
        if asset_type == "swatches":
            key = "swatch_image"
        # Hero images from editorials are used for look_image
        elif asset_type == "editorials" and "hero_image" in row["filename"]:
            key = "look_image"
        
        if not key:
            continue

        if row.get("is_accessory") and key == "look_image":
            continue

        file_gid = None
        # Standardize the filename robustly for checking
        shopify_filename = re.sub(r'\s+', '_', row['filename'])
        
        if debug_cpi:
            print(f"Checking for standardized filename: '{shopify_filename}'")
        
        if shopify_filename in existing_files_map:
            file_gid = existing_files_map[shopify_filename]
            print(f"  ✅ FOUND existing file '{shopify_filename}' for {cpi}. Using GID: {file_gid}")
        else:
            if debug_cpi:
                print(f"  ❌ NOT FOUND. Script would attempt to upload this file.")

            alt = f"{key.replace('_',' ').capitalize()} - {cpi}"
            resource_url = CDN_PREFIX + shopify_filename

            if dry_run or debug_cpi:
                print(f"[dry-run] Would upload '{shopify_filename}' for {cpi} to set metafield '{key}'.")
                continue

            print(f"  > Uploading '{shopify_filename}' for {cpi}...")
            file_gid = client.upload_file(resource_url, alt)
            # In a real scenario, you would wait for the file to be ready
            # For this version, we assume it's ready immediately

        if file_gid:
            if dry_run or debug_cpi:
                 print(f"[dry-run] Would link file GID '{file_gid}' to product GID '{product_gid}' with key '{key}'.")
                 continue

            resp = client.set_product_metafield(product_gid, key, file_gid)
            jobs.append({
                "cpi": cpi, "product_gid": product_gid, "file_gid": file_gid,
                "key": key, "response": resp
            })
            print(f"✅ Linked {shopify_filename} → {key} for {cpi}")

    if not dry_run and not debug_cpi and jobs:
        log_path = pathlib.Path(f"capsules/{capsule}/outputs/api_jobs/metafields_{capsule}.json")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(jobs, open(log_path, "w"), indent=2)
        print(f"🗂  Log written to {log_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug-cpi", help="Run a focused debug test on a single CPI.")
    parser.add_argument('--cpis', nargs='+', help='(Optional) A list of specific CPIs to process.')
    args = parser.parse_args()
    main(args.capsule, args.dry_run, args.debug_cpi)