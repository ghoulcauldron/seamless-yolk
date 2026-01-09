#!/usr/bin/env python3
"""
metafields_writer.py
Uploads swatch + look images (if any) from images_manifest.jsonl
and sets the corresponding product metafields.

Usage:
    python api/metafields_writer.py --capsule S126 [--dry-run]
    python api/metafields_writer.py --capsule S126 --debug-cpi 1008-000182
    python api/metafields_writer.py --capsule S126 --cpis 1008-000182 --verbose
"""

import argparse, json, pathlib, re
from api.shopify_client import ShopifyClient
from utils.state_gate import StateGate

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

def resolve_handle_from_state(gate: StateGate, cpi: str) -> str | None:
    """
    Resolve product handle from state using CPI.
    Returns None if no matching product is found.
    """
    for handle, record in gate.products.items():
        if record.get("cpi") == cpi:
            return handle
    return None

def main(capsule: str, dry_run: bool = False, debug_cpi: str = None, cpis: list | None = None, verbose: bool = False):
    client = ShopifyClient(verbose=verbose)
    gate = StateGate(f"capsules/{capsule}/state/product_state_{capsule}.json")

    # Determine CPI scope
    if debug_cpi:
        target_cpis = {debug_cpi}
    elif cpis:
        target_cpis = set(cpis)
    else:
        target_cpis = {
            record.get("cpi")
            for record in gate.products.values()
            if record.get("cpi")
        }

    # Enforce strict CPI scoping: filter manifest and all processing to only target_cpis
    manifest = load_manifest(capsule)
    manifest = [
        r for r in manifest
        if r.get("cpi") in target_cpis
    ]

    prod_map = load_product_map(capsule)

    # Always fetch existing files to provide an accurate simulation.
    existing_files_map = client.get_staged_uploads_map()
    if dry_run or debug_cpi:
        print("[run mode] The script will now check against the list of existing files.")

    if cpis:
        print(f"--- Running in CPI filter mode for {len(cpis)} CPI(s) ---")

    if debug_cpi:
        print(f"--- Running in DEBUG mode for CPI: {debug_cpi} ---")
        if not manifest:
            print(f"❌ No swatch or editorial assets found in manifest for CPI {debug_cpi}.")
            return
        print("\n--- Full Existing Files Map (first 10 items for brevity) ---")
        print(json.dumps(dict(list(existing_files_map.items())[:10]), indent=2))
        print("--------------------------------------------------\n")

    # Group manifest rows by CPI for per-CPI processing and summary
    from collections import defaultdict
    rows_by_cpi = defaultdict(list)
    for row in manifest:
        cpi = row.get("cpi")
        if cpi in target_cpis:
            rows_by_cpi[cpi].append(row)

    jobs = []
    for cpi in sorted(target_cpis):
        rows = rows_by_cpi.get(cpi, [])

        handle = resolve_handle_from_state(gate, cpi)
        if not handle:
            raise RuntimeError(f"[STATE ERROR] No handle found in product_state for CPI {cpi}")

        promotion = gate.products.get(handle, {}).get("promotion", {})
        stage = promotion.get("stage", "UNKNOWN")

        decision = gate.can(handle=handle, action="metafield_write")

        print(
            f"[CPI] {cpi} | handle={handle} | "
            f"stage={stage} | metafield_write={decision.allowed}"
        )

        swatch_status = "missing"
        look_status = "missing"

        if not decision.allowed:
            print(f"⏭ Skipping metafield write for {handle}: {decision.reason}")
            swatch_status = "skipped"
            look_status = "skipped"
            print(f"[CPI SUMMARY] {cpi} | handle={handle} | gate=DENY | swatch={swatch_status} | look={look_status}")
            continue

        if cpi not in prod_map:
            # No product GID mapping found; treat as missing uploads
            swatch_status = "missing"
            look_status = "missing"
            print(f"[CPI SUMMARY] {cpi} | handle={handle} | gate=ALLOW | swatch={swatch_status} | look={look_status}")
            continue

        product_gid = prod_map[cpi]

        for row in rows:
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
                local_path = pathlib.Path(row["source_dir"]) / row["filename"]

                if dry_run or debug_cpi:
                    print(f"[dry-run] Would upload '{shopify_filename}' for {cpi} to set metafield '{key}'.")
                    # Mark as skipped in dry-run/debug mode
                    if key == "swatch_image":
                        swatch_status = "skipped"
                    elif key == "look_image":
                        look_status = "skipped"
                    continue

                if not local_path.exists():
                    raise FileNotFoundError(f"[UPLOAD ERROR] Local file missing: {local_path}")

                print(f"  > Uploading '{shopify_filename}' for {cpi}...")
                file_gid = client.upload_file_from_path(local_path, alt)

            if file_gid:
                if dry_run or debug_cpi:
                    print(f"[dry-run] Would link file GID '{file_gid}' to product GID '{product_gid}' with key '{key}'.")
                    # Mark as skipped in dry-run/debug mode
                    if key == "swatch_image":
                        swatch_status = "skipped"
                    elif key == "look_image":
                        look_status = "skipped"
                    continue

                resp = client.set_product_metafield(product_gid, key, file_gid)
                jobs.append({
                    "cpi": cpi, "product_gid": product_gid, "file_gid": file_gid,
                    "key": key, "response": resp
                })
                print(f"✅ Linked {shopify_filename} → {key} for {cpi}")

                if key == "swatch_image":
                    swatch_status = "uploaded"
                elif key == "look_image":
                    look_status = "uploaded"

        # If no rows found for swatch or look, keep status as missing unless updated
        # But if status not updated from missing, it stays missing

        print(f"[CPI SUMMARY] {cpi} | handle={handle} | gate={'ALLOW' if decision.allowed else 'DENY'} | swatch={swatch_status} | look={look_status}")

    if not dry_run and not debug_cpi and jobs:
        log_path = pathlib.Path(f"capsules/{capsule}/outputs/api_jobs/metafields_{capsule}.json")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(jobs, open(log_path, "w"), indent=2)
        print(f"🗂  Log written to {log_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (passed through to ShopifyClient).")
    parser.add_argument("--debug-cpi", help="Run a focused debug test on a single CPI.")
    parser.add_argument('--cpis', nargs='+', help='(Optional) A list of specific CPIs to process.')
    args = parser.parse_args()
    main(args.capsule, args.dry_run, args.debug_cpi, args.cpis, verbose=args.verbose)