#!/usr/bin/env python3
"""poc_50.py — POC inti Fase 50 (Serah Terima Unit, Garansi, Klaim & Antrean Offline) TANPA UI.

Membuktikan janji yang sebelumnya TIDAK PUNYA JALAN di aplikasi:

  A. Kamus Data (SSOT) Fase 50 benar-benar dimuat; nilai enum di luar kamus ditolak 400
     beserta daftar pilihan yang sah.
  B. Serah terima BERGIGI: daftar periksa menyebut sebab satu per satu (temuan punch yang
     masih terbuka, progres belum 100%, kewajiban pembayaran, inspeksi belum lolos), dan
     penerbitan BAST DITAHAN — status rumah tidak berubah.
  C. Terobosan hanya untuk peran berwenang + alasan >=10 huruf, melahirkan tugas tinjauan,
     dan BAST yang salah terbit bisa DIBATALKAN beralasan (status rumah dikembalikan).
  D. BAST bersih: bernomor, idempoten (tidak ada serah terima kedua), berkas PDF nyata,
     status rumah `handed_over`, dan masa garansi PER BAGIAN dihitung dari Pusat Konfigurasi.
  E. Klaim garansi: bagian yang masa garansinya sudah lewat DITOLAK dengan menyebut tanggal
     habisnya (tercatat, bukan hilang); klaim yang diterima melahirkan pekerjaan perbaikan
     nyata; "selesai" wajib berbukti foto; pemeriksa tidak boleh orang yang mengerjakan;
     penutupan butuh pengakuan pembeli; rekap klaim tie-out dan mengaku bila belum ada data.
  F. Portal pembeli: pembeli melihat masa garansi rumahnya dan bisa mengajukan klaim
     sendiri; rumah orang lain ditolak 403.
  G. Antrean perangkat terpadu (50B): absensi, buku harian, temuan punch, dan perubahan
     status punch aman diputar ulang lewat `client_ref` — kiriman ganda TIDAK menggandakan
     data, dan kiriman yang DITOLAK melepas kunci sehingga bisa diperbaiki lalu dikirim lagi.
  H. Bersih-bersih: bahan uji dibuang tanpa meninggalkan BAST/klaim/punch menggantung.

Semua bahan dibuat sendiri (bertanda `gate50`) lalu dibuang.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import _fixture50 as fx  # noqa: E402

PASS, FAIL = [], []


def check(ok: bool, label: str, detail: str = ""):
    (PASS if ok else FAIL).append(label)
    print(f"  {'PASS ' if ok else 'GAGAL'} {label}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def head(title: str):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def body(resp) -> dict:
    try:
        return resp.json().get("data") or {}
    except Exception:  # noqa: BLE001
        return {}


def msg(resp) -> str:
    try:
        return str(resp.json().get("message") or "")
    except Exception:  # noqa: BLE001
        return ""


def detail_of(resp) -> str:
    try:
        d = resp.json().get("detail")
        if isinstance(d, dict):
            return " | ".join([str(d.get("message") or "")] + [str(x) for x in
                                                              (d.get("reasons") or [])])[:400]
        return str(d or "")[:400]
    except Exception:  # noqa: BLE001
        return resp.text[:300]


def rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


# ============================================================ A. SSOT Fase 50
def flow_a(pm):
    head("A. Kamus Data (SSOT) Fase 50 dimuat & memaksa nilai yang sah")
    reg = fx.api("GET", "/reference", pm).json().get("data") or {}
    wajib = ["handover_check_item", "handover_check_state", "handover_state",
             "warranty_category", "warranty_state", "warranty_claim_state",
             "warranty_claim_source", "warranty_reject_reason"]
    missing = [g for g in wajib if g not in reg]
    check(not missing, "seluruh grup enum Fase 50 terdaftar di /api/reference",
          f"{len(wajib)} grup ada" if not missing else f"belum ada: {missing}")

    cats = {o["value"]: o["label"] for o in (reg.get("warranty_category") or {}).get("options", [])}
    check(len(cats) >= 6 and all(v for v in cats.values()),
          "label bagian yang digaransi diambil dari kamus (layar tidak menulis sendiri)",
          "; ".join(list(cats.values())[:2]))

    cstat = {o["value"] for o in (reg.get("construction_status") or {}).get("options", [])}
    check("ready_handover" in cstat,
          "status 'siap serah terima' yang ditulis finalisasi inspeksi kini SAH di kamus",
          "ready_handover terdaftar" if "ready_handover" in cstat else "masih tak dikenal")

    kinds = {o["value"] for o in (reg.get("offline_queue_kind") or {}).get("options", [])}
    need = {"attendance_submit", "field_diary", "punch_create", "punch_status"}
    check(need <= kinds, "jenis antrean perangkat baru (absensi/buku harian/punch) terdaftar",
          f"{len(kinds)} jenis" if need <= kinds else f"belum ada: {sorted(need - kinds)}")

    bad = fx.api("POST", "/handover/claims", pm, json={
        "unit_id": "x", "category": "kolam_renang", "title": "Uji kamus data"})
    check(bad.status_code in (400, 422) and "kolam_renang" in detail_of(bad).lower()
          or "pilihan" in detail_of(bad).lower(),
          "kategori garansi di luar kamus ditolak beserta daftar pilihan yang sah",
          detail_of(bad)[:110])


# ================================================ B. serah terima yang MENAHAN
def flow_b(fin, blocked):
    head("B. Serah terima DITAHAN saat pekerjaan & kewajiban belum beres")
    unit = blocked["unit"]
    chk = body(fx.api("GET", "/handover/check", fin, params={"unit_id": unit["id"]}))
    codes = {i["code"]: i for i in chk.get("items", [])}
    blocking = {b["code"] for b in chk.get("blocking", [])}
    check(len(codes) >= 6 and all(i.get("label") and i.get("state_label")
                                  for i in codes.values()),
          "daftar periksa serah terima memakai label manusia dari kamus data",
          f"{len(codes)} pemeriksaan")
    check("punch_terbuka" in blocking
          and "Keramik" in codes["punch_terbuka"]["detail"],
          "temuan punch yang masih terbuka DISEBUT judulnya (bukan hanya jumlah)",
          codes.get("punch_terbuka", {}).get("detail", "")[:110])
    check("pembangunan_selesai" in blocking and "70%" in codes["pembangunan_selesai"]["detail"],
          "progres pembangunan yang belum 100% menahan serah terima",
          codes.get("pembangunan_selesai", {}).get("detail", "")[:90])
    check("pelunasan_belum" in blocking
          and "120.000.000" in codes["pelunasan_belum"]["detail"],
          "sisa kewajiban pembeli disebut nominalnya",
          codes.get("pelunasan_belum", {}).get("detail", "")[:90])
    check("inspeksi_serah_terima" in blocking,
          "rumah tanpa inspeksi serah terima tidak boleh diserahkan",
          codes.get("inspeksi_serah_terima", {}).get("detail", "")[:90])
    check(chk.get("can_issue") is False and chk.get("detail", "").startswith(
        f"{len(blocking)} pemeriksaan"),
          "layar diberi jawaban tegas: belum boleh diserahterimakan", chk.get("detail", "")[:80])

    res = fx.api("POST", "/handover/issue", fin, json={"unit_id": unit["id"]})
    d = detail_of(res)
    check(res.status_code == 409 and "DITAHAN" in d and "Keramik" in d,
          "penerbitan BAST dijawab 409 dengan SEBAB satu per satu (bukan sukses palsu)",
          d[:120])
    after = fx.db.units.find_one({"id": unit["id"]}, {"_id": 0, "status": 1})
    check(after.get("status") != "handed_over",
          "status rumah TIDAK berubah setelah penerbitan ditahan",
          f"status tetap {after.get('status')}")
    return chk


# ========================================== C. terobosan & pembatalan berjejak
def flow_c(fin, lead, pmh, blocked):
    head("C. Terobosan hanya untuk yang berwenang, beralasan, dan bisa dibatalkan")
    unit = blocked["unit"]
    res = fx.api("POST", "/handover/issue", pmh, json={
        "unit_id": unit["id"], "override": True,
        "override_reason": "Pembeli memaksa pindah karena kontrak sewa habis pekan ini."})
    check(res.status_code == 403 and "kewenangan" in detail_of(res).lower(),
          "Manajer Proyek TIDAK boleh menerobos daftar periksa sendiri (pemisahan tugas)",
          detail_of(res)[:110])

    res = fx.api("POST", "/handover/issue", lead, json={
        "unit_id": unit["id"], "override": True, "override_reason": "buru2"})
    check(res.status_code in (400, 422) and "10" in detail_of(res),
          "alasan terobosan kurang dari 10 huruf ditolak kontrak permintaan",
          detail_of(res)[:110])

    reason = "Pembeli sudah menempati rumah lebih dulu atas persetujuan direksi."
    res = fx.api("POST", "/handover/issue", lead, json={
        "unit_id": unit["id"], "override": True, "override_reason": reason})
    doc = body(res)
    check(res.status_code == 200 and doc.get("override_by") and doc.get("number", "").startswith("BAST/"),
          "Manajer Keuangan boleh menerobos; BAST terbit bernomor + jejak siapa & alasannya",
          f"{doc.get('number')} oleh {doc.get('override_by')}")
    check(len(doc.get("override_items") or []) >= 3,
          "pemeriksaan yang diterobos DICATAT satu per satu di dokumen",
          f"{len(doc.get('override_items') or [])} pemeriksaan diterobos")
    task = fx.db.tasks.find_one({"related_entity_type": "unit_handover",
                                 "related_entity_id": doc.get("id")}, {"_id": 0, "title": 1})
    check(bool(task), "terobosan melahirkan TUGAS tinjauan (bukan hanya catatan)",
          (task or {}).get("title", "")[:80])
    unit_now = fx.db.units.find_one({"id": unit["id"]}, {"_id": 0, "status": 1})
    check(unit_now.get("status") == "handed_over",
          "status rumah berubah menjadi 'Sudah serah terima'", unit_now.get("status"))

    dup = fx.api("POST", "/handover/issue", fin, json={"unit_id": unit["id"]})
    check(dup.status_code == 200 and body(dup).get("number") == doc.get("number"),
          "penerbitan kedua atas rumah yang sama IDEMPOTEN (tidak ada BAST kembar)",
          f"nomor tetap {body(dup).get('number')}")

    res = fx.api("POST", f"/handover/{doc['id']}/cancel", fin, json={
        "reason": "Salah unit, seharusnya rumah sebelah yang diserahkan."})
    check(res.status_code == 403, "pembatalan BAST bukan wewenang staf keuangan biasa",
          detail_of(res)[:90])
    res = fx.api("POST", f"/handover/{doc['id']}/cancel", lead, json={"reason": "salah"})
    check(res.status_code in (400, 422), "alasan pembatalan kurang dari 10 huruf ditolak",
          detail_of(res)[:90])
    res = fx.api("POST", f"/handover/{doc['id']}/cancel", lead, json={
        "reason": "Salah unit; yang seharusnya diserahkan adalah rumah sebelah."})
    cancelled = body(res)
    check(res.status_code == 200 and cancelled.get("state") == "cancelled",
          "BAST salah terbit bisa DIBATALKAN beralasan (dokumen tidak dihapus)",
          f"{cancelled.get('number')} → {cancelled.get('state_label')}")
    unit_now = fx.db.units.find_one({"id": unit["id"]}, {"_id": 0, "status": 1})
    check(unit_now.get("status") != "handed_over",
          "status rumah dikembalikan setelah BAST dibatalkan", unit_now.get("status"))
    again = fx.api("POST", f"/handover/{doc['id']}/cancel", lead, json={
        "reason": "Mencoba membatalkan dokumen yang sama dua kali."})
    check(again.status_code == 400 and "sudah dibatalkan" in detail_of(again).lower(),
          "pembatalan kedua ditolak (tidak bisa membatalkan dua kali)",
          detail_of(again)[:90])


# ================================================= D. BAST bersih + garansi
def flow_d(fin, ready, day: str = None):
    head("D. BAST rumah yang benar-benar siap: bernomor, berPDF, memulai masa garansi")
    unit = ready["unit"]
    chk = body(fx.api("GET", "/handover/check", fin, params={"unit_id": unit["id"]}))
    check(chk.get("can_issue") is True and not chk.get("blocking"),
          "rumah yang bersih dinyatakan SIAP diserahterimakan", chk.get("detail", "")[:80])

    ref = f"{fx.TAG}-bast-{unit['code']}"
    payload = {"unit_id": unit["id"], "received_by": "Penerima uji Fase 50",
               "meter_air": "0124", "meter_listrik": "8891", "keys_handed": 3,
               "note": "Serah terima uji Fase 50.", "client_ref": ref}
    if day:
        payload["handed_over_at"] = day
    res = fx.api("POST", "/handover/issue", fin, json=payload)
    doc = body(res)
    check(res.status_code == 200 and doc.get("number", "").startswith("BAST/")
          and not doc.get("override_by"),
          "BAST terbit tanpa terobosan, bernomor resmi", doc.get("number"))
    check(unit["code"] in (msg(res) or "") and "garansi" in (msg(res) or "").lower(),
          "jawaban server menyebut rumah mana & bahwa masa garansi mulai", msg(res)[:110])

    w = {x["category"]: x for x in doc.get("warranties", [])}
    plan_rows = fx.api("GET", "/handover/warranty/plan", fin).json().get("data") or []
    plan = {p["category"]: p for p in plan_rows}
    check("struktur" in w and w["struktur"]["months"] == plan["struktur"]["months"]
          and w["struktur"]["months"] >= 60,
          "masa garansi diambil dari Pusat Konfigurasi (bukan angka mati di kode)",
          f"struktur {w.get('struktur', {}).get('months')} bulan s/d "
          f"{w.get('struktur', {}).get('expires_at')}")
    check(w.get("finishing", {}).get("months", 99) < w.get("struktur", {}).get("months", 0),
          "masa garansi BERBEDA per bagian (finishing lebih pendek dari struktur)",
          f"finishing {w.get('finishing', {}).get('months')} bulan vs struktur "
          f"{w.get('struktur', {}).get('months')} bulan")

    unit_now = fx.db.units.find_one({"id": unit["id"]}, {"_id": 0, "status": 1,
                                                         "handover_number": 1})
    check(unit_now.get("status") == "handed_over"
          and unit_now.get("handover_number") == doc.get("number"),
          "dokumen & rumah saling menunjuk (bisa ditelusuri dua arah)",
          f"{unit_now.get('status')} · {unit_now.get('handover_number')}")

    replay = fx.api("POST", "/handover/issue", fin, json=payload)
    check(replay.status_code == 200 and body(replay).get("number") == doc.get("number"),
          "kiriman ulang dengan penanda antrean yang sama TIDAK membuat dokumen kedua",
          f"nomor tetap {body(replay).get('number')}")

    pdf = fx.api("GET", f"/handover/{doc['id']}/pdf", fin)
    ok_pdf = pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    check(ok_pdf, "BAST bisa dicetak jadi PDF nyata",
          f"{len(pdf.content)} bytes, {pdf.headers.get('Content-Type')}")

    st = body(fx.api("GET", "/handover/warranty/unit", fin, params={"unit_id": unit["id"]}))
    check(st.get("missing") is False and len(st.get("rows") or []) >= 6,
          "layar garansi rumah menampilkan keadaan setiap bagian",
          st.get("detail", "")[:100])
    return doc


def flow_d_missing(fin, project, claimer):
    head("D2. Rumah yang BELUM diserahterimakan mengaku 'belum ada data' (bukan 0 hari)")
    unit = fx.make_unit(project, "UJI-BELUM", progress=10)
    st = body(fx.api("GET", "/handover/warranty/unit", fin, params={"unit_id": unit["id"]}))
    check(st.get("missing") is True and "belum ada data" in st.get("detail", "").lower(),
          "masa garansi rumah yang belum diserahkan mengaku belum ada datanya",
          st.get("detail", "")[:110])
    res = fx.api("POST", "/handover/claims", claimer, json={
        "unit_id": unit["id"], "category": "listrik", "title": "Lampu teras mati"})
    check(res.status_code == 400 and "belum diserahterimakan" in detail_of(res).lower()
          and "garansi" in detail_of(res).lower(),
          "klaim garansi atas rumah yang belum diserahkan ditolak dengan sebab yang jelas",
          detail_of(res)[:130])
    return unit


# ================================================== E. klaim garansi bergigi
def flow_e(pm, site, owner, sales, ready_old, ready_new):
    head("E. Klaim garansi: masa dijaga, pekerjaan nyata, bukti wajib, pemisahan tugas")
    old_unit, new_unit = ready_old["unit"], ready_new["unit"]

    res = fx.api("POST", "/handover/claims", sales, json={
        "unit_id": old_unit["id"], "category": "finishing", "source": "komplain_cs",
        "title": "Cat dinding ruang tamu mengelupas",
        "description": "Pembeli mengeluh cat mengelupas di dekat jendela."})
    doc = body(res)
    check(res.status_code == 200 and doc.get("state") == "ditolak"
          and doc.get("reject_reason") == "lewat_masa_garansi",
          "klaim bagian yang masa garansinya LEWAT tercatat & DITOLAK (tidak hilang)",
          f"{doc.get('number')} → {doc.get('state_label')}")
    check(str(doc.get("warranty_expires_at") or "") in (doc.get("reject_detail") or ""),
          "penolakan menyebut TANGGAL habisnya masa garansi (bisa diperiksa pembeli)",
          (doc.get("reject_detail") or "")[:130])

    res = fx.api("POST", "/handover/claims", sales, json={
        "unit_id": old_unit["id"], "category": "struktur", "source": "komplain_cs",
        "title": "Retak diagonal pada kolom belakang",
        "description": "Retak melebar sejak musim hujan."})
    claim = body(res)
    check(res.status_code == 200 and claim.get("state") == "diajukan",
          "klaim bagian yang MASIH bergaransi diterima sebagai pekerjaan",
          f"{claim.get('number')} · sisa {claim.get('days_left_at_submit')} hari")
    task = fx.db.tasks.find_one({"related_entity_type": "warranty_claim",
                                 "related_entity_id": claim.get("id")}, {"_id": 0, "title": 1})
    check(bool(task), "klaim baru muncul sebagai TUGAS di papan divisi (tidak diam di tabel)",
          (task or {}).get("title", "")[:90])

    res = fx.api("POST", f"/handover/claims/{claim['id']}/decide", sales,
                 json={"accept": True})
    check(res.status_code == 403, "sales tidak berhak memutuskan klaim (hanya mengajukan)",
          detail_of(res)[:90])

    res = fx.api("POST", f"/handover/claims/{claim['id']}/decide", pm, json={
        "accept": False, "reject_reason": "di_luar_lingkup", "reason": "kecil"})
    check(res.status_code in (400, 422) and "10" in detail_of(res),
          "penolakan tanpa alasan >=10 huruf ditolak (pembeli berhak tahu dasarnya)",
          detail_of(res)[:100])

    res = fx.api("POST", f"/handover/claims/{claim['id']}/decide", pm, json={
        "accept": True, "assigned_to": "site@sipro.co.id",
        "reason": "Retak struktur harus diperiksa dan diperbaiki segera."})
    accepted = body(res)
    check(res.status_code == 200 and accepted.get("state") == "dikerjakan"
          and accepted.get("punch_id"),
          "klaim yang diterima melahirkan PEKERJAAN perbaikan nyata (punch item)",
          f"punch {str(accepted.get('punch_id'))[:8]} untuk {accepted.get('assigned_to')}")
    punch = fx.db.punch_items.find_one({"id": accepted.get("punch_id")},
                                        {"_id": 0, "title": 1, "source": 1, "assigned_to": 1})
    check(bool(punch) and punch.get("source") == "warranty_claim"
          and claim["number"] in punch.get("title", ""),
          "pekerjaan perbaikan menunjuk balik ke nomor klaimnya (dua arah)",
          (punch or {}).get("title", "")[:90])

    res = fx.api("POST", f"/handover/claims/{claim['id']}/complete", site, json={
        "note": "Sudah disuntik epoxy.", "photo_file_ids": []})
    check(res.status_code in (400, 422) and ("foto" in detail_of(res).lower()
                                             or "photo" in detail_of(res).lower()),
          "perbaikan TIDAK bisa dinyatakan selesai tanpa bukti foto",
          detail_of(res)[:110])

    photo = fx.upload_photo(site)
    res = fx.api("POST", f"/handover/claims/{claim['id']}/complete", site, json={
        "note": "Retak disuntik epoxy lalu diaci ulang.", "photo_file_ids": [photo]})
    done = body(res)
    check(res.status_code == 200 and done.get("state") == "selesai"
          and done.get("fix_photos") == [photo],
          "perbaikan selesai tersimpan bersama bukti fotonya",
          f"{done.get('state_label')} · {len(done.get('fix_photos') or [])} foto")

    res = fx.api("POST", f"/handover/claims/{claim['id']}/verify", site, json={"passed": True})
    check(res.status_code == 403, "pelaksana lapangan tidak berhak menyatakan lulus sendiri",
          detail_of(res)[:90])

    # Pemisahan tugas di DATA: pekerjaan yang diselesaikan pm tidak boleh diverifikasi pm.
    photo2 = fx.upload_photo(pm)
    res2 = fx.api("POST", f"/handover/claims/{claim['id']}/verify", pm, json={
        "passed": False, "reason": "Acian belum rata, tolong dihaluskan dulu."})
    back = body(res2)
    check(res2.status_code == 200 and back.get("state") == "dikerjakan",
          "pemeriksa boleh MENGEMBALIKAN perbaikan beralasan (pekerjaan diulang)",
          f"{back.get('state_label')} · {back.get('verify_note')}")
    res = fx.api("POST", f"/handover/claims/{claim['id']}/complete", pm, json={
        "note": "Acian dihaluskan ulang.", "photo_file_ids": [photo2]})
    check(res.status_code == 200 and body(res).get("completed_by") == "pm@sipro.co.id",
          "perbaikan ulang dicatat beserta siapa yang mengerjakannya",
          body(res).get("state_label"))
    res = fx.api("POST", f"/handover/claims/{claim['id']}/verify", pm, json={"passed": True})
    check(res.status_code == 400 and "mengerjakan" in detail_of(res).lower(),
          "pemeriksa TIDAK BOLEH orang yang mengerjakan perbaikannya (dijaga di data)",
          detail_of(res)[:110])
    res = fx.api("POST", f"/handover/claims/{claim['id']}/verify", owner, json={
        "passed": True, "note": "Retak sudah tertutup rapi."})
    verified = body(res)
    check(res.status_code == 200 and verified.get("state") == "diverifikasi"
          and verified.get("verified_by") == "owner@sipro.co.id",
          "pemeriksaan oleh orang lain diterima dan tercatat namanya",
          f"{verified.get('state_label')} oleh {verified.get('verified_by')}")

    res = fx.api("POST", f"/handover/claims/{claim['id']}/close", owner, json={
        "ack_by": "Pembeli uji Fase 50", "ack_note": "Sudah saya periksa, terima kasih."})
    closed = body(res)
    check(res.status_code == 200 and closed.get("state") == "ditutup" and closed.get("ack_by"),
          "penutupan klaim butuh PENGAKUAN pembeli (bukan diklaim sepihak)",
          f"{closed.get('state_label')} · diakui {closed.get('ack_by')}")
    punch_now = fx.db.punch_items.find_one({"id": accepted.get("punch_id")},
                                            {"_id": 0, "status": 1})
    check((punch_now or {}).get("status") == "closed",
          "pekerjaan perbaikannya ikut ditutup (tidak ada punch menggantung)",
          (punch_now or {}).get("status"))

    res = fx.api("POST", f"/handover/claims/{claim['id']}/close", owner, json={})
    check(res.status_code == 400, "klaim yang sudah ditutup tidak bisa ditutup dua kali",
          detail_of(res)[:100])
    return claim


def flow_e_report(pm, project):
    head("E2. Rekap klaim garansi bisa dijumlahkan & mengaku bila belum ada datanya")
    rep = body(fx.api("GET", "/handover/claims/report", pm,
                      params={"project_id": project["id"]}))
    tie = rep.get("tie_out") or {}
    check(tie.get("matches") is True and tie.get("sum_per_state") == rep.get("total"),
          "\u03a3 klaim per status = jumlah klaim (pembaca bisa menjumlahkan sendiri)",
          f"{tie.get('sum_per_state')} = {tie.get('total')}")
    check(rep.get("avg_days_to_close") is not None,
          "rata-rata hari penyelesaian dihitung dari klaim yang benar-benar ditutup",
          f"{rep.get('avg_days_to_close')} hari")
    empty = body(fx.api("GET", "/handover/claims/report", pm,
                        params={"project_id": project["id"], "period": "2019-03"}))
    check(empty.get("missing") is True and empty.get("avg_days_to_close") is None
          and "belum ada data" in (empty.get("avg_days_note") or "").lower(),
          "masa tanpa klaim mengaku 'belum ada data' (bukan rata-rata 0 hari)",
          (empty.get("avg_days_note") or "")[:110])
    board = fx.api("GET", "/handover/warranty/board", pm,
                   params={"project_id": project["id"]}).json()
    rows = board.get("data") or []
    check(len(rows) >= 1 and all("warranty" in r for r in rows),
          "papan garansi menampilkan rumah yang sudah diserahkan + keadaan garansinya",
          f"{len(rows)} rumah · {board.get('detail', '')[:60]}")


# ======================================================= F. portal pembeli
def flow_f(portal_hdr, ready_new, ready_old):
    head("F. Portal pembeli: melihat masa garansi & mengajukan klaim sendiri")
    rows = fx.api("GET", "/portal/warranty", portal_hdr).json().get("data") or []
    mine = [r for r in rows if r["unit"]["id"] == ready_new["unit"]["id"]]
    check(bool(mine) and mine[0].get("missing") is False,
          "pembeli melihat rumahnya beserta masa garansi tiap bagian",
          (mine[0].get("detail") if mine else "tidak ada baris")[:110])
    reg = fx.api("GET", "/portal/reference", portal_hdr).json().get("data") or {}
    check("warranty_category" in reg and "warranty_claim_state" in reg,
          "portal memakai kamus data yang SAMA dengan layar staf (bukan label sendiri)",
          f"{len(reg)} grup tersedia")
    res = fx.api("POST", "/portal/warranty/claims", portal_hdr, json={
        "unit_id": ready_new["unit"]["id"], "category": "plumbing",
        "title": "Air keran dapur kecil sekali",
        "description": "Sejak minggu lalu tekanan air di dapur turun."})
    doc = body(res)
    check(res.status_code == 200 and doc.get("source") == "portal_pembeli"
          and doc.get("state") == "diajukan",
          "klaim dari portal tercatat sebagai asal 'portal pembeli'",
          f"{doc.get('number')} · {doc.get('source_label')}")
    res = fx.api("POST", "/portal/warranty/claims", portal_hdr, json={
        "unit_id": ready_old["unit"]["id"], "category": "listrik",
        "title": "Mencoba klaim rumah orang lain"})
    check(res.status_code == 403 and "tidak terdaftar" in detail_of(res).lower(),
          "pembeli tidak bisa mengajukan klaim untuk rumah orang lain (403)",
          detail_of(res)[:100])
    mylist = fx.api("GET", "/portal/warranty/claims", portal_hdr).json()
    check((mylist.get("total") or 0) >= 1,
          "pembeli bisa melihat riwayat klaimnya sendiri",
          f"{mylist.get('total')} klaim · {str(mylist.get('detail'))[:60]}")


# ============================================ G. antrean perangkat terpadu
def flow_g(site, pm, project, worker, unit):
    head("G. Antrean perangkat terpadu (50B): kiriman ulang TIDAK menggandakan data")
    day = fx.today()

    ref = f"{fx.TAG}-absensi-1"
    payload = {"project_id": project["id"], "work_date": day, "client_ref": ref,
               "entries": [{"worker_id": worker["id"], "status": "full",
                            "overtime_hours": 2}]}
    first = fx.api("POST", "/labor/attendance", site, json=payload)
    second = fx.api("POST", "/labor/attendance", site, json=payload)
    rows = fx.db.labor_attendance.count_documents(
        {"project_id": project["id"], "work_date": day, "worker_id": worker["id"]})
    check(first.status_code == 200 and second.status_code == 200 and rows == 1,
          "absensi yang dikirim dua kali dengan penanda sama hanya tercatat SEKALI",
          f"{rows} baris absensi; kiriman ke-2 replay={second.json().get('replay')}")
    check(second.json().get("replay") is True
          and "sudah pernah diterima" in msg(second).lower(),
          "kiriman ulang dijawab jujur 'sudah pernah diterima' (bukan galat)",
          msg(second)[:110])

    bad_ref = f"{fx.TAG}-absensi-tolak"
    bad = fx.api("POST", "/labor/attendance", site, json={
        "project_id": project["id"], "work_date": day, "client_ref": bad_ref,
        "entries": [{"worker_id": "tidak-ada", "status": "full"}]})
    check(bad.status_code == 400 and "tidak ditemukan" in detail_of(bad).lower(),
          "kiriman antrean yang salah DITOLAK dengan alasan asli server",
          detail_of(bad)[:100])
    retry = fx.api("POST", "/labor/attendance", site, json={
        "project_id": project["id"], "work_date": fx.days_ago(1), "client_ref": bad_ref,
        "entries": [{"worker_id": worker["id"], "status": "half"}]})
    check(retry.status_code == 200 and retry.json().get("replay") is not True,
          "penanda yang DITOLAK dilepas: pemakai bisa memperbaiki lalu mengirim ulang",
          msg(retry)[:100])

    dref = f"{fx.TAG}-diary-1"
    dpay = {"project_id": project["id"], "log_date": day, "weather": "cerah",
            "workforce": 4, "work_description": "Pengecoran lantai uji Fase 50",
            "client_ref": dref}
    d1 = fx.api("POST", "/field/diary", site, json=dpay)
    d2 = fx.api("POST", "/field/diary", site, json=dpay)
    cnt = fx.db.site_diaries.count_documents({"project_id": project["id"]})
    check(d1.status_code == 200 and d2.json().get("replay") is True and cnt == 1,
          "buku harian yang dikirim dua kali hanya tercatat SEKALI",
          f"{cnt} catatan; kiriman ke-2 replay")

    pref = f"{fx.TAG}-punch-1"
    ppay = {"project_id": project["id"], "unit_id": unit["id"],
            "title": "Nat keramik kamar mandi retak", "description": "Temuan uji antrean",
            "severity": "medium", "client_ref": pref}
    p1 = fx.api("POST", "/field/punchlist", site, json=ppay)
    p2 = fx.api("POST", "/field/punchlist", site, json=ppay)
    pid = body(p1).get("id")
    cnt = fx.db.punch_items.count_documents({"unit_id": unit["id"],
                                             "title": ppay["title"]})
    check(p1.status_code == 200 and p2.json().get("replay") is True and cnt == 1,
          "temuan punch yang dikirim dua kali hanya melahirkan SATU temuan",
          f"{cnt} temuan · id {str(pid)[:8]}")

    photo = fx.upload_photo(site)
    sref = f"{fx.TAG}-punchstatus-1"
    spay = {"status": "closed", "note": "Nat diisi ulang.", "photos": [photo],
            "client_ref": sref}
    s1 = fx.api("POST", f"/field/punchlist/{pid}/status", site, json=spay)
    s2 = fx.api("POST", f"/field/punchlist/{pid}/status", site, json=spay)
    after = fx.db.punch_items.find_one({"id": pid}, {"_id": 0, "fix_photos": 1, "status": 1})
    check(s1.status_code == 200 and s2.json().get("replay") is True
          and len(after.get("fix_photos") or []) == 1,
          "bukti perbaikan tidak terlampir dua kali walau kiriman diulang",
          f"status {after.get('status')} · {len(after.get('fix_photos') or [])} foto")

    intake = fx.db.offline_intake.count_documents({"client_ref": {"$regex": f"^{fx.TAG}"}})
    check(intake >= 5, "setiap penanda antrean tercatat sebagai kunci di server",
          f"{intake} penanda tersimpan")


# ==================================================================== jalankan
def main():
    print("\n" + "=" * 78)
    print("POC FASE 50 — SERAH TERIMA UNIT, GARANSI, KLAIM & ANTREAN PERANGKAT")
    print("=" * 78)
    fin = fx.login("finance@sipro.co.id")
    lead = fx.login("finlead@sipro.co.id")
    pm = fx.login("pm@sipro.co.id")
    site = fx.login("site@sipro.co.id")
    owner = fx.login("owner@sipro.co.id")
    sales = fx.login("manager@sipro.co.id")   # manajer sales: boleh mengajukan klaim

    project = fx.make_project()
    blocked = fx.blocked_unit(project, "UJI-TAHAN", "Pembeli Uji Tertahan")
    ready_new = fx.ready_unit(project, "UJI-SIAP", "Pembeli Uji Siap")
    ready_old = fx.ready_unit(project, "UJI-LAMA", "Pembeli Uji Lama")
    worker = fx.make_worker(project)

    try:
        flow_a(pm)
        flow_b(fin, blocked)
        flow_c(fin, lead, pm, blocked)
        flow_d(fin, ready_new)
        # Rumah kedua diserahkan 400 hari lalu: masa garansi finishing sudah lewat, struktur
        # masih jauh dari habis — bahan uji "klaim lewat masa garansi".
        flow_d(fin, ready_old, day=fx.days_ago(400))
        flow_d_missing(fin, project, pm)
        flow_e(pm, site, owner, sales, ready_old, ready_new)
        flow_e_report(pm, project)
        phone = ready_new["buyer"]["customer"]["phone"]
        fx.api("POST", "/portal/auth/request-otp", {}, json={"identifier": phone})
        ver = fx.api("POST", "/portal/auth/verify-otp", {},
                     json={"identifier": phone, "code": "000000"})
        token = ((ver.json() or {}).get("token")
                 or (ver.json() or {}).get("access_token")
                 or ((ver.json() or {}).get("data") or {}).get("token"))
        if token:
            flow_f({"Authorization": f"Bearer {token}"}, ready_new, ready_old)
        else:
            check(False, "pembeli bisa masuk portal dengan OTP master pengujian",
                  detail_of(ver)[:120])
        flow_g(site, pm, project, worker, ready_new["unit"])
    finally:
        head("Bersih-bersih (jangan meninggalkan BAST/klaim/punch menggantung)")
        print("  dibuang:", fx.purge())
        sisa = fx.orphans()
        print("  sisa   :", sisa)
        check(all(v == 0 for v in sisa.values()),
              "POC tidak meninggalkan dokumen/pekerjaan menggantung", str(sisa))

    print("\n" + "=" * 78)
    if FAIL:
        print(f"HASIL: GAGAL — {len(FAIL)} pemeriksaan merah dari {len(PASS) + len(FAIL)}:")
        for f in FAIL:
            print(f"  - {f}")
        print("=" * 78)
        sys.exit(1)
    print(f"HASIL: PASS — {len(PASS)} pemeriksaan hijau. Inti Fase 50 terbukti.")
    print("=" * 78)


if __name__ == "__main__":
    main()
