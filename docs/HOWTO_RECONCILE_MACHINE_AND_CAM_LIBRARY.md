# How-to: Reconcile a machine and a CAM library you built separately

## Goal

You have a machine tool table **and** a CAM tool library, built independently.
Same shop, same physical tools, but the server doesn't yet know which machine
slot corresponds to which CAM tool. This guide links them.

This is an **identity** question: "is this machine slot the same physical tool
as this record?" It is **not** a data merge. If the two sides hold different
geometry for what turns out to be the same tool, binding changes neither side's
numbers or measurements. Settling identity and settling a data difference are
separate concerns; this guide settles identity (and, at the end, set
numbering) only. See [the note below](#a-note-on-data-differences).

Direction: **both sides already populated**.

"Control client" means the integration that syncs a CNC control's tool table;
"CAM client" means the integration that manages a CAM tool library. (Reference
implementations: smooth-linuxcnc and smooth-freecad. The steps assume any
control and CAM client behave the same way.)

## Before you start

- Server running, logged in with `loobric` (see [CLI.md](CLI.md)).
- The control client has synced the machine's tool table up — entries exist.
- The CAM client has synced its library up — tool records and a tool set exist.
  Confirm with `loobric list-tools` and `loobric list-tool-sets`.

## Steps

### 1. Review the inbox

When a machine reports a tool the server doesn't recognize, the server may
propose a matching record. Proposals collect in the inbox.

```bash
loobric pending
```

```
  ID: 4f2a1c9b
  Machine entry: T2
  Proposed match: 1/4 in downcut, 2-flute
  Confidence: 88% - same diameter and flute count
```

Each item is a scored guess about identity. Resolving one overwrites nothing on
either side.

### 2. Confirm or reject each proposal

```bash
loobric resolve 4f2a confirm   # same tool: link the entry to the record
loobric resolve 7c10 reject    # different tools: drop the suggestion
```

- `confirm` = **same physical tool**. The entry binds to the record; future
  changes route between them. Both keep their own data.
- `reject` = **different tools**. The suggestion is dropped permanently; the
  entry stays unbound and keeps syncing.

If unsure, `reject`: a rejected pair can still be linked by hand later (step 3),
while a wrong `confirm` is currently hard to undo.

### 3. Bind the entries that had no proposal

The inbox only holds cases the server could guess at. Some entries will have no
proposal — a match the server couldn't see. Find them and link by hand.

```bash
loobric tool-table <machine>   # which entries are still unbound
loobric list-tools             # the record id to link to
loobric bind <machine> 5 <record>
```

Binding never overwrites either side; it routes future changes between the entry
and the record.

### 4. Reconcile the set's numbering against the machine

Identity is now settled per tool. The last step lines up the CAM set's member
numbers with the machine's slot numbers, so the library and the control agree on
T-numbers.

This needs the set to be **machine-linked**. The CAM client may have set the
link already; if not, `loobric link-machine` sets it:

```bash
loobric list-tool-sets               # find the set id
loobric link-machine <set> <machine> # link it to the machine it mirrors
```

Then run **reconcile**. For a machine-linked set, reconcile inherits each
member's number from the machine slot that holds it — the machine is observed
fact, the set conforms:

```bash
loobric reconcile <set>
```

It reports any **unreconciled** members — set members with no matching machine
slot. The server reports these rather than inventing a number for them. Resolve
each one by binding the corresponding entry (step 3) or by removing the member
from the set, then reconcile again.

### 5. Confirm with coverage

`coverage` is a read-only diff of the set against the machine's table. Use it to
check the reconcile took and to see what, if anything, is still unbound:

```bash
loobric coverage <set>
```

Every member should read `in sync`. A member that still reads `NUMBER MISMATCH`
or `NOT ON MACHINE` points to a tool whose identity or numbering isn't settled
yet — go back to step 3 to bind it, then reconcile and check coverage again.

### A note on data differences

Binding and reconciling answer **identity** and **numbering**. They do not merge
**measurements**. If the machine measured a 6.35 mm diameter and the CAM record
says 6.30 mm for the same tool, binding leaves both values exactly as they were.

A data difference is a separate concern, decided through the observe/assert
doors ([TOOL_SCHEMA.md](TOOL_SCHEMA.md) §5), not through binding. Don't expect a
bind to "fix" a geometry mismatch — it answers "same tool?", nothing more.

## Confirm success

- `loobric tool-table <machine>` — every entry you intended to link reads
  `bound -> <record>`.
- `loobric pending` — empty, or only items you deliberately left.
- `loobric reconcile <set>` reports no unreconciled members.
- `loobric coverage <set>` — every member reads `in sync`.
- `loobric list-tool-sets` — the set is present and machine-linked.

## Related

- [CLI.md](CLI.md) — `pending`, `resolve`, `bind`, `tool-table`, `list-tools`,
  `link-machine`, `reconcile`, `coverage`.
- [HOWTO_MIRROR_MACHINE_TOOLS_TO_CAM.md](HOWTO_MIRROR_MACHINE_TOOLS_TO_CAM.md)
  — when the machine has the tools and CAM is empty (control → CAM).
- [TOOL_SCHEMA.md](TOOL_SCHEMA.md) §8 — install-once and number-reconciliation
  invariants.
- **Coming soon:** the CAM → control direction, once the coverage view ships
  (issue #18).
