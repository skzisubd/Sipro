#!/usr/bin/env python3
"""poc_51.py — POC CORE Fase 51 (satu berkas, tiga urusan).

Dijalankan SEBELUM implementasi: berkas ini adalah KONTRAK yang harus dipenuhi.

## 51A — Masa pemeliharaan & retensi subkon TERHUBUNG klaim garansi
Uang retensi adalah jaminan mutu. Sampai Fase 50, gerbang pencairannya hanya memeriksa masa
pemeliharaan dan temuan punch list — sedangkan **klaim garansi** (jalur keluhan pasca-huni
yang baru lahir di Fase 50) tidak dilihat sama sekali. Akibatnya jaminan bisa cair persis
saat rumahnya sedang diperbaiki karena cacat pekerjaan subkon itu: perusahaan kehilangan satu-
satunya alat tekan yang dimilikinya, tepat pada saat alat itu dibutuhkan.

Yang dibuktikan:
  A1  gerbang retensi MENYEBUT klaim garansi yang masih berjalan (nomor klaimnya, bukan
      "ada kendala"), dan pengajuan pencairan DITOLAK karenanya;
  A2  pengabaian (waiver) butuh IZIN khusus — `pm@` & `finance@` ditolak 403;
  A3  pengabaian butuh alasan ≥10 huruf (alasan pendek DITOLAK);
  A4  pengabaian hanya boleh atas hal yang MEMANG bisa diabaikan; kode yang tidak
      menghalangi / tidak dikenal ditolak apa adanya;
  A5  setelah diabaikan dengan benar: pengajuan lolos, pencairan lolos, dan dokumen retensi
      menyimpan jejak siapa mengabaikan + alasannya + kode yang diabaikan;
  A6  pemisahan tugas tetap berlaku (pengaju ≠ pencair);
  A7  pencairan idempoten lewat `client_ref` (kiriman ulang = jawaban lama, bukan tagihan
      kedua) dan tetap tidak bisa dicairkan dua kali;
  A8  klaim garansi yang SUDAH DITUTUP tidak lagi menahan (blokade hilang sendiri);
  A9  honest-null: retensi tanpa catatan masa pemeliharaan menulis "belum dicatat", bukan
      "0 hari" (0 hari berarti "sudah lewat" — kebalikan artinya).

## 51B — Pengingat WhatsApp otomatis (garansi hampir habis, termin jatuh tempo, tunggakan)
Sistem sudah menyimpan tanggal jatuh tempo termin, tunggakan, dan tanggal habis garansi per
bagian — tetapi tidak seorang pun diberi tahu. Pengingat dikirim manual, jadi tidak konsisten.

Yang dibuktikan:
  B1  kandidat pengingat DIHITUNG dari data nyata (bukan daftar yang diketik): garansi hampir
      habis, termin jatuh tempo H-N, dan tunggakan;
  B2  ambang batas dibaca dari Pusat Konfigurasi (mengubah setelan mengubah kandidat);
  B3  menjalankan pengingat DUA KALI tidak menghasilkan pesan kedua (dedup per periode);
  B4  mode SIMULASI jujur: tanpa kredensial WhatsApp statusnya "simulasi", TIDAK PERNAH
      mengaku "terkirim";
  B5  penerima tanpa nomor telepon dicatat sebagai DILEWATI beserta sebabnya, bukan dihitung
      sebagai terkirim;
  B6  RBAC: hanya peran ber-izin kelola yang boleh menjalankan; sales ditolak 403;
  B7  riwayat pengingat bisa dibaca ulang (audit) dan menyebut template yang dipakai;
  B8  pengingat tidak dikirim untuk hal yang sudah beres (termin lunas / garansi habis).

## 51C — Portal pembeli diperkuat
Pembeli sudah bisa melihat masa garansi & mengajukan klaim (Fase 50), tetapi tiga hal paling
sering diminta manusia justru belum ada: salinan BAST-nya sendiri, kwitansi pembayarannya,
dan cara MENGAKUI bahwa perbaikan garansi memang sudah selesai (padahal mesin MEWAJIBKAN
pengakuan pembeli untuk menutup klaim — jadi selama ini pengakuan itu diketik oleh staf).

Yang dibuktikan:
  C1  pembeli melihat daftar BAST miliknya dan bisa mengunduh PDF-nya;
  C2  BAST milik orang lain TIDAK bisa diunduh (404/403), termasuk dengan menebak id;
  C3  pembeli melihat & mengunduh kwitansi pembayarannya sendiri (PDF sungguhan);
  C4  pembeli bisa MENGAKUI penyelesaian klaim garansi, dan pengakuan itu tercatat atas
      namanya (bukan atas nama staf);
  C5  pengakuan hanya untuk klaim yang sudah diverifikasi selesai — klaim yang masih
      dikerjakan ditolak dengan alasan jujur;
  C6  tanpa token portal, seluruh pintu itu 401/403.

Bahan uji: `scripts/_fixture51.py` (dibuat & DIBUANG otomatis).
"""
import json
import os
import pathlib
import sys
import uuid

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / "backend" / ".env")
import _fixture51 as fx  # noqa: E402

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG = os.environ.get("DEFAULT_ORG_ID", "org-sipro")
fails = []
n_ok = 0


def check(label: str, cond, detail: str = ""):
    global n_ok
    ok = bool(cond)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
    if ok:
        n_ok += 1
    else:
        fails.append(label)
    return ok


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def api(method: str, path: str, headers: dict, **kw):
    return requests.request(method, f"{BASE}{path}", headers=headers, timeout=90, **kw)


def portal_login(phone: str) -> dict:
    """Login portal pembeli memakai OTP master pengujian (`PORTAL_MASTER_OTP`)."""
    api("POST", "/portal/auth/request-otp", {}, json={"identifier": phone})
    otp = os.environ.get("PORTAL_MASTER_OTP", "000000")
    r = api("POST", "/portal/auth/verify-otp", {}, json={"identifier": phone, "code": otp})
    r.raise_for_status()
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    return {"Authorization": f"Bearer {tok}"}


def gate_of(rid: str, headers: dict) -> dict:
    r = api("GET", "/subcon/retentions", headers)
    if not r.ok:
        return {}
    row = next((x for x in r.json().get("data", []) if x["id"] == rid), None)
    return (row or {}).get("gate") or {}


# ============================================================== 51A
def part_a(world, actors):
    admin, pm, finance, finlead, sales = (actors[k] for k in
                                          ("admin", "pm", "finance", "finlead", "sales"))
    ret = world["subcon"]["retention"]
    rid = ret["id"]
    claim = world["claim"]
    print("\n51A. Retensi subkon ditahan oleh klaim garansi berjalan")

    g = gate_of(rid, admin)
    codes = [b.get("code") for b in (g.get("blocks") or [])]
    check("A1a gerbang retensi menahan karena klaim garansi berjalan",
          "warranty_claim_active" in codes, f"blocks={codes}")
    detail = " ".join(b.get("detail", "") for b in (g.get("blocks") or []))
    check("A1b penahanan MENYEBUT nomor klaimnya (bukan 'ada kendala')",
          claim["number"] in detail, detail[:160])
    r = api("POST", f"/subcon/retentions/{rid}/request-release", pm,
            json={"reason": "Pekerjaan sudah selesai, mohon dicairkan."})
    check("A1c pengajuan pencairan DITOLAK selama klaim garansi berjalan",
          r.status_code == 400 and "garansi" in r.text.lower(), f"{r.status_code} {r.text[:120]}")

    for nama, hdr in (("pm", pm), ("finance", finance)):
        r = api("POST", f"/subcon/retentions/{rid}/waive", hdr,
                json={"codes": ["warranty_claim_active"],
                      "reason": "Sudah disepakati subkon memperbaiki setelah pencairan."})
        check(f"A2 {nama} TIDAK boleh mengabaikan tahanan retensi (403)",
              r.status_code == 403, f"got {r.status_code}: {r.text[:90]}")

    r = api("POST", f"/subcon/retentions/{rid}/waive", finlead,
            json={"codes": ["warranty_claim_active"], "reason": "oke"})
    check("A3 alasan pengabaian <10 huruf DITOLAK", r.status_code == 400,
          f"got {r.status_code}: {r.text[:90]}")

    r = api("POST", f"/subcon/retentions/{rid}/waive", finlead,
            json={"codes": ["already_released"],
                  "reason": "Mencoba mengabaikan hal yang bukan penahan sah."})
    check("A4a kode yang tidak menahan/tidak bisa diabaikan DITOLAK",
          r.status_code == 400, f"got {r.status_code}: {r.text[:110]}")
    r = api("POST", f"/subcon/retentions/{rid}/waive", finlead,
            json={"codes": ["ngawur_kode"], "reason": "Kode karangan harus ditolak mesin."})
    check("A4b kode pengabaian tak dikenal DITOLAK", r.status_code == 400,
          f"got {r.status_code}: {r.text[:90]}")

    alasan = "Perbaikan garansi ditanggung subkon lewat adendum tertulis 21/08."
    r = api("POST", f"/subcon/retentions/{rid}/waive", finlead,
            json={"codes": ["warranty_claim_active"], "reason": alasan})
    check("A5a Manajer Keuangan boleh mengabaikan dengan alasan jelas", r.ok,
          f"{r.status_code} {r.text[:120]}")
    doc = db.subcon_retentions.find_one({"id": rid}, {"_id": 0})
    waivers = doc.get("waivers") or []
    check("A5b jejak pengabaian tersimpan (kode + alasan + siapa + kapan)",
          any(w.get("code") == "warranty_claim_active"
              and w.get("reason") == alasan
              and w.get("by") == "finlead@sipro.co.id" and w.get("at") for w in waivers),
          json.dumps(waivers, ensure_ascii=False)[:200])
    check("A5c pengabaian melahirkan tugas penelaahan (bukan hanya catatan)",
          db.tasks.count_documents({"org_id": ORG, "related_entity_id": rid}) >= 1)
    g = gate_of(rid, admin)
    check("A5d sesudah diabaikan, gerbang menyatakan boleh cair", g.get("ok") is True,
          json.dumps(g.get("blocks"), ensure_ascii=False)[:160])
    check("A5e gerbang tetap MENAMPILKAN tahanan yang diabaikan (transparan)",
          any(b.get("waived") for b in (g.get("waived_blocks") or g.get("blocks") or [])),
          json.dumps(g, ensure_ascii=False)[:200])

    r = api("POST", f"/subcon/retentions/{rid}/request-release", pm,
            json={"reason": "Pekerjaan selesai; tahanan garansi sudah diabaikan resmi."})
    check("A5f pengajuan pencairan lolos sesudah pengabaian sah", r.ok,
          f"{r.status_code} {r.text[:120]}")

    r = api("POST", f"/subcon/retentions/{rid}/release", pm,
            json={"reason": "Mencairkan sendiri padahal saya yang mengajukan."})
    check("A6 pengaju tidak boleh mencairkan sendiri", r.status_code in (400, 403),
          f"got {r.status_code}")

    ref1 = f"poc51-release-{uuid.uuid4().hex[:8]}"
    r1 = api("POST", f"/subcon/retentions/{rid}/release", finlead,
             json={"reason": "Retensi dicairkan sesuai adendum.", "client_ref": ref1})
    check("A7a pencairan berhasil", r1.ok, f"{r1.status_code} {r1.text[:140]}")
    bills1 = db.ap_invoices.count_documents({"org_id": ORG, "retention_id": rid})
    r2 = api("POST", f"/subcon/retentions/{rid}/release", finlead,
             json={"reason": "Retensi dicairkan sesuai adendum.", "client_ref": ref1})
    bills2 = db.ap_invoices.count_documents({"org_id": ORG, "retention_id": rid})
    check("A7b kiriman ulang dengan client_ref sama = jawaban lama (idempoten)",
          r2.ok and bills2 == bills1 == 1, f"{r2.status_code} bills={bills1}->{bills2}")
    r3 = api("POST", f"/subcon/retentions/{rid}/release", finlead,
             json={"reason": "Coba cairkan lagi dengan penanda baru."})
    check("A7c retensi tidak bisa dicairkan dua kali", r3.status_code == 400,
          f"got {r3.status_code}: {r3.text[:90]}")

    # A8 — klaim ditutup: blokade hilang dengan sendirinya (tanpa pengabaian).
    # Retensi KEDUA dibuat di dunia uji yang SAMA (bukan `fx.make()` baru): membangun ulang
    # dunia akan membuang BAST & kwitansi yang dipakai bagian 51C setelahnya.
    kedua = fx.make_subcon_retention(world["project"], world["unit"])
    rid2 = kedua["retention"]["id"]
    g = gate_of(rid2, admin)
    check("A8a retensi baru ditahan klaim garansi",
          any(b.get("code") == "warranty_claim_active" for b in (g.get("blocks") or [])),
          json.dumps(g.get("blocks"), ensure_ascii=False)[:140])
    db.warranty_claims.update_one({"id": claim["id"]}, {"$set": {"state": "ditutup"}})
    g = gate_of(rid2, admin)
    check("A8b klaim ditutup → tahanan garansi hilang sendiri",
          not any(b.get("code") == "warranty_claim_active" for b in (g.get("blocks") or [])),
          json.dumps(g.get("blocks"), ensure_ascii=False)[:140])

    db.subcon_retentions.update_one({"id": rid2}, {"$set": {"maintenance_until": None,
                                                           "maintenance_days": None}})
    r = api("GET", "/subcon/retentions", admin)
    row = next((x for x in r.json().get("data", []) if x["id"] == rid2), {})
    teks = json.dumps(row.get("gate") or {}, ensure_ascii=False).lower()
    check("A9 masa pemeliharaan yang belum dicatat ditulis 'belum dicatat' (bukan 0 hari)",
          "belum dicatat" in teks and "0 hari" not in teks, teks[:200])
    return {"sales": sales}


