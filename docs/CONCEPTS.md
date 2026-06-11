# Smooth Concepts — how the pieces fit

A first-time user's guide to the domain model: what the four nouns mean, why the
Machine is treated specially, why there is exactly one tool table per machine, and
why "binding" lives in the core even though only one client seems to use it.

Vocabulary is normative in `UBIQUITOUS_LANGUAGE.md`; this document explains the
*relationships*.

---

## The problem Smooth exists to solve

Tool data lives in three places that don't talk to each other:

1. **Your CAM system** knows what a tool *is* — geometry, feeds & speeds.
2. **Your controller** knows what a tool *does right now* — tool number, pocket,
   and the wear/length offsets you discovered by touching off at the machine.
3. **Your head** knows which rows in (2) are which tools in (1).

Today, (3) never gets written down, so the offsets in (2) are stranded: re-measure
the tool, re-enter the offset, repeat forever. Smooth's whole purpose is the loop:

> touch off at the machine → offset flows to the server → CAM sees the real,
> current offset for *that tool on that machine* → edits flow back down.

Every concept below exists to make that loop close **without ever guessing,
prompting, blocking, or overwriting anything silently**.

---

## The four nouns

| Noun | What it is | One-line test |
|------|-----------|---------------|
| **ToolRecord** | A tool's *identity and canonical data*: geometry, tags, presets. | "Which tool are we talking about?" |
| **ToolSet** | A *named grouping* of ToolRecords. Pure membership, nothing else. | "Which tools belong together?" |
| **Machine** + its **ToolTableEntries** | A *mirror of one controller's current state*: numbered rows with pockets and offsets. | "What does the machine say is loaded, right now?" |
| **Binding** | The confirmed link between one ToolTableEntry and one ToolRecord. | "Is row T3 on millstone the 1/4″ downcut?" |

Two of these are things *you curate* (ToolRecord, ToolSet). One is a thing the
*machine reports* (the tool table). The last is the *join* between those two
worlds — and the join is the product.

---

## Intent vs. observation — why the machine's list is NOT a ToolSet

This is the most important distinction in the model.

A **ToolSet is intent.** A human decided "these tools go together" — a drawer, a
job kit, the contents of a CAM tool library. Its members are ToolRecord ids. It
carries no numbers, no offsets, no machine. You can have as many as you like, and
one ToolRecord can belong to many of them.

A **tool table is observation.** It is what one physical controller actually
reports: "T3 is in pocket 3 with Z−48.25." Its rows are keyed by
`(machine, tool_number)`, they carry offsets and provenance, and — critically —
they exist *whether or not anyone knows which ToolRecord they correspond to*. An
unbound entry is a perfectly valid fact about the machine. A ToolSet could never
represent that: ToolSet membership is made of ToolRecord ids, and an anonymous
`T7 P7 Z-12.1` has no ToolRecord id. The two collections aren't different sizes
of the same thing; they're different *kinds* of thing.

That's also why offsets live on the entry and not the record: a wear offset is
not a property of the tool, it's a property of **the tool in that machine,
measured there**. Provenance (`"offsets.z": "machine"`) records who said so, and
the sync rules promise never to silently overwrite a value a human entered.

### Why exactly one tool table per machine

Because there is exactly one machine. The table mirrors the controller's current
truth; the controller has one active table; so the server holds one per Machine.
The server never invents rows — clients push what the controller reports, and
rows upsert on `(machine, tool_number)`.

### "But my machine swaps between tool sets!"

Yes — and that workflow is *composition*, not a missing core feature. Swapping a
carousel is an act of intent: "make the machine's reality match this grouping."
That is precisely a client feature built from the two existing primitives:

1. You curate ToolSets on the server ("aluminum job", "wood job").
2. A client (or future feature) writes the chosen set's tools into the
   controller's table.
3. The next sync reports the new reality, and the server's tool table mirrors it.

Your instinct is the design: which set is *loaded* is machine-side state, and how
loading happens is controller-specific — best handled by a client. The core's job
is only to never lose the facts on either side of the swap. If core grew
"multiple alternative tables per machine," it would be modeling intent twice and
observation never — and the wear offsets discovered under setup A would have no
single home when setup B is loaded.

---

## Binding — the identity problem, and why it lives in core

Every client must answer the same question: **"which server ToolRecord does this
local thing correspond to?"** The clients differ only in *where the answer can be
stored*.

### Identity-carrying clients (e.g. the CAM side)

A `.fctb` file is JSON; the client can write the server id directly into the file
(the additive `smooth` key) at export time. Identity is *embedded in the
representation*, so correspondence is deterministic — no human confirmation
needed, because the client that created the record is the same client reading the
file. When an editor strips the key, recovery is still deterministic (stored
native id, recorded filename, sync journal) and the rule is: **if it's ambiguous,
error — never guess.**

