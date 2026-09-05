#!/usr/bin/env python3
"""poc_49.py — POC inti Fase 49 (Penutupan Buku, Laporan Owner, Pajak & Kepatuhan) TANPA UI.

Membuktikan tujuh janji yang sebelumnya TIDAK PUNYA JALAN di aplikasi:

  A. Kamus Data (SSOT) Fase 49 benar-benar dimuat; nilai enum di luar kamus ditolak 400
     beserta daftar pilihan yang sah.
  B. Tutup bulan BERGIGI: daftar periksa menyebut sebab satu per satu, penutupan DITAHAN,
     terobosan hanya untuk peran berwenang + alasan ≥10 huruf, dan terobosan melahirkan
     tugas tinjauan.
  C. Tutup TAHUN: laba tahun berjalan pindah ke Laba Ditahan lewat jurnal SEIMBANG,
     idempoten, dan bisa DIBALIK (reversal berjejak) — bukan dihapus.
  D. Arus kas PER PROYEK: Σ(proyek + tidak teralokasi) = arus kas konsolidasi (tie-out).
  E. Paket laporan owner membawa status periode, siapa menutup, alasan terobosan, dan
     bagian yang memang belum ada datanya (bukan Rp 0 palsu).
  F. e-Faktur v2: pengganti bernomor baru berjejak, pembatalan beralasan, dan EKSPOR yang
     MENAHAN diri bila identitas wajib belum lengkap + menyebut faktur mana.
  G. e-Bupot: potongan PPh nyata (fee mitra & pembayaran tagihan) melahirkan bukti potong
     bernomor; pembayaran memotong PPh sehingga vendor terima NETO dan potongan menjadi
     utang pajak; pembetulan memakai NOMOR YANG SAMA; tie-out potongan↔bukti jujur.
  H. Rekap SPT Masa PPN dapat direkonstruksi; masa tanpa data mengaku "belum ada data".

Semua bahan dibuat sendiri lewat API resmi (bertanda `gate49`, tahun uji 2024 yang kosong di
data demo) lalu dibuang; antrean event ditunggu kosong sebelum pemeriksaan & pembersihan
supaya tidak meninggalkan jurnal menggantung.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import _fixture49 as fx  # noqa: E402

PASS, FAIL = [], []
RESTORE = {}


def check(ok: bool, label: str, detail: str = ""):
    (PASS if ok else FAIL).append(label)
    print(f"  {'PASS ' if ok else 'GAGAL'} {label}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def rp(n) -> str:
    return f"Rp {int(n or 0):,}"


def head(title: str):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def body(resp) -> dict:
    try:
        return resp.json().get("data") or {}
    except Exception:  # noqa: BLE001
        return {}


def detail_of(resp) -> str:
    try:
        return str(resp.json().get("detail") or "")[:160]
    except Exception:  # noqa: BLE001
        return resp.text[:160]


# ============================================================ A. SSOT Fase 49
def flow_a(fin):
    head("A. Kamus Data (SSOT) Fase 49 dimuat & memaksa nilai yang sah")
    reg = fx.api("GET", "/reference", fin).json().get("data") or {}
    wajib = ["closing_check_item", "closing_check_state", "year_closing_state", "faktur_state",
             "tax_export_format", "vat_return_state", "withholding_kind", "withholding_basis",
             "withholding_state", "withholding_object_code", "withholding_party_kind"]
    missing = [g for g in wajib if g not in reg]
    check(not missing, "seluruh grup enum Fase 49 terdaftar di /api/reference",
          f"{len(wajib)} grup ada" if not missing else f"belum ada: {missing}")
    kinds = {o["value"]: o["label"] for o in (reg.get("withholding_kind") or {}).get("options", [])}
    check(len(kinds) >= 4 and all(v for v in kinds.values()),
          "label jenis pemotongan diambil dari kamus (layar tidak menulis sendiri)",
          "; ".join(list(kinds.values())[:2]))
    obj = reg.get("withholding_object_code") or {}
    check(obj.get("strict") is False and len(obj.get("options", [])) >= 10,
          "kode objek pajak: daftar bantu TIDAK strict (kode lain tetap boleh diisi)",
          f"{len(obj.get('options', []))} kode acuan")

    bad = fx.api("POST", "/tax/compliance/withholding/issue", fin, json={
        "kind": "pph99", "party_name": "PT Uji SSOT", "base": 1_000_000, "rate": 2})
    check(bad.status_code == 400 and "pph23" in bad.text,
          "jenis pemotongan di luar kamus ditolak 400 + daftar pilihan yang sah",
          detail_of(bad))
    bad2 = fx.api("POST", "/tax/compliance/withholding/issue", fin, json={
        "kind": "pph23", "party_name": "PT Uji SSOT", "base": 1_000_000, "rate": 2,
        "object_code": "24104-07"})
    check(bad2.status_code == 400 and "NN-NNN-NN" in bad2.text,
          "pola kode objek pajak salah ditolak dengan contoh bentuk yang benar",
          detail_of(bad2))


# ============================================================ B. tutup bulan bergigi
def flow_b(fin, lead, ctx):
    head("B. Daftar periksa tutup buku MENAHAN penutupan (49A)")
    per = fx.PERIOD
    # Dua jurnal nyata di bulan uji: pendapatan & beban (dasar laba tahun 2024).
    j1 = fx.journal(lead, "pendapatan uji tutup tahun", [
        {"account_code": "1-1200", "debit": 500_000_000, "credit": 0},
        {"account_code": "4-1100", "debit": 0, "credit": 500_000_000}])
    j2 = fx.journal(lead, "beban uji tutup tahun", [
        {"account_code": "6-1200", "debit": 200_000_000, "credit": 0},
        {"account_code": "1-1200", "debit": 0, "credit": 200_000_000}])
    check(j1.status_code == 200 and j2.status_code == 200,
          "jurnal uji periode 2024-05 terbit lewat API resmi",
          f"{body(j1).get('entry_no')} & {body(j2).get('entry_no')}")

    chk = body(fx.api("GET", "/gl/periods/close-check", lead, params={"period": per}))
    states = {i["code"]: i["state"] for i in chk["items"]}
    check(chk["can_close"] is True and not chk["blocking"],
          "periode bersih boleh ditutup (tidak ada pemeriksaan yang menahan)",
          f"{len(chk['items'])} pemeriksaan, {chk['warning_count']} peringatan")
    check(states.get("bank_belum_dicocokkan") == "missing_data",
          "bulan tanpa mutasi bank mengaku 'belum ada data' (bukan 'beres' palsu)",
          next(i["detail"] for i in chk["items"] if i["code"] == "bank_belum_dicocokkan")[:80])
    check(chk["net_income"] == 300_000_000,
          "laba periode dihitung dari jurnal nyata", rp(chk["net_income"]))

    # Mutasi bank BELUM dicocokkan pada TANGGAL TERAKHIR bulan — dulu lolos karena batas
    # pemeriksaan memakai tanggal terakhir sebagai batas eksklusif (cacat off-by-one).
    fx.make_bank_txn(f"{per}-31", 750_000_000, "TRANSFER MASUK belum jelas (uji Fase 49)")
    chk2 = body(fx.api("GET", "/gl/periods/close-check", lead, params={"period": per}))
    bank = next(i for i in chk2["items"] if i["code"] == "bank_belum_dicocokkan")
    check(bank["state"] == "blocking" and chk2["can_close"] is False,
          "mutasi bank tanggal TERAKHIR bulan tetap MENAHAN penutupan (off-by-one ditutup)",
          bank["detail"][:100])
    check("750.000.000" in bank["detail"] and bank.get("link"),
          "sebab menyebut nilai & tautan ke halaman sumbernya", bank.get("link"))

    hold = fx.api("POST", "/gl/periods/close", fin, json={"period": per})
    check(hold.status_code == 409 and "DITAHAN" in hold.text,
          "penutupan tanpa terobosan DITAHAN (409) + sebab disebut satu per satu",
          detail_of(hold))

    forb = fx.api("POST", "/gl/periods/close", fin, json={
        "period": per, "override": True, "override_reason": "alasan cukup panjang untuk uji"})
    check(forb.status_code == 403,
          "peran finance TIDAK boleh menerobos daftar periksa (403)", detail_of(forb))

    short = fx.api("POST", "/gl/periods/close", lead, json={
        "period": per, "override": True, "override_reason": "buru2"})
    check(short.status_code == 400 and "10" in short.text,
          "alasan terobosan < 10 huruf ditolak", detail_of(short))

    reason = "Tutup paksa untuk uji: mutasi bank dicocokkan bulan depan sesuai memo direksi."
    ok = fx.api("POST", "/gl/periods/close", lead, json={
        "period": per, "override": True, "override_reason": reason, "note": "POC49"})
    doc = body(ok)
    check(ok.status_code == 200 and doc.get("status") == "closed",
          "Manajer Keuangan boleh menerobos dengan alasan tertulis", doc.get("closed_by"))
    check(doc.get("override_by") and doc.get("override_reason") == reason
          and "bank_belum_dicocokkan" in (doc.get("override_items") or []),
          "terobosan tercatat: siapa, alasannya, dan pemeriksaan apa yang dilewati",
          f"{doc.get('override_by')} melewati {doc.get('override_items')}")
    check(len(doc.get("checklist") or []) == len(chk2["items"]),
          "potret daftar periksa saat ditutup disimpan (bisa diaudit ulang)",
          f"{len(doc.get('checklist') or [])} item")

    task = fx.db.tasks.find_one({"source_event": f"closing.override:{fx.ORG}:{per}"})
    check(bool(task), "terobosan melahirkan TUGAS tinjauan (bukan hanya catatan)",
          (task or {}).get("title", "-"))
    audit = fx.db.audit_logs.find_one({"entity_id": per, "action": "close"})
    check(bool(audit), "penutupan tercatat di jejak audit", (audit or {}).get("actor", "-"))

    late = fx.journal(lead, "jurnal terlambat di periode tertutup", [
        {"account_code": "6-1200", "debit": 1_000_000, "credit": 0},
        {"account_code": "1-1200", "debit": 0, "credit": 1_000_000}])
    check(late.status_code == 400 and "ditutup" in late.text.lower(),
          "periode tertutup benar-benar menolak jurnal manual (penutupan bergigi)",
          detail_of(late))
    again = fx.api("POST", "/gl/periods/close", lead, json={"period": per})
    check(again.status_code == 400 and "sudah ditutup" in again.text,
          "menutup periode yang sudah tertutup ditolak", detail_of(again))
    ctx["period_closed"] = True


# ============================================================ C. tutup tahun
def flow_c(fin, lead, ctx):
    head("C. Tutup tahun: laba pindah ke Laba Ditahan, idempoten & reversible (49B)")
    year = fx.YEAR
    before_re = fx.account_balance("3-1900")
    chk = body(fx.api("GET", "/gl/year/check", lead, params={"year": year}))
    check(chk["can_close"] is True and chk["state"] == "open" and not chk["open_months"],
          "tahun boleh ditutup setelah SEMUA bulan bertransaksi ditutup",
          f"bulan: {chk['months']}")
    check(chk["pl"]["net_income"] == 300_000_000,
          "laba tahun dihitung dari akun laba-rugi tahun itu", rp(chk["pl"]["net_income"]))

    forb = fx.api("POST", "/gl/year/close", fin, json={"year": year})
    check(forb.status_code == 403, "peran finance TIDAK boleh menutup tahun buku (403)",
          detail_of(forb))

    res = fx.api("POST", "/gl/year/close", lead, json={"year": year, "note": "POC49"})
    doc = body(res)
    check(res.status_code == 200 and doc.get("state") == "closed"
          and doc.get("net_income") == 300_000_000,
          "tutup tahun memindahkan laba tahun berjalan ke Laba Ditahan",
          f"{doc.get('entry_no')} — {rp(doc.get('net_income'))}")
    je = fx.db.journal_entries.find_one({"id": doc.get("entry_id")}, {"_id": 0})
    check(bool(je) and je["total_debit"] == je["total_credit"],
          "jurnal penutup SEIMBANG", f"D {rp(je['total_debit'])} = K {rp(je['total_credit'])}")
    after_re = fx.account_balance("3-1900")
    check(after_re - before_re == 300_000_000,
          "saldo Laba Ditahan naik tepat sebesar laba tahun itu",
          f"{rp(before_re)} → {rp(after_re)}")
    check(str(je.get("date")).startswith(f"{year}-12-31"),
          "jurnal penutup bertanggal 31 Desember tahun itu (bukan digeser)", str(je.get("date")))

    res2 = fx.api("POST", "/gl/year/close", lead, json={"year": year})
    doc2 = body(res2)
    n_je = fx.db.journal_entries.count_documents(
        {"source_event": f"year_close:{fx.ORG}:{year}"})
    check(res2.status_code == 200 and doc2.get("idempotent") is True and n_je == 1,
          "tutup tahun kedua kali IDEMPOTEN (tidak melahirkan jurnal kedua)",
          f"jurnal penutup: {n_je}")
    check(fx.account_balance("3-1900") == after_re,
          "saldo Laba Ditahan tidak berubah pada panggilan kedua", rp(after_re))

    noreason = fx.api("POST", "/gl/year/reopen", lead, json={"year": year})
    check(noreason.status_code == 400, "buka tahun tanpa alasan ditolak", detail_of(noreason))
    short = fx.api("POST", "/gl/year/reopen", lead, json={"year": year, "reason": "salah"})
    check(short.status_code == 400 and "10" in short.text,
          "alasan buka tahun < 10 huruf ditolak", detail_of(short))
    rsn = "Ada koreksi pendapatan 2024 yang baru ditemukan saat audit internal triwulan ini."
    reo = fx.api("POST", "/gl/year/reopen", lead, json={"year": year, "reason": rsn})
    rdoc = body(reo)
    check(reo.status_code == 200 and rdoc.get("state") == "reopened"
          and rdoc.get("reversal_entry_no"),
          "buka tahun membuat jurnal BALIK berjejak (bukan menghapus jurnal penutup)",
          f"{rdoc.get('entry_no')} dibalik {rdoc.get('reversal_entry_no')}")
    check(fx.account_balance("3-1900") == before_re,
          "Laba Ditahan kembali ke posisi sebelum tutup tahun", rp(before_re))
    rows = fx.api("GET", "/gl/year", lead).json().get("data") or []
    row = next((r for r in rows if r["year"] == year), None)
    check(bool(row) and row["state"] == "reopened" and row.get("reopen_reason") == rsn,
          "riwayat tahun buku menyimpan alasan pembukaan kembali", (row or {}).get("state"))
    ctx["year_reopened"] = True


# ============================================================ D. arus kas per proyek
def flow_d(fin, lead, ctx):
    head("D. Arus kas per proyek + tie-out ke konsolidasi (49C)")
    span = {"date_from": fx.day(-40), "date_to": fx.day(0)}
    # Ambil POSISI AWAL lebih dulu: database demo punya mutasi kas sendiri, jadi yang
    # dibuktikan adalah PERUBAHAN akibat transaksi uji — bukan angka absolut yang kebetulan.
    base = body(fx.api("GET", "/gl/reports/cash-flow-projects", lead, params=span))
    base_un = int((base.get("unassigned") or {}).get("net_change", 0))
    p1 = fx.make_project("Proyek Uji Kas A (POC49)", "POC49-A")
    p2 = fx.make_project("Proyek Uji Kas B (POC49)", "POC49-B")
    ctx["p1"], ctx["p2"] = p1, p2
    b1 = fx.make_bill(fin, "PT Uji Kas A", p1["id"], 60_000_000)
    b2 = fx.make_bill(fin, "PT Uji Kas B", p2["id"], 40_000_000)
    b3 = fx.make_bill(fin, "PT Uji Tanpa Proyek", None, 20_000_000)
    for bill, amount in ((b1, 60_000_000), (b2, 40_000_000), (b3, 20_000_000)):
        r = fx.api("POST", f"/finance/ap/bills/{bill['id']}/pay", fin,
                   json={"amount": amount, "note": "POC49 bayar penuh"})
        if r.status_code != 200:
            print("    (galat bayar tagihan)", detail_of(r))
    fx.settle()

    data = body(fx.api("GET", "/gl/reports/cash-flow-projects", lead, params=span))
    rows = {r["project_id"]: r for r in data["rows"]}
    r1, r2 = rows.get(p1["id"]), rows.get(p2["id"])
    check(bool(r1) and r1["net_change"] == -60_000_000,
          "kas keluar proyek A muncul di barisnya sendiri",
          f"{(r1 or {}).get('project_name')} {rp((r1 or {}).get('net_change'))}")
    check(bool(r2) and r2["net_change"] == -40_000_000,
          "kas keluar proyek B muncul di barisnya sendiri",
          f"{(r2 or {}).get('project_name')} {rp((r2 or {}).get('net_change'))}")
    un = data.get("unassigned") or {}
    delta_un = int(un.get("net_change", 0)) - base_un
    check(bool(un) and delta_un == -20_000_000,
          "pembayaran tanpa proyek ditulis apa adanya di baris 'tidak teralokasi'",
          f"{rp(base_un)} → {rp(un.get('net_change'))} (perubahan {rp(delta_un)})")
    total = sum(r["net_change"] for r in data["rows"]) + int(un.get("net_change", 0))
    check(data["tie_out"]["matches"] is True
          and total == data["consolidated"]["net_change"],
          "TIE-OUT: Σ(proyek + tidak teralokasi) = arus kas konsolidasi",
          f"{rp(total)} = {rp(data['consolidated']['net_change'])}")
    empty = body(fx.api("GET", "/gl/reports/cash-flow-projects", lead,
                        params={"date_from": "2019-01-01", "date_to": "2019-12-31"}))
    check(empty["missing"] == ["jurnal_kas"] and "belum ada" in empty["detail"].lower(),
          "periode tanpa mutasi kas mengaku 'belum ada data' (bukan nol palsu)",
          empty["detail"][:80])


# ============================================================ E. paket laporan owner
def flow_e(owner, ctx):
    head("E. Paket laporan bulanan owner (49D)")
    pack = body(fx.api("GET", "/gl/reports/owner-pack", owner, params={"period": fx.PERIOD}))
    check(pack["status"] == "closed" and pack.get("closed_by"),
          "paket membawa status periode + siapa yang menutup",
          f"{pack['status']} oleh {pack.get('closed_by')}")
    check(bool(pack.get("override_reason")) and pack.get("override_items"),
          "terobosan penutupan ikut TERBACA di laporan owner",
          str(pack.get("override_reason"))[:70])
    check(pack["income_statement"]["total_revenue"] == 500_000_000
          and pack["income_statement"]["total_expense"] == 200_000_000,
          "laba-rugi periode itu benar", rp(pack["income_statement"]["net_income"]))
    check(pack["year_closing"]["state"] == "reopened",
          "status tutup tahun ikut dibawa (tahun uji sudah dibuka kembali)",
          pack["year_closing"]["state"])
    unalloc = [r for r in pack["project_pl"]["rows"] if not r.get("project_id")]
    check(bool(unalloc) and "Tidak teralokasi" in unalloc[0]["project_name"],
          "laba per proyek menampilkan baris 'tidak teralokasi' apa adanya",
          f"{unalloc[0]['project_name']}: {rp(unalloc[0]['net_income'])}" if unalloc else "-")
    kosong = body(fx.api("GET", "/gl/reports/owner-pack", owner, params={"period": "2019-03"}))
    check(set(kosong["missing"]) >= {"laba_rugi", "arus_kas", "laba_per_proyek"}
          and "belum ada datanya" in kosong["detail"],
          "periode tanpa transaksi menyebut bagian yang BELUM ADA DATANYA (bukan Rp 0)",
          kosong["detail"][:100])
    check("tidak bisa berubah" in pack["trust_note"],
          "laporan periode TERTUTUP menyatakan angkanya tidak bisa berubah",
          pack["trust_note"][:70])
    live = body(fx.api("GET", "/gl/reports/owner-pack", owner,
                       params={"period": fx.this_period()}))
    check(live["status"] == "open" and "TERBUKA" in live["trust_note"],
          "laporan periode TERBUKA diberi peringatan angka masih bisa berubah",
          live["trust_note"][:70])
    hist = body(fx.api("GET", "/gl/reports/closing-history", owner))
    check(fx.PERIOD in (hist.get("overridden") or []),
          "riwayat penutupan menandai bulan yang DITEROBOS", str(hist.get("overridden")))


# ============================================================ F. e-Faktur v2
def flow_f(fin, owner, ctx):
    head("F. e-Faktur: pengganti, pembatalan, dan ekspor yang MENAHAN diri (49E)")
    # NPWP perusahaan dikosongkan dulu → ekspor harus ditahan.
    cur = fx.api("GET", "/settings/effective", owner,
                 params={"keys": "tax.company_npwp"}).json()["data"]
    RESTORE["tax.company_npwp"] = cur.get("tax.company_npwp")
    fx.api("PUT", "/settings/tax.company_npwp", owner,
           json={"value": "", "reason": "POC49 uji gerbang ekspor tanpa identitas pemungut"})

    cands = fx.api("GET", "/tax/faktur-candidates", fin).json().get("data") or []
    check(bool(cands), "ada deal yang belum berfaktur untuk diuji", f"{len(cands)} kandidat")
    deal = cands[0]
    fak = body(fx.api("POST", "/tax/faktur", fin, json={"deal_id": deal["deal_id"]}))
    fx.db.faktur_pajak.update_one({"id": fak["id"]},
                                  {"$set": {fx.TAG: True, "buyer_npwp": None}})
    ctx["deal_id"] = deal["deal_id"]
    check(bool(fak.get("number")), "faktur pajak keluaran terbit bernomor seri",
          f"{fak.get('number')} — {rp(fak.get('dpp'))} + PPN {rp(fak.get('ppn'))}")

    chk = body(fx.api("GET", "/tax/compliance/faktur-export/check", fin,
                      params={"period": fak["period"]}))
    scopes = {b["scope"] for b in chk["blocking"]}
    check(chk["can_export"] is False and "perusahaan" in scopes,
          "ekspor DITAHAN saat NPWP perusahaan belum diisi",
          next(b["reason"] for b in chk["blocking"] if b["scope"] == "perusahaan")[:90])

    fx.api("PUT", "/settings/tax.company_npwp", owner, json={
        "value": "0012345678901000", "reason": "POC49 mengisi identitas pemungut untuk uji"})
    chk = body(fx.api("GET", "/tax/compliance/faktur-export/check", fin,
                      params={"period": fak["period"]}))
    faktur_block = [b for b in chk["blocking"] if b["scope"] == "faktur"]
    check(chk["can_export"] is False and faktur_block
          and faktur_block[0]["number"] == fak["number"],
          "ekspor DITAHAN dan MENYEBUT faktur mana yang identitasnya belum lengkap",
          faktur_block[0]["reason"][:90] if faktur_block else "-")
    held = fx.api("GET", "/tax/compliance/faktur-export/file", fin,
                  params={"period": fak["period"], "format": "coretax_xml"})
    check(held.status_code == 409 and "ditahan" in held.text.lower(),
          "unduhan berkas benar-benar ditolak (409), bukan berkas berkolom kosong",
          detail_of(held))

    short = fx.api("POST", f"/tax/compliance/faktur/{fak['id']}/replace", fin,
                   json={"reason": "salah"})
    check(short.status_code == 400, "alasan faktur pengganti < 10 huruf ditolak",
          detail_of(short))
    rep = body(fx.api("POST", f"/tax/compliance/faktur/{fak['id']}/replace", fin, json={
        "reason": "NPWP pembeli belum terisi saat faktur pertama diterbitkan.",
        "buyer_npwp": "0012345678901000"}))
    fx.db.faktur_pajak.update_one({"id": rep["id"]}, {"$set": {fx.TAG: True}})
    old = fx.db.faktur_pajak.find_one({"id": fak["id"]}, {"_id": 0})
    check(rep.get("number") != fak["number"] and rep["transaction_code"].endswith("1"),
          "faktur pengganti memakai NOMOR BARU + kode status faktur pengganti",
          f"{fak['number']} → {rep['number']} (kode {rep['transaction_code']})")
    check(old["status"] == "replaced" and old["replaced_by_number"] == rep["number"]
          and rep["replaces_number"] == fak["number"],
          "jejak dua arah: faktur lama menunjuk pengganti dan sebaliknya",
          f"{old['status']} → {old['replaced_by_number']}")

    chk = body(fx.api("GET", "/tax/compliance/faktur-export/check", fin,
                      params={"period": rep["period"]}))
    check(chk["can_export"] is True and chk["count"] == 1,
          "setelah identitas lengkap, ekspor siap (hanya faktur aktif yang ikut)",
          chk["detail"])
    xml = fx.api("GET", "/tax/compliance/faktur-export/file", fin,
                 params={"period": rep["period"], "format": "coretax_xml"})
    check(xml.status_code == 200 and rep["number"] in xml.text
          and "0012345678901000" in xml.text,
          "berkas XML berisi nomor faktur & NPWP pemungut yang benar",
          f"{len(xml.content)} bita")
    csv_ = fx.api("GET", "/tax/compliance/faktur-export/file", fin,
                  params={"period": rep["period"], "format": "excel_csv"})
    check(csv_.status_code == 200 and rep["number"] in csv_.text and ";" in csv_.text,
          "berkas CSV (tempel ke template Excel) juga tersedia", f"{len(csv_.content)} bita")

    # NPWP 15 digit lama: DINORMALKAN (0 di depan) — satu aturan untuk seluruh Fase 49.
    rep2 = body(fx.api("POST", f"/tax/compliance/faktur/{rep['id']}/replace", fin, json={
        "reason": "Pembeli memberi NPWP lama 15 digit sesuai kartu NPWP fisiknya.",
        "buyer_npwp": "09.123.456.7-011.000"}))
    fx.db.faktur_pajak.update_one({"id": rep2["id"]}, {"$set": {fx.TAG: True}})
    chk = body(fx.api("GET", "/tax/compliance/faktur-export/check", fin,
                      params={"period": rep2["period"]}))
    xml2 = fx.api("GET", "/tax/compliance/faktur-export/file", fin,
                  params={"period": rep2["period"], "format": "coretax_xml"})
    check(not chk["blocking"] and any("15 digit" in n for n in chk.get("normalized", [])),
          "NPWP 15 digit lama dinormalkan + pemakai DIBERI TAHU perubahannya",
          (chk.get("normalized") or ["-"])[0][:90])
    check("0091234567011000" in xml2.text,
          "berkas memuat NPWP 16 digit hasil normalisasi (PMK 112/2022)",
          "0091234567011000")

    canc_short = fx.api("POST", f"/tax/compliance/faktur/{rep2['id']}/cancel", fin,
                        json={"reason": "batal"})
    check(canc_short.status_code == 400, "alasan pembatalan faktur < 10 huruf ditolak",
          detail_of(canc_short))
    canc = body(fx.api("POST", f"/tax/compliance/faktur/{rep2['id']}/cancel", fin, json={
        "reason": "Transaksi dibatalkan pembeli sebelum penyerahan unit dilakukan."}))
    check(canc["status"] == "cancelled" and canc.get("cancel_reason"),
          "faktur bisa DIBATALKAN dengan alasan tertulis", canc["cancel_reason"][:60])
    again = fx.api("POST", f"/tax/compliance/faktur/{rep2['id']}/cancel", fin,
                   json={"reason": "Percobaan pembatalan kedua untuk menguji gerbang."})
    check(again.status_code == 400 and "sudah dibatalkan" in again.text,
          "faktur yang sudah batal tidak bisa dibatalkan dua kali", detail_of(again))
    rep_canc = fx.api("POST", f"/tax/compliance/faktur/{rep2['id']}/replace", fin, json={
        "reason": "Percobaan mengganti faktur yang sudah dibatalkan untuk uji gerbang."})
    check(rep_canc.status_code == 400 and "DIBATALKAN" in rep_canc.text,
          "faktur yang sudah batal tidak bisa diganti (harus terbit baru)",
          detail_of(rep_canc))
    cands2 = fx.api("GET", "/tax/faktur-candidates", fin).json().get("data") or []
    check(any(c["deal_id"] == ctx["deal_id"] for c in cands2),
          "deal dengan faktur BATAL kembali jadi kandidat (tidak terkunci selamanya)",
          f"{len(cands2)} kandidat")
    chk = body(fx.api("GET", "/tax/compliance/faktur-export/check", fin,
                      params={"period": rep2["period"]}))
    check(chk["count"] == 0 and chk["can_export"] is False,
          "tidak ada faktur aktif → ekspor mengaku tidak ada yang bisa diekspor",
          chk["detail"])
    ctx["faktur_period"] = rep2["period"]


# ============================================================ G. e-Bupot
def flow_g(fin, lead, sales, ctx):
    head("G. Bukti potong PPh (e-Bupot): potong, buktikan, betulkan (49F)")
    per = fx.this_period()
    cand = body(fx.api("GET", "/tax/compliance/withholding/candidates", fin,
                       params={"period": per}))
    fee_rows = [r for r in cand["rows"] if r["basis"] == "partner_fee"]
    check(bool(fee_rows) and cand["total"] > 0,
          "potongan PPh NYATA yang belum berbukti potong terdaftar apa adanya",
          f"{cand['count']} potongan — {rp(cand['total'])}")
    fee = fee_rows[0]
    doc = body(fx.api("POST", f"/tax/compliance/withholding/from-fee/{fee['ref_id']}", fin))
    check(len(doc.get("number", "")) == 10 and doc["amount"] == fee["amount"],
          "bukti potong terbit dengan nomor 10 digit & nilai = potongan yang nyata",
          f"{doc['number']} — {rp(doc['amount'])} ({doc['kind']})")
    dup = body(fx.api("POST", f"/tax/compliance/withholding/from-fee/{fee['ref_id']}", fin))
    check(dup.get("idempotent") is True and dup["number"] == doc["number"],
          "penerbitan kedua untuk potongan yang SAMA idempoten (tidak lapor dobel)",
          dup["number"])
    cand2 = body(fx.api("GET", "/tax/compliance/withholding/candidates", fin,
                        params={"period": per}))
    check(not [r for r in cand2["rows"] if r["ref_id"] == fee["ref_id"]],
          "potongan yang sudah berbukti keluar dari daftar kerja", cand2["detail"][:80])

    # Pembayaran tagihan DENGAN potongan PPh: vendor terima NETO, potongan jadi utang pajak.
    bill = fx.make_bill(fin, "PT Uji Potong PPh", ctx["p1"]["id"], 100_000_000)
    tax_before = fx.account_balance("2-1300")
    over = fx.api("POST", f"/finance/ap/bills/{bill['id']}/pay-withholding", fin, json={
        "bill_id": bill["id"], "amount": 1_000_000, "base": 1_000_000, "kind": "pph23",
        "rate": 100})
    check(over.status_code == 400 and "melebihi" in over.text,
          "potongan yang menghabiskan seluruh pembayaran DITOLAK", detail_of(over))
    res = fx.api("POST", f"/finance/ap/bills/{bill['id']}/pay-withholding", fin, json={
        "bill_id": bill["id"], "amount": 50_000_000, "base": 50_000_000,
        "kind": "pph4_2_konstruksi", "rate": 1.75, "object_code": "28-409-22",
        "note": "POC49 termin dengan potongan PPh final"})
    pay = body(res)
    check(res.status_code == 200 and pay["withheld"] == 875_000
          and pay["cash_out"] == 49_125_000,
          "vendor menerima NETO; potongan = tarif × dasar",
          f"kas keluar {rp(pay['cash_out'])}, potongan {rp(pay['withheld'])}")
    fx.settle()
    check(fx.account_balance("2-1300") - tax_before == 875_000,
          "potongan masuk buku sebagai UTANG PAJAK (2-1300)",
          rp(fx.account_balance("2-1300") - tax_before))
    bupot = pay["withholding"]
    check(bupot.get("number") and bupot["amount"] == 875_000
          and bupot["object_code"] == "28-409-22",
          "bukti potong atas pembayaran itu terbit OTOMATIS bernomor",
          f"{bupot['number']} — {rp(bupot['amount'])}")
    je = fx.db.journal_entries.find_one({"source_id": bill["id"], "source_type": "ap_bill",
                                        "memo": "Pembayaran tagihan AP"}, {"_id": 0})
    codes = {ln["account_code"]: ln for ln in (je or {}).get("lines", [])}
    check(bool(je) and je["total_debit"] == je["total_credit"]
          and codes.get("2-1300", {}).get("credit") == 875_000
          and codes.get("1-1200", {}).get("credit") == 49_125_000,
          "jurnal pembayaran SEIMBANG: utang lunas bruto, kas keluar neto, sisanya utang pajak",
          f"D {rp(je['total_debit'])} = K {rp(je['total_credit'])}")

    same = body(fx.api("POST", "/tax/compliance/withholding/issue", fin, json={
        "kind": "pph4_2_konstruksi", "basis": "ap_payment", "party_name": bill["vendor"],
        "base": 50_000_000, "rate": 1.75, "ref_id": bupot["ref_id"]}))
    check(same.get("idempotent") is True and same["number"] == bupot["number"],
          "bukti potong untuk referensi pembayaran yang sama tidak bisa dobel",
          same["number"])

    csr = fx.api("POST", f"/tax/compliance/withholding/{bupot['id']}/correct", fin,
                 json={"reason": "salah"})
    check(csr.status_code == 400, "alasan pembetulan < 10 huruf ditolak", detail_of(csr))
    cor = body(fx.api("POST", f"/tax/compliance/withholding/{bupot['id']}/correct", fin, json={
        "reason": "Dasar pengenaan dikoreksi karena ada bagian material yang tidak dipotong.",
        "base": 40_000_000}))
    check(cor["number"] == bupot["number"] and cor["version"] == 2
          and cor["amount"] == 700_000 and len(cor["history"]) == 1,
          "PEMBETULAN memakai NOMOR YANG SAMA, versi naik, nilai lama tersimpan",
          f"{cor['number']} v{cor['version']} — {rp(cor['amount'])}")

    tie = fx.api("GET", "/tax/compliance/withholding", fin,
                 params={"period": per}).json()["tie_out"]
    check(tie["matches"] is False and tie["unproven"] != 0,
          "selisih potongan vs bukti akibat pembetulan dilaporkan APA ADANYA",
          tie["detail"][:110])

    canc = body(fx.api("POST", f"/tax/compliance/withholding/{bupot['id']}/cancel", fin, json={
        "reason": "Pembayaran dibatalkan bank sehingga potongan ini tidak pernah terjadi."}))
    check(canc["state"] == "cancelled", "bukti potong bisa DIBATALKAN beralasan",
          canc.get("cancel_reason", "")[:60])
    after = fx.api("POST", f"/tax/compliance/withholding/{bupot['id']}/correct", fin, json={
        "reason": "Percobaan membetulkan bukti yang sudah dibatalkan untuk uji gerbang."})
    check(after.status_code == 400 and "dibatalkan" in after.text,
          "bukti potong yang dibatalkan tidak bisa dibetulkan lagi", detail_of(after))
    reissue = body(fx.api("POST", "/tax/compliance/withholding/issue", fin, json={
        "kind": "pph4_2_konstruksi", "basis": "ap_payment", "party_name": bill["vendor"],
        "party_npwp": "0012345678904210", "base": 50_000_000, "rate": 1.75,
        "object_code": "28-409-22", "ref_id": bupot["ref_id"],
        "ref_label": f"Pembayaran tagihan {bill['vendor']}"}))
    check(reissue.get("idempotent") is False and reissue["number"] != bupot["number"],
          "setelah dibatalkan, bukti baru boleh terbit dengan nomor baru",
          f"{bupot['number']} → {reissue['number']}")
    tie2 = fx.api("GET", "/tax/compliance/withholding", fin,
                  params={"period": per}).json()["tie_out"]
    check(tie2["matches"] is True and tie2["unproven"] == 0,
          "TIE-OUT: seluruh potongan PPh yang terjadi kini berbukti potong",
          tie2["detail"][:90])

    pdf = fx.api("GET", f"/tax/compliance/withholding/{reissue['id']}/pdf", fin)
    check(pdf.status_code == 200 and pdf.content[:4] == b"%PDF",
          "bukti potong bisa dicetak jadi PDF untuk diberikan ke pihak dipotong",
          f"{len(pdf.content)} bita")

    chk = body(fx.api("GET", "/tax/compliance/withholding-export/check", fin,
                      params={"period": per}))
    check(bool(chk["warnings"]) or bool(chk["blocking"]) or chk["can_export"],
          "kesiapan ekspor bukti potong dijelaskan (blokir/peringatan/siap)",
          chk["detail"])
    if chk["blocking"]:
        target = chk["blocking"][0]
        rows = fx.api("GET", "/tax/compliance/withholding", fin,
                      params={"period": per}).json()["data"]
        bad = next(r for r in rows if r["number"] == target["number"])
        fx.api("POST", f"/tax/compliance/withholding/{bad['id']}/correct", fin, json={
            "reason": "Melengkapi NPWP pihak dipotong agar berkas ekspor tidak berkolom kosong.",
            "party_npwp": "0012345678901000", "object_code": "24-104-29"})
        chk = body(fx.api("GET", "/tax/compliance/withholding-export/check", fin,
                          params={"period": per}))
    check(chk["can_export"] is True, "setelah identitas lengkap, ekspor bukti potong siap",
          chk["detail"])
    xml = fx.api("GET", "/tax/compliance/withholding-export/file", fin,
                 params={"period": per, "format": "coretax_xml"})
    csv_ = fx.api("GET", "/tax/compliance/withholding-export/file", fin,
                  params={"period": per, "format": "excel_csv"})
    check(xml.status_code == 200 and reissue["number"] in xml.text,
          "berkas XML bukti potong berisi nomor yang benar", f"{len(xml.content)} bita")
    check(csv_.status_code == 200 and ";" in csv_.text,
          "berkas CSV bukti potong tersedia", f"{len(csv_.content)} bita")

    forb = fx.api("GET", "/tax/compliance/withholding", sales)
    forb2 = fx.api("POST", "/tax/compliance/withholding/issue", sales, json={
        "kind": "pph23", "party_name": "PT Uji RBAC", "base": 1_000_000, "rate": 2})
    check(forb.status_code == 403 and forb2.status_code == 403,
          "peran sales tidak bisa melihat maupun menerbitkan bukti potong (403)",
          f"{forb.status_code}/{forb2.status_code}")
    ctx["bupot_period"] = per


# ============================================================ H. rekap SPT Masa PPN
def flow_h(fin, ctx):
    head("H. Rekap SPT Masa PPN yang bisa direkonstruksi (49G)")
    empty = body(fx.api("GET", "/tax/compliance/vat-return", fin, params={"period": fx.PERIOD}))
    check(empty["state"] == "missing_data" and "belum ada data" in empty["detail"],
          "masa tanpa faktur & tanpa tagihan mengaku 'belum ada data' (bukan nihil)",
          empty["detail"][:90])
    live = body(fx.api("GET", "/tax/compliance/vat-return", fin,
                       params={"period": ctx["faktur_period"]}))
    check(live["net"] == live["ppn_keluaran"] - live["ppn_masukan"],
          "PPN net = keluaran − masukan (bisa dihitung ulang pembaca)",
          f"{rp(live['ppn_keluaran'])} − {rp(live['ppn_masukan'])} = {rp(live['net'])}")
    check(live["faktur_cancelled"] >= 1 and live["faktur_replaced"] >= 2
          and live["faktur_count"] == 0 and live["ppn_keluaran"] == 0,
          "faktur batal & diganti TERBACA jumlahnya tetapi TIDAK dihitung sebagai PPN keluaran",
          f"aktif {live['faktur_count']}, batal {live['faktur_cancelled']}, "
          f"diganti {live['faktur_replaced']}, PPN keluaran {rp(live['ppn_keluaran'])}")
    check(bool(live.get("reconstruct")) and live["state_label"],
          "cara menghitungnya ditulis di jawaban (bisa diaudit)",
          live["reconstruct"][:90])


# ============================================================ pembersihan
def cleanup(owner):
    head("Bersih-bersih (jangan meninggalkan jurnal/dokumen menggantung)")
    if "tax.company_npwp" in RESTORE:
        fx.api("PUT", "/settings/tax.company_npwp", owner, json={
            "value": RESTORE["tax.company_npwp"] or "",
            "reason": "POC49 selesai: nilai setelan dikembalikan seperti sebelum uji"})
    before = fx.orphans()
    print("  sebelum dibuang:", before)
    fx.purge()
    after = fx.orphans()
    print("  sesudah dibuang:", after)
    check(all(v == 0 for v in after.values()),
          "POC tidak meninggalkan dokumen/jurnal menggantung", str(after))


def main() -> int:
    head("POC FASE 49 — penutupan buku, laporan owner, dan kepatuhan pajak")
    fin = fx.login("finance@sipro.co.id")
    lead = fx.login("finlead@sipro.co.id")
    owner = fx.login("owner@sipro.co.id")
    sales = fx.login("sales@sipro.co.id")
    ctx = {}
    try:
        flow_a(fin)
        flow_b(fin, lead, ctx)
        flow_c(fin, lead, ctx)
        flow_d(fin, lead, ctx)
        flow_e(owner, ctx)
        flow_f(fin, owner, ctx)
        flow_g(fin, lead, sales, ctx)
        flow_h(fin, ctx)
    finally:
        cleanup(owner)
    head(f"HASIL: {'PASS' if not FAIL else 'GAGAL'} — {len(PASS)} pemeriksaan hijau"
         + (f", {len(FAIL)} MERAH" if FAIL else ". Inti Fase 49 terbukti."))
    if FAIL:
        for f in FAIL:
            print("  MERAH:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
