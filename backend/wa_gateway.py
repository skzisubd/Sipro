"""wa_gateway — SATU pintu kirim WhatsApp (Fase 94).

Dua adapter dengan kontrak sama: `SimulationAdapter` (tanpa kredensial, pesan tercatat
jujur berstatus `simulated`) dan `MetaCloudAdapter` (Graph API). Mode & kredensial dibaca
dari `channel_accounts.wa_main` (terenkripsi Fernet dari JWT_SECRET) dengan fallback `.env`.
Setiap pengiriman menulis `messages` dengan `provider_message_id`, `status`, `mode`,
`error_code/error_detail` — tidak ada lagi fallback diam-diam.
"""
import asyncio
import base64
import hashlib
import logging
import os
import re

import httpx
from cryptography.fernet import Fernet, InvalidToken

from core_utils import new_id, normalize_phone_e164, now_iso
from db import db, ORG_ID

logger = logging.getLogger("sipro.wa_gateway")

GRAPH = "https://graph.facebook.com/v21.0"
CHANNEL_CODE = "wa_main"
CRED_KEYS = ("token", "phone_id", "waba_id", "app_secret", "verify_token")
ENV_KEYS = {"token": "WHATSAPP_TOKEN", "phone_id": "WHATSAPP_PHONE_ID",
            "waba_id": "WHATSAPP_WABA_ID", "app_secret": "WHATSAPP_APP_SECRET",
            "verify_token": "WHATSAPP_VERIFY_TOKEN"}
PHONE_RE = re.compile(r"^\+62\d{8,13}$")
RETRY_DELAYS = (0.5, 1.0, 2.0)


# ------------------------------------------------------------------ enkripsi
def _fernet() -> Fernet:
    secret = os.environ["JWT_SECRET"].encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):  # noqa: BLE001
        return ""


def mask(value: str) -> str:
    if not value:
        return ""
    return value[:4] + "•" * 6 + value[-4:] if len(value) > 8 else "•" * len(value)


# ------------------------------------------------------------------ konfigurasi
async def _channel(org_id: str) -> dict:
    ch = await db.channel_accounts.find_one({"org_id": org_id, "code": CHANNEL_CODE}, {"_id": 0})
    if ch:
        return ch
    ts = now_iso()
    ch = {"id": new_id(), "org_id": org_id, "code": CHANNEL_CODE, "channel": "whatsapp",
          "name": "WhatsApp Sales", "mode": "simulation", "is_active": True,
          "created_by": "system", "created_at": ts}
    await db.channel_accounts.insert_one(dict(ch))
    return ch


async def get_config(org_id: str = ORG_ID) -> dict:
    """{mode, effective_mode, creds{k: plain}, sources{k: db|env|none}, channel}."""
    ch = await _channel(org_id)
    enc = ch.get("credentials_enc") or {}
    creds, sources = {}, {}
    for k in CRED_KEYS:
        val = decrypt(enc[k]) if enc.get(k) else ""
        src = "db" if val else "none"
        if not val and os.environ.get(ENV_KEYS[k]):
            val, src = os.environ[ENV_KEYS[k]], "env"
        creds[k], sources[k] = val, src
    mode = ch.get("mode") or "simulation"
    live_ready = bool(creds["token"] and creds["phone_id"])
    return {"mode": mode, "effective_mode": "live" if mode == "live" and live_ready else "simulation",
            "live_ready": live_ready, "creds": creds, "sources": sources, "channel": ch,
            "is_active": ch.get("is_active", True)}


async def save_config(org_id: str, *, mode: str = None, creds: dict = None, actor: str = "") -> dict:
    ch = await _channel(org_id)
    enc = dict(ch.get("credentials_enc") or {})
    for k, v in (creds or {}).items():
        if k not in CRED_KEYS or v is None:
            continue
        if v == "__clear__":
            enc.pop(k, None)
        elif v.strip():
            enc[k] = encrypt(v.strip())
    upd = {"credentials_enc": enc, "updated_at": now_iso(), "updated_by": actor}
    if mode in ("simulation", "live"):
        upd["mode"] = mode
    await db.channel_accounts.update_one({"id": ch["id"]}, {"$set": upd})
    return await get_config(org_id)


async def note_webhook(org_id: str, *, signature_ok, kind: str) -> None:
    ch = await _channel(org_id)
    await db.channel_accounts.update_one({"id": ch["id"]}, {"$set": {
        "webhook_last_received_at": now_iso(), "webhook_last_signature_ok": signature_ok,
        "webhook_last_kind": kind}})


# ------------------------------------------------------------------ adapter
class SimulationAdapter:
    mode = "simulation"

    async def send(self, payload: dict) -> dict:
        logger.info("[SIM WhatsApp] to=%s type=%s", payload.get("to"), payload.get("type"))
        return {"ok": True, "status": "simulated", "provider_message_id": f"sim-{new_id()}",
                "error_code": None, "error_detail": None}

    async def probe(self) -> dict:
        return {"ok": False, "mode": "simulation",
                "detail": "Mode simulasi: tidak ada kredensial yang diuji. Isi kredensial lalu ubah mode ke live."}


