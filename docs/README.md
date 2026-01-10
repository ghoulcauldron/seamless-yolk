# Shopify Files + Metafields Pipeline  
## Capsule Asset Management System — Final, Locked Documentation

This document is the **authoritative, completionist reference** for the Seamless‑Yolk system as it exists today.

It captures:
- The **actual contracts** we discovered through ~10+ hours of real debugging
- The **correct mental model** for Shopify Files, Media, and Metafields
- The **end‑to‑end capsule lifecycle**, including scripts that exist today (even if some are only partially formalized)
- The **reasons past attempts failed**, so we do not regress

This README is intentionally verbose. Nothing here is theoretical.

---

## 0. Core Philosophy (Read First)

### Shopify is the Source of Truth  
Local manifests and preflight checks are **beliefs**, not facts.

Clients **will**:
- Upload images manually
- Reorder images
- Fix mistakes directly in Shopify
- Do this without telling us

Therefore:
- **Shopify reality always overrides local assumptions**
- Our system must be able to *inspect*, *adopt*, *reconcile*, and *record provenance*
- Drift is expected, not exceptional

---

## 1. High‑Level System Phases

The system is intentionally split into **four phases**:

1. **Preflight & Local Beliefs**
2. **Manual Shopify Import**
3. **Post‑Import Inspection & Reconciliation**
4. **Authorized Mutation (Files, Metafields, Collections)**

Only Phase 4 mutates Shopify.

---

## 2. Canonical Folder Structure

```
capsules/<CAPSULE>/
├── inputs/                      # Client‑provided inputs
│   ├── *_masterfile.csv
│   ├── products_export_*.csv
│   ├── ghostFileNames.txt
│   └── modelFileNames.txt
│
├── assets/
│   ├── ghosts/                  # Ghost images (local)
│   ├── editorials/              # Editorial images (local)
│   └── swatches/                # Swatches (generated locally)
│
├── manifests/
│   ├── product_map.json         # CPI → Shopify Product GID
│   └── images_manifest.jsonl    # Canonical asset index (append‑only)
│
├── state/
│   └── product_state_<CAPSULE>.json
│
├── outputs/
│   ├── inspect_images_<CAPSULE>.json
│   ├── asset_drift_<CAPSULE>.jsonl
│   ├── actions_swatch_queue_<CAPSULE>.jsonl
│   └── manual_review_queue_<CAPSULE>.jsonl
│
└── preflight_outputs/
    ├── preflight_*_internal.json
    └── preflight_*_client_advisory.csv
```

---

## 3. Phase 1 — Preflight & State Seeding

### `scripts/preflight_<capsule>.py`
**Purpose**
- Validate client‑provided files
- Simulate image completeness
- Identify missing ghosts, editorials, swatches
- Produce GO / NO‑GO advisory

**Important**
- This phase **does not** inspect Shopify
- Output reflects *only what the client gave us*

---

### `scripts/seed_product_state_from_preflight.py`
**Purpose**
- Create `product_state_<CAPSULE>.json`
- Encode initial beliefs and permissions

Each product includes:
- CPI
- Handle
- Preflight status
- Promotion stage
- Allowed actions

#### Locked rule
These are **always true** once a product exists:
```
allowed_actions.size_guide_write = true
allowed_actions.collection_write = true
```

Image completeness must **never** block size guides or collections.

---

## 4. Phase 2 — Local Asset Generation

### Swatch Creation (External, Siloed)
Directories:
- `swatch_pipeline_pre_api/`
- `swatch_pipeline_ml/`

**Purpose**
- Generate swatches from ghost images
- Output files into `assets/swatches/`

The main system:
- Does **not** generate swatches
- Only registers and promotes them

---

### `scripts/build_image_manifests.py`
**Purpose**
- Build / append `images_manifest.jsonl`
- Canonical index of *known* assets

This manifest is what mutation scripts trust.

---

## 5. Phase 3 — Shopify Inspection & Drift Detection

### `api/inspect_product_images.py`
**READ‑ONLY**

**Purpose**
- Query Shopify product media
- Identify hero candidates
- Capture Shopify reality

**Output**
- `inspect_images_<CAPSULE>.json`

No state mutation. No inference. No adoption.

---

### `api/derive_look_images_from_shopify.py`
**Purpose**
- Select the canonical hero image
- Write into `product_state.assets.look_images`

