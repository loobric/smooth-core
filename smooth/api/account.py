# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
Account-level operations.

`reset` wipes all of the caller's tool data — instance/catalog records, tool
sets, machines, tool-table entries, and open binding proposals — while keeping
the account itself and its API keys. It exists to make testing and demos easy:
return to a clean slate in one call. Admin-gated; in solo mode the built-in solo
user is an admin, so it works with no ceremony.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from smooth.api.auth import get_db
from smooth.api.backup_api import require_admin
from smooth.database.schema import (
    User, ToolInstanceRecord, ToolCatalogRecord, ToolTableEntryRecord,
    ToolSetRecord, MachineRecord, EntryProposal,
)
from smooth.audit import create_audit_log

router = APIRouter(prefix="/api/v1/account", tags=["account"])


@router.post("/reset")
def reset_account(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Delete ALL of the caller's tool data, keeping the account and API keys.
    Atomic. The account, its users, and its API keys are untouched."""
    uid = admin.id
    deleted = {}
    # Order: binding proposals → tool-table entries → records/sets/machines.
    for label, model in (
        ("binding_proposals", EntryProposal),
        ("tool_table_entries", ToolTableEntryRecord),
        ("tool_sets", ToolSetRecord),
        ("tool_instances", ToolInstanceRecord),
        ("tool_catalogs", ToolCatalogRecord),
        ("machines", MachineRecord),
    ):
        deleted[label] = db.query(model).filter(model.user_id == uid).delete()
    create_audit_log(session=db, user_id=uid, operation="RESET",
                     entity_type="account", entity_id=uid, changes=deleted)
    db.commit()
    return {"reset": True, "deleted": deleted}
