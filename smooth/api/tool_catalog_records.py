# GNU Affero General Public License v3.0 only
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: AGPL-3.0-only

"""
ToolCatalogRecord facade — a catalog TYPE (docs/TOOL_SCHEMA.md §7.1).

Mirrors the ToolInstanceRecord tracer exactly: the same three-section shape,
the same lane discipline, the same contract-validated responses. A catalog type
is a reusable, shareable definition (a manufacturer's published spec) that can
exist with zero owned instances.

The one meaningful difference from the instance tracer: a catalog type carries
**nominal, asserted** data — its geometry is the published spec, never a
measurement. A machine never measures a *type*, so there is deliberately **no
observe door** here. Canonical moves only through `assert` (deliberate, audited);
routine sync still cannot touch it.
"""
import copy
from datetime import datetime, UTC
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import User, ToolCatalogRecord as Row
from smooth.audit import create_audit_log
from smooth.contract import (
    ToolCatalogRecord, CatalogCanonical, Provenance, UNKNOWN,
    LaneViolation, reject_out_of_lane,
)

router = APIRouter(prefix="/api/v1/tool-catalog-records", tags=["tool-catalog-records"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _blank_canonical() -> dict:
    """A freshly-minted catalog type asserts nothing — its name is honestly
    unknown until asserted, and manufacturer/product_code/item_type/components
    are optional and simply absent until someone declares them."""
    return {
        "name": {"value": None, "source": UNKNOWN},
        "geometry": {},
    }


def _response(row: Row) -> dict:
    """Build the sectioned response and validate it against the contract — the
    server never emits a record that doesn't conform to its own schema."""
    doc = {
        "internal": {
            "id": row.id, "version": row.version,
            "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at),
        },
        "canonical": row.canonical,
        "clients": row.clients,
    }
    ToolCatalogRecord.model_validate(doc)
    return doc


def _owned(db: Session, user: User, record_id: str) -> Optional[Row]:
    return db.query(Row).filter(Row.id == record_id, Row.user_id == user.id).first()


def _validate_canonical(canonical: dict) -> None:
    try:
        CatalogCanonical.model_validate(canonical)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid canonical: %s" % exc)


def _set_path(canonical: dict, path: str, field: dict) -> dict:
    """Return a copy of canonical with the dotted `path` leaf set to `field`."""
    out = copy.deepcopy(canonical)
    node = out
    parts = path.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
        if not isinstance(node, dict):
            raise HTTPException(status_code=400, detail="path %r is not a section" % path)
    node[parts[-1]] = field
    return out


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateRequest(BaseModel):
    # optional initial client section (the creating client names itself here;
    # subsequent section writes name the client in the path instead)
    client: Optional[str] = None
    client_version: Optional[str] = None
    client_item_id: Optional[str] = None
    data: dict = {}


class AssertRequest(BaseModel):
    path: str
    value: Any = None
    unit: Optional[str] = None
    actor: str          # e.g. "catalog-import" or "human@inbox"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
def create_catalog(payload: CreateRequest, db: Session = Depends(get_db),
                   user: User = Depends(get_authenticated_user)):
    """Mint a catalog type. Canonical starts all-unknown; an optional initial
    client section may be seeded. Canonical is populated only via the assert
    door thereafter (a type is never observed)."""
    clients = {}
    if payload.client:
        clients[payload.client] = {
            "client_version": payload.client_version or "",
            "client_item_id": payload.client_item_id,
            "created_at": _now(), "updated_at": _now(),
            "data": payload.data or {},
        }
    row = Row(canonical=_blank_canonical(), clients=clients,
              user_id=user.id, created_by=user.id, updated_by=user.id)
    db.add(row)
    db.flush()
    create_audit_log(session=db, user_id=user.id, operation="CREATE",
                     entity_type="tool_catalog_record", entity_id=row.id)
    db.commit()
    return _response(row)


@router.get("")
def list_catalogs(db: Session = Depends(get_db),
                  user: User = Depends(get_authenticated_user)):
    rows = db.query(Row).filter(Row.user_id == user.id).order_by(Row.created_at).all()
    return {"items": [_response(r) for r in rows]}


@router.get("/{record_id}")
def get_catalog(record_id: str, db: Session = Depends(get_db),
                user: User = Depends(get_authenticated_user)):
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return _response(row)


@router.put("/{record_id}/clients/{client}")
def write_client_section(record_id: str, client: str, payload: dict,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_authenticated_user)):
    """Routine sync: write THIS client's section. The client is named by the
    path; the body is the envelope (`client_version`, `client_item_id`) + opaque
    `data`. A body carrying `internal`/`canonical`/stray keys is a 400."""
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        write = reject_out_of_lane(payload)          # lane discipline
    except LaneViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    clients = copy.deepcopy(row.clients)
    existing = clients.get(client) or {}
    clients[client] = {
        "client_version": write.client_version,
        "client_item_id": write.client_item_id,
        "created_at": existing.get("created_at") or _now(),   # server-stamped
        "updated_at": _now(),
        "data": write.data,
    }
    row.clients = clients
    row.version += 1
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="SYNC",
                     entity_type="tool_catalog_record", entity_id=row.id,
                     changes={"client": client})
    db.commit()
    return _response(row)


@router.post("/{record_id}/assert")
def assert_canonical(record_id: str, req: AssertRequest,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_authenticated_user)):
    """Deliberately declare a nominal canonical value (name, manufacturer,
    product_code, a published geometry dimension). Rare, audited. Stamps source
    asserted:<actor>. This is the ONLY door into a catalog type's canonical — a
    machine never measures a type, so there is no observe endpoint."""
    row = _owned(db, user, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    field = {"value": req.value, "source": Provenance.asserted(req.actor)}
    if req.unit is not None:
        field["unit"] = req.unit
    canonical = _set_path(row.canonical, req.path, field)
    _validate_canonical(canonical)
    row.canonical = canonical
    row.version += 1
    row.updated_by = user.id
    create_audit_log(session=db, user_id=user.id, operation="ASSERT",
                     entity_type="tool_catalog_record", entity_id=row.id,
                     changes={"path": req.path, "source": field["source"]})
    db.commit()
    return _response(row)
