# Ubiquitous Language

A shared vocabulary for the Smooth / Loobric project. Use these terms consistently in code,
docs, UI, marketing, and conversation. When code and this document disagree, fix one of them —
don't let them drift.

Status: **v2 vocabulary settled 2026-06-09** (grill-me session; see `RESEARCH_BRIEF.md` §6);
**Library purged in favor of ToolSet 2026-06-11**. The "v2 Public Vocabulary" section below is
normative for the facade API. Deep-schema terms remain internal. Terms marked ⚠️ have known
ambiguity.

**Language rule — client neutrality.** Smooth is client-application agnostic. The names of
specific applications (FreeCAD, LinuxCNC, Fusion, …) never appear in the normative vocabulary,
the facade API, core docs, or core UI text. They appear only (a) when referring to that
application's own artifact or term (a `.fctl` file IS a "FreeCAD tool library"), and (b) in
explicitly client-specific sections such as the reconciliation tables below or a client's own
repository. Generic domain categories — "CAM application", "controller", "tool table" — are the
neutral vocabulary.

---

## v2 Public Vocabulary (normative)

The facade API exposes ONLY these concepts. Deep entities never appear in public docs, client
code, or user-facing prose.

| Term | Definition |
|------|------------|
| **ToolRecord** | The facade resource: one user-meaningful tool — geometry + tags + Presets + per-machine ToolTableEntries. Maps internally to the deep chain; its public ID is stable for the record's life. In prose, "tool" stays informal; use **ToolRecord** whenever precision matters. |
| **ToolTableEntry** | One machine's table row for a ToolRecord: tool number, pocket, offsets, provenance. Nested as `ToolRecord.machines[]`, scoped to a Machine. Mirrors a controller's tool-table / offset-table row. (Rejected names: `MachineToolInstance` — collides with ToolInstance; `ToolPocket` — names a field; old `ToolPreset` — collides with Preset.) |
| **Machine** | First-class entity: a CNC machine — identity, controller type, limits (incl. spindle min/max). Clients sync their native machine definitions to it. |
| **ToolSet** | A named collection of ToolRecords. The public resource and the internal entity share one name — there is no separate facade word. (Supersedes **Library**, purged 2026-06-11: "library" is a client-side term and now appears only when referring to a specific application's artifact.) |
| **Preset** | A named feeds-and-speeds record on a ToolRecord (`preset_schema: 1`): surface speed (Vc), chipload (Fz), optional vertical-feed ratio, optional material reference, operation type. Engineering values only; raw feed/RPM are derived by the consuming application at use time and never persisted. |
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
| **Smooth Web** | The hosted web application / management UI. The v1 app (`smooth-web`, app.loobric.com) is retired; a v2 rebuild on the facade is scoped in M3. Part of the commercial offering, not the open core. |

## Domain Concepts — Tools

The word "tool" alone is ⚠️ **overloaded** in machining. Smooth resolves it into four distinct
entities along the catalog → physical → machine axis. Always use the specific term.

| Term | Definition |
|------|------------|
| **ToolItem** | A *catalog-level* description of a tool type: manufacturer, part number, tool type (drill, end mill, …), and geometry. Describes *what kind of thing* a tool is, not a physical object. Both cutters and holders are ToolItems. |
| **ToolAssembly** | A combination of a holder ToolItem and a cutter ToolItem, with assembly-specific data (e.g. stickout). What a CAM programmer typically thinks of as "a tool." |
| **ToolInstance** | A *physical* tool with a unique serial number, lifecycle status (AVAILABLE, IN_USE, MAINTENANCE, RETIRED), and actual measured values. Two identical end mills are one ToolItem but two ToolInstances. |
| **ToolPreset** | (Deep, historical) A machine-specific setup of a ToolInstance: the parameters a particular controller needs (tool number, pocket, offsets). This is what a controller tool-table row maps to. Publicly renamed **ToolTableEntry** in v2. |
| **ToolUsage** | A record of a ToolInstance being used: machine, program, operator, runtime metrics, wear measurements. The basis for wear tracking and analytics. |
| **ToolSet** | The collection entity (`tool_sets`). In v2 it directly backs the public **ToolSet** resource — internal and public nomenclature are identical. |
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
| **Sync / Synchronization** | The core verb: making tool data consistent between Smooth Core and a client system (a CAM application's tool data, a controller's tool table, etc.). |
| **Bidirectional sync** | Changes flow both ways: CAM → server → controller *and* controller → server → CAM (e.g. wear offsets entered at the machine propagate back). |
| **Tool table** | A controller's native tool data store (e.g. a `.tbl` file with T/P/D/Z parameters). A client-side format, not a Smooth concept; Smooth models its rows as ToolTableEntries. |
| **Tool library** | ⚠️ Client-side term only — some CAM applications call their tool collections "libraries". Inside Smooth the word is **ToolSet**; "library" appears only when naming that application's own artifact. |
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
| **Machine** | A CNC machine/controller. First-class entity since v2 (see Public Vocabulary); the old free-string `machine_id` is gone. |
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
| **Tool Library** | Persisted collection of Tool Bits, independent of Jobs | ToolSet | **RESOLVED:** FreeCAD Tool Library / `.fctl` ↔ Smooth **ToolSet**. ("Library" was briefly the facade word; purged 2026-06-11 — it is FreeCAD's term, and the facade now uses the internal name.) |
| **Machine** | `.fcm` definition: axes, limits, spindle min/max, post settings | free-string `machine_id` | Smooth **Machine entity** syncs `.fcm` content. Same word, compatible meaning. |
| **Tool Bit** | The cutter: geometry, edges, parameters, F&S Presets; persisted as `.fctb` | ≈ ToolItem (type=cutting_tool) | Equivalence documented; `.fctb` round-trip **must preserve the additive `presets` key**. |
| **Provenance** | Per-field source string (`"user"`, `"preset:…"`); resolver never overwrites `"user"` | (audit log, coarser grain) | Adopt term + semantics for synced F&S fields. **Sync must never replace a `"user"`-provenance value silently.** |
| **OP_TYPES** | Controlled cutting-kind vocabulary: `profile, pocket, slot, drill, adaptive, surface_finish` | (none) | Adopt verbatim for Preset records. |
| **Tool assembly** | *Avoided* in CAM-workbench prose (confusable with Tool Controller) | Core entity (holder + cutter) | Keep `ToolAssembly` in Smooth's deep schema; never in facade/hobbyist docs. |

## Naming Tensions — status after 2026-06-09 grill

1. ~~Facade resource name~~ **RESOLVED:** the facade resource is **`ToolRecord`** — keeps an unambiguous term available without a prose register rule; bare "tool" remains harmlessly informal.
2. ~~Library vs ToolSet vs Catalog~~ **RE-RESOLVED 2026-06-11:** **ToolSet** = the one word, public and internal — "Library" purged from the facade as a client-side (FreeCAD) term; **Catalog** = manufacturer-published collections only.
3. **ToolInstance may point at a ToolItem *or* a ToolAssembly** — now internal-only (facade-only public API), but the schema rule is still needed for phase 2. Open.
4. ~~`machine_id` string~~ **RESOLVED:** Machine entity (D4); syncs `.fcm`. Pending implementation.
5. ~~Open source vs source-available~~ **RESOLVED:** AGPL-3.0 core + commercial, MIT clients (G6). After relicense, "open source" is accurate.
