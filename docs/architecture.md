# Capsule Asset Management System — Architecture

This document defines the **authoritative architecture** of the Shopify Files + Metafields
pipeline. It explains *why* the system exists, *what problems it solves*, and the
non-negotiable design principles that govern every script.

If a script behaves differently than described here, the script is wrong.

---

## 1. Core Problem

We are not the owner of truth.

Clients:
- Upload images manually
- Fix mistakes directly in Shopify
- Reorder images
- Add assets without notifying us

Local manifests, CSVs, and preflight checks represent **beliefs**, not reality.

**Shopify is the source of truth.**

The system must:
- Detect drift between belief and reality
- Adopt Shopify truth safely
- Record provenance for every adoption
- Mutate Shopify only when explicitly authorized

---

## 2. Design Principles (Non-Negotiable)

### 2.1 Shopify Overrides Local Belief

If Shopify has an asset and local state does not:
- Shopify wins
- Local state must be updated to reflect reality

### 2.2 Evidence ≠ Action

The system is deliberately split into layers:

| Layer | Purpose |
|-----|--------|
| Inspection | Observe Shopify reality |
| Derivation | Translate reality into structured candidates |
| Reconciliation | Decide what to adopt and why |
| Authorization | Explicitly permit mutation |
| Mutation | Write to Shopify |

No script may collapse these responsibilities.

## 2.5 Canonical Data Flow (State ⇄ Shopify ⇄ Outputs)

The system operates as a **closed-loop reconciliation engine** between three domains:

1. **Shopify (Truth)**
2. **Local State (Authorization + Belief)**
3. **Outputs (Evidence + Intent)**

No script is allowed to bypass this loop.

---

### 2.5.1 High-Level Flow Diagram

```
                ┌──────────────────────────┐
                │          SHOPIFY         │
                │  (Source of Truth)       │
                │                          │
                │  • Products              │
                │  • Images                │
                │  • Collections           │
                │  • Metafields            │
                └───────────▲──────────────┘
                            │
                  INSPECTION │  (read-only)
                            │
        ┌───────────────────┴───────────────────┐
        │            DERIVATION                  │
        │  Scripts translate Shopify reality     │
        │  into structured candidates            │
        │                                        │
        │  • inspect_*                           │
        │  • derive_*                            │
        └───────────▲──────────────┬─────────────┘
                    │              │
        RECONCILIATION│              │ EVIDENCE
                    │              │
        ┌───────────┴──────────┐   │   ┌──────────────────────────┐
        │     PRODUCT STATE    │◄───┼───│         OUTPUTS          │
        │  (Authorization +    │       │  (Append-only)            │
        │   Local Belief)      │       │                            │
        │                      │       │  • Drift logs              │
        │  • allowed_actions   │       │  • API job logs            │
        │  • asset provenance  │       │  • Review CSVs             │
        │  • preflight status  │       │  • Audit artifacts         │
        └───────────▲──────────┘       └───────────▲───────────────┘
                    │                              │
         AUTHORIZATION│                              │ OBSERVABILITY
                    │                              │
                ┌───┴───────────────┐
                │      MUTATION     │
                │  (Write to        │
                │   Shopify)        │
                │                   │
                │  • metafields     │
                │  • collections    │
                │  • images         │
                └───────────────────┘
```

---

### 2.5.2 Domain Responsibilities (Strict)

#### Shopify
- The **only authoritative record** of what actually exists
- Can change at any time, without notice
- Must never be “trusted” indirectly

#### Product State (`product_state_<CAPSULE>.json`)
- The **only authorization surface**
- Determines *whether* writes are allowed — never *what* to write
- Must be explicitly enriched (never inferred)

Examples:
- `allowed_actions.collection_write`
- `allowed_actions.size_guide_write`
- Known asset provenance
- Adopted tags from Shopify (post-upload)

If it’s not in state, it doesn’t exist **for mutation purposes**.

#### Outputs (`capsules/<CAPSULE>/outputs/`)
- **Evidence, not authority**
- Append-only
- Used for:
  - Human review
  - Auditability
  - Recovery
- Never read as inputs for mutation decisions

Examples:
- `collections_<CAPSULE>.json`
- Drift reports
- Review CSVs sent to clients

---

### 2.5.3 Directional Rules (Non-Negotiable)

