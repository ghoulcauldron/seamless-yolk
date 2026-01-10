# Shopify Files + Metafields Pipeline  
## Capsule Asset Management System — Authoritative Documentation

> This document describes the **real, production-tested pipeline** as it exists today.  
> Nothing here is aspirational. Every step is present because it solved a real failure mode.

---

## 0. Core Philosophy

**Shopify is the source of truth.**  
Local files, manifests, and preflight checks represent *beliefs*, not reality.

Clients **will**:
- Upload images manually
- Reorder images
- Fix mistakes directly in Shopify
- Do this without telling us

Therefore:
- Shopify reality always overrides local assumptions
- Drift is expected and must be reconciled
- All adoption must record provenance
- All mutation must be gated and auditable

---

**NOTE:**  
Shopify-exported CSVs are now considered authoritative for *post-upload discovery*. Local enriched CSVs are not sufficient after client upload.

---

## Phase 0 — Capsule Initialization & Local Asset Generation

This phase happens **before any CSV enrichment and before Shopify is involved**.

### Capsule Folder Scaffold

Each capsule lives under:

```
capsules/<CAPSULE>/
├── inputs/
│   ├── ghosts/
│   ├── *_masterfile.csv
│   └── products_export_*.csv
│
├── outputs/
│   ├── swatches/
│   ├── api_jobs/
│   └── *.csv
│
├── manifests/
│   ├── images_manifest.jsonl
│   └── product_map.json
│
├── state/
│   └── product_state_<CAPSULE>.json
│
└── preflight_outputs/
```

---

### Swatch Creation (Manual, GUI‑Driven)

Tool:
```
swatch_creator/SwatchCropGUI.py
```

Inputs:
```
capsules/<CAPSULE>/inputs/ghosts/
```

Outputs (authoritative):
```
capsules/<CAPSULE>/outputs/swatches/
```

Notes:
- Swatches are **generated artifacts**
- No Shopify APIs are touched
- Registration happens later

---

## Phase 1 — Import Construction (Manifests + CSVs)

### Build Image Manifest

```
scripts/build_image_manifests.py
```

Creates or appends:
```
capsules/<CAPSULE>/manifests/images_manifest.jsonl
```

---

### Build Product Map (CPI → Shopify GID)

```
scripts/build_product_map.py
```

Outputs:
```
capsules/<CAPSULE>/manifests/product_map.json
```

This file is the backbone of all downstream operations.

---

### Preflight Validation

```
scripts/preflight_<capsule>.py
```

Purpose:
- Validate client inputs
- Identify missing assets
- Produce advisory outputs only

---

### Seed Product State

```
scripts/seed_product_state_from_preflight.py
```

Creates:
```
product_state_<CAPSULE>.json
```

Locked rules:
```
allowed_actions.size_guide_write = true
allowed_actions.collection_write = true
```

---

### Enrich Shopify Import CSV

```
scripts/enrich_shopify_import.py
```

Produces:
- enriched CSV
- anomalies CSV
- missing image rows CSV
- data gap report

---

### Combine Import CSVs

```
scripts/combine_shopify_imports.py
```

Outputs final client‑uploadable CSV.

---

## Phase 2 — Client Shopify Upload

Client uploads CSV.  
Images may be reordered or fixed manually.  
Drift begins.

---

## Phase 3 — Post‑Upload Inspection & Reconciliation

### Inspect Shopify Images

```
api/inspect_product_images.py
```

---

### Derive Look Images

```
api/derive_look_images_from_shopify.py
```

Writes to product state with provenance.

---

### Accessory & Handbag Image Semantics

For accessories (e.g. handbags, baskets, clutches):

- `derive_look_images_from_shopify` **may populate** `assets.look_images` in `product_state`
- This reflects **observed Shopify media**, not required editorial usage
- Write‑phase scripts (e.g. `metafields_writer.py`) remain gated by:
  - `allowed_actions.metafield_write`
  - `preflight.status`
  - product category (`is_accessory`)
- **No `look_image` metafield will be written for accessories**, even if `look_images` are present in state

This behavior is intentional and ensures Shopify reality is observed without implying mutation intent.

---

### Reconcile Capsule Assets

```
api/reconcile_capsule_assets.py
```

Produces:
- drift logs
- swatch queue
- manual review queue

---

## Preparing product_state for Write Operations

Before any authorized Shopify mutation steps, product_state must be aligned with current Shopify reality and enriched to enable downstream writers. This is accomplished by running the following scripts in order:

- `utils/enrich_product_state_with_tags.py`  
  Enriches product_state by adding tags and other relevant attributes. This step updates product_state to reflect the latest Shopify tagging and classification.

- `api/promote_static_allowed_actions.py`  
  Promotes static allowed_actions such as `collection_write` and `size_guide_write` to true, ensuring legacy capsules comply with the current authorization model.

These scripts do mutate product_state and are prerequisites for writers handling collections, size guides, and metafields.

---

## Phase 4 — Authorized Shopify Mutation

### Metafields

```
api/metafields_writer.py
```

Writes:
- swatch_image
- look_image

---

### Size Guides

```
api/size_guide_writer.py
```

Never gated.

---

### Smart Collections

```
scripts/smart_collections.py
```

