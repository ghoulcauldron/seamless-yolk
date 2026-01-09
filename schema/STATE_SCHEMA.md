# Product State Schema (v1)

This schema defines the authoritative post-import state and serves as the single source of truth after CSV upload.

---

## File Location

```
capsules/{CAPSULE}/state/product_state_{CAPSULE}.json
```

One file exists per capsule and is append-only after preflight.

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

Each product is keyed by its Shopify handle and conforms to the following structure.

```json
{
  "allowed_actions": ["go", "skip"],
  "body_ready": true,
  "client_recommendation": "go",
  "cpi": "8301-000001",
  "current_stage": "PREFLIGHT_COMPLETE",
  "details_ready": true,
  "image_state": "IMAGE_READY",
  "preflight_errors": ["Missing ghost image"],
  "preflight_status": "NO-GO",
  "preflight_warnings": [],
  "product_type": "RTW",
  "ws_buy": false
}
```

---

## Section Contracts

### Identity Fields (Immutable)

- **cpi**  
  Capsule product identifier, unique per product.

- **product_type**  
  Product classification, e.g. `RTW`.

- **ws_buy**  
  Boolean indicating wholesale buy exclusion.

---

### Preflight Fields (Immutable)

- **preflight_status**  
  Enum: `GO | NO-GO | SKIP`  
  Snapshot of pre-import validation status.

- **preflight_errors**  
  Array of strings describing validation errors.

- **preflight_warnings**  
  Array of strings describing validation warnings.

---

### Image State

- **image_state**  
  Enum: `IMAGE_READY | IMAGE_MINIMAL | IMAGE_INCOMPLETE | N/A`  
  Indicates completeness of product images.

---

### Current Stage

- **current_stage**  
  Enum: `PREFLIGHT_COMPLETE`  
  Indicates the current processing stage; only `PREFLIGHT_COMPLETE` is defined in v1.

---

### Readiness Flags

- **body_ready**  
  Boolean indicating if the product body content is ready.

- **details_ready**  
  Boolean indicating if product details are ready.

- **client_recommendation**  
  String recommendation from client, e.g. `go`.

- **allowed_actions**  
  Array of strings indicating permitted manual actions, e.g. `["go", "skip"]`.

---

## Schema Guarantees

- Preflight fields (`preflight_status`, `preflight_errors`, `preflight_warnings`) are immutable after initial seeding.
- This schema is version 1 and intentionally minimal.
- Future versions (v2+) will extend this schema to support state-driven gating and richer product lifecycle management.

---