"""/api/wa — konfigurasi integrasi WhatsApp, antrean kontak → lead, simulasi pesan masuk."""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

import wa_contacts as wc
import wa_gateway as gw
import wa_inbound as wi
from db import db, ORG_ID
from rbac import audit_log, require_permission

router = APIRouter(prefix="/wa", tags=["whatsapp"])


class ConfigIn(BaseModel):
    mode: Optional[str] = None
    token: Optional[str] = None
    phone_id: Optional[str] = None
    waba_id: Optional[str] = None
    app_secret: Optional[str] = None
    verify_token: Optional[str] = None
    is_active: Optional[bool] = None


class TestMessageIn(BaseModel):
    to: str
    body: str = "Pesan uji dari SIPRO — integrasi WhatsApp berfungsi."


class ImportIn(BaseModel):
    text: str
    label: Optional[str] = None


class CaptureIn(BaseModel):
    ids: List[str] = []
    all_new: bool = False
    phones: List[str] = []
    policy_lead: str = "skip"      # skip | link
    policy_customer: str = "create"  # skip | create
    assigned_to: Optional[str] = None
    campaign: Optional[str] = None


class StatusIn(BaseModel):
    reason: Optional[str] = None


class SimulateIn(BaseModel):
    phone: str
    name: Optional[str] = None
    message: Optional[str] = "Halo, saya tertarik dengan unitnya. Boleh info harga?"
    mtype: str = "text"
    filename: Optional[str] = None


# ------------------------------------------------------------------ konfigurasi
@router.get("/config")
async def get_config(user: dict = Depends(require_permission("settings", "view"))):
    return {"data": await gw.status_summary(user.get("org_id", ORG_ID))}


@router.put("/config")
async def put_config(p: ConfigIn, user: dict = Depends(require_permission("settings", "manage"))):
    org = user.get("org_id", ORG_ID)
    if p.mode and p.mode not in ("simulation", "live"):
        raise HTTPException(400, "Mode harus simulation atau live")
    creds = {k: getattr(p, k) for k in gw.CRED_KEYS}
    if p.mode == "live":
        cur = await gw.get_config(org)
        merged = {k: (creds[k].strip() if creds[k] and creds[k] != "__clear__" else ("" if creds[k] == "__clear__" else cur["creds"][k]))
                  for k in gw.CRED_KEYS}
        if not (merged["token"] and merged["phone_id"]):
            raise HTTPException(400, "Mode live membutuhkan minimal WHATSAPP_TOKEN dan WHATSAPP_PHONE_ID.")
    cfg = await gw.save_config(org, mode=p.mode, creds=creds, actor=user.get("email"))
    if p.is_active is not None:
        await db.channel_accounts.update_one({"id": cfg["channel"]["id"]}, {"$set": {"is_active": p.is_active}})
    await audit_log(user, "update", "wa_config", cfg["channel"]["id"],
                    {"mode": p.mode, "fields": [k for k in gw.CRED_KEYS if creds.get(k)]})
    return {"data": await gw.status_summary(org)}


@router.post("/config/test")
async def test_connection(user: dict = Depends(require_permission("settings", "manage"))):
    return {"data": await gw.probe(user.get("org_id", ORG_ID))}


@router.post("/config/test-message")
async def test_message(p: TestMessageIn, user: dict = Depends(require_permission("settings", "manage"))):
    msg = await gw.send(user.get("org_id", ORG_ID), p.to, kind="test", body=p.body, actor=user.get("email"))
    return {"data": {k: msg.get(k) for k in ("id", "status", "mode", "provider_message_id", "error_code", "error_detail", "to")}}


# ------------------------------------------------------------------ antrean kontak
@router.get("/contacts")
async def list_contacts(status: str = "", q: str = "", source: str = "", dup: str = "", skip: int = 0,
                        limit: int = 50, user: dict = Depends(require_permission("leads", "view_all"))):
    limit = max(1, min(limit, 200))
    return await wc.listing(user.get("org_id", ORG_ID), status=status, q=q, source=source, dup=dup,
                            skip=max(0, skip), limit=limit)


@router.post("/contacts/preview")
async def preview_import(p: ImportIn, user: dict = Depends(require_permission("leads", "create"))):
    rows = wc.parse_import(p.text)
    if not rows:
        raise HTTPException(400, "Tidak ada nomor yang terbaca. Tempel daftar nomor (satu per baris), CSV, atau VCF.")
    items = await wc.analyze(user.get("org_id", ORG_ID), rows)
    return {"data": {"items": items[:500], "summary": wc.summarize(items)}}


