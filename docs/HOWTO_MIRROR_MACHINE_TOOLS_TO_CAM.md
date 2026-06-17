# How-to: Mirror your machine's tools into CAM

## Goal

Your machine already has a tool table. You want those same tools in your CAM
library so you can program against them, without re-entering anything by hand.
This guide takes you from "the tools exist on the machine" to "the tools are a
CAM library that mirrors the machine."

Direction: **control → CAM**.

Throughout, "control client" means the integration that syncs a CNC control's
tool table up to the server, and "CAM client" means the integration that
manages a CAM tool library. (Reference implementations: smooth-linuxcnc and
smooth-freecad. The steps assume any control and CAM client behave the same
way.)

## Before you start

- A running Smooth Core server and a logged-in `loobric`. See
  [QUICK_START.md](QUICK_START.md) and [CLI.md](CLI.md).
- A control client configured against this server and pointed at your machine.
- A CAM client configured against the same server.
- The control client has run at least once, so the machine's tool table has
  synced up.

## Steps

### 1. Let the control client sync the tool table up

Nothing to type. When the control client runs, each slot in the machine's tool
table becomes a **tool-table entry** on the server. These entries arrive
**unbound**: the server has the slot and its measured values, but no shared
tool record stands behind it yet.

### 2. Find the machine

```bash
loobric list-machines
```

Note the machine id (or a unique prefix — short prefixes work like a git short
SHA).

### 3. See what the machine reported

```bash
loobric tool-table <machine>
```

Every entry shows as unbound:

```
T1: 6mm flat endmill  ⌀6.00  [unbound]
T2: 1/4" downcut      ⌀6.35  [unbound]
T3: 3mm ball          ⌀3.00  [unbound]
```

### 4. Promote each entry to a tool record

`create-record` adopts an entry: it creates a brand-new tool record from the
entry's observed values and binds the entry to it, in one step. Do this for
each tool you want in CAM.

```bash
loobric create-record <machine> 1 --name "6mm flat endmill"
loobric create-record <machine> 2 --name "1/4 downcut"
loobric create-record <machine> 3 --name "3mm ball"
```

`--name` defaults to the entry's description, so you can omit it.

A note on T-numbers: the slot number stays on the **machine entry**, not on the
record. A tool record is the machine-independent description of a tool; its
position is a property of the machine slot, never of the record itself. (See
[TOOL_SCHEMA.md](TOOL_SCHEMA.md) §7.)

### 5. Confirm the records exist and the entries are bound

```bash
loobric list-tools
loobric tool-table <machine>
```

`list-tools` shows one record per tool. The table now reads `bound -> <record>`
for each entry you adopted.

### 6. Import the records into your CAM library

This is the CAM client's job, not `loobric`. Point your CAM client at the
server and import (or refresh). It reads the tool records and represents them as
a CAM library — that representation lives in the set's own client section, so
the library is just *one client's view* of a shared tool set (see
[TOOL_SCHEMA.md](TOOL_SCHEMA.md) §7.4). Each imported tool keeps a link back to
its server record.

### 7. Record that this set mirrors the machine

A CAM library that mirrors a specific machine should say so. A tool set carries
an optional `machine_id` link meaning "this set mirrors this machine's
tooling." Setting it lets the set's member numbers be inherited from the
machine's slots later (see the reconcile how-to).

Your CAM client may set this link when it creates the set. If not, `loobric`
links it for you:

```bash
# find the set id
loobric list-tool-sets

# link the set to the machine it mirrors
loobric link-machine <set> <machine>
```

### 8. Confirm the set mirrors the machine

With the link in place, `coverage` shows how the set lines up against the
machine's tool table. Since you adopted these tools straight from the machine,
every member should read `in sync`:

```bash
loobric coverage <set>
```

The summary line confirms it — every tool in sync, nothing left to order or
load. If a tool reads `NOT ON MACHINE`, it exists in the set but the machine
hasn't reported it; if it reads `NUMBER MISMATCH`, run `loobric reconcile <set>`
to inherit the machine's numbering (see the reconcile how-to).

## Confirm success

- `loobric tool-table <machine>` — every adopted entry reads `bound -> <record>`.
- `loobric list-tools` — one record per machine tool.
- `loobric list-tool-sets` — the CAM library shows up as a set with the
  expected member count.
- `loobric coverage <set>` — every member reads `in sync`, nothing left to load.
- In your CAM client, the imported library matches the machine's tools.

## Related

- [CLI.md](CLI.md) — every command used here, plus the touch-off-to-bound
  walkthrough.
- [HOWTO_RECONCILE_MACHINE_AND_CAM_LIBRARY.md](HOWTO_RECONCILE_MACHINE_AND_CAM_LIBRARY.md)
  — when the machine and the CAM library were built separately and need linking.
- **Coming soon:** the reverse direction (CAM → control — push a CAM library
  down to a machine) lands once the coverage view ships (issue #18).