#### Selection rules (locked):
1. Filename match (`hero_image`)
2. Positional fallback
3. Manual override if ambiguous

Each adoption records:
- Source
- Reason
- Timestamp
- Filename (if applicable)

---

### `api/reconcile_capsule_assets.py`
**Purpose**
- Compare:
  - Preflight beliefs
  - Local state
  - Shopify inspection
- Adopt missing assets
- Flip authorization gates when conditions are met
- Record drift history

**Outputs (append‑only, deduped):**
- `asset_drift_<CAPSULE>.jsonl`
- `actions_swatch_queue_<CAPSULE>.jsonl`
- `manual_review_queue_<CAPSULE>.jsonl`

This is where **belief becomes authority**.

---

## 6. Swatch Registration & Promotion

### `api/register_created_swatches.py`
**Purpose**
- Detect newly created swatches
- Register them into product state
- Attach provenance

No Shopify calls.

---

### `api/promote_state_swatches_to_manifest.py`
**Purpose**
- Promote registered swatches into `images_manifest.jsonl`
- Normalize schema
- Prevent duplicates

This is required before metafield writes.

---

## 7. Phase 4 — Authorized Shopify Mutation

### Core Invariants (DO NOT VIOLATE)

#### 1. One and only one way to upload files

All Shopify Files **must** be created via:

```
stagedUploadsCreate
→ PUT raw bytes (NO HEADERS)
→ fileCreate
```

Implemented in:
```
api/shopify_client.py
└── upload_file_from_path()
```

No alternatives allowed.

---

#### 2. PUT means PUT — no headers, ever

Shopify staged upload URLs are cryptographically signed.

They allow:
- PUT
- Raw bytes
- **No headers**

Any headers = silent failure.

---

#### 3. `fileCreate.contentType` is critical

| contentType | Resulting GID | Valid for image metafields |
|------------|--------------|-----------------------------|
| FILE       | GenericFile  | ❌ NO |
| IMAGE      | MediaImage   | ✅ YES |

**Swatches and look images MUST use `IMAGE`.**

This was the primary breakthrough.

---

#### 4. Never assert GID prefixes

Shopify may return:
- `MediaImage`
- `GenericFile`
- `File`

Assertions caused false failures.

Only Shopify validation matters.

---

### `api/metafields_writer.py`
**The only script allowed to mutate Shopify**

Writes:
- `swatch_image`
- `look_image`
- (future: size guides, collections)

**Safety guarantees**
- CPI‑scoped execution
- State‑gated writes
- Idempotent (NOOP if already correct)
- Append‑only logs

---

### Debugging Rule (Mandatory)

Always run CPI‑scoped:

```
python -m api.metafields_writer \
  --capsule S226 \
  --cpis 3004-416689 \
  --verbose
```

Never full‑capsule during debugging.

---

## 8. Size Guides

### `api/size_guide_writer.py`
**Purpose**
- Attach correct size guide pages via metafields
- Driven by `productType`

**Key rule**
- Size guides are **never gated**
- If product exists → size guide allowed

---

## 9. Smart Collections (Planned, Defined)

Rule:
- One smart collection per style
- Driven by `style_<Name>` tag

Authorization:
- Always allowed

Implementation pending.

---

## 10. Drift Handling (Critical Concept)

### Auto‑Adopt
Used when:
- Shopify assets are unambiguous
- Clear hero / ghost / swatch candidates

System adopts automatically.

---

### Manual Review
Used when:
- Multiple competing hero candidates
- Ambiguous filenames
- Unexpected ordering

Queued for human review.

---

## 11. Final Mental Model (Locked)

- Shopify truth > local belief
- Drift is normal
- Adoption must record provenance
- Mutation must be gated
- Upload success ≠ metafield success
- File class matters more than file content
- Append‑only logs prevent gaslighting ourselves

---

## Status

✅ Upload transport locked  
✅ File classification correct  
✅ Metafield attachment stable  
✅ Drift adoption implemented  
✅ Swatch creation + registration + promotion wired  
✅ State‑driven authorization working  

This system is now **production‑safe**.

---

## Open Follow‑Ups (Explicit)

1. Daily Shopify drift scan + local log
2. Ghost‑missing inspector + downloader
3. Smart collection writer
4. Size guide gating flip at seed time

Nothing here contradicts current behavior.

---

**If this README and the code disagree, the README wins.**