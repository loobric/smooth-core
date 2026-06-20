# M2 — Catalog records and instance creation

> Status: scoped 2026-06-20 via grill. This plan supersedes the prior M2
> "importers" framing. Importers are **secondary** and deferred. The M2 value
> story is: **author a catalog line, create a physical tool from it, and see it.**

## 1. Goal

Deliver early, demonstrable value to anyone experimenting with the application:
the ability to create a `ToolCatalogRecord` and create `ToolInstanceRecord`s
from it, exercised end to end through the CLI (the reference client) and made
visible in the web UI.

## 2. Scope

| Surface | M2 | Notes |
|---|---|---|
| **CLI** (`loobric`) | ✅ full vertical slice | the reference client; script-wrappable |
| **Web UI** | ✅ browse + create-from-catalog | kept deliberately thin; the *visual drift detector* |
| **FreeCAD client** | ⛔ deferred | layers on after the server primitive exists |
| **Importers** (other tool tables) | ⛔ deferred | secondary; will reuse the create path + natural-key 409 |

## 3. The provenance gradient (conceptual core)

A tool's geometry exists at three honesty levels, **all expressible today with
no schema change** (the model's `source` is a free string validated by kind +
structure; the `observed:presetter@…` precedent already blesses non-CNC
measurers):

| Reality | Lives on | `source` |
|---|---|---|
| Published catalog spec (nominal) | `ToolCatalogRecord.canonical.geometry` | `asserted:<manufacturer>` |
| This certified tool's QA measurement | `ToolInstanceRecord.canonical.geometry` | `observed:manufacturer@<cert/serial>` |
| Shop touch-off | `ToolInstanceRecord.canonical.geometry` | `observed:<client>@<machine>` |

- **No new provenance kind** (`certified:` rejected — splits "measured" for no
  enforcement benefit, breaks "learn the model once").
- The catalog→instance creation endpoint is a **deliberate audited door** (like
  `bind`) that is *permitted to stamp third-party `observed:manufacturer@*`
  provenance*. The routine `observe` door is **unchanged** and still requires a
  client to stamp its own identity.

## 4. Server work

### 4.1 `create_catalog_record` (rename + seeded create)

- Rename the endpoint function `create_catalog` → **`create_catalog_record`**
  (glossary: "catalog" = a *set*/collection; "item" is loaded — retired
  `ToolItem` + live `item_type`; **`ToolCatalogRecord`** is the ratified noun).
  Resource path `/api/v1/tool-catalog-records` is unchanged.
- **Seeded, atomic canonical-create.** The request carries `{value, unit}` per
  nominal field **plus one declared `actor`**; the **server stamps
  `asserted:<actor>`** on each (client never writes `source` — lane discipline).
  One `CREATE` audit row, all-or-nothing. Replaces create-blank-then-N-asserts.
- **Identity floor (required, non-null):** `name`, `manufacturer`,
  `product_code`. Findability/de-dup, not spec completeness.
- **Spec fields optional, honest-sparse:** geometry etc. — as sparse as the
  source honestly provides; never fabricated to pass a gate.
- **Shop-ground convention:** a no-vendor tool sets `manufacturer = "shop"`
  (honest — the shop *is* the manufacturer of a tool it ground).

### 4.2 Uniqueness on the natural key

