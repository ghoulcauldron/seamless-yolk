# api/reconcile_capsule_assets.py

import argparse
import json
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone

def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def load_or_empty_list(path: Path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []

def main(capsule: str, cpis=None, inspect_json=None):
    if inspect_json:
        inspect_path = Path(inspect_json).resolve()
    else:
        inspect_path = Path(f"capsules/{capsule}/outputs/inspect_images_{capsule}.json")

    state_path = Path(f"capsules/{capsule}/state/product_state_{capsule}.json")

    state = load_json(state_path)
    inspect_rows = load_json(inspect_path)
    inspect_by_cpi = {row["cpi"]: row for row in inspect_rows}

    if cpis:
        active_cpis = set(cpis)
    else:
        active_cpis = set(inspect_by_cpi.keys())

    drift_log = []
    swatch_queue = []
    manual_queue = []

    products = state.get("products", {})
    updated = False

    for handle, product in products.items():
        cpi = product.get("cpi")
        if not cpi or cpi not in inspect_by_cpi:
            continue
        if cpi not in active_cpis:
            continue

        inspection = inspect_by_cpi[cpi]
        shopify = inspection.get("shopify", {})
        hero_candidates = shopify.get("hero_candidates", [])

        baseline = {
            "local_has_hero": bool(product.get("assets", {}).get("look_images")),
            "local_has_swatch": bool(product.get("assets", {}).get("swatch_image")),
        }

        adopted = {}
        provenance = {}

        # --- HERO ADOPTION ---
        if hero_candidates:
            hero = hero_candidates[0]
            adopted["look_images"] = [{
                "media_gid": hero["media_gid"],
                "source": "shopify",
                "adopted_at": now_utc(),
            }]
            provenance["look_images"] = "shopify"

        # --- DRIFT RECORD ---
        drift_log.append({
            "cpi": cpi,
            "handle": handle,
            "baseline": baseline,
            "observed": {
                "shopify_media_count": shopify.get("media_count"),
                "shopify_has_hero": bool(hero_candidates),
            },
            "adopted": adopted,
            "timestamp": now_utc(),
        })

        # --- APPLY ADOPTION TO STATE ---
        if adopted:
            product.setdefault("assets", {})
            product["assets"].update(adopted)

            product.setdefault("assets_provenance", {})
            product["assets_provenance"].update(provenance)

            product.setdefault("preflight", {})
            product["preflight"]["image_status"] = "IMAGE_OK"
            product["preflight"]["status"] = "GO"

            product.setdefault("allowed_actions", {})
            product["allowed_actions"]["metafield_write"] = True

            updated = True

        # --- ACTION QUEUES ---
        if not baseline["local_has_swatch"]:
            swatch_queue.append({
                "cpi": cpi,
                "handle": handle,
                "reason": "SWATCH_MISSING_LOCALLY",
                "timestamp": now_utc(),
            })

        if not hero_candidates:
            manual_queue.append({
                "cpi": cpi,
                "handle": handle,
                "reason": "NO_HERO_CANDIDATE_IN_SHOPIFY",
                "timestamp": now_utc(),
            })

    if updated:
        save_json(state_path, state)

    if cpis:
        drift_path = Path(f"capsules/{capsule}/outputs/asset_drift_{capsule}_SCOPED.json")
        swatch_path = Path(f"capsules/{capsule}/outputs/actions_swatch_queue_{capsule}_SCOPED.json")
        manual_path = Path(f"capsules/{capsule}/outputs/actions_manual_review_{capsule}_SCOPED.json")
    else:
        drift_path = Path(f"capsules/{capsule}/outputs/asset_drift_{capsule}.json")
        swatch_path = Path(f"capsules/{capsule}/outputs/actions_swatch_queue_{capsule}.json")
        manual_path = Path(f"capsules/{capsule}/outputs/actions_manual_review_{capsule}.json")

    # --- APPEND + DEDUPE OUTPUTS ---

    def dedupe(rows, key_fields):
        seen = set()
        out = []
        for r in rows:
            key = tuple(r.get(k) for k in key_fields)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    # Drift: append, dedupe by (cpi, timestamp)
    existing_drift = load_or_empty_list(drift_path)
    combined_drift = existing_drift + drift_log
    combined_drift = dedupe(combined_drift, ["cpi", "timestamp"])
    save_json(drift_path, combined_drift)

    # Swatch queue: append, dedupe by (cpi, reason)
    existing_swatch = load_or_empty_list(swatch_path)
    combined_swatch = existing_swatch + swatch_queue
    combined_swatch = dedupe(combined_swatch, ["cpi", "reason"])
    save_json(swatch_path, combined_swatch)

    # Manual review queue: append, dedupe by (cpi, reason)
    existing_manual = load_or_empty_list(manual_path)
    combined_manual = existing_manual + manual_queue
    combined_manual = dedupe(combined_manual, ["cpi", "reason"])
    save_json(manual_path, combined_manual)

    print(f"Reconciliation complete for capsule {capsule}")
    print(f"- Drift records: {len(drift_log)}")
    print(f"- Swatch actions: {len(swatch_queue)}")
    print(f"- Manual review actions: {len(manual_queue)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile Shopify asset reality into local state")
    parser.add_argument("--capsule", required=True)
    parser.add_argument("--cpis", nargs="+", help="List of CPI strings to scope reconciliation")
    parser.add_argument("--inspect-json", help="Path override for inspect JSON file")
    args = parser.parse_args()
    main(args.capsule, cpis=args.cpis, inspect_json=args.inspect_json)