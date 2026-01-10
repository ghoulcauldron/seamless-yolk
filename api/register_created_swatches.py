"""
register_created_swatches.py

Purpose:
- Acknowledge newly created swatch image files
- Adopt them into local product_state as authoritative assets
- Append resolution entries to swatch action queue

This script MUST:
- Read local filesystem only
- Mutate product_state deterministically
- Append (never overwrite) action queue records

This script MUST NOT:
- Inspect Shopify
- Upload images
- Write metafields
- Infer hero / ghost / editorial logic
"""

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

# -------------------------
# Helpers
# -------------------------

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def load_product_state(capsule: str) -> dict:
    path = Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing product_state: {path}")
    return json.loads(path.read_text())

def save_product_state(capsule: str, state: dict):
    path = Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    path.write_text(json.dumps(state, indent=2))

def load_or_init_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def append_dedupe_jsonl(path: Path, records: list, dedupe_keys: list):
    existing = load_or_init_jsonl(path)
    seen = {(r.get(k) for k in dedupe_keys) for r in existing}
    # Corrected: need to build set of tuples of dedupe keys from existing
    seen = set()
    for r in existing:
        key = tuple(r.get(k) for k in dedupe_keys)
        seen.add(key)
    with path.open("a", encoding="utf-8") as f:
        for r in records:
            key = tuple(r.get(k) for k in dedupe_keys)
            if key in seen:
                continue
            f.write(json.dumps(r) + "\n")
            seen.add(key)

def find_swatch_file(swatch_dir: Path, cpi: str, capsule: str) -> Path | None:
    """
    Match swatch files created by swatch_creator.

    Expected filename contains:
      - capsule prefix (must be present)
      - style number (first CPI segment)
      - color number (second CPI segment)
      - 'swatch'

    Both style and color tokens must match exactly as whole tokens, not substrings.

    If multiple candidates match, log and return None.
    """
    style, color = cpi.split("-")
    candidates = []

    for p in swatch_dir.glob("*swatch*"):
        name = p.name
        if capsule not in name:
            continue
        # Split filename into tokens by non-alphanumeric chars to match whole tokens
        tokens = [t.lower() for t in Path(name).stem.replace("_","-").replace(" ","-").split("-")]
        # Check exact token match for style and color (case-insensitive)
        if style.lower() in tokens and color.lower() in tokens:
            candidates.append(p)

    if len(candidates) > 1:
        print(f"[DEBUG] Multiple swatch candidates found for CPI {cpi} in {swatch_dir}: {[c.name for c in candidates]}. Skipping to force manual resolution.")
        return None

    if len(candidates) == 1:
        return candidates[0]

    return None

# -------------------------
# Main
# -------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", required=True)
    parser.add_argument("--cpis", nargs="*", help="Optional CPI filter")
    parser.add_argument(
        "--swatch-dir",
        default=None,
        help="Defaults to capsules/{capsule}/assets/swatches"
    )
    args = parser.parse_args()

    capsule = args.capsule
    state = load_product_state(capsule)

    swatch_dir = (
        Path(args.swatch_dir)
        if args.swatch_dir
        else Path(f"capsules/{capsule}/assets/swatches")
    )

    if not swatch_dir.exists():
        raise FileNotFoundError(f"Swatch directory not found: {swatch_dir} (expected default: capsules/{capsule}/assets/swatches)")

    products = state.get("products", {})
    target_cpis = args.cpis or [p.get("cpi") for p in products.values() if p.get("cpi")]

    swatch_queue_path = Path(
        f"capsules/{capsule}/outputs/actions_swatch_queue_{capsule}.jsonl"
    )

    queue_updates = []
    now = utc_now()

    for handle, product in products.items():
        cpi = product.get("cpi")
        if not cpi:
            print(f"[SKIP] Product {handle} missing CPI, skipping.")
            continue
        if cpi not in target_cpis:
            continue

        swatch_file = find_swatch_file(swatch_dir, cpi, capsule)
        if not swatch_file:
            print(f"[SKIP] {cpi} | no swatch file found")
            continue

        # Defensive guard: ensure swatch file includes capsule prefix
        if capsule not in swatch_file.name:
            print(f"[SKIP] {cpi} | swatch file {swatch_file.name} missing capsule prefix '{capsule}'")
            continue

        # ---- Adopt swatch into state ----
        product.setdefault("assets", {})
        product["assets"]["swatch"] = {
            "file_path": str(swatch_file),
            "source": "local_created",
            "created_by": "swatch_creator",
            "registered_by": "register_created_swatches",
            "registered_at": now,
        }

        # ---- Enable actions ----
        product.setdefault("allowed_actions", {})
        product["allowed_actions"]["image_upsert"] = True
        product["allowed_actions"]["metafield_write"] = True

        # ---- Queue record ----
        queue_updates.append({
            "cpi": cpi,
            "action": "SWATCH_CREATED",
            "file_path": str(swatch_file),
            "timestamp": now,
            "resolved": False,
        })

        print(f"[REGISTERED] {cpi} swatch adopted")

    # Persist state + queue
    save_product_state(capsule, state)
    append_dedupe_jsonl(swatch_queue_path, queue_updates, dedupe_keys=["cpi", "action"])

    print(f"\n✔ Registered {len(queue_updates)} swatches")

if __name__ == "__main__":
    main()