class MetaCloudAdapter:
    mode = "live"

    def __init__(self, creds: dict):
        self.token, self.phone_id, self.waba_id = creds["token"], creds["phone_id"], creds.get("waba_id")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    @staticmethod
    def _err(resp) -> tuple:
        try:
            e = resp.json().get("error") or {}
        except Exception:  # noqa: BLE001
            e = {}
        code = e.get("code") or resp.status_code
        detail = e.get("error_user_msg") or e.get("message") or resp.text[:200]
        return str(code), detail

    async def send(self, payload: dict) -> dict:
        url = f"{GRAPH}/{self.phone_id}/messages"
        last = None
        async with httpx.AsyncClient(timeout=20) as cli:
            for attempt, delay in enumerate((0,) + RETRY_DELAYS):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    resp = await cli.post(url, headers=self._headers(), json=payload)
                except httpx.HTTPError as e:
                    last = {"ok": False, "status": "failed", "provider_message_id": None,
                            "error_code": "network", "error_detail": str(e)[:200]}
                    continue
                if resp.status_code < 300:
                    data = resp.json()
                    wamid = ((data.get("messages") or [{}])[0]).get("id")
                    return {"ok": True, "status": "sent", "provider_message_id": wamid,
                            "error_code": None, "error_detail": None, "raw": data}
                code, detail = self._err(resp)
                last = {"ok": False, "status": "failed", "provider_message_id": None,
                        "error_code": code, "error_detail": detail}
                if resp.status_code not in (429,) and resp.status_code < 500:
                    break
        return last

    async def upload_media(self, data: bytes, filename: str, content_type: str) -> dict:
        url = f"{GRAPH}/{self.phone_id}/media"
        async with httpx.AsyncClient(timeout=60) as cli:
            resp = await cli.post(url, headers={"Authorization": f"Bearer {self.token}"},
                                  data={"messaging_product": "whatsapp", "type": content_type},
                                  files={"file": (filename, data, content_type)})
        if resp.status_code >= 300:
            code, detail = self._err(resp)
            return {"ok": False, "error_code": code, "error_detail": detail}
        return {"ok": True, "media_id": resp.json().get("id")}

    async def download_media(self, media_id: str) -> dict:
        async with httpx.AsyncClient(timeout=60) as cli:
            meta = await cli.get(f"{GRAPH}/{media_id}", headers=self._headers())
            if meta.status_code >= 300:
                code, detail = self._err(meta)
                return {"ok": False, "error_code": code, "error_detail": detail}
            info = meta.json()
            blob = await cli.get(info["url"], headers={"Authorization": f"Bearer {self.token}"})
            if blob.status_code >= 300:
                return {"ok": False, "error_code": str(blob.status_code), "error_detail": "unduh media gagal"}
        return {"ok": True, "data": blob.content, "mime_type": info.get("mime_type"),
                "sha256": info.get("sha256"), "size": info.get("file_size")}

    async def probe(self) -> dict:
        out = {"ok": True, "mode": "live"}
        async with httpx.AsyncClient(timeout=20) as cli:
            r = await cli.get(f"{GRAPH}/{self.phone_id}", headers=self._headers(),
                              params={"fields": "display_phone_number,verified_name,quality_rating,code_verification_status"})
            if r.status_code >= 300:
                code, detail = self._err(r)
                return {"ok": False, "mode": "live", "error_code": code, "detail": detail}
            out["phone"] = r.json()
            if self.waba_id:
                t = await cli.get(f"{GRAPH}/{self.waba_id}/message_templates",
                                  headers=self._headers(), params={"limit": 50, "fields": "name,status,category,language"})
                if t.status_code < 300:
                    rows = t.json().get("data") or []
                    out["templates"] = rows
                    out["templates_approved"] = sum(1 for x in rows if x.get("status") == "APPROVED")
                else:
                    code, detail = self._err(t)
                    out["templates_error"] = f"{code}: {detail}"
        return out


async def adapter_for(org_id: str = ORG_ID):
    cfg = await get_config(org_id)
    if cfg["effective_mode"] == "live":
        return MetaCloudAdapter(cfg["creds"]), cfg
    return SimulationAdapter(), cfg


# ------------------------------------------------------------------ kirim
def valid_phone(phone: str) -> str:
    """-> E.164 bila valid Indonesia, '' bila tidak."""
    p = normalize_phone_e164(phone or "")
    return p if p and PHONE_RE.match(p) else ""


def _template_payload(to: str, template: dict, params: list) -> dict:
    body = {"messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": template.get("meta_name") or template.get("code"),
                         "language": {"code": template.get("language") or "id"}}}
    if params:
        body["template"]["components"] = [{"type": "body", "parameters": [
            {"type": "text", "text": str(p)} for p in params]}]
    return body


