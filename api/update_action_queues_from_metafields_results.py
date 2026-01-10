#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime

def load_json_file(path):
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def mark_resolved(actions, cpi_set, now_iso):
    for action in actions:
        if action.get("cpi") in cpi_set:
            if not action.get("resolved", False):
                action["resolved"] = True
                action["resolved_by"] = "metafields_writer"
                action["resolved_at"] = now_iso

def deduplicate_actions(actions):
    seen = set()
    deduped = []
    for action in actions:
        cpi = action.get("cpi")
        resolved = action.get("resolved", False)
        key = (cpi, resolved)
        if key not in seen:
            seen.add(key)
            deduped.append(action)
    return deduped

def main():
    parser = argparse.ArgumentParser(description="Update action queues from metafields_writer results")
    parser.add_argument("--capsule", required=True, help="Capsule name")
    parser.add_argument("--results-json", required=True, help="Path to metafields_writer results JSON")
    args = parser.parse_args()

    capsule = args.capsule
    results_json_path = args.results_json

    # Load results JSON
    with open(results_json_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    base_path = os.path.join("capsules", capsule, "outputs")
    swatch_queue_path = os.path.join(base_path, f"actions_swatch_queue_{capsule}.json")
    manual_review_path = os.path.join(base_path, f"actions_manual_review_{capsule}.json")

    swatch_actions = load_json_file(swatch_queue_path)
    manual_review_actions = load_json_file(manual_review_path)

    # Collect CPIs to mark resolved from results with action WROTE or NOOP_ALREADY_SET
    cpis_to_resolve = set()
    for record in results:
        action = record.get("action")
        if action in ("WROTE", "NOOP_ALREADY_SET"):
            cpi = record.get("cpi")
            if cpi is not None:
                cpis_to_resolve.add(cpi)

    now_iso = datetime.utcnow().isoformat() + "Z"

    # Mark matching swatch actions as resolved
    mark_resolved(swatch_actions, cpis_to_resolve, now_iso)

    # Deduplicate swatch actions (same cpi + unresolved)
    swatch_actions = deduplicate_actions(swatch_actions)

    # Deduplicate manual review actions (same cpi + unresolved)
    manual_review_actions = deduplicate_actions(manual_review_actions)

    # Write back updated queues
    if swatch_actions or os.path.isfile(swatch_queue_path):
        save_json_file(swatch_queue_path, swatch_actions)
    if manual_review_actions or os.path.isfile(manual_review_path):
        save_json_file(manual_review_path, manual_review_actions)

if __name__ == "__main__":
    main()
