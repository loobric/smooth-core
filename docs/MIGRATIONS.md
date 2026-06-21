# Schema Migrations — Design

> Status: **proposed** (2026-06-21). This is a design for review, not yet implemented.
> It addresses the top data-durability gap: today an upgrade that changes an existing
> table breaks a populated database with a silent `no such column` 500, and there is no
> way to tell what schema version a database is at.

## The problem (what exists today)

- `init_db()` (`smooth/database/session.py`) calls SQLAlchemy `create_all`, which creates
  **missing tables only**. It never adds columns to, or alters, existing tables — the code
  comment says so, and notes it *"bit production on the v2 cutover."*
- There is **no schema-version record** anywhere in the database. Nothing can answer
  "what version is this DB at?"
- Schema changes ship as **bespoke one-off scripts** (`scripts/migrate_m2_catalog_natural_key.py`)
  that a human must know about and run by hand. There is no registry, no ordering, no
  record of what ran.
- **Backup/restore** checks only the backup's *major* version, not whether the backup's
  schema is compatible with the running code. Restoring across a schema change fails with
  no recovery path.
- A `docker pull` of a release with a schema change → crash on first use.

## Design goals & constraints

1. **SQLite-first.** SQLite is the supported database; the spine must work within SQLite's
   limited `ALTER TABLE` (add-column is fine; drops/renames need the create-copy-swap
   pattern). PostgreSQL is exploratory — the design must not *assume* it, but must not
   preclude it.
2. **No heavy dependency.** Alembic was deliberately removed. The spine is a small,
   in-repo runner — a few hundred lines, no new runtime dep.
3. **Automatic and safe on startup.** Self-hosters upgrade by `docker pull` + restart.
   Migrations must run automatically, take a backup first, run transactionally, and on
   any failure **stop the server loudly** rather than serve a half-migrated database.
4. **Forward-only.** No down-migrations (consistent with the project's "freeze + human
   resolve, no three-way merge" ethos). Rollback = restore the pre-migration backup.
5. **Idempotent migrations.** Each migration checks before it acts (the existing M2 script
   already does this with a column-existence guard). Idempotency is belt-and-suspenders
   against imperfect baseline detection on legacy databases — **and it is mandatory on
   SQLite**, where the driver auto-commits before DDL, so a `CREATE`/`ALTER` that later
   fails is *not* rolled back. A failed migration is never recorded, so it is retried on the
   next boot; the idempotent guard makes that retry safe over partially-applied state.

## The spine

### 1. A version ledger: `schema_migrations`

One small table, the source of truth for "what has been applied":

| column | meaning |
|---|---|
| `revision` | zero-padded ordinal, e.g. `0002` — the migration's identity and sort key |
| `name` | human label, e.g. `m2_catalog_natural_key` |
| `applied_at` | UTC timestamp |
| `checksum` | hash of the migration source, to detect a migration edited after it ran |

The **current schema version** is `MAX(revision)` in this table.

### 2. Migration units: `smooth/migrations/NNNN_name.py`

Each migration is a Python module — full flexibility for SQLite's create-copy-swap pattern,
unlike raw `.sql`:

```python
revision = "0002"
name = "m2_catalog_natural_key"

def upgrade(conn):
    """Idempotent. Receives a live DB-API connection inside a transaction."""
    if "manufacturer_norm" in _columns(conn, "tool_catalog_records"):
        return  # already applied
    conn.execute("ALTER TABLE tool_catalog_records ADD COLUMN manufacturer_norm TEXT")
    ...
```

The existing `scripts/migrate_m2_catalog_natural_key.py` becomes migration `0002`
(see baseline below for why it isn't `0001`) essentially unchanged — it is already idempotent.

### 3. The runner: `run_migrations(engine)`

```
ensure schema_migrations exists
applied  = {rows in schema_migrations}
defined  = discover smooth/migrations/*.py, sorted by revision
pending  = [m for m in defined if m.revision not in applied]
if pending:
    take ONE timestamped backup before the batch (reuse smooth/backup.py)
    for m in pending:
        with engine.begin() as conn:   # transactional per migration
            m.upgrade(conn)
            record (revision, name, now, checksum) into schema_migrations
    log "migrated 000X → 000Y"
on any exception: log the failed revision + the backup path, re-raise → startup aborts
```

### 4. Baseline — the one genuinely hard part

Three database states must be handled:

- **Fresh DB (no tables).** `create_all` builds every current table from the models. The DB
  is already at head, so the runner **stamps every known migration as applied** without
  running them.
- **Legacy populated DB (tables exist, no `schema_migrations`).** Introduce the spine with a
  `0001_baseline` revision that represents "the schema as shipped at spine introduction."
  Stamp `0001` as applied (its `upgrade` is a no-op assertion that core tables exist), then
  apply anything newer. Migrations that legacy DBs may genuinely be missing (like the M2
  columns) live at `0002+` and, being idempotent, are safe to run whether or not the manual
  script was already applied.
- **Spine-managed DB.** Normal case: apply pending, done.

Detection: *tables exist but `schema_migrations` is absent* ⇒ legacy ⇒ stamp baseline.
*No tables* ⇒ fresh ⇒ `create_all` + stamp all. *`schema_migrations` present* ⇒ managed.

### 5. Startup wiring

`init_db()` becomes:

```
create_all(engine)        # greenfield bootstrap; no-op on existing tables
run_migrations(engine)    # baseline-stamp and/or apply pending
```

`create_all` stays as the greenfield path so the model definitions remain the DDL source for
*new* installs; migrations own all *changes to existing* installs.

## Closing the backup/restore drift gap

- Stamp the **schema revision** into backup metadata at export time.
- At restore:
  - backup revision **==** head → restore directly.
  - backup revision **<** head → restore, then `run_migrations` forward.
  - backup revision **>** head → **refuse** (cannot downgrade), with a clear message.

This makes "restore an old backup into a newer server" a supported, tested path instead of a
silent failure, and lets the README's "backup and restore … with rollback" claim become true.

## Out of scope here (separate decision): solo → multi-user

This is a **data-ownership** migration, not a schema migration, but it's the other way user
data gets stranded (the solo user's password is generated and discarded, so its data is
unreachable once `SMOOTH_SOLO` is unset). Proposed companion, to be specified separately:
an admin-gated `POST /api/v1/account/adopt-solo` (CLI: `loobric adopt-solo`) that reassigns
all rows owned by `solo@localhost.smooth` to a named real account, run once when promoting a
solo instance to multi-user. Tracked alongside the spine but designed on its own.

## Phased implementation

1. **Ledger + runner + baseline**, `schema_migrations` table, `0001_baseline`. Wire into
   `init_db()`. Test: fresh DB, legacy DB, managed DB.
2. **Adopt the M2 script** as `0002`. Test: a pre-M2 DB upgrades cleanly on startup with no
   manual step.
3. **Backup metadata revision + restore drift handling.** Test: restore older backup → auto
   forward-migrate; reject newer.
4. **solo→multi-user adopt** (own design doc).

Test matrix lives in `tests/integration/test_migrations.py` (new): fresh / legacy / managed
boot paths, idempotent re-run, failure-aborts-startup, and the three restore-drift cases.