- **Disallow duplicates** on `(user_id, manufacturer, product_code)`.
- **Scope: per-account** (a future hosted multi-account world adds a
  *public/cross-account* catalog layer above this; M2's key is its floor).
- **Normalization: trim + casefold** both fields for the comparison; store the
  original display value. (Without this the constraint is illusory.)
- **Enforcement: DB-level unique index** on the normalized extracted values
  (parallel to the install-once index), covering **both create *and* an
  `assert` that edits `manufacturer`/`product_code` into a collision**.
- **Collision → `409`** naming the existing record and inviting reuse:
  *"Kennametal B201 already exists as `a1b2c3` — create an instance from it, or
  edit that record."* (Also the deferred importer's merge/skip signal.)

### 4.3 `POST /tool-catalog-records/{id}/create-instance` (new)

The catalog→instance door. **No "mint" wording** anywhere (CLI, endpoint,
glossary).

- Asserts `catalog_type_id` ← the path id, `source = asserted:<requester>`
  (link-actor **defaults to the requesting context** — it's the minter's own
  first-party act, unlike create's nominal which can be third-party).
- `name` ← request override, else copied from the catalog name.
- **Optional QA:** a geometry-shaped payload + a required **cert** identifier
  when QA is present → stamped `observed:manufacturer@<cert>`. No QA → measured
  geometry stays `unknown` (nominal reachable through the link).
- **Leaves the instance unbound** (a catalog is not a machine position).
- `status` left **unknown** at creation (status vocabulary deferred).
- **Every call produces a new, distinct instance** (two identical tools = two
  instances pointing at one type). No dedup on instances.
- Returns the new instance.

### 4.4 Already present (reuse, no change)

`GET /tool-catalog-records`, `GET /tool-catalog-records/{id}`, the
`assert` door, the instance/entry `bind` door (`create-record --from-entry`).

## 5. CLI work (`loobric` / loobric.py)

- **`create-catalog-record`** — JSON on **stdin** (primary) or `--file`; **thin
  convenience flags** (`--name`, `--manufacturer`, `--product-code`,
  `--diameter`, `--flutes`) for the by-hand case; **required `--source`** actor
  (no default — a scraped spec and a typed guess get distinguishable
  provenance). JSON carries values+units; `--source` carries the actor.
- **`list-catalog-records`** — headless browse.
- **`show-catalog-record CATALOG`** — view one with provenance.
- **`create-record` gains `--from-catalog`** (context-aware, no new verb):
  - `create-record MACHINE TOOL_NUMBER` — existing entry form, unchanged →
    **bound** instance.
  - `create-record --from-catalog CATALOG [--name N] [--qa qa.json --cert C]`
    → **unbound** instance.
  - Output **names the outcome**: *"created instance X, bound to millstone T3"*
    vs *"created instance X from Kennametal B201 — not yet installed."*
- **Catalog resolver** accepts **id / unique id-prefix / name / product_code**
  (ambiguity prints candidates, like the other resolvers).
- Library methods: `create_catalog_record` exists; add the
  create-instance-from-catalog call + the `--source`/`--qa`/`--cert` plumbing.

## 6. Web UI work (thin — the drift detector)

Flow: **browse → Create → pre-populated form → Done.**

- **List** `ToolCatalogRecord`s.
- **Detail** view: every nominal field shown **with its `source` badge** — so
  fabrication is *visible* (`asserted:manufacturer` vs `observed:…`).
- **"Create tool from catalog"** → a **form pre-populated with defaults**:
  - `name` pre-filled, editable (defaults to catalog name).
  - nominal geometry shown **read-only** with source badges (what you're
    creating from).
  - **Not in the M2 form** (their future home): QA fields, `status`.
  - Confirm → `POST …/create-instance` with the (possibly edited) name, no QA.
- Web catalog **authoring** and **QA entry** are **deferred** (CLI/script only).
- Optional polish: a live "N instances created" count via
  `WHERE catalog_type_id = X` (not a stored back-reference).

## 7. Docs & glossary

- **Glossary:** identity floor + normalized natural key `(manufacturer,
  product_code)`; shop-as-manufacturer convention; the
  `observed:manufacturer@<cert>` QA provenance; note the future
  public/cross-account catalog layer. **No "mint" term.**
- **CLI.md:** the new verbs; `create-record --from-catalog`; a one-line note
  disambiguating the instance-creation paths (entry → bound; catalog → unbound).
- **TOOL_SCHEMA.md / DATA_MODEL.md:** the seeded-create authoring path; the
  manufacturer-QA provenance example; the catalog uniqueness invariant.

## 8. Explicitly deferred

FreeCAD client · importers · web catalog authoring · web QA entry · `status`
vocabulary · assemblies/composition flows (JSON *structurally* permits
`item_type`/`components`; M2 flows target **leaf** tools only) · copy-count
analytics · public/cross-account catalogs · images (when added: a
provenance-tagged **reference** in `canonical`, blob hosted out-of-record —
`CatalogCanonical`'s `extra="forbid"` is the conscious gate).

## 9. Acceptance walkthrough (the demo)

1. `scrape-kennametal.py <URL> | loobric create-catalog-record --source manufacturer:kennametal -`
2. `loobric list-catalog-records` → the record appears.
3. Web → browse catalog records → detail shows nominal geometry with
   `asserted:manufacturer` badges.
4. Web → **Create tool from catalog** → form pre-filled with the name → Done →
   an **unbound** instance is created.
5. `loobric create-record --from-catalog B201 --qa qa.json --cert "kennametal@SN12345"`
   → instance with `observed:manufacturer@SN12345` measured geometry.
6. Re-run step 1 → **`409`** pointing at the existing record.
7. `loobric create-record millstone 3` → instance **bound to T3** (the existing
   path still works) — output names the binding.