async def send(org_id: str, to: str, *, kind: str, body: str = None, template: dict = None,
               template_params: list = None, document: dict = None, conversation_id: str = None,
               actor: str = "system", ref: dict = None) -> dict:
    """Kirim teks / template / dokumen. Selalu menulis `messages`; kembalikan dokumennya.

    kind: inbox|broadcast|reminder|otp|document|notification|test|playbook
    document: {link, filename, caption}
    """
    ts = now_iso()
    adapter, cfg = await adapter_for(org_id)
    dest = valid_phone(to)
    text = body if body is not None else (template or {}).get("body") or (document or {}).get("caption") or ""
    msg = {
        "id": new_id(), "org_id": org_id, "conversation_id": conversation_id, "direction": "out",
        "body": text, "sender": actor, "is_template": bool(template),
        "template_id": (template or {}).get("id"), "template_code": (template or {}).get("code"),
        "kind": kind, "to": dest or to, "mode": adapter.mode, "ref": ref or {},
        "document": document, "created_at": ts, "status_at": ts,
    }
    if not dest:
        res = {"ok": False, "status": "failed", "provider_message_id": None,
               "error_code": "invalid_phone", "error_detail": f"Nomor tidak valid / bukan +62: {to!r}"}
    elif not cfg.get("is_active", True):
        res = {"ok": False, "status": "failed", "provider_message_id": None,
               "error_code": "channel_inactive", "error_detail": "Channel WhatsApp dinonaktifkan."}
    else:
        if document:
            payload = {"messaging_product": "whatsapp", "to": dest.lstrip("+"), "type": "document",
                       "document": {k: v for k, v in {"link": document.get("link"), "id": document.get("media_id"),
                                                      "filename": document.get("filename"),
                                                      "caption": document.get("caption")}.items() if v}}
        elif template:
            payload = _template_payload(dest.lstrip("+"), template, template_params or [])
        else:
            payload = {"messaging_product": "whatsapp", "to": dest.lstrip("+"), "type": "text",
                       "text": {"body": text, "preview_url": False}}
        res = await adapter.send(payload)
    msg.update({"status": res["status"], "provider_message_id": res.get("provider_message_id"),
                "error_code": res.get("error_code"), "error_detail": res.get("error_detail")})
    await db.messages.insert_one(dict(msg))
    if conversation_id:
        await db.conversations.update_one({"id": conversation_id}, {"$set": {
            "last_message_at": ts, "updated_at": ts, "last_direction": "out", "status": "active"}})
    if res["status"] == "failed":
        logger.warning("WA gagal kirim to=%s code=%s detail=%s", to, res.get("error_code"), res.get("error_detail"))
    return msg


async def probe(org_id: str = ORG_ID) -> dict:
    adapter, cfg = await adapter_for(org_id)
    if cfg["effective_mode"] != "live" and cfg["live_ready"]:
        # kredensial ada tapi mode masih simulasi: uji koneksi tetap boleh dijalankan
        adapter = MetaCloudAdapter(cfg["creds"])
    try:
        out = await adapter.probe()
    except httpx.HTTPError as e:
        out = {"ok": False, "mode": "live", "error_code": "network", "detail": str(e)[:200]}
    ch = cfg["channel"]
    await db.channel_accounts.update_one({"id": ch["id"]}, {"$set": {
        "last_probe_at": now_iso(), "last_probe": {k: v for k, v in out.items() if k != "templates"}}})
    return out


async def status_summary(org_id: str = ORG_ID) -> dict:
    """Ringkasan untuk layar konfigurasi: kredensial (tersamar), webhook, checklist go-live."""
    cfg = await get_config(org_id)
    ch = cfg["channel"]
    creds = cfg["creds"]
    probe_res = ch.get("last_probe") or {}
    quality = ((probe_res.get("phone") or {}).get("quality_rating") or "").upper()
    checklist = [
        {"key": "creds", "label": "Kredensial lengkap (token, phone ID, WABA ID, app secret, verify token)",
         "ok": all(creds[k] for k in CRED_KEYS)},
        {"key": "probe", "label": "Tes koneksi ke Meta berhasil", "ok": bool(probe_res.get("ok"))},
        {"key": "webhook", "label": "Webhook pernah diterima dengan tanda tangan sah",
         "ok": bool(ch.get("webhook_last_received_at")) and ch.get("webhook_last_signature_ok") is True},
        {"key": "template", "label": "≥1 template APPROVED di Meta",
         "ok": (probe_res.get("templates_approved") or 0) > 0},
        {"key": "quality", "label": "Kualitas nomor pengirim GREEN", "ok": quality == "GREEN"},
        {"key": "mode", "label": "Mode live aktif", "ok": cfg["effective_mode"] == "live"},
    ]
    return {
        "mode": cfg["mode"], "effective_mode": cfg["effective_mode"], "live_ready": cfg["live_ready"],
        "is_active": cfg["is_active"],
        "credentials": {k: {"set": bool(creds[k]), "masked": mask(creds[k]), "source": cfg["sources"][k]}
                        for k in CRED_KEYS},
        "webhook": {"path": "/api/webhooks/wa", "last_received_at": ch.get("webhook_last_received_at"),
                    "last_signature_ok": ch.get("webhook_last_signature_ok"),
                    "last_kind": ch.get("webhook_last_kind")},
        "last_probe_at": ch.get("last_probe_at"), "last_probe": probe_res,
        "checklist": checklist, "go_live_ready": all(c["ok"] for c in checklist[:-1]),
    }
