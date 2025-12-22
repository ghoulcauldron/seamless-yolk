#!/usr/bin/env python3

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def utc_now_iso_z() -> str:
    # timezone-aware UTC timestamp (no deprecated utcnow)
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_csv_handles(csv_path: Path) -> set[str]:
    df = pd.read_csv(csv_path, low_memory=False)
    if "Handle" not in df.columns:
        raise ValueError(f"CSV missing required column 'Handle': {csv_path}")
    return set(df["Handle"].dropna().astype(str).unique())


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        raise FileNotFoundError(f"State file not found: {state_path}")
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_state(state_path: Path, state: dict) -> None:
    # Do not sort keys: preserve human-readable ordering
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post-import inference: update product_state.json based on manual Shopify import CSVs (no API)."
    )
    parser.add_argument("--capsule", required=True, help="Capsule code (e.g. S226)")
    parser.add_argument(
        "--combined-csv",
        required=True,
        help="Path to combined import CSV (import_ready + missing_image_rows).",
    )
    parser.add_argument(
        "--anomalies-csv",
        default=None,
        help="Optional path to anomalies CSV (only used if --include-anomalies is set).",
    )
    parser.add_argument(
        "--include-anomalies",
        action="store_true",
        help="If set, treat anomalies CSV handles as imported (client approved anomalies upload).",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Optional explicit path to product_state_{CAPSULE}.json. Defaults to capsules/{CAPSULE}/state/product_state_{CAPSULE}.json",
    )

    args = parser.parse_args()

    capsule = args.capsule
    combined_csv = Path(args.combined_csv)

    anomalies_csv = Path(args.anomalies_csv) if args.anomalies_csv else None
    if args.include_anomalies and anomalies_csv is None:
        raise ValueError("--include-anomalies was provided but --anomalies-csv is missing.")
    if args.include_anomalies and anomalies_csv and not anomalies_csv.exists():
        raise FileNotFoundError(f"Anomalies CSV not found: {anomalies_csv}")

    state_path = (
        Path(args.state_file)
        if args.state_file
        else Path(f"capsules/{capsule}/state/product_state_{capsule}.json")
    )

    state = load_state(state_path)

    # Basic schema sanity checks
    if state.get("schema_version") != "1.0":
        raise ValueError(f"Unsupported schema_version in state: {state.get('schema_version')}")
    if state.get("capsule") != capsule:
        raise ValueError(f"State capsule mismatch: state={state.get('capsule')} args={capsule}")
    if "products" not in state or not isinstance(state["products"], dict):
        raise ValueError("State file missing top-level 'products' object.")

    # Determine imported handle sets
    combined_handles = read_csv_handles(combined_csv)
    anomaly_handles = set()
    if args.include_anomalies and anomalies_csv:
        anomaly_handles = read_csv_handles(anomalies_csv)

    # Imported handle set (contract definition)
    imported_handles = set(combined_handles)
    if args.include_anomalies:
        imported_handles |= anomaly_handles

    now = utc_now_iso_z()

    updated = 0
    already_imported = 0
    ineligible_skipped = 0
    imported_via_combined = 0
    imported_via_anomalies = 0
    anomaly_accepted_count = 0

    for handle_key, rec in state["products"].items():
        # products are keyed by handle; still honor record["handle"] if present
        handle = rec.get("handle") or handle_key

        # Rule 1: Eligibility gate
        imp = rec.get("import", {})
        if imp.get("eligible") is False:
            # Ignore entirely even if present in CSVs
            if handle in imported_handles:
                ineligible_skipped += 1
            continue

        # Only mutate if handle inferred imported
        if handle not in imported_handles:
            continue

        # Rule 4: Idempotency — if already imported, do nothing
        if imp.get("imported") is True:
            already_imported += 1
            continue

        # Rule 2: Import detection + stage transition
        if handle in combined_handles:
            source = "combined_csv"
            imported_via_combined += 1
        elif args.include_anomalies and handle in anomaly_handles:
            source = "anomalies_csv"
            imported_via_anomalies += 1
        else:
            # Should not happen (handle is in imported_handles union), but keep safe
            source = "combined_csv"
            imported_via_combined += 1

        rec.setdefault("import", {})
        rec["import"]["imported"] = True
        rec["import"]["imported_at"] = now
        rec["import"]["import_source"] = source

        # Rule 3: Anomaly acceptance (only for NO-GO imported via anomalies_csv)
        pre = rec.get("preflight", {})
        if source == "anomalies_csv" and pre.get("status") == "NO-GO":
            rec["import"]["anomaly_accepted"] = True
            anomaly_accepted_count += 1
        else:
            # Do not infer acceptance otherwise
            rec["import"]["anomaly_accepted"] = imp.get("anomaly_accepted", False) or False

        # Promotion transition
        rec.setdefault("promotion", {})
        rec["promotion"]["stage"] = "IMPORTED"
        rec["promotion"]["last_transition_at"] = now

        updated += 1

    # Update top-level generated_at
    state["generated_at"] = now

    save_state(state_path, state)

    print("✅ Post-import inference complete.")
    print(f"   State file: {state_path}")
    print(f"   Imported handles inferred: {len(imported_handles)}")
    print(f"   Products updated to IMPORTED: {updated}")
    print(f"   Already imported (no changes): {already_imported}")
    if args.include_anomalies:
        print(f"   Imported via combined_csv: {imported_via_combined}")
        print(f"   Imported via anomalies_csv: {imported_via_anomalies}")
        print(f"   anomaly_accepted set true: {anomaly_accepted_count}")
    if ineligible_skipped:
        print(f"   Ineligible products present in CSVs but ignored (eligible=false): {ineligible_skipped}")


if __name__ == "__main__":
    main()