So the CAM client absolutely *does* have the binding concept — it's just solved
at the file level, invisibly, because the file format permits it.

### Identity-less clients (e.g. the controller side)

A LinuxCNC `.tbl` row is `T3 P3 D+6.350000 Z-48.250000 ;comment`. There is
nowhere to put a server id: the controller owns that file, rewrites it, and its
format has no extension mechanism. The local representation **cannot carry
identity**. So the identity link must live somewhere else — and the only
"somewhere else" both sides can see is the server. That link is the **Binding**:
a server-side, human-confirmed assertion that entry `(millstone, T3)` *is*
ToolRecord "1/4″ downcut".

This is the user-stated principle, confirmed: **binding is the universal concept
— confirmation that a server tool maps to a client representation — instantiated
explicitly only where the representation can't carry the mapping itself.**

### Why the core, and not the LinuxCNC client?

Three reasons, and the first is decisive:

1. **The loop crosses clients.** "Touch off on millstone → see the offset in
   CAM" requires joining the controller's row to the CAM tool's record. Neither
   client can see the other; only the server sees both. A binding kept privately
   by the LinuxCNC client could never light up the CAM side.
2. **Confirmation needs a human, and the control box must never wait for one.**
   The sync script on the controller is a non-interactive cron-style script on a
   machine you shouldn't be browsing the web on. So the server *proposes*
   bindings (heuristically — diameter, name similarity — never auto-confirms),
   parks them in the **Inbox**, and a human confirms from any device. Rejected
   proposals are remembered and never re-proposed. Meanwhile sync continues:
   **unbound entries sync as unbound** — facts are never held hostage to
   identification.
3. **Bindings are durable, sticky state.** Confirmed once, the link survives
   table rewrites, offset changes, and client reinstalls, because it's keyed on
   `(machine, tool_number)` server-side — not on anything in the fragile file.

### What a binding changes

- **Before binding:** the entry's offsets are recorded and versioned, but no one
  else can use them. CAM shows nothing.
- **After binding:** the entry appears nested under its ToolRecord
  (`ToolRecord.machines[]`); CAM displays "Z−48.007 on millstone, measured at
  the machine"; a server-side offset edit flows back into the controller's
  `.tbl` (surgically, with a backup, comments preserved). The loop is closed.
- **Conflict protection applies only to bound entries:** if both sides change a
  bound field between syncs, the field freezes and lands in the Inbox. Neither
  side is overwritten. Unbound rows can't conflict with a record they aren't
  linked to.

---

## The loop, end to end (concrete)

1. You design with a 1/4″ downcut in CAM. Export → ToolRecord exists; the
   `.fctb` carries its id (identity-carrying client: bound by construction).
2. The sync script on **millstone** pushes its `.tbl`. Row `T3 P3 D+6.35 Z-48.25`
   becomes an *unbound* ToolTableEntry. Nothing prompts, nothing guesses.
3. The server notices T3's diameter matches the downcut's and **proposes** a
   binding → Inbox.
4. From your phone, you confirm. `(millstone, T3)` ⇄ "1/4″ downcut" — forever.
5. Weeks later you touch off and enter Z−48.007 at the machine. Sync pushes it;
   because the entry is bound, CAM now shows the measured offset with machine
   provenance.
6. You correct the offset on the server; the next controller sync rewrites
   exactly that line of `tool.tbl`, backup first, comments intact.

Steps 3–4 are the *only* place a human is required, they happen exactly once per
machine-tool pairing, and they're required precisely because step 2's file format
cannot say which tool it means.

---

## FAQ

**Is the machine's tool list a ToolSet?**
No. ToolSet members are ToolRecord ids (intent); tool-table rows are
number+offset facts that exist even when unbound (observation). See
"Intent vs. observation."

**Can a machine have several tool sets and switch between them?**
You can have any number of ToolSets, and a client may implement "load this set
into the machine." The *server* still keeps one table per machine, because the
table mirrors what the one physical controller currently reports. Which set is
loaded is exactly the kind of controller-specific workflow that belongs in a
client — the core only guarantees no facts are lost across the swap.

**Why doesn't the CAM client have bindings?**
It does — implicitly. Its file format can carry the server id, so the mapping is
embedded and deterministic, and no human confirmation is needed. Binding becomes
an explicit, server-side, human-confirmed object only when the client
representation (a controller tool table) cannot carry identity itself.

**Could other clients ever use explicit Bindings?**
Yes — any future identity-less representation (another controller format, a
spreadsheet import, a presetter feed) gets the same treatment: push facts
unbound, let the server propose, let a human confirm in the Inbox. The concept is
universal; the explicit mechanism is reserved for representations that need it.

**Why is Machine first-class instead of a string?**
Because offsets are meaningless without provenance. "Z−48.007" is not tool data;
"Z−48.007 *on millstone*" is. Machines also carry controller type and limits so
CAM can resolve feeds & speeds against the machine that will actually run the job.
