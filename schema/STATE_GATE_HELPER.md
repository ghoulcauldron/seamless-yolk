State-Gate Helper Contract (v1)

Purpose

The state-gate helper is a shared utility whose sole responsibility is to:

Answer the question:
“Given the current recorded state of a product, is this action allowed right now?”

It does not:
	•	Modify state
	•	Advance stages
	•	Record overrides
	•	Write to Shopify
	•	Infer outcomes

It is a policy reader, not a controller.

⸻

Inputs

Required Inputs
	1.	State file

capsules/{CAPSULE}/state/product_state_{CAPSULE}.json


	2.	Product identifier
One of:
	•	handle (preferred)
	•	cpi (optional fallback)
	3.	Action being evaluated
One of a fixed, known set (see below).

⸻

Supported Actions (v1)

The helper must support evaluating only these actions in v1:

Action name	Meaning
include_in_import_csv	May this product be included in a Shopify CSV import
image_upsert	May images be uploaded or linked
metafield_write	May metafields be written via API
collection_write	May collections be created or updated

These map 1:1 to allowed_actions in state.

⸻

Output

Canonical Response Shape

{
  "allowed": true,
  "reason": null,
  "state_snapshot": {
    "current_stage": "PREFLIGHT_COMPLETE",
    "preflight_status": "GO",
    "image_state": "IMAGE_READY"
  }
}

If not allowed:

{
  "allowed": false,
  "reason": "preflight_status=NO-GO",
  "state_snapshot": {
    "current_stage": "PREFLIGHT_COMPLETE",
    "preflight_status": "NO-GO",
    "image_state": "IMAGE_INCOMPLETE"
  }
}


⸻

Decision Rules (v1)

Primary rule (authoritative)

allowed = product.allowed_actions[action] == true

Nothing overrides this.

⸻

Secondary context (explanatory only)

The helper may include contextual fields for logging or debugging:
	•	preflight_status
	•	client_recommendation
	•	image_state
	•	ws_buy

These do not affect the allow/deny decision in v1.

⸻

Required Behavior

The helper must:
	•	Be deterministic
	•	Never mutate the state file
	•	Never infer missing data
	•	Fail loudly on unknown actions
	•	Fail loudly on missing product entries

⸻

Forbidden Behavior (explicit)

The helper must not:
	•	Change current_stage
	•	Set IMPORTED
	•	Accept anomalies
	•	Promote products
	•	Lock products
	•	Write override flags
	•	Infer Shopify outcomes

Those belong to post-import inference or promotion orchestration, not here.

⸻

Example Usage

CLI / Script Context

gate = StateGate("capsules/S226/state/product_state_S226.json")

decision = gate.can(
    handle="arp-dress-black",
    action="metafield_write"
)

if not decision.allowed:
    print(f"SKIPPED: {decision.reason}")


⸻

Logging-Only Enforcement (current phase)

Scripts log and skip, they do not error:

⏭  metafields_writer: skipped basket-clutch-pale-blush
   reason: image_upsert not allowed (IMAGE_INCOMPLETE)


⸻

Relationship to Future Phases

v1 (now)
	•	Read-only
	•	Advisory + gating
	•	Script-local enforcement

v2 (later)
	•	Promotion ladder
	•	Locking semantics
	•	Override tracking
	•	Mutation allowed via orchestrator

This contract is intentionally minimal and stable so it can be imported everywhere without refactor churn.