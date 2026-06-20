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
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smooth.api.auth import get_db, get_authenticated_user
from smooth.database.schema import User, ToolCatalogRecord as Row
from smooth.audit import create_audit_log
from smooth.contract import (
    ToolCatalogRecord, CatalogCanonical, Provenance,
    LaneViolation, reject_out_of_lane,
)

router = APIRouter(prefix="/api/v1/tool-catalog-records", tags=["tool-catalog-records"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


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


def _norm(value) -> Optional[str]:
    """Comparison form of an identity field: trim + casefold. Without it the
    natural-key constraint is illusory ("Kennametal" vs "kennametal ")."""
    if value is None:
        return None
    return str(value).strip().casefold()


def _natural_key(canonical: dict) -> tuple:
    """Extract the normalized (manufacturer, product_code) from canonical — the
    values that back the per-account unique index."""
    man = (canonical.get("manufacturer") or {}).get("value")
    pc = (canonical.get("product_code") or {}).get("value")
    return _norm(man), _norm(pc)


def _stamp_natural_key(row: Row, canonical: dict) -> None:
    """Server-maintain the extracted, normalized natural-key columns. Mirrors the
    entry tracer stamping its install-once `bound_instance_id` column — one
    enforcement point shared by every canonical write (create and assert)."""
    row.manufacturer_norm, row.product_code_norm = _natural_key(canonical)


def _collision_409(db: Session, user: User, canonical: dict) -> HTTPException:
    """Turn a unique-index violation into the reuse funnel: name the existing
    record and invite reuse, never a bare 'duplicate'. The lookup is only for the
    friendly message — the DB index, not this query, is what enforces uniqueness."""
    man_norm, pc_norm = _natural_key(canonical)
    existing = db.query(Row).filter(
        Row.user_id == user.id,
        Row.manufacturer_norm == man_norm,
        Row.product_code_norm == pc_norm,
    ).first()
    man = (canonical.get("manufacturer") or {}).get("value")
    pc = (canonical.get("product_code") or {}).get("value")
    where = existing.id if existing is not None else "an existing record"
    return HTTPException(
        status_code=409,
        detail="%s %s already exists as %s — create an instance from it, or "
               "edit that record." % (man, pc, where))


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

class NominalField(BaseModel):
    """A client-supplied nominal value (+ optional unit) for the seeded create.
    The client NEVER sends `source` — the server stamps asserted:<actor> on each.
    `extra="forbid"` is what makes that lane discipline real: a leaf that smuggles
    in `source` (or any stray key) fails validation, which the API turns into a
    422/400 — provenance is the server's to write, not the client's."""

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    unit: Optional[str] = None


class CreateRequest(BaseModel):
    """Seeded, atomic catalog-type create. One declared `actor` plus the nominal
    fields as bare {value, unit} leaves; the server stamps asserted:<actor> as
    each field's source. Identity floor: name/manufacturer/product_code are
    required (checked in the endpoint for a clear message). Spec fields
    (geometry, item_type) are optional and honest-sparse. `extra="forbid"` keeps
    the client out of the internal/canonical lane — a stray top-level `source`
    or section is rejected, never silently stripped."""

    model_config = ConfigDict(extra="forbid")

    actor: str
    # identity floor — required, non-null (enforced in the endpoint)
    name: Optional[NominalField] = None
    manufacturer: Optional[NominalField] = None
    product_code: Optional[NominalField] = None
    # optional, honest-sparse nominal spec
    geometry: Dict[str, NominalField] = {}
    item_type: Optional[NominalField] = None
    # optional initial client section (the creating client names itself here;
    # subsequent section writes name the client in the path instead)
    client: Optional[str] = None
    client_version: Optional[str] = None
    client_item_id: Optional[str] = None
    client_data: dict = {}


class AssertRequest(BaseModel):
    path: str
    value: Any = None
    unit: Optional[str] = None
    actor: str          # e.g. "catalog-import" or "human@inbox"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
def create_catalog_record(req: CreateRequest, db: Session = Depends(get_db),
                          user: User = Depends(get_authenticated_user)):
    """Seeded, atomic create of a catalog type. The request carries one declared
    `actor` plus nominal {value, unit} fields; the server stamps asserted:<actor>
    as each field's source (lane discipline — the client never writes
    provenance). Identity floor: name/manufacturer/product_code are required and
    non-null (findability/de-dup, not spec completeness). Spec fields are
    optional and honest-sparse — a record with no geometry is accepted, never
    fabricated to pass a gate. All-or-nothing: a malformed request leaves no
    half-built record, and a success writes exactly one CREATE audit row."""
    actor = (req.actor or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required")

    # Identity floor: required and non-null. Findability/de-dup, not spec.
    for fld in ("name", "manufacturer", "product_code"):
        leaf = getattr(req, fld)
        if leaf is None or leaf.value is None:
            raise HTTPException(
                status_code=400,
                detail="identity floor: %s is required (name, manufacturer and "
                       "product_code identify the record)" % fld)

    def _stamp(leaf: NominalField) -> dict:
        """Seed one canonical leaf — value + (optional) unit + server-stamped
        provenance. The actor is the ONLY thing the client declares about
        source."""
        field = {"value": leaf.value, "source": Provenance.asserted(actor)}
        if leaf.unit is not None:
            field["unit"] = leaf.unit
        return field

    canonical = {
        "name": _stamp(req.name),
        "manufacturer": _stamp(req.manufacturer),
        "product_code": _stamp(req.product_code),
        "geometry": {k: _stamp(v) for k, v in req.geometry.items()},
    }
    if req.item_type is not None:
        canonical["item_type"] = _stamp(req.item_type)
    # Validate the whole canonical BEFORE any DB write — a malformed seed is
    # rejected with no half-built record (atomicity).
    _validate_canonical(canonical)

    clients = {}
    if req.client:
        clients[req.client] = {
            "client_version": req.client_version or "",
            "client_item_id": req.client_item_id,
            "created_at": _now(), "updated_at": _now(),
            "data": req.client_data or {},
        }
    row = Row(canonical=canonical, clients=clients,
              user_id=user.id, created_by=user.id, updated_by=user.id)
    _stamp_natural_key(row, canonical)   # server-maintained; feeds the unique index
    db.add(row)
    try:
        db.flush()                        # the unique index fires here, race-safe
    except IntegrityError:
        db.rollback()
        raise _collision_409(db, user, canonical)
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
    _stamp_natural_key(row, canonical)   # same enforcement point as create
    row.version += 1
    row.updated_by = user.id
    try:
        db.flush()                        # editing into a collision is a 409 too
    except IntegrityError:
        db.rollback()
        raise _collision_409(db, user, canonical)
    create_audit_log(session=db, user_id=user.id, operation="ASSERT",
                     entity_type="tool_catalog_record", entity_id=row.id,
                     changes={"path": req.path, "source": field["source"]})
    db.commit()
    return _response(row)
