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
    return [r for r in records if r["asset_type"] == "swatches"]

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

def append_result(path: pathlib.Path, record: dict):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def main(capsule: str, dry_run: bool = False, debug_cpi: str = None, cpis: list | None = None, verbose: bool = False):
    client = ShopifyClient(verbose=verbose)
    gate = StateGate(f"capsules/{capsule}/state/product_state_{capsule}.json")

    results_log_path = pathlib.Path(f"capsules/{capsule}/outputs/metafields_results_{capsule}.jsonl")
    results_log_path.parent.mkdir(parents=True, exist_ok=True)

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
            print(f"❌ No swatch assets found in manifest for CPI {debug_cpi}.")
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
            append_result(results_log_path, {
                "cpi": cpi,
                "handle": handle,
                "product_gid": None,
                "action": "SKIP_GATE",
                "metafield": "swatch_image",
                "reason": decision.reason,
                "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
            })
            append_result(results_log_path, {
                "cpi": cpi,
                "handle": handle,
                "product_gid": None,
                "action": "SKIP_GATE",
                "metafield": "look_image",
                "reason": decision.reason,
                "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
            })
            print(f"[CPI SUMMARY] {cpi} | handle={handle} | gate=DENY | swatch={swatch_status} | look={look_status}")
            continue

        if cpi not in prod_map:
            # No product GID mapping found; treat as missing uploads
            swatch_status = "missing"
            look_status = "missing"
            append_result(results_log_path, {
                "cpi": cpi,
                "handle": handle,
                "product_gid": None,
                "action": "SKIP_NO_ASSET",
                "metafield": "swatch_image",
                "reason": "No product GID mapping found",
                "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
            })
            append_result(results_log_path, {
                "cpi": cpi,
                "handle": handle,
                "product_gid": None,
                "action": "SKIP_NO_ASSET",
                "metafield": "look_image",
                "reason": "No product GID mapping found",
                "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
            })
            print(f"[CPI SUMMARY] {cpi} | handle={handle} | gate=ALLOW | swatch={swatch_status} | look={look_status}")
            continue

        product_gid = prod_map[cpi]

        # Process swatch images from manifest (unchanged)
        for row in rows:
            asset_type = row["asset_type"]
            key = None
            if asset_type == "swatches":
                key = "swatch_image"

            if not key:
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
                    continue

                resp = client.set_product_metafield(product_gid, key, file_gid)
                jobs.append({
                    "cpi": cpi, "product_gid": product_gid, "file_gid": file_gid,
                    "key": key, "response": resp
                })
                print(f"✅ Linked {shopify_filename} → {key} for {cpi}")

                if key == "swatch_image":
                    swatch_status = "uploaded"

        # Process look_image from state only
        state_product = gate.products.get(handle, {})
        look_images = state_product.get("assets", {}).get("look_images", [])
        preflight_status = state_product.get("preflight", {}).get("status")

        if not look_images:
            look_status = "skipped"
            print(f"[LOOK_IMAGE] {cpi} | handle={handle} | reason=NO_LOOK_IMAGE_IN_STATE | action=SKIP")
            append_result(results_log_path, {
                "cpi": cpi,
                "handle": handle,
                "product_gid": product_gid,
                "action": "SKIP_NO_ASSET",
                "metafield": "look_image",
                "reason": "NO_LOOK_IMAGE_IN_STATE",
                "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
            })
        elif preflight_status != "GO":
            look_status = "skipped"
            print(f"[LOOK_IMAGE] {cpi} | handle={handle} | reason=PRE_FLIGHT_STATUS_NOT_GO | action=SKIP")
            append_result(results_log_path, {
                "cpi": cpi,
                "handle": handle,
                "product_gid": product_gid,
                "action": "SKIP_PREFLIGHT",
                "metafield": "look_image",
                "reason": "PRE_FLIGHT_STATUS_NOT_GO",
                "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
            })
        else:
            target_media_gid = look_images[0].get("media_gid")
            if not target_media_gid:
                look_status = "skipped"
                print(f"[LOOK_IMAGE] {cpi} | handle={handle} | reason=MEDIA_GID_MISSING | action=SKIP")
                append_result(results_log_path, {
                    "cpi": cpi,
                    "handle": handle,
                    "product_gid": product_gid,
                    "action": "SKIP_NO_ASSET",
                    "metafield": "look_image",
                    "reason": "MEDIA_GID_MISSING",
                    "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
                })
            else:
                # Read existing look_image metafield
                existing_look_image = None
                try:
                    existing_look_image = client.get_product_metafield(product_gid, "look_image")
                except Exception as e:
                    print(f"[LOOK_IMAGE] {cpi} | handle={handle} | error=Failed to read existing metafield: {e}")

                if existing_look_image == target_media_gid:
                    look_status = "noop"
                    print(f"[LOOK_IMAGE] {cpi} | handle={handle} | product_gid={product_gid} | target_media_gid={target_media_gid} | action=NOOP_ALREADY_SET")
                    append_result(results_log_path, {
                        "cpi": cpi,
                        "handle": handle,
                        "product_gid": product_gid,
                        "action": "NOOP_ALREADY_SET",
                        "metafield": "look_image",
                        "target_media_gid": target_media_gid,
                        "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
                    })
                else:
                    if dry_run or debug_cpi:
                        look_status = "skipped"
                        print(f"[LOOK_IMAGE] {cpi} | handle={handle} | product_gid={product_gid} | target_media_gid={target_media_gid} | action=SKIP (dry-run)")
                        append_result(results_log_path, {
                            "cpi": cpi,
                            "handle": handle,
                            "product_gid": product_gid,
                            "action": "SKIP_PREFLIGHT",
                            "metafield": "look_image",
                            "target_media_gid": target_media_gid,
                            "reason": "dry-run or debug mode",
                            "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
                        })
                    else:
                        try:
                            resp = client.set_product_metafield(product_gid, "look_image", target_media_gid)
                            look_status = "wrote"
                            jobs.append({
                                "cpi": cpi,
                                "handle": handle,
                                "product_gid": product_gid,
                                "target_media_gid": target_media_gid,
                                "key": "look_image",
                                "response": resp
                            })
                            print(f"[LOOK_IMAGE] {cpi} | handle={handle} | product_gid={product_gid} | target_media_gid={target_media_gid} | action=WROTE")
                            append_result(results_log_path, {
                                "cpi": cpi,
                                "handle": handle,
                                "product_gid": product_gid,
                                "action": "WROTE",
                                "metafield": "look_image",
                                "target_media_gid": target_media_gid,
                                "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
                            })
                        except Exception as e:
                            look_status = "skipped"
                            print(f"[LOOK_IMAGE] {cpi} | handle={handle} | product_gid={product_gid} | target_media_gid={target_media_gid} | action=ERROR | error={e}")
                            append_result(results_log_path, {
                                "cpi": cpi,
                                "handle": handle,
                                "product_gid": product_gid,
                                "action": "ERROR",
                                "metafield": "look_image",
                                "target_media_gid": target_media_gid,
                                "reason": str(e),
                                "timestamp": __import__('datetime').datetime.utcnow().isoformat() + "Z"
                            })

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