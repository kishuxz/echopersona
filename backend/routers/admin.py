"""Admin panel backend router — operator-only, authenticated by X-Admin-Key header.

All endpoints use the service-role Supabase client which bypasses RLS.
No JWT required — this is a static-key-gated internal tool.

Endpoints:
  GET  /admin/stats
  GET  /admin/personas
  GET  /admin/personas/{persona_id}
  POST /admin/personas/{persona_id}/re-enrich
  POST /admin/personas/{persona_id}/relationships
  DELETE /admin/personas/{persona_id}/relationships/{listener_user_id}
"""
import logging
from collections import Counter
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from middleware.admin_auth import require_admin
from services.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ── Pydantic models ───────────────────────────────────────────────────────────

class AdminPersonaRow(BaseModel):
    id: str
    name: str
    readiness_status: str
    owner_email: str
    plan_tier: str
    memory_unit_count: int
    relationship_count: int
    created_at: Optional[str] = None


class AdminMemoryUnit(BaseModel):
    unit_id: str
    content_first_person: str
    memory_category: str
    verified: bool
    fidelity_score: float
    captured_at: Optional[str] = None


class AdminRelationship(BaseModel):
    id: str
    listener_user_id: str
    listener_email: str
    entity_canonical: str
    relationship: str
    address_term: str
    invite_id: Optional[str] = None
    created_at: Optional[str] = None


class AdminPersonaDetail(BaseModel):
    id: str
    name: str
    user_id: str
    readiness_status: str
    owner_email: str
    plan_tier: str
    tone: str
    avoid_phrases: list[str]
    answer_length_pref: str
    tavus_replica_id: Optional[str] = None
    voice_card: dict
    identity_card: dict
    created_at: Optional[str] = None
    recent_memory_units: list[AdminMemoryUnit]
    relationships: list[AdminRelationship]


class AdminStats(BaseModel):
    total_personas: int
    by_readiness: dict[str, int]
    total_users: int
    total_memory_units: int
    total_relationships: int
    plan_tier_counts: dict[str, int]


class AdminRelationshipCreate(BaseModel):
    listener_user_id: str
    entity_canonical: str
    relationship: str
    address_term: str = ""


class ReEnrichResponse(BaseModel):
    job_id: Optional[str]
    persona_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_email_map(db: Any) -> dict[str, str]:
    """Return {user_id: email} by paginating auth.users via the Admin API."""
    email_map: dict[str, str] = {}
    page = 1
    while True:
        try:
            batch = db.auth.admin.list_users(page=page, per_page=1000)
            users = batch.users if hasattr(batch, "users") else []
            for u in users:
                if u.id and u.email:
                    email_map[u.id] = u.email
            if len(users) < 1000:
                break
            page += 1
        except Exception as exc:
            logger.warning("admin: auth.users page %d failed: %s", page, exc)
            break
    return email_map


def _get_user_email(db: Any, user_id: str) -> str:
    try:
        resp = db.auth.admin.get_user_by_id(user_id)
        return resp.user.email if resp.user else ""
    except Exception as exc:
        logger.warning("admin: email lookup for %s failed: %s", user_id, exc)
        return ""


# ── GET /admin/stats ──────────────────────────────────────────────────────────

@router.get("/stats", response_model=AdminStats)
async def get_stats(request: Request):
    db = get_db()

    personas = db.table("personas").select("readiness_status").execute().data or []
    memory_units = db.table("memory_units").select("id", count="exact").execute()
    relationships = db.table("persona_relationships").select("id", count="exact").execute()
    entitlements = db.table("stripe_entitlements").select("plan_tier").execute().data or []

    by_readiness: dict[str, int] = Counter(p["readiness_status"] for p in personas)
    plan_tier_counts: dict[str, int] = Counter(e["plan_tier"] for e in entitlements)

    total_users = 0
    try:
        batch = db.auth.admin.list_users(page=1, per_page=1)
        total_users = getattr(batch, "total", 0) or 0
    except Exception as exc:
        logger.warning("admin: user count failed: %s", exc)

    return AdminStats(
        total_personas=len(personas),
        by_readiness=dict(by_readiness),
        total_users=total_users,
        total_memory_units=memory_units.count or 0,
        total_relationships=relationships.count or 0,
        plan_tier_counts=dict(plan_tier_counts),
    )


# ── GET /admin/personas ───────────────────────────────────────────────────────

@router.get("/personas", response_model=list[AdminPersonaRow])
async def list_personas(request: Request):
    db = get_db()

    personas = db.table("personas").select("id,name,readiness_status,user_id,created_at").execute().data or []
    if not personas:
        return []

    email_map = _build_email_map(db)

    ent_rows = db.table("stripe_entitlements").select("user_id,plan_tier").execute().data or []
    plan_map = {e["user_id"]: e["plan_tier"] for e in ent_rows}

    unit_rows = db.table("memory_units").select("persona_id").execute().data or []
    unit_counts: Counter = Counter(u["persona_id"] for u in unit_rows)

    rel_rows = db.table("persona_relationships").select("persona_id").execute().data or []
    rel_counts: Counter = Counter(r["persona_id"] for r in rel_rows)

    return [
        AdminPersonaRow(
            id=p["id"],
            name=p["name"],
            readiness_status=p["readiness_status"] or "unknown",
            owner_email=email_map.get(p["user_id"], ""),
            plan_tier=plan_map.get(p["user_id"], "free"),
            memory_unit_count=unit_counts.get(p["id"], 0),
            relationship_count=rel_counts.get(p["id"], 0),
            created_at=p.get("created_at"),
        )
        for p in personas
    ]


# ── GET /admin/personas/{persona_id} ─────────────────────────────────────────