# ============================================================== 51B
def part_b(world, actors):
    admin, sales, finlead = actors["admin"], actors["sales"], actors["finlead"]
    print("\n51B. Pengingat WhatsApp otomatis (garansi, termin, tunggakan)")
    phone = fx.PHONE

    r = api("GET", "/reminders/settings", admin)
    check("B0 setelan pengingat bisa dibaca (ambang + mode kirim)", r.ok, r.text[:120])
    setelan = (r.json().get("data") or {}) if r.ok else {}
    check("B0b setelan menyebut mode kirim (simulasi/nyata) apa adanya",
          setelan.get("mode") in ("simulasi", "nyata"), json.dumps(setelan)[:160])

    r = api("GET", "/reminders/candidates", admin)
    check("B1a daftar kandidat pengingat bisa dibaca", r.ok, r.text[:140])
    cands = (r.json().get("data") or []) if r.ok else []
    kinds = {c.get("kind") for c in cands}
    mine = [c for c in cands if c.get("phone") == phone]
    check("B1b kandidat memuat garansi HAMPIR HABIS dari data nyata",
          any(c["kind"] == "warranty_expiring" for c in mine),
          f"kinds={sorted(kinds)}")
    check("B1c kandidat memuat termin JATUH TEMPO dari jadwal tagihan nyata",
          any(c["kind"] == "installment_due" for c in mine))
    check("B1d kandidat memuat TUNGGAKAN dari tagihan yang lewat jatuh tempo",
          any(c["kind"] == "installment_overdue" for c in mine))
    check("B1e setiap kandidat menyebut alasan & nilai yang bisa diperiksa manusia",
          all(c.get("reason") and c.get("dedup_key") for c in mine),
          json.dumps(mine[:1], ensure_ascii=False)[:220])

    # B2 — ambang batas dari Pusat Konfigurasi.
    r = api("PUT", "/settings/reminder.installment_days_before", admin,
            json={"value": 1, "reason": "Uji POC 51: ambang H-1."})
    check("B2a ambang pengingat termin bisa diubah dari Pusat Konfigurasi", r.ok, r.text[:120])
    r = api("GET", "/reminders/candidates", admin)
    mine2 = [c for c in (r.json().get("data") or []) if c.get("phone") == phone]
    check("B2b mengubah ambang MENGUBAH kandidat (bukan angka mati di kode)",
          not any(c["kind"] == "installment_due" for c in mine2),
          f"masih ada: {[c['kind'] for c in mine2]}")
    api("PUT", "/settings/reminder.installment_days_before", admin,
        json={"value": 3, "reason": "Kembalikan bawaan sesudah uji POC."})

    r = api("POST", "/reminders/run", sales, json={})
    check("B6 sales TIDAK boleh menjalankan pengingat (403)", r.status_code == 403,
          f"got {r.status_code}")

    # Penjaga perangkat uji: menjalankan pengingat di lingkungan berkredensial WhatsApp NYATA
    # berarti mengirim pesan sungguhan ke pelanggan demo. POC berhenti jujur di sini alih-alih
    # "lulus" dengan cara yang tidak boleh diulang di lingkungan pelanggan.
    if setelan.get("mode") == "nyata":
        check("B3 mode kirim NYATA: pengingat TIDAK dijalankan POC (lindungi pelanggan)",
              False,
              "kosongkan WHATSAPP_TOKEN/WHATSAPP_PHONE_ID untuk menjalankan POC 51B")
        return

    r1 = api("POST", "/reminders/run", finlead, json={})
    check("B3a pengingat bisa dijalankan peran berwenang", r1.ok, r1.text[:160])
    out1 = (r1.json().get("data") or {}) if r1.ok else {}
    kirim1 = db.wa_reminders.count_documents({"org_id": ORG, "phone": phone})
    check("B3b pengingat untuk pembeli uji benar-benar tercatat", kirim1 >= 3,
          f"{kirim1} baris | ringkasan={json.dumps(out1, ensure_ascii=False)[:180]}")
    r2 = api("POST", "/reminders/run", finlead, json={})
    kirim2 = db.wa_reminders.count_documents({"org_id": ORG, "phone": phone})
    out2 = (r2.json().get("data") or {}) if r2.ok else {}
    check("B3c menjalankan ulang TIDAK menghasilkan pesan kedua (dedup per periode)",
          kirim2 == kirim1, f"{kirim1} -> {kirim2}")
    check("B3d hasil jalan kedua mengaku 'dilewati', bukan 'terkirim'",
          int(out2.get("sent", 0)) == 0 and int(out2.get("skipped", 0)) >= 1,
          json.dumps(out2, ensure_ascii=False)[:180])

    rows = list(db.wa_reminders.find({"org_id": ORG, "phone": phone}, {"_id": 0}))
    check("B4 tanpa kredensial WhatsApp statusnya 'simulasi', tidak mengaku 'terkirim'",
          rows and all(r.get("status") in ("simulasi", "gagal", "dilewati") for r in rows),
          str(sorted({r.get("status") for r in rows})))
    check("B7a riwayat menyebut template yang dipakai",
          all(r.get("template_code") for r in rows),
          str(sorted({r.get("template_code") for r in rows})))
    r = api("GET", "/reminders", admin, params={"limit": 50})
    check("B7b riwayat pengingat bisa dibaca dari API", r.ok and r.json().get("total", 0) >= 3,
          r.text[:140])

    # B5 — penerima tanpa nomor telepon: dicatat DILEWATI, bukan terkirim.
    db.customers.update_one({"phone": phone}, {"$set": {"phone": None}})
    db.leads.update_one({"phone": phone}, {"$set": {"phone": None}})
    db.wa_reminders.delete_many({"org_id": ORG, "phone": phone})
    r = api("GET", "/reminders/candidates", admin)
    tanpa = [c for c in (r.json().get("data") or []) if not c.get("phone")]
    check("B5a kandidat tanpa nomor tetap DITAMPILKAN dengan sebabnya",
          any("nomor" in (c.get("blocked_reason") or "").lower() for c in tanpa),
          json.dumps(tanpa[:1], ensure_ascii=False)[:200])
    r = api("POST", "/reminders/run", finlead, json={})
    out3 = (r.json().get("data") or {}) if r.ok else {}
    lewat = db.wa_reminders.count_documents({"org_id": ORG, "status": "dilewati",
                                            "reason_code": "no_phone"})
    check("B5b dijalankan: dicatat DILEWATI dengan sebab 'tidak ada nomor'", lewat >= 1,
          f"{lewat} baris | {json.dumps(out3, ensure_ascii=False)[:160]}")
    db.customers.update_one({fx.TAG: True}, {"$set": {"phone": phone}})
    db.leads.update_one({fx.TAG: True}, {"$set": {"phone": phone}})

    # B8 — yang sudah beres tidak diingatkan lagi.
    inv = db.ar_invoices.find_one({fx.TAG: True}, {"_id": 0})
    db.ar_invoices.update_one({"id": inv["id"]}, {"$set": {
        "status": "paid", "paid": inv["total"], "outstanding": 0,
        "items": [{**it, "paid": it["amount"], "status": "paid"} for it in inv["items"]]}})
    r = api("GET", "/reminders/candidates", admin)
    sisa = [c for c in (r.json().get("data") or [])
            if c.get("entity_id") == inv["id"]]
    check("B8 tagihan yang sudah lunas tidak lagi jadi kandidat pengingat", not sisa,
          json.dumps(sisa[:1], ensure_ascii=False)[:160])