@router.post("/contacts/import")
async def import_contacts(p: ImportIn, user: dict = Depends(require_permission("leads", "create"))):
    rows = wc.parse_import(p.text)
    if not rows:
        raise HTTPException(400, "Tidak ada nomor yang terbaca.")
    res = await wc.import_rows(user.get("org_id", ORG_ID), rows, actor=user.get("email"), label=p.label or "")
    await audit_log(user, "import", "wa_contacts", res["batch"]["id"], {"added": res["added"], "updated": res["updated"]})
    return {"data": res}


@router.post("/contacts/import-file")
async def import_file(file: UploadFile = File(...), label: str = "",
                      user: dict = Depends(require_permission("leads", "create"))):
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "Berkas terlalu besar (maks 5 MB).")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    rows = wc.parse_import(text)
    if not rows:
        raise HTTPException(400, "Tidak ada nomor yang terbaca dari berkas (dukungan: .csv, .txt, .vcf).")
    res = await wc.import_rows(user.get("org_id", ORG_ID), rows, actor=user.get("email"),
                               label=label or file.filename or "")
    return {"data": res}


@router.post("/contacts/capture")
async def capture_contacts(p: CaptureIn, user: dict = Depends(require_permission("leads", "create"))):
    if p.policy_lead not in ("skip", "link") or p.policy_customer not in ("skip", "create"):
        raise HTTPException(400, "Kebijakan duplikat tidak dikenal.")
    if not (p.ids or p.all_new or p.phones):
        raise HTTPException(400, "Pilih kontak yang akan dijadikan lead.")
    if p.assigned_to and not await db.users.find_one({"email": p.assigned_to, "org_id": user.get("org_id", ORG_ID)}):
        raise HTTPException(400, "PIC tidak ditemukan.")
    res = await wc.capture(user.get("org_id", ORG_ID), ids=p.ids, all_new=p.all_new, phones=p.phones,
                           policy_lead=p.policy_lead, policy_customer=p.policy_customer,
                           assigned_to=p.assigned_to, campaign=p.campaign, actor=user.get("email"))
    await audit_log(user, "capture", "wa_contacts", None,
                    {k: res[k] for k in ("created", "linked", "skipped", "invalid")})
    return {"data": res}


@router.post("/contacts/{cid}/skip")
async def skip_contact(cid: str, p: StatusIn, user: dict = Depends(require_permission("leads", "update"))):
    r = await wc.set_status(user.get("org_id", ORG_ID), cid, "skipped", actor=user.get("email"),
                            reason=p.reason or "Dilewati manual")
    if not r["matched"]:
        raise HTTPException(404, "Kontak tidak ditemukan")
    return {"data": {"id": cid, "status": "skipped"}}


@router.post("/contacts/{cid}/restore")
async def restore_contact(cid: str, user: dict = Depends(require_permission("leads", "update"))):
    r = await wc.set_status(user.get("org_id", ORG_ID), cid, "new", actor=user.get("email"), reason="")
    if not r["matched"]:
        raise HTTPException(404, "Kontak tidak ditemukan")
    return {"data": {"id": cid, "status": "new"}}


@router.delete("/contacts/{cid}")
async def delete_contact(cid: str, user: dict = Depends(require_permission("leads", "delete"))):
    r = await db.wa_contacts.delete_one({"id": cid, "org_id": user.get("org_id", ORG_ID)})
    if not r.deleted_count:
        raise HTTPException(404, "Kontak tidak ditemukan")
    return {"data": {"id": cid, "deleted": True}}


# ------------------------------------------------------------------ simulasi
@router.post("/simulate/inbound")
async def simulate_inbound(p: SimulateIn, user: dict = Depends(require_permission("inbox", "create"))):
    """Bentuk payload Meta ASLI lalu lewatkan ke pemroses webhook yang sama (simulasi jujur)."""
    phone = gw.valid_phone(p.phone)
    if not phone:
        raise HTTPException(400, "Nomor tidak valid (harus nomor Indonesia +62).")
    payload = wi.build_meta_payload(phone=phone, name=p.name, text=p.message, mtype=p.mtype, filename=p.filename)
    res = await wi.process_meta_payload(payload, user.get("org_id", ORG_ID), mode="simulation")
    return {"data": {"summary": {k: v for k, v in res.items() if k != "results"},
                     "result": (res["results"] or [{}])[0], "payload": payload}}