- Now requires a Shopify-exported CSV as input.  
- That CSV is used for *style discovery only*.  
- Authorization comes exclusively from product_state.  
- This step must be preceded by `utils/enrich_product_state_with_tags.py` and `api/promote_static_allowed_actions.py` for legacy capsules.

---

## Phase 5 — QA & Launch Validation

```
qa_tracker.py
```

Produces capsule readiness report.

---

## Final Mental Model

- Shopify truth > local belief  
- Drift is normal  
- Adoption requires provenance  
- Mutation requires authorization  

---

## Utilities — State & Authorization Helpers

> These utilities exist to stabilize decision-making across the pipeline.  
> They are intentionally boring, deterministic, and side-effect free unless explicitly stated.

⸻

```
api/promote_static_allowed_actions.py
```

One-time (repeat-safe) state normalizer.

Promotes static allowed_actions that should always be true for any valid product:
	•	collection_write
	•	size_guide_write

This script:
	•	Operates only on product_state
	•	Does not inspect Shopify
	•	Does not infer asset completeness
	•	Is safe to re-run at any time

Use this to:
	•	Retrofit legacy capsules
	•	Align historical state with the current authorization model

---

```
utils/enrich_product_state_with_tags.py
```

Enriches product_state by adding tags and other Shopify-derived attributes.  
Run after product_state seeding and before any mutation steps.  
Mutates product_state to reflect current Shopify tagging and classification, enabling accurate authorization and downstream processing.

---

```
utils/shopify_csv_enricher_poc.py
```

Proof-of-concept tool for enriching Shopify-exported CSVs with additional computed fields.  
Does not mutate product_state or Shopify directly.  
Intended for exploratory or transitional use to improve CSV-based insights.

---

```
utils/state_gate.py
```

Read-only authorization evaluator for product actions.

Provides a single authoritative answer to:

“Is this action allowed right now for this product?”

This module:
	•	Never mutates state
	•	Never infers outcomes
	•	Never promotes or demotes products
	•	Evaluates permissions strictly from product_state.json

All writers (metafields, images, collections, size guides) should rely on this gate instead of duplicating authorization logic.

## Future Phase — Pipeline Consolidation (Planned)

The following components are **intentionally not implemented yet**.  
They represent a future consolidation phase once the current write‑phase logic has fully stabilized.

These are documented now to:
- Preserve architectural intent
- Prevent ad‑hoc orchestration from emerging
- Make future refactors deliberate instead of reactive

---

### capsule_write_phase.py (Write‑Phase Orchestrator)

**Purpose**  
A thin, deterministic coordinator responsible for executing the *write phase* of a capsule in the correct order.

This script would:
- Accept `--capsule`, `--dry-run`, and environment flags once
- Execute the approved write‑phase steps in sequence
- Halt immediately if a prerequisite step fails
- Produce a single consolidated execution log per capsule

**It would explicitly *not*:**
- Contain business logic
- Make authorization decisions
- Infer state or completeness
- Replace individual scripts

**Likely execution order:**
1. `api/promote_static_allowed_actions.py`
2. `utils/enrich_product_state_with_tags.py`
3. `api/smart_collections.py`
4. `api/size_guide_writer.py`
5. `api/publish_collections.py`

**When this should exist**  
Only after:
- Write‑phase semantics are stable
- Authorization rules are finalized
- Individual scripts are considered boring and trustworthy

This is an *operational convenience*, not a correctness primitive.

---

### state_authorization.py (Shared Authorization Helper)

**Purpose**  
A single authoritative evaluator for product and style‑level permissions derived from `product_state_<CAPSULE>.json`.

This module would answer questions like:
- “Is this product allowed to perform action X right now?”
- “Which styles are authorized for collection publication?”
- “Why was this operation denied?”

**This helper would:**
- Be read‑only
- Never mutate state
- Never infer outcomes
- Never promote or demote products
- Centralize all authorization semantics

**Consumers would include:**
- `smart_collections.py`
- `size_guide_writer.py`
- `publish_collections.py`
- Any future Shopify writers

**Why this does not exist yet**  
Some duplication is currently intentional:
- It keeps authorization logic visible
- It reveals mismatches between scripts
- It prevents premature abstraction

This helper should be introduced only when:
- Authorization rules are fully settled
- Copy‑pasted logic becomes risky rather than informative

---

### Design Principle (Important)

> **Correctness before elegance.  
> Semantics before orchestration.**

These future components should reduce friction — not obscure logic.

If introduced too early, they would:
- Lock in incorrect assumptions
- Hide important differences
- Make debugging harder

If introduced at the right time, they will be:
- Small
- Obvious
- Boring
- Safe

---

### Future Refinement — Accessory Look Image Semantics

`derive_look_images_from_shopify` may be refined to better express accessory intent.

Possible future improvements:
- Skip look‑image enrichment entirely for `is_accessory == true` products
- Or annotate `assets.look_images` with `required=false` to distinguish observation from requirement

This is **not implemented intentionally** to avoid destabilizing the current reconciliation and write‑phase pipeline.

---

## NOTES

**Runbooks**  
Where we can go next (optional)  
	•	Convert runbooks into Makefile targets  
	•	Add a single capsule doctor command  
	•	Generate machine-readable pipeline graph

**Update seeding script to all-inclusive: tags and perhaps other attribs.**

**If this README and the code disagree, the README wins.**
---</file>