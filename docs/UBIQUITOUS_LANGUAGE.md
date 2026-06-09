# Ubiquitous Language

A shared vocabulary for the Smooth / Loobric project. Use these terms consistently in code,
docs, UI, marketing, and conversation. When code and this document disagree, fix one of them —
don't let them drift.

Status: **v2 vocabulary settled 2026-06-09** (grill-me session; see `RESEARCH_BRIEF.md` §6).
The "v2 Public Vocabulary" section below is normative for the facade API. Deep-schema terms
remain internal. Terms marked ⚠️ have known ambiguity.

---

## v2 Public Vocabulary (normative)

The facade API exposes ONLY these concepts. Deep entities never appear in public docs, client
code, or user-facing prose.

| Term | Definition |
|------|------------|
| **ToolRecord** | The facade resource: one user-meaningful tool — geometry + tags + Presets + per-machine ToolTableEntries. Maps internally to the deep chain; its public ID is stable for the record's life. In prose, "tool" stays informal; use **ToolRecord** whenever precision matters. |
| **ToolTableEntry** | One machine's table row for a ToolRecord: tool number, pocket, offsets, provenance. Nested as `ToolRecord.machines[]`, scoped to a Machine. Mirrors what LinuxCNC/Fanuc/Haas users call a tool-table or offset-table entry. (Rejected names: `MachineToolInstance` — collides with ToolInstance; `ToolPocket` — names a field, collides with the Pocket op; old `ToolPreset` — collides with FreeCAD Preset.) |
| **Machine** | First-class entity: a CNC machine — identity, controller type, limits (incl. spindle min/max). Syncs FreeCAD `.fcm` definitions. |
| **Library** | A named collection of ToolRecords (internal entity: ToolSet). Maps to FreeCAD Tool Library / `.fctl`. |
| **Preset** | FreeCAD's meaning, schema-identical (`preset_schema: 1`): named F&S record — surface speed (Vc), chipload (Fz), optional vert-feed ratio, optional material UUID/name, op type. Engineering values only; raw feed/rpm never persisted. |
| **Binding** | The confirmed link between a Machine's ToolTableEntry and a ToolRecord. Server-proposed, user-confirmed once, sticky. What makes the sync loop close. |
| **Pending review / Inbox** | First-class server state for items awaiting a human: proposed Bindings and frozen Conflicts. Sync never prompts, blocks, or guesses. |
| **Conflict** | Both sides changed the same bound field between syncs. The field freezes (neither side overwritten) until resolved in the Inbox. |

---

---

## Project & Product Names

| Term | Definition |
|------|------------|
| **Loobric** | The company/organization and brand (loobric.com, GitHub org). Not the product name. |
| **Smooth** | The product: an open-core tool data synchronization system. |
| **Smooth Core** | The central REST API + database server (`smooth-core`). The thing clients talk to. Licensed Elastic 2.0. |
| **Client** | Any program that synchronizes tool data with a Smooth Core server: `smooth-freecad`, `smooth-linuxcnc`, the `loobric.py` CLI, or third-party integrations. Clients are MIT-licensed reference implementations. |
| **Smooth Web** | The hosted web application / management UI (`smooth-web`, app.loobric.com). Part of the commercial offering, not the open core. |

## Domain Concepts — Tools

The word "tool" alone is ⚠️ **overloaded** in machining. Smooth resolves it into four distinct
entities along the catalog → physical → machine axis. Always use the specific term.

| Term | Definition |
|------|------------|
| **ToolItem** | A *catalog-level* description of a tool type: manufacturer, part number, tool type (drill, end mill, …), and geometry. Describes *what kind of thing* a tool is, not a physical object. Both cutters and holders are ToolItems. |
| **ToolAssembly** | A combination of a holder ToolItem and a cutter ToolItem, with assembly-specific data (e.g. stickout). What a CAM programmer typically thinks of as "a tool." |
| **ToolInstance** | A *physical* tool with a unique serial number, lifecycle status (AVAILABLE, IN_USE, MAINTENANCE, RETIRED), and actual measured values. Two identical end mills are one ToolItem but two ToolInstances. |
| **ToolPreset** | A machine-specific setup of a ToolInstance: the parameters a particular controller needs (tool number, pocket, offsets). One ToolInstance can have presets on multiple machines. This is what a LinuxCNC tool-table row maps to. |
| **ToolUsage** | A record of a ToolInstance being used: machine, program, operator, runtime metrics, wear measurements. The basis for wear tracking and analytics. |
| **ToolSet** | A user-defined collection of ToolInstances and/or ToolPresets for a purpose (a job, a machine's carousel, a kit). |
| **Geometry** | The dimensional definition of a ToolItem (diameter, length, flutes, shape). Stored as structured JSON; the part CAM systems care most about. |
| **Measurements** | *Actual* measured values on a ToolInstance (as opposed to nominal catalog geometry). E.g. presetter results. |
| **Wear / Offset** | Adjustments discovered at the machine (tool wear, length/diameter offsets). The canonical example of data that today gets stranded in the controller and never flows back to CAM. |

## Domain Concepts — Catalogs & Sharing

| Term | Definition |
|------|------------|
| **Manufacturer** | A user role for tool vendors who publish catalogs. Admin-created, optionally **verified** (partnership flag). |
| **Manufacturer Catalog** | A published, searchable collection of ToolItems owned by a manufacturer account. Users *copy* tools out of catalogs; they never edit catalog tools directly. |
| **Copy (from catalog)** | Creating a user-owned ToolItem from a catalog ToolItem. The copy is independent and editable. |
| **parent_tool_id** | The link from a copied ToolItem back to its catalog source. Enables provenance and copy-count analytics. |
| **Published** | A catalog flagged visible to the public. Unpublished catalogs are private to the manufacturer. |

## Domain Concepts — Sync

| Term | Definition |
|------|------------|
| **Sync / Synchronization** | The core verb: making tool data consistent between Smooth Core and a client system (CAM library, controller tool table, etc.). |
| **Bidirectional sync** | Changes flow both ways: CAM → server → controller *and* controller → server → CAM (e.g. wear offsets entered at the machine propagate back). |
| **Tool table** | LinuxCNC's native tool data file (`.tbl`), with parameters T, P, D, Z, X, Y, Q, etc. A client-side format, not a Smooth concept. |
| **Tool library** | ⚠️ Loose, client-side term for a collection of tools (e.g. "FreeCAD tool library"). Inside Smooth, prefer the specific entity (ToolSet, catalog, or a user's ToolItems). |
| **Change detection** | Using `version` / `updated_at` to find what changed since last sync, so clients sync deltas instead of everything. |
| **Version (optimistic locking)** | Integer incremented on every write to an entity. A write with a stale version is a **conflict**. |
| **Conflict** | A write attempted against a stale version, typically because two systems changed the same entity between syncs. |
| **Bulk operation** | API endpoints that create/update many entities in one request. The API is "bulk-first" because sync workloads are batch-shaped. |
| **Import / Export** | Moving tool data in/out of Smooth in portable formats (JSON, CSV, XML) — the no-lock-in escape hatch, distinct from live sync. |

## Roles, Tenancy & Security

| Term | Definition |
|------|------------|
| **User** | An account. Owns its tool data; all queries are isolated per account (**multi-tenant by default**). |
| **Role** | `user`, `admin`, or `manufacturer`. Governs what an account may do. |
| **API key** | User-created credential for programmatic/machine access (what a controller-side sync script uses). Distinct from email/password login. |
| **Tag-based API access** | Scoping an API key's reach by entity tags (e.g. a key for machine `mill01` only sees tools tagged for it). |
| **Audit log** | Immutable structured record of who changed what, when. Compliance/forensics, separate from operational logs. |

## Machines & Shop Concepts

| Term | Definition |
|------|------------|
| **Machine** | A CNC machine/controller, referenced by `machine_id` (currently a free string, e.g. `mill01`). ⚠️ Not yet a first-class entity. |
| **Controller** | The CNC control software/hardware (LinuxCNC, Fanuc, Haas, …) that consumes ToolPresets. |
| **CAM system** | Software that generates toolpaths (FreeCAD CAM workbench, Fusion 360, Mastercam, …) and consumes ToolItems/Assemblies/geometry. |
| **Tool room / Tool crib** | Where physical tools are stored, assembled, and measured in a shop. A target integration domain (presetters, inventory). |
| **Presetter** | Shop-floor device that measures actual tool dimensions; a future source of ToolInstance measurements. |

## Standards

| Term | Definition |
|------|------------|
| **ISO 13399** | International standard for cutting tool data representation and exchange. Smooth aims to be *aligned* with (not strictly conformant to) it. |
| **STEP-NC (ISO 14649)** | Standard for machining process data including tooling. |
| **MTConnect** | Read-only protocol for machine-tool data; relevant for usage/wear telemetry. |
| **GTC (Generic Tool Catalog)** | Industry format for distributing manufacturer tool catalogs; relevant to the Manufacturer Catalog feature. |

## Business Model

| Term | Definition |
|------|------------|
| **Open core** | Business model: Smooth Core is free and self-hostable; revenue comes from hosting, the web UI, and team/enterprise features. |
| **Self-hosted** | Running Smooth Core on your own infrastructure (free tier, full data control). |
| **Cloud-hosted** | Loobric-managed hosting (Hobbyist $15/mo, Professional $299/mo, Enterprise custom). |
| **AGPL-3.0** | smooth-core's license (relicensed from Elastic 2.0 on 2026-06-09, decision G6): OSI-approved open source; network-use copyleft prevents proprietary SaaS forks while keeping self-hosting fully free. Commercial licensing covers the hosted/enterprise offering. Clients remain MIT. |

---

## Reconciliation with FreeCAD CAM (ADR-000)

FreeCAD's CAM workbench maintains its own ubiquitous language in `src/Mod/CAM/Roadmap/ADR/ADR-000.md`,
extended by the Feeds & Speeds work (PR #30078). Smooth's first client lives there, so collisions are
resolved **in FreeCAD's favor** wherever FreeCAD's term is shipping. Proposed resolutions (see
`RESEARCH_BRIEF.md` §3.4, decision D13 — pending grill-me):

| Term | FreeCAD meaning | Smooth PoC meaning | Proposed resolution |
|------|-----------------|--------------------|---------------------|
| **Preset** | Named F&S record on a Tool Bit: surface speed (Vc), chipload (Fz), optional vert-feed ratio, optional material UUID, op type. Engineering values only; raw feed/rpm derived at use-time. | `ToolPreset` = machine-specific tool-table entry (tool number, pocket, offsets) | **RESOLVED: adopt FreeCAD's meaning.** Smooth's cutting-parameter records are "Presets" with the identical schema. Smooth's old entity renamed → **ToolTableEntry**. |
| **Tool Library** | Persisted collection of Tool Bits, independent of Jobs | (no entity; ToolSet ≈ collection) | FreeCAD Tool Library / `.fctl` ↔ Smooth **ToolSet**; consider renaming ToolSet → Library in facade vocabulary. |
| **Machine** | `.fcm` definition: axes, limits, spindle min/max, post settings | free-string `machine_id` | Smooth **Machine entity** syncs `.fcm` content. Same word, compatible meaning. |
| **Tool Bit** | The cutter: geometry, edges, parameters, F&S Presets; persisted as `.fctb` | ≈ ToolItem (type=cutting_tool) | Equivalence documented; `.fctb` round-trip **must preserve the additive `presets` key**. |
| **Provenance** | Per-field source string (`"user"`, `"preset:…"`); resolver never overwrites `"user"` | (audit log, coarser grain) | Adopt term + semantics for synced F&S fields. **Sync must never replace a `"user"`-provenance value silently.** |
| **OP_TYPES** | Controlled cutting-kind vocabulary: `profile, pocket, slot, drill, adaptive, surface_finish` | (none) | Adopt verbatim for Preset records. |
| **Tool assembly** | *Avoided* in CAM-workbench prose (confusable with Tool Controller) | Core entity (holder + cutter) | Keep `ToolAssembly` in Smooth's deep schema; never in facade/hobbyist docs. |

## Naming Tensions — status after 2026-06-09 grill

1. ~~Facade resource name~~ **RESOLVED:** the facade resource is **`ToolRecord`** — keeps an unambiguous term available without a prose register rule; bare "tool" remains harmlessly informal.
2. ~~Library vs ToolSet vs Catalog~~ **RESOLVED:** **Library** = public/facade word (internal entity ToolSet); **Catalog** = manufacturer-published collections only.
3. **ToolInstance may point at a ToolItem *or* a ToolAssembly** — now internal-only (facade-only public API), but the schema rule is still needed for phase 2. Open.
4. ~~`machine_id` string~~ **RESOLVED:** Machine entity (D4); syncs `.fcm`. Pending implementation.
5. ~~Open source vs source-available~~ **RESOLVED:** AGPL-3.0 core + commercial, MIT clients (G6). After relicense, "open source" is accurate.