# ============================================================== 51C
def part_c(world, actors):
    admin, pm, finlead = actors["admin"], actors["pm"], actors["finlead"]
    print("\n51C. Portal pembeli: BAST, kwitansi, dan pengakuan penyelesaian klaim")
    ho = world["handover"]
    unit = world["unit"]
    buyer = world["buyer"]

    r = api("GET", "/portal/handovers", {})
    check("C6a tanpa token portal, daftar BAST 401/403", r.status_code in (401, 403),
          f"got {r.status_code}")

    portal = portal_login(fx.PHONE)
    r = api("GET", "/portal/handovers", portal)
    check("C1a pembeli melihat daftar BAST miliknya", r.ok, r.text[:140])
    rows = (r.json().get("data") or []) if r.ok else []
    check("C1b BAST rumahnya ada di daftar",
          any(x.get("id") == ho["id"] or x.get("number") == ho["number"] for x in rows),
          json.dumps(rows, ensure_ascii=False)[:180])
    r = api("GET", f"/portal/handovers/{ho['id']}/pdf", portal)
    check("C1c PDF BAST bisa diunduh pembeli",
          r.ok and r.content[:4] == b"%PDF", f"{r.status_code} {r.content[:20]}")

    lain = db.unit_handovers.find_one({fx.TAG: {"$ne": True}}, {"_id": 0, "id": 1})
    if lain:
        r = api("GET", f"/portal/handovers/{lain['id']}/pdf", portal)
        check("C2 BAST milik orang lain tidak bisa diunduh", r.status_code in (403, 404),
              f"got {r.status_code}")

    r = api("GET", "/portal/receipts", portal)
    check("C3a pembeli melihat kwitansi pembayarannya", r.ok, r.text[:140])
    kw = (r.json().get("data") or []) if r.ok else []
    check("C3b kwitansi uji ada di daftar dengan nominalnya",
          any(int(x.get("amount") or 0) == int(world["receipt"]["amount"]) for x in kw),
          json.dumps(kw[:1], ensure_ascii=False)[:180])
    if kw:
        r = api("GET", f"/portal/receipts/{kw[0]['id']}/pdf", portal)
        check("C3c PDF kwitansi bisa diunduh pembeli",
              r.ok and r.content[:4] == b"%PDF", f"{r.status_code} {r.content[:20]}")

    # C4/C5 — pengakuan penyelesaian klaim.
    claim = db.warranty_claims.find_one({fx.TAG: True, "state": "dikerjakan"}, {"_id": 0}) \
        or db.warranty_claims.find_one({fx.TAG: True}, {"_id": 0})
    if not claim:
        claim = fx.make_warranty_claim(unit, buyer, world["handover"])
    db.warranty_claims.update_one({"id": claim["id"]}, {"$set": {"state": "dikerjakan"}})
    r = api("POST", f"/portal/warranty/claims/{claim['id']}/ack", portal,
            json={"note": "Belum saya cek, tapi saya akui saja."})
    check("C5 klaim yang masih dikerjakan tidak bisa diakui selesai (alasan jujur)",
          r.status_code == 400
          and any(k in r.text.lower() for k in ("diperiksa", "verifikasi")),
          f"{r.status_code} {r.text[:140]}")
    db.warranty_claims.update_one({"id": claim["id"]}, {"$set": {"state": "diverifikasi"}})
    r = api("POST", f"/portal/warranty/claims/{claim['id']}/ack", portal,
            json={"note": "Perbaikan sudah beres, terima kasih."})
    check("C4a pembeli bisa mengakui penyelesaian klaim garansi", r.ok,
          f"{r.status_code} {r.text[:140]}")
    fresh = db.warranty_claims.find_one({"id": claim["id"]}, {"_id": 0})
    check("C4b pengakuan tercatat ATAS NAMA PEMBELI (bukan staf)",
          (fresh.get("ack_by") or "").lower() not in ("", "finlead@sipro.co.id",
                                                      "pm@sipro.co.id")
          and (fx.PHONE in str(fresh.get("ack_by")) or
               str(buyer["customer"]["name"]).split()[0] in str(fresh.get("ack_by"))),
          f"ack_by={fresh.get('ack_by')}")
    check("C4c klaim yang sudah diakui pembeli berstatus ditutup",
          fresh.get("state") == "ditutup", str(fresh.get("state")))
    r = api("GET", f"/portal/warranty/claims/{claim['id']}", portal)
    check("C4d pembeli bisa membuka rincian klaimnya", r.ok, r.text[:120])

    _ = (admin, pm, finlead)


def main():
    print("=" * 70)
    print("POC 51 — retensi↔garansi, pengingat WhatsApp, portal pembeli")
    print("=" * 70)
    actors = {"admin": login("superadmin@sipro.co.id"), "pm": login("pm@sipro.co.id"),
              "finance": login("finance@sipro.co.id"),
              "finlead": login("finlead@sipro.co.id"), "sales": login("sales@sipro.co.id")}
    world = fx.make(with_active_claim=True)
    try:
        part_a(world, actors)
        part_b(world, actors)
        part_c(world, actors)
    finally:
        print("\nPembersihan bahan uji")
        buang = fx.purge()
        print(f"  info  dibuang: {buang or 'tidak ada sisa'}")
        for nama, jumlah in fx.orphans().items():
            check(f"bersih: {nama}", jumlah == 0, f"{jumlah} tersisa")
    print("-" * 70)
    if fails:
        print(f"POC 51 GAGAL: {len(fails)} temuan dari {n_ok + len(fails)} pemeriksaan")
        for f in fails:
            print(f"   - {f}")
        return 1
    print(f"POC 51 PASS — {n_ok} pemeriksaan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
