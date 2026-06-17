# loobric CLI

`loobric` is the command-line client for a Smooth Core server. Use it to create
a user, manage API keys, inspect machines and tool records, and review and
resolve the binding inbox.

This page has two parts:

- [Command reference](#command-reference) — every subcommand, its arguments, and
  what it prints.
- [Walkthrough: from touch-off to a bound tool](#walkthrough-from-touch-off-to-a-bound-tool)
  — the core workflow, end to end.

For goal-oriented walkthroughs that span a CNC control and a CAM library, see
the how-to guides:
[Mirror your machine's tools into CAM](HOWTO_MIRROR_MACHINE_TOOLS_TO_CAM.md) and
[Reconcile a machine and a CAM library you built separately](HOWTO_RECONCILE_MACHINE_AND_CAM_LIBRARY.md).

## Installing the command

`loobric` is installed with `smooth-core`. From a clone:

```bash
cd smooth-core
uv venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

After this, `loobric` is on your PATH inside the virtual environment:

```bash
loobric --help
```

If you prefer not to install, you can run the script directly with
`python loobric.py …` from the `smooth-core` directory. Every command below
works the same way; only the leading word changes.

## How authentication works

`loobric` picks credentials in this order:

1. The `--api-key` flag, if given.
2. A saved session cookie from a previous `loobric login`.
3. No authentication — fine for `ping` and `register` (first user), rejected by
   everything else on a multi-tenant server.

A successful `login` saves the server URL and session cookie to
`~/.loobric/session.json` (owner-readable only). After that, you can omit
`--base-url` and run commands directly.

## Global options

These go before the subcommand: `loobric [global options] <command> [...]`.

| Option | Description |
| --- | --- |
| `--base-url URL`, `-b URL` | Server base URL. Defaults to `$LOOBRIC_BASE_URL`, then the saved session. |
| `--api-key KEY` | Authenticate with an API key instead of a session. Overrides the session cookie and `$LOOBRIC_API_KEY`. |
| `--verbose`, `-v` | Print the resolved base URL and auth source to stderr. |
| `--login` | Shortcut for interactive login (prompts for URL, email, password). |
| `--logout` | Shortcut to end the current session. |
| `-h`, `--help` | Show help. Works on the top level and on any subcommand. |

Environment variables:

- `LOOBRIC_BASE_URL` — default server URL.
- `LOOBRIC_API_KEY` — used **only** when you pass `--api-key "$LOOBRIC_API_KEY"`;
  it is not read automatically, to avoid clashing with a saved session.

## Command reference

Many commands accept **id prefixes**: like a git short SHA, you can pass the
first few characters of a machine, record, or inbox-item id as long as the
prefix is unique. An ambiguous prefix prints the candidates and exits.

### Account and session

#### `register`

```
loobric --base-url URL register [email] [--password PASSWORD]
```

Create a user account. The first account on a fresh database becomes the admin;
later registrations require admin authentication. Prompts for any missing email
or password (with confirmation). Prints the created email and user id, then the
login command to run next.

#### `login`

```
loobric login [email] [--password PASSWORD] [--url URL]
```

Authenticate with email and password and save the session. Prompts for any
missing value; the URL prompt defaults to `http://127.0.0.1:8000`. On success,
prints the user and writes the session to `~/.loobric/session.json`.

#### `logout`

```
loobric logout
```

End the current session and delete the saved session file. `loobric --logout`
does the same thing.

#### `ping`

```
loobric ping
```

Check that the server is reachable and healthy (calls `/api/health`, no auth
required). Prints status, version (if reported), and the URL. Exits non-zero if
the server is unreachable or unhealthy.

### API keys

#### `create-key`

```
loobric create-key NAME [--scopes "read write"] [--tags "production mill-3"] [--expires-at ISO8601]
```

Create an API key. `--scopes` and `--tags` are space-separated lists;
`--expires-at` is an ISO 8601 datetime such as `2027-12-31T23:59:59Z`.

The plaintext key is printed to **stdout** on its own line; the human-readable
details and warnings go to **stderr**. This lets you capture just the key:

```bash
loobric create-key "LinuxCNC mill" --scopes "read write" > mill.key
```

The server stores only a hash of the key, so it cannot be shown again. Save it
when it is created.

#### `list-keys`

```
loobric list-keys
```

List your API keys: id, name, scopes, tags, and created / expiry / last-used
timestamps where available. The plaintext key is never shown.

#### `revoke-key`

```
loobric revoke-key KEY_ID
```

Revoke (delete) an API key by its id. Prints a confirmation.

### Inspecting machines and tools

#### `list-machines`

```
loobric list-machines
```

List your machines: id, name, and controller type (when set).

#### `list-tools`

```
loobric list-tools
```

List your tool records — the public, machine-independent view of a tool. Prints
id, name, and a short geometry summary (shape and diameter) when present.

#### `list-tool-sets`

```
loobric list-tool-sets
```

List your tool sets (named collections of tool records): id, name, member count,
last-updated, and version.

#### `tool-table`

```
loobric tool-table MACHINE
```

Show one machine's tool-table entries — the tools the controller has reported.
`MACHINE` is a machine id or unique prefix. Each line shows the tool number,
description, diameter (when reported), and bind state: either `unbound` or
`bound -> <record-prefix>`.

### Tool sets and coverage

A tool set can carry an optional link to a machine, meaning "this set mirrors
this machine's tool table." Once linked, you can inherit member numbers from the
machine and diff the set against the machine's slots.

#### `link-machine`

```
loobric link-machine SET MACHINE
```

Link a tool set to a machine: record that the set mirrors that machine's tool
table. `SET` and `MACHINE` accept id prefixes. This asserts the set's
`machine_id` and is what enables `reconcile` and `coverage`. Prints a
confirmation naming the set and the machine it now mirrors.

#### `reconcile`

```
loobric reconcile SET
```

For a machine-linked set, set each member's tool number from the machine slot
that holds it — the machine is observed fact, so the set conforms. Prints a
confirmation. Members with no matching machine slot are reported (a count and
their short ids) and left with an unknown number, never silently renumbered.

#### `coverage`

```
loobric coverage SET
```

Read-only diff of a machine-linked set against the machine's tool table. For
each member it prints a status — `in sync`, `NUMBER MISMATCH` (with the number
the machine has it at), or `NOT ON MACHINE` — and flags any number collisions
between members. It then lists machine-only pockets (on the machine, not in the
set) and empty pockets, and ends with a summary line. When some tools are in the
set but not yet on the machine, it calls them out as "the tools to order/load."
If the set isn't linked to a machine, it says so and points you to
`link-machine`.

### Resolving the inbox

When a machine reports a tool the server does not recognize, the server may
propose a match. These proposals collect in the inbox.

#### `pending`

```
loobric pending
```

List inbox items awaiting review. For each: a short item id, the machine entry
(`T<n>`), the proposed matching record, and a confidence score with the reason.
This is an identity question — "is this the same tool?" — not a data conflict;
resolving it overwrites nothing on either side.

#### `resolve`

```
loobric resolve ITEM_ID {confirm|reject}
```

Resolve one inbox item. `ITEM_ID` is the item id or a unique prefix from
`pending`.

- `confirm` — "same tool": links the machine entry to the proposed record so
  future changes route between them. Both keep their data.
- `reject` — "different tools": drops the suggestion permanently. The entry stays
  unbound and keeps syncing.

If unsure, `reject`: a rejected pair can be linked manually later with `bind`,
while a wrong `confirm` is currently hard to undo.

### Managing bindings

A machine *entry* (a slot in a tool table, `T<n>`) can be linked to a *tool
record*. Binding never overwrites either side; it just routes future changes
between them.

#### `bind`

```
loobric bind MACHINE TOOL_NUMBER RECORD
```

Link an entry to an existing tool record. `MACHINE` and `RECORD` accept id
prefixes; `TOOL_NUMBER` is the integer slot (e.g. `3`).

#### `unbind`

```
loobric unbind MACHINE TOOL_NUMBER
```

Unbind an entry. The entry keeps its data and becomes eligible for future match
suggestions again.

#### `create-record`

```
loobric create-record MACHINE TOOL_NUMBER [--name NAME]
```

Adopt a machine entry: create a brand-new tool record seeded from the entry's
observed values and bind it, in one step. Use this when the machine has a tool
the server has never seen and you want to promote it to a record. `--name`
defaults to the entry's description. (This is the `adopt` operation; there is no
separate `adopt` command.)

### Removing data

All three deletes prompt for confirmation. Pass `--yes`/`-y` to skip the prompt;
in a non-interactive shell (no TTY) `--yes` is required.

#### `delete-entry`

```
loobric delete-entry MACHINE TOOL_NUMBER [--yes]
```

Remove a machine-reported tool-table entry. If the controller reports it again,
it returns.

#### `delete-tool`

```
loobric delete-tool RECORD [--yes]
```

Delete a tool record. Any entries bound to it are unbound (not orphaned); their
data stays on the machine.

#### `delete-machine`

```
loobric delete-machine MACHINE [--yes]
```

Delete a machine and its tool-table entries. Tool records are not affected.

## Walkthrough: from touch-off to a bound tool

This is the core loop: a tool gets measured at the machine, shows up on the
server, and you decide what it is. It assumes you have a running server (see
[QUICK_START.md](QUICK_START.md)) and have logged in.

### 1. A tool is touched off at the machine

On the shop floor, an operator measures tool 3 and the controller's tool table
gets a new entry. A client such as
[smooth-linuxcnc](https://github.com/loobric/smooth-linuxcnc) syncs that entry
up to the server. Nothing for you to type here — this is the event that starts
the workflow.

### 2. See what the machine reported

```bash
loobric list-machines
loobric tool-table <machine>
```

The new entry shows up as `unbound`:

```
T3: 1/4" downcut  ⌀6.35  [unbound]
```

### 3. Check the inbox

If the server found a likely match for T3, it proposes one:

```bash
loobric pending
```

```
  ID: 4f2a1c9b
  Machine entry: T3
  Proposed match: 1/4 in downcut, 2-flute
  Confidence: 88% - same diameter and flute count
```

### 4. Resolve it

If the proposal is right, confirm it. T3 is now linked to that record:

```bash
loobric resolve 4f2a confirm
```

If it is wrong (or you are unsure), reject it. T3 stays unbound:

```bash
loobric resolve 4f2a reject
```

### 5. No proposal? Bind or adopt by hand

The inbox only holds cases the server could guess at. For an unbound entry with
no proposal, you have two choices.

If a matching record already exists, link to it:

```bash
loobric list-tools                 # find the record id
loobric bind <machine> 3 <record>
```

If no record exists yet, promote the entry into a new record in one step:

```bash
loobric create-record <machine> 3 --name "1/4 downcut"
```

### 6. Confirm the result

```bash
loobric tool-table <machine>
```

T3 now reads `bound -> <record>`. From here, changes on either side route
between the entry and the record. If you ever got it wrong, `unbind <machine> 3`
puts the entry back to `unbound` without losing its data.
