Shopify Files + Metafields Pipeline

Canonical Workflow & Invariants

This document records the final, correct implementation of Shopify file uploads and metafield attachment, as discovered through iterative debugging.
Deviations from this contract will silently fail or regress.

⸻

High-level overview

This project manages product image uploads and metafield attachment for a capsule-based catalog using Shopify’s GraphQL API.

The system is intentionally split into three phases:
	1.	Preflight / Enrichment (CSV generation)
	2.	Import (manual Shopify CSV upload)
	3.	Post-import API jobs (files + metafields)

This README focuses on Phase 3, which was the source of repeated regressions until the correct Shopify contract was enforced.

⸻

Core invariants (DO NOT VIOLATE)

1. There is exactly one supported way to create Shopify Files

All files must be created via:

stagedUploadsCreate
→ PUT raw bytes (NO HEADERS)
→ fileCreate

This logic lives in:

api/shopify_client.py
└── upload_file_from_path()

No other file creation methods are allowed.

⸻

2. PUT means PUT — no headers, ever

Shopify staged upload URLs are cryptographically signed.

They allow only:
	•	HTTP PUT
	•	Raw file bytes
	•	NO custom headers

Violations cause errors like:

MalformedSecurityHeader
Header must be signed
x-goog-acl

Correct implementation:

req = Request(
    method="PUT",
    url=upload_url,
    data=file_bytes
)
prepared = req.prepare()
prepared.headers.clear()
session.send(prepared)

If headers are present, Shopify will reject the upload.

⸻

3. fileCreate.contentType determines the class of file

This was the key breakthrough.

contentType	Resulting GID	Valid for image metafields
"FILE"	GenericFile	❌ NO
"IMAGE"	MediaImage	✅ YES

If you want to attach a file to an image-only metafield, you MUST use contentType: "IMAGE".

Correct mutation (locked):

mutation fileCreate($files: [FileCreateInput!]!) {
  fileCreate(files: [{
    alt: "...",
    contentType: IMAGE,
    originalSource: "..."
  }]) {
    files { id fileStatus }
  }
}

Using "FILE" will upload successfully but fail at metafield attachment time.

This is why earlier runs appeared to “work” but silently broke swatches.

⸻

4. Do NOT assert GID types

Shopify may return:
	•	gid://shopify/MediaImage/...
	•	gid://shopify/GenericFile/...
	•	gid://shopify/File/...

All are valid depending on context.

Never assert GID prefixes.
The only valid check is whether Shopify accepts the GID for the intended operation.

Earlier assertions caused false failures and masked the real issue.

⸻

Metafields: what actually works

Image metafields (file_reference)
	•	Must reference MediaImage
	•	GenericFile will be rejected with:

Value must be one of the following file types: Image



Confirmed working flow
	1.	Upload image via upload_file_from_path()
	2.	Wait until file is READY
	3.	Attach returned GID directly to metafield
	4.	Shopify validates type and accepts

⸻

State-driven gating (why this exists)

All API writes are gated by product state to prevent accidental mutation.

State is generated via:

scripts/seed_product_state_from_preflight.py
→ product_state_<CAPSULE>.json

Each product includes:

"allowed_actions": {
  "metafield_write": true,
  "image_upsert": true,
  "collection_write": false,
  "include_in_import_csv": false
}

The gate is enforced by:

utils/state_gate.py

Gate behavior (locked)
	•	Missing or invalid allowed_actions → DENY, not crash
	•	No mutation occurs unless explicitly allowed
	•	Debug logs always emit a per-CPI summary

⸻

Debugging correctly (and safely)

CPI-scoped runs (required)

Always debug using CPI scoping, never full capsule runs:

python -m api.metafields_writer \
  --capsule S226 \
  --cpis 2003-000182 \
  --verbose

This guarantees:
	•	Single product mutation
	•	Deterministic output
	•	No collateral damage

⸻

Expected verbose output (healthy)

[CPI] 2003-000182 | stage=PRE_FLIGHT | metafield_write=True
> Uploading swatch image...
> Waiting for file gid://shopify/MediaImage/... to be READY
> File is READY
Linked swatch_image
[CPI SUMMARY] swatch=uploaded | look=uploaded

If you see:
	•	GenericFile + metafield error → wrong contentType
	•	Upload succeeds but metafield missing → wrong file class
	•	PUT fails → headers leaked

⸻

Explicitly forbidden (do not reintroduce)

❌ Remote URL uploads
❌ Shopify CDN URLs as sources
❌ Header injection on staged PUT
❌ GID prefix assertions
❌ Non-gated API writes
❌ Full capsule runs during debugging

These were all sources of regression.

⸻

Final mental model
	•	Upload correctness ≠ metafield correctness
	•	Shopify will happily store unusable files
	•	File class matters more than file content
	•	The only safe system is one with:
	•	Locked contracts
	•	Gated writes
	•	CPI-scoped execution
	•	Explicit logging

⸻

Status

✅ Upload transport fixed
✅ File classification fixed
✅ Metafield attachment stable
✅ State gating enforced
✅ Regressions understood and prevented

This pipeline is now production-safe.