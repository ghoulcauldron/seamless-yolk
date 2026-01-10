import json
import argparse
from pathlib import Path
from datetime import datetime

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--capsule", required=True)
    p.add_argument("--inspect-json")
    p.add_argument("--cpis", nargs="*")
    return p.parse_args()

def main():
    args = parse_args()

    state_path = Path(f"capsules/{args.capsule}/state/product_state_{args.capsule}.json")

    if args.inspect_json:
        inspect_path = Path(args.inspect_json)
        if not inspect_path.is_absolute():
            inspect_path = Path("capsules") / args.capsule / "outputs" / inspect_path
    else:
        inspect_path = Path(f"capsules/{args.capsule}/outputs/inspect_images_{args.capsule}.json")

    if not inspect_path.exists():
        raise FileNotFoundError(f"Missing inspection file: {inspect_path}")

    state = json.loads(state_path.read_text())
    inspection = json.loads(inspect_path.read_text())

    if args.cpis:
        inspection = [row for row in inspection if row.get("cpi") in args.cpis]

    products = state["products"]
    now = datetime.utcnow().isoformat() + "Z"

    for row in inspection:
        shopify_block = row.get("shopify") or {}
        hero_candidates = shopify_block.get("hero_candidates") or []
        cpi = row["cpi"]
        handle = row["handle"]
        if not hero_candidates:
            print(f"[derive] SKIP {cpi} ({handle}): no hero candidates")
            continue

        if handle not in products:
            print(f"[derive] SKIP {cpi} ({handle}): handle not found in product_state")
            continue

        # Prefer filename-based hero detection when available.
        # Rules:
        # 1) If any candidate filename includes "hero_image" (case-insensitive), take the first such match.
        # 2) Else, if we have at least 2 candidates and the first looks like a ghost (filename includes "ghost"), take the second.
        # 3) Else, fall back to the first candidate.
        def _fname(m: dict) -> str:
            return str(m.get("filename") or "").lower()

        chosen = None
        for cand in hero_candidates:
            if "hero_image" in _fname(cand):
                chosen = cand
                selection_reason = "FILENAME_MATCH_HERO_IMAGE"
                break

        if chosen is None and len(hero_candidates) >= 2 and "ghost" in _fname(hero_candidates[0]):
            chosen = hero_candidates[1]
            selection_reason = "IDX1_AFTER_GHOST_AT_IDX0"

        if chosen is None:
            chosen = hero_candidates[0]
            selection_reason = "FALLBACK_IDX0"

        record = products[handle]
        assets = record.setdefault("assets", {})
        assets["look_images"] = [{
            "media_gid": chosen["media_gid"],
            "source": "shopify_existing",
            "derived_from": "inspect_product_images",
            "derived_at": now,
            "selection_reason": selection_reason,
            "chosen_filename": chosen.get("filename")
        }]
        print(f"[derive] SET look_image for {cpi} ({handle})")

    state_path.write_text(json.dumps(state, indent=2))
    print(f"Updated product_state for capsule {args.capsule}")

if __name__ == "__main__":
    main()