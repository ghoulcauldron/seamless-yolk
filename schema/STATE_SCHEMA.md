

# Product State Schema v1

This document defines the canonical product state model used across the capsule
pipeline. State is the single source of truth governing enrichment, import,
media attachment, metafield writes, collection creation, and promotion.

---

## File Location

```
capsules/{CAPSULE}/state/product_state_{CAPSULE}.json
```

---

## Top-Level Structure

```json
{
  "capsule": "S226",
  "schema_version": "1.0",
  "generated_at": "2025-12-21T20:30:00Z",
  "products": {
    "arp-dress-black": { }
  }
}
```

### Fields

- **capsule** — Capsule identifier (e.g. `S226`)
- **schema_version** — Locked schema version
- **generated_at** — ISO timestamp of last state write
- **products** — Map keyed by Shopify handle

---

## Product Record

Each product is keyed by its Shopify handle and conforms to the following
structure.

```json
{
  "handle": "arp-dress-black",
  "product_id": "S226-8301 KCS049 000001 BLACK",
  "cpi": "8301-000001",
  "product_type": "RTW",
  "is_accessory": false,

  "preflight": {
    "status": "NO-GO",
    "image_status": "IMAGE_SOFT_FAIL",
    "errors": ["Missing ghost image"],
    "warnings": []
  },

  "import": {
    "eligible": true,
    "imported": true,
    "imported_at": "2025-12-21T20:14:05Z",
    "import_source": "combined_csv",
    "anomaly_accepted": true
  },

  "images": {
    "expected": {
      "count": 5,
      "max_position": 5
    },
    "last_enriched_at": "2025-12-21T19:55:00Z"
  },

  "promotion": {
    "stage": "IMPORTED",
    "locked": false,
    "last_transition_at": "2025-12-21T20:14:05Z"
  },

  "overrides": {
    "manual_go": false,
    "notes": ""
  }
}
```

---

## Section Contracts

### Identity (Immutable)

- **handle**
- **product_id**
- **cpi**
- **product_type**
- **is_accessory**

These fields are set once during seeding and must never change.

---

### Preflight (Read-Only)

```json
"preflight": {
  "status": "GO | NO-GO",
  "image_status": "IMAGE_OK | IMAGE_SOFT_FAIL | IMAGE_HARD_FAIL",
  "errors": [],
  "warnings": []
}
```

- Snapshot of pre-import validation
- Never mutated post-import
- Used for audit and reporting only

---

### Import State (Authoritative Gate)

```json
"import": {
  "eligible": true,
  "imported": true,
  "imported_at": "...",
  "import_source": "combined_csv | anomalies_csv",
  "anomaly_accepted": true
}
```

Rules:

- `eligible = false` → product is excluded entirely (e.g. WS Buy)
- `imported = true` → product must not re-enter enrichment
- `anomaly_accepted = true` → client approved upload despite issues

---

### Image Expectation

```json
"images": {
  "expected": {
    "count": 5,
    "max_position": 5
  }
}
```

- Reflects attempted image layout
- Does not verify Shopify state
- Prevents duplicate uploads downstream

---

### Promotion State

```json
"promotion": {
  "stage": "IMPORTED",
  "locked": false,
  "last_transition_at": "..."
}
```

Controls orchestration and gating.

---

### Overrides (Human Authority)

```json
"overrides": {
  "manual_go": false,
  "notes": ""
}
```

- Only set manually
- Scripts must respect overrides
- Never auto-cleared

---

## Promotion Ladder

```
PRE_FLIGHT
  ↓
ENRICHED
  ↓
IMPORT_READY
  ↓
IMPORTED
  ↓
MEDIA_ATTACHED
  ↓
METAFIELDS_WRITTEN
  ↓
COLLECTIONS_CREATED
  ↓
LIVE
```

---

## Stage Definitions

### PRE_FLIGHT
- Product seeded from preflight output
- No CSVs generated

### ENRICHED
- Appears in import-ready or anomalies CSV

### IMPORT_READY
- Human decision to upload
- Anomaly approval may occur here

### IMPORTED
- Confirmed by post-import inference
- Hard gate: enrichment must skip

### MEDIA_ATTACHED
- Images uploaded (ghost, hero, model, swatch)

### METAFIELDS_WRITTEN
- Look products, size guides, swatches written

### COLLECTIONS_CREATED
- Smart collections created (idempotent)

### LIVE
- Fully promoted
- Locked unless rollback is intentional

---

## Locking Rules

- `promotion.locked = true` freezes the product
- Used for live products, legal holds, or emergency stops

---

## Design Principles

- State is the single source of truth
- Scripts are idempotent and obedient to state
- Anomalies are first-class, not hacks
- Human decisions are explicit and preserved