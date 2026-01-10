import argparse
import csv
import json
import logging
import os
from collections import defaultdict

def load_product_state(capsule):
    filename = f"capsules/{capsule}/state/product_state_{capsule}.json"
    if not os.path.isfile(filename):
        logging.error(f"Product state file '{filename}' does not exist.")
        return None
    with open(filename, "r", encoding="utf-8") as f:
        try:
            state = json.load(f)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON from '{filename}': {e}")
            return None
    return state

def save_product_state(capsule, state):
    filename = f"capsules/{capsule}/state/product_state_{capsule}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def extract_tags_from_csv(source_csv):
    tags_per_handle = defaultdict(set)
    if not os.path.isfile(source_csv):
        logging.error(f"Source CSV file '{source_csv}' does not exist.")
        return None
    with open(source_csv, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        if "Handle" not in reader.fieldnames or "Tags" not in reader.fieldnames:
            logging.error("CSV must have 'Handle' and 'Tags' columns.")
            return None
        for row in reader:
            handle = row["Handle"].strip()
            tags_str = row["Tags"].strip()
            if not handle:
                continue
            if tags_str:
                tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                tags_per_handle[handle].update(tags)
    return tags_per_handle

def merge_tags_into_state(state, tags_per_handle):
    if "products" not in state or not isinstance(state["products"], dict):
        logging.error("Invalid product state: missing or invalid 'products' dictionary.")
        return False

    changes_made = False
    for handle, new_tags in tags_per_handle.items():
        product = state["products"].get(handle)
        if product is None:
            logging.info(f"{handle}: SKIP (handle not in product state)")
            continue
        if not isinstance(product, dict):
            logging.info(f"{handle}: SKIP (product entry is not a dict)")
            continue
        existing_tags = product.get("tags", [])
        if not isinstance(existing_tags, list):
            logging.info(f"{handle}: SKIP (existing tags is not a list)")
            continue
        existing_tag_set = set(existing_tags)
        combined_tags = existing_tag_set | new_tags
        if combined_tags == existing_tag_set:
            logging.info(f"{handle}: NOOP (tags unchanged)")
        else:
            # Update tags preserving original order of existing tags, then add new ones
            updated_tags = existing_tags[:]
            for tag in new_tags:
                if tag not in existing_tag_set:
                    updated_tags.append(tag)
            product["tags"] = updated_tags
            changes_made = True
            logging.info(f"{handle}: ADOPT (tags updated)")
    return changes_made

def main():
    parser = argparse.ArgumentParser(description="Enrich product state with tags from Shopify CSV export.")
    parser.add_argument("capsule", help="Capsule name to identify product_state_{capsule}.json")
    parser.add_argument("--source-csv", required=True, help="Shopify-exported CSV file path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    state = load_product_state(args.capsule)
    if state is None:
        return

    tags_per_handle = extract_tags_from_csv(args.source_csv)
    if tags_per_handle is None:
        return

    changes_made = merge_tags_into_state(state, tags_per_handle)

    if changes_made:
        save_product_state(args.capsule, state)
        logging.info(f"Product state saved to product_state_{args.capsule}.json")
    else:
        logging.info("No changes made; product state not saved.")

if __name__ == "__main__":
    main()
