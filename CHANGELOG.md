# Changelog

All notable changes to **smooth-core** are recorded here. This project adheres to
[Semantic Versioning](https://semver.org/). Dates are ISO-8601.

## [0.1.0] — 2026-06-19

First tagged release. This is the **v2** server produced by the June 2026 reboot:
a single, sectioned tool-data schema with a thin public API, and `loobric.py` as
the reference client.

### Added
- **Sectioned tool schema** (`docs/TOOL_SCHEMA.md`): every entity is
  `internal` / `canonical` / `clients`, with provenance-tagged canonical fields
  (`{value, source}`, source ∈ observed/asserted/derived/unknown). Canonical data
  changes only through three doors — **sync** (a client writes its own section),
  **observe** (a machine measurement), **assert** (an explicit declaration).
- **Public vocabulary** (`docs/UBIQUITOUS_LANGUAGE.md`): `ToolInstanceRecord`,
  `ToolCatalogRecord`, `ToolTableEntry` ("entry"), `Machine`, `ToolSet`,
  `Binding`, `Inbox`, `Conflict`. Public paths under `/api/v1/*-records`.
- **Binding**: `POST /tool-table-entry-records/{id}/bind` (pass `instance_id` to
  bind an existing tool; omit it to mint a new one from the entry's observations),
  `/unbind`, and the proposal **Inbox** (`/instance-inbox`) with confirm/reject.
- **`loobric.py`** — the MIT-licensed, single-file, stdlib-only **reference Python
  client**: an importable `Client` covering all published routes plus a 29-command
  CLI (`docs/CLI.md`). Clients vendor it instead of re-rolling an HTTP client.
- **Account reset** — `POST /api/v1/account/reset` (admin) wipes the caller's tool
  data while keeping the account and API keys.
- **Web UI** (`/ui`): Machines · Tools · Tool Sets · Audit log. Binding is folded
  into the Machines tab (each unbound entry surfaces its proposal: Same tool /
  Different / Bind new).
- **Vocabulary gate** in CI: the published OpenAPI excludes the legacy deep
  routers, and the bundled web UI + CLI are scanned for both retired endpoint
  paths and retired *words*.

### Changed
- The API is now a thin facade speaking the sectioned contract models directly
  (no separate "facade vocabulary").
- Backup/export and change-detection rewritten to operate on the v2 sectioned
  records.
- License is AGPL-3.0 (core); clients are MIT.

### Removed
- The rejected concepts **Coverage**, **Reconcile**, **Adopt**, **Needs
  Attention**, **mirror**, and **slot** — along with their endpoints
  (`/coverage`, `/reconcile`, `/adopt`) and the legacy deep routers from the
  published schema. `/adopt` folded into `/bind`; "mirror" → **link**; "slot" →
  **entry**.

### Security
- `/backup/export` and `/backup/import` are now admin-gated (previously
  unauthenticated).
- API-key revocation verifies ownership (returns 404 to non-owners).

### Known issues
- Two `test_registration_security.py` tests fail due to a pre-existing
  test-isolation defect (they assume an empty DB); not a code regression.

[0.1.0]: https://github.com/loobric/smooth-core/releases/tag/v0.1.0
