# loobric CLI

`loobric` is the command-line client for a Smooth Core server. Use it to create
a user, manage API keys, inspect machines and tool records, and review and
resolve the binding inbox.

This page has two parts:

- [Command reference](#command-reference) — every subcommand, its arguments, and
  what it prints.
- [Walkthrough: from touch-off to a bound tool](#walkthrough-from-touch-off-to-a-bound-tool)
  — the core workflow, end to end.

Goal-oriented walkthroughs that span a CNC control and a CAM library are TBD.

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

Many commands resolve a machine, record, or tool set by its **id, its name, or
a unique id-prefix**: like a git short SHA, you can pass the first few characters
of an id as long as the prefix is unique, or pass the full name. An ambiguous
value prints the candidates and exits.

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

#### `whoami`

```
loobric whoami
```

Show the authenticated account: email, role, admin flag, and id. This needs a
session (or an API key), so it reports "not authenticated" under solo mode,
which has no session.

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

### Machines and tools

#### `create-machine`

```
loobric create-machine NAME [--controller TYPE]
```

Create a machine and assert its name. `--controller` records the controller type
(e.g. `linuxcnc`). Prints the new machine's name and short id.

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
`MACHINE` is a machine id, name, or unique prefix. Each line shows the tool
number, description, diameter (when reported), and bind state: either `unbound`
or `bound -> <record-prefix>`.

#### `push`

```
loobric push MACHINE --entry "N[:DESC[:DIA]]" [--entry ...] [--client NAME] [--snapshot]
```

The controller-side tool-table sync: upsert tool-table entries on a machine by
tool number. `MACHINE` is a machine id, name, or unique prefix. Each `--entry`
is a tool number with an optional description and diameter (mm), e.g.
`--entry "3:1/4 downcut:6.35"`; the flag is repeatable. `--client` stamps the
client name on the push (default `loobric`). `--snapshot` makes the push
authoritative — entries absent from it are removed — and the removed tool
numbers are printed. Prints how many entries were pushed.

### Tool sets

A tool set is a named collection of tool records. It can optionally be **linked**
to a machine (see `link-machine`); once linked, its member numbers are inherited
from that machine's tool-table entries.

#### `create-set`

```
loobric create-set NAME
```

Create a tool set and assert its name. Prints the new set's name and short id.

#### `link-machine`

```
loobric link-machine SET MACHINE
```

Link a tool set to a machine so its member numbers are inherited from that
machine's tool-table entries. `SET` and `MACHINE` accept an id, name, or unique
prefix. This asserts the set's `machine_id`. Prints a confirmation naming the set
and the machine it is now linked to.

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

A machine *entry* (a row in a tool table, `T<n>`) can be linked to a *tool
record*. Binding never overwrites either side; it just routes future changes
between them.

#### `bind`

```
loobric bind MACHINE TOOL_NUMBER RECORD
```

Link an entry to an existing tool record. `MACHINE` and `RECORD` accept an id,
name, or unique prefix; `TOOL_NUMBER` is the integer tool number (e.g. `3`).

#### `unbind`

```
loobric unbind MACHINE TOOL_NUMBER
```

Unbind an entry. The entry keeps its data and becomes eligible for future match
suggestions again.

#### `create-record`

```
loobric create-record MACHINE TOOL_NUMBER [--name NAME]
loobric create-record --from-catalog CATALOG [--name NAME]
```

Context-aware: it creates a tool instance from one of two sources, and the
outcome differs by bind state.

- **Entry form** (`MACHINE TOOL_NUMBER`): seed a brand-new instance from a
  machine entry's observed values and **bind** it to that tool-table position,
  in one step. Use this when the machine has a tool the server has never seen.
  `--name` defaults to the entry's description.
- **Catalog form** (`--from-catalog CATALOG`): create an instance from a catalog
  record (resolved by id / unique prefix / name / product code) and leave it
  **unbound** — a catalog is a type, not a machine position. The new instance
  links the catalog via `catalog_type_id`; measured geometry and status stay
  unknown (nominal geometry is reachable through the link). `--name` defaults to
  the catalog record's name. Each call yields a new, distinct instance.

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

### The canonical assert door

#### `assert`

```
loobric assert RESOURCE RECORD_ID PATH VALUE
```

Set a canonical field directly — the canonical "assert" door. `RESOURCE` is a
record collection (e.g. `tool-set-records`, `machine-records`), `RECORD_ID` is
the record id, `PATH` is the canonical path (e.g. `name`), and `VALUE` is the
new value. `VALUE` is JSON-parsed when possible (so numbers, booleans, and JSON
objects work), otherwise it is treated as a plain string. For example:

```bash
loobric assert tool-set-records <id> name "Aluminum job"
```

### Admin and housekeeping

#### `audit`

```
loobric audit [--limit N]
```

Show recent audit-log entries — operation, entity type, short entity id, and
time, one per line. `--limit` caps how many are shown (default 50).

#### `reset`

```
loobric reset [--yes]
```

Wipe **all** tool data for the account — records, sets, machines, and
tool-table entries — keeping the login and API keys. Admin operation. Prompts
for confirmation; pass `--yes`/`-y` to skip it (required in a non-interactive
shell). Prints how many items were deleted.

#### `backup-export`

```
loobric backup-export [--out FILE]
```

Export a full account backup as JSON (admin). Writes to `--out FILE` when given,
otherwise to stdout.

#### `backup-import`

```
loobric backup-import FILE
```

Restore an account backup from a JSON file (admin). `FILE` is the path to a
backup produced by `backup-export`.

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

### 5. No proposal? Bind or create a record by hand

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

## Using loobric as a library

`loobric.py` is MIT-licensed and importable. The same `Client` class the CLI
uses is the reference implementation other Python clients (FreeCAD, etc.) reuse,
so you don't have to write your own HTTP client:

```python
from loobric import Client, NotFound, LoobricError

c = Client(base_url="http://nas:8000", api_key="…")   # solo mode: api_key optional

for s in c.list_tool_sets():
    ...

c.create_machine("millstone", controller_type="linuxcnc")

try:
    c.get_machine(machine_id)
except NotFound:
    ...
```

Client methods return parsed data and raise `LoobricError` subclasses on
failure — `NotFound`, `AuthRequired`, `HTTPError`, and `ConnectionFailed` — so
callers handle errors instead of parsing printed output. The module is
single-file and stdlib-only, so clients can vendor `loobric.py` directly.
