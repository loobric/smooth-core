# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Admin-only, server-wide operations.

`wipe` is a FACTORY RESET: it deletes ALL data, ALL accounts, and ALL API keys —
including the administrator who calls it. After it runs the database is empty and
the next account to register becomes the new admin (first-user-is-admin). It
exists to return a shared/sandbox deployment to a clean slate in one call.

It is guarded two ways: admin-only, and the caller must echo an exact
confirmation phrase in the body. There is no undo.

Distinct from `POST /api/v1/account/reset`, which wipes only the caller's *tool
data* and keeps every account and key.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, clear_all_sessions
from smooth.api.backup_api import require_admin
from smooth.database.schema import Base, User

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# The caller must echo this exactly — a deliberate, un-fat-fingerable phrase so a
# factory reset can never be a stray click or a default-empty body.
WIPE_CONFIRMATION = "WIPE ALL DATA AND ACCOUNTS"


class WipeRequest(BaseModel):
    confirm: str = ""


@router.post("/wipe")
def wipe_everything(
    request: WipeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """FACTORY RESET — delete ALL data, accounts, and API keys (incl. the admin).

    Requires admin authentication AND an exact confirmation phrase. There is no
    undo. After this the database is empty; the next registration becomes the new
    admin. The schema and migration history are left intact.
    """
    if request.confirm != WIPE_CONFIRMATION:
        raise HTTPException(
            status_code=400,
            detail=f"Refused. To wipe EVERYTHING (all data, accounts, and keys, "
                   f"including your own), set confirm to exactly "
                   f"'{WIPE_CONFIRMATION}'. There is no undo.",
        )

    # Delete every ORM-mapped table, children before parents (reverse FK order),
    # so users/keys are removed last without violating foreign keys. The
    # `schema_migrations` ledger is a raw table (not ORM-mapped), so the schema
    # and migration state survive — this empties the data, it doesn't un-migrate.
    deleted = {}
    for table in reversed(Base.metadata.sorted_tables):
        result = db.execute(table.delete())
        if result.rowcount:
            deleted[table.name] = result.rowcount
    db.commit()

    # Sessions live in memory, not the DB — clear them too, so no stale cookie
    # maps to a now-deleted user.
    clear_all_sessions()

    return {"wiped": True, "deleted": deleted}
