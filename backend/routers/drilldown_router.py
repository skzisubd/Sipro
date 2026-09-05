"""Drill-down KPI lintas modul (Fase 92)."""
from fastapi import APIRouter, Depends, HTTPException, Request

import kpi_drilldown as kd
from security import get_current_user

router = APIRouter(prefix="/drilldown", tags=["drilldown"])


LEAD_KPIS = [
    {"key": "new24", "label": "Lead baru 24 jam", "tone": "primary", "params": {"new_hours": "24"}},
    {"key": "hot", "label": "Lead panas (hot)", "tone": "rose", "params": {"band": "hot"}},
    {"key": "sla", "label": "Melewati SLA tahap", "tone": "amber", "params": {"sla": "breached"}},
    {"key": "idle7", "label": "Diam ≥ 7 hari", "tone": "sky", "params": {"idle_days": "7"}},
    {"key": "won", "label": "Menang (won)", "tone": "emerald", "params": {"stage": "won"}},
]


@router.get("/_summary/leads")
async def leads_summary(user: dict = Depends(get_current_user)):
    """Angka kartu KPI Pipeline Lead — dihitung dengan definisi yang SAMA dengan rinciannya."""
    if not await kd.allowed(user, "leads"):
        raise HTTPException(status_code=403, detail="Peran Anda tidak boleh membaca lead.")
    out = []
    for k in LEAD_KPIS:
        d = await kd.drilldown(user, "leads", k["params"])
        out.append({**k, "value": d["count"], "drill": d["href_all"]})
    return {"data": out}


@router.get("/{key}")
async def drilldown(key: str, request: Request, user: dict = Depends(get_current_user)):
    """Baris penyusun satu angka KPI (Beranda/Lead/Pembangunan/Keuangan) + tautan terfilter."""
    if not await kd.allowed(user, key):
        raise HTTPException(status_code=403, detail="Peran Anda tidak boleh membuka rincian angka ini.")
    try:
        return {"data": await kd.drilldown(user, key, dict(request.query_params))}
    except KeyError:
        raise HTTPException(status_code=404, detail="Kunci KPI tidak dikenal.")