@router.get("/personas/{persona_id}", response_model=AdminPersonaDetail)
async def get_persona_detail(persona_id: str, request: Request):
    db = get_db()

    p_row = db.table("personas").select("*").eq("id", persona_id).maybe_single().execute()
    if not p_row.data:
        raise HTTPException(status_code=404, detail="Persona not found")
    p = p_row.data

    owner_email = _get_user_email(db, p["user_id"])
    ent = db.table("stripe_entitlements").select("plan_tier").eq("user_id", p["user_id"]).maybe_single().execute()
    plan_tier = ent.data["plan_tier"] if ent.data else "free"

    units_raw = (
        db.table("memory_units")
        .select("id,content_first_person,memory_category,verified,fidelity_score,captured_at")
        .eq("persona_id", persona_id)
        .order("captured_at", desc=True)
        .limit(10)
        .execute()
        .data or []
    )
    recent_units = [
        AdminMemoryUnit(
            unit_id=u["id"],
            content_first_person=u.get("content_first_person", ""),
            memory_category=u.get("memory_category", ""),
            verified=bool(u.get("verified")),
            fidelity_score=float(u.get("fidelity_score") or 0.0),
            captured_at=u.get("captured_at"),
        )
        for u in units_raw
    ]

    rel_rows = (
        db.table("persona_relationships")
        .select("id,listener_user_id,entity_canonical,relationship,address_term,invite_id,created_at")
        .eq("persona_id", persona_id)
        .execute()
        .data or []
    )
    relationships = []
    for r in rel_rows:
        member_email = _get_user_email(db, r["listener_user_id"]) if r.get("listener_user_id") else ""
        relationships.append(AdminRelationship(
            id=r["id"],
            listener_user_id=r["listener_user_id"],
            listener_email=member_email,
            entity_canonical=r.get("entity_canonical", ""),
            relationship=r.get("relationship", ""),
            address_term=r.get("address_term", ""),
            invite_id=r.get("invite_id"),
            created_at=r.get("created_at"),
        ))

    return AdminPersonaDetail(
        id=p["id"],
        name=p["name"],
        user_id=p["user_id"],
        readiness_status=p.get("readiness_status", "unknown"),
        owner_email=owner_email,
        plan_tier=plan_tier,
        tone=p.get("tone", ""),
        avoid_phrases=p.get("avoid_phrases") or [],
        answer_length_pref=p.get("answer_length_pref", ""),
        tavus_replica_id=p.get("tavus_replica_id"),
        voice_card=p.get("voice_card") or {},
        identity_card=p.get("identity_card") or {},
        created_at=p.get("created_at"),
        recent_memory_units=recent_units,
        relationships=relationships,
    )


# ── POST /admin/personas/{persona_id}/re-enrich ───────────────────────────────

@router.post("/personas/{persona_id}/re-enrich", response_model=ReEnrichResponse)
async def re_enrich(persona_id: str, request: Request):
    db = get_db()

    p_row = db.table("personas").select("readiness_status").eq("id", persona_id).maybe_single().execute()
    if not p_row.data:
        raise HTTPException(status_code=404, detail="Persona not found")
    if p_row.data.get("readiness_status") == "processing":
        raise HTTPException(status_code=409, detail="Re-enrichment already in progress")

    arq_pool = getattr(request.app.state, "arq_pool", None)
    job_id: Optional[str] = None
    if arq_pool:
        job = await arq_pool.enqueue_job("enrich_persona", persona_id)
        job_id = job.job_id if job else None
    else:
        logger.warning("admin: arq_pool not available — re-enrich skipped for %s", persona_id)

    return ReEnrichResponse(job_id=job_id, persona_id=persona_id)


# ── POST /admin/personas/{persona_id}/relationships ───────────────────────────

@router.post("/personas/{persona_id}/relationships", status_code=201, response_model=AdminRelationship)
async def add_relationship(persona_id: str, body: AdminRelationshipCreate, request: Request):
    db = get_db()

    p_row = db.table("personas").select("id").eq("id", persona_id).maybe_single().execute()
    if not p_row.data:
        raise HTTPException(status_code=404, detail="Persona not found")

    existing = (
        db.table("persona_relationships")
        .select("id")
        .eq("persona_id", persona_id)
        .eq("listener_user_id", body.listener_user_id)
        .maybe_single()
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Relationship already exists")

    result = (
        db.table("persona_relationships")
        .insert({
            "persona_id": persona_id,
            "listener_user_id": body.listener_user_id,
            "entity_canonical": body.entity_canonical,
            "relationship": body.relationship,
            "address_term": body.address_term,
        })
        .execute()
    )
    row = result.data[0]
    member_email = _get_user_email(db, body.listener_user_id)

    return AdminRelationship(
        id=row["id"],
        listener_user_id=row["listener_user_id"],
        listener_email=member_email,
        entity_canonical=row.get("entity_canonical", ""),
        relationship=row.get("relationship", ""),
        address_term=row.get("address_term", ""),
        invite_id=None,
        created_at=row.get("created_at"),
    )


# ── DELETE /admin/personas/{persona_id}/relationships/{listener_user_id} ──────

@router.delete("/personas/{persona_id}/relationships/{listener_user_id}", status_code=200)
async def remove_relationship(persona_id: str, listener_user_id: str, request: Request):
    db = get_db()

    existing = (
        db.table("persona_relationships")
        .select("id")
        .eq("persona_id", persona_id)
        .eq("listener_user_id", listener_user_id)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Relationship not found")

    db.table("persona_relationships").delete().eq("persona_id", persona_id).eq("listener_user_id", listener_user_id).execute()
    return {"deleted": True}