| Flow | Allowed | Notes |
|------|---------|-------|
| Shopify → Derivation | ✅ | Read-only |
| Derivation → State | ❌ | Must go through reconciliation |
| Shopify → State | ❌ | Never direct |
| State → Mutation | ✅ | Only if explicitly authorized |
| Outputs → State | ❌ | Outputs are evidence only |
| Outputs → Mutation | ❌ | Forbidden |
| Shopify → Outputs | ✅ | Inspection logs |

---

### 2.5.4 Why This Matters

This architecture guarantees:
- No silent writes
- No inferred permissions
- No accidental mutation
- Safe re-runs
- Deterministic behavior even under drift

If a script reads Shopify and writes Shopify without consulting state, it violates architecture and must be corrected.

---

## 3. Drift as a First-Class Concept

**Drift is expected, not exceptional.**

Drift examples:
- Hero image uploaded after CSV import
- Ghost image reordered
- Swatch created manually outside system

The system must:
- Detect drift
- Log drift
- Adopt drift when safe
- Escalate when ambiguous

---

## 4. Capsule Structure (Canonical)

Each capsule lives under:

capsules//
├── inputs/              # Client-provided inputs
├── outputs/             # Evidence, drift logs, action queues
├── assets/              # Generated artifacts (swatches, ghosts)
├── manifests/           # Canonical manifests (append-only)
├── state/               # Product state (authoritative local belief)
└── preflight_outputs/   # Advisory checks

---

## 5. Product State (`product_state_<CAPSULE>.json`)

This is the **authorization surface** of the system.

It records:
- Known assets (local + adopted)
- Provenance of each asset
- Preflight results
- Allowed actions

### 5.1 What State Is

- A *living snapshot* of our current belief
- Updated by reconciliation, never by inspection
- Required input for all mutation scripts

### 5.2 What State Is NOT

- A mirror of Shopify
- A manifest replacement
- A write-through cache

---

## 6. Asset Adoption Model

Every adopted asset must record:

```json
{
  "media_gid": "gid://shopify/MediaImage/…",
  "source": "shopify_existing",
  "derived_from": "inspect_product_images",
  "selection_reason": "FILENAME_MATCH_HERO_IMAGE",
  "derived_at": "ISO-8601"
}

No silent adoption is allowed.

⸻

7. Authorization Model

Mutation scripts never infer permission.

They require:
	•	Explicit flags in product_state
	•	Presence of required assets
	•	Deterministic selection (no heuristics)

If authorization is missing → skip with log.

⸻

8. Mutation Guarantees

All Shopify writes must be:
	•	Idempotent
	•	Scoped (capsule + CPI)
	•	Logged (append-only)
	•	Safe to re-run

⸻

9. Script Taxonomy

Category
Examples
Evidence
inspect_product_images
Derivation
derive_look_images_from_shopify
Reconciliation
reconcile_capsule_assets
Registration
register_created_swatches
Promotion
promote_state_swatches_to_manifest
Mutation
metafields_writer, size_guide_writer
Generation
swatch_creator (external GUI)

⸻

---

# `docs/runbooks/`

Below are **three runbooks**, which you can split into separate files or keep grouped.

---

## `docs/runbooks/capsule_setup.md`

```md
# Runbook — Capsule Setup (Pre-Shopify)

This runbook covers everything that happens **before the client uploads to Shopify**.

---

## 1. Create Capsule Scaffold

scripts/create_capsule_scaffold.py

Creates folder structure under `capsules/<CAPSULE>/`.

---

## 2. Generate Swatches (Manual)

swatch_creator/SwatchCropGUI.py

Inputs:
- `inputs/ghosts/`

Outputs:
- `assets/swatches/`

⚠️ This does NOT update state or manifests.

---

## 3. Build Image Manifest

scripts/build_image_manifests.py

Appends to:

manifests/images_manifest.jsonl

---

## 4. Build Product Map

scripts/build_product_map.py

Outputs:

manifests/product_map.json

Required for all downstream scripts.

---

## 5. Preflight Validation

scripts/preflight_.py

Produces advisory outputs only.

---

## 6. Seed Product State

scripts/seed_product_state_from_preflight.py

Creates:

state/product_state_.json

---

## 7. Enrich Shopify Import CSV

scripts/enrich_shopify_import.py
scripts/combine_shopify_imports.py

Deliver final CSV to client.

⸻

</file>
