Post-Import Inference Script Contract

Version: 1.0
Status: Locked once committed

⸻

1. Purpose

The post-import inference script exists to advance product state after a manual Shopify import, based solely on what was attempted, not on Shopify verification.

It is the only mechanism allowed to transition products into the IMPORTED stage.

⸻

2. Scope (Strict)

The script infers state.
It does not enrich, validate, fix, or verify data.

Explicitly out of scope

The script must never:
	•	Call the Shopify API
	•	Re-run enrichment logic
	•	Inspect the filesystem
	•	Modify CSV files
	•	Fix anomalies
	•	Decide whether an import should have happened
	•	Reassign image positions
	•	Generate placeholders
	•	Write metafields or images

⸻

3. Inputs (Authoritative)

The script accepts only the following inputs:

Required
	1.	Combined Import CSV
Output of:

import_ready.csv + missing_image_rows.csv


	2.	Product State JSON

capsules/{CAPSULE}/state/product_state_{CAPSULE}.json


	3.	Capsule code

--capsule S226



Optional
	4.	Anomalies CSV

poc_shopify_anomalies_*.csv


	5.	Explicit flag

--include-anomalies



If --include-anomalies is not passed, anomalies are assumed not imported.

⸻

4. Definitions

Imported Handle

A handle is considered imported if:
	•	It appears in the combined import CSV, OR
	•	It appears in the anomalies CSV and --include-anomalies is provided

No other inference is permitted.

⸻

5. Allowed State Mutations

The script may mutate only the following fields:

import.imported
import.imported_at
import.import_source
import.anomaly_accepted
promotion.stage
promotion.last_transition_at

All other fields are read-only.

⸻

6. Inference Rules (Normative)

Rule 1 — Eligibility

If:

import.eligible = false

The product is ignored entirely, even if present in CSVs.

(Example: WS Buy products.)

⸻

Rule 2 — Import Detection

If a product’s handle is present in the imported handle set:
	•	Set:

import.imported = true
import.imported_at = <UTC timestamp>
import.import_source = "combined_csv" | "anomalies_csv"
promotion.stage = "IMPORTED"
promotion.last_transition_at = <UTC timestamp>


⸻

Rule 3 — Anomaly Acceptance

If:
	•	Product preflight status was NO-GO
	•	AND the product was imported via anomalies CSV

Then:

import.anomaly_accepted = true

This indicates explicit client approval, not issue resolution.

⸻

Rule 4 — Idempotency

If:

import.imported = true

The product must not be modified again by this script.

Timestamps must not be overwritten.

⸻

7. Image Expectations (Non-Verifying)

The script may read image expectations but must not verify them.

Permitted behavior:
	•	Read image count / max position from CSV rows
	•	Preserve existing images.expected

Forbidden behavior:
	•	Verifying Shopify image existence
	•	Re-deriving image positions
	•	Healing missing images

⸻

8. Promotion Semantics

After the script runs:
	•	promotion.stage = IMPORTED is authoritative
	•	Downstream scripts may safely assume:
	•	The Shopify product exists
	•	Enrichment must not re-run
	•	Image/metafield utilities may proceed if state allows

⸻

9. Failure Modes

Allowed failures
	•	Missing anomalies CSV when --include-anomalies is false
	•	Products in state but not in CSVs (no mutation)

Disallowed failures
	•	Partial state writes
	•	Silent mutation of non-imported products
	•	Schema drift
	•	Implicit approvals

⸻

10. Outputs

The script produces one output only:
	•	Updated product_state_{CAPSULE}.json

Optional console output:
	•	Count of imported products
	•	Count of anomaly imports
	•	List of skipped (already imported) handles

No CSVs are written.

⸻

11. Guarantees to Downstream Systems

After successful execution:
	•	product_state.json is the single source of truth
	•	Import status is authoritative
	•	Anomalies are explicitly accepted or not
	•	Utilities can be made state-aware safely

⸻

12. Non-Goals (Explicit)

This script is not:
	•	A Shopify validator
	•	A reconciliation engine
	•	A fixer of historical mistakes
	•	A replacement for preflight
	•	A gatekeeper for client decisions

⸻

13. Contract Stability
	•	This contract is versioned
	•	Changes require:
	•	Schema version bump
	•	Explicit migration step

⸻

Summary (One Sentence)

The post-import inference script exists solely to record what the business chose to upload, advance product state accordingly, and make that decision authoritative for all downstream automation.

⸻