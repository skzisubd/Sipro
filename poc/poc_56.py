#!/usr/bin/env python3
"""poc_56.py — POC INTI Fase 56C: PEMBATALAN KONTRAK & REFUND BERJURNAL.

Membuktikan (dengan HTTP nyata, tanpa menyentuh database langsung) bahwa janji yang SUDAH
TERCETAK di dokumen SPR akhirnya bisa dijalankan:

  A. Pengaju bukan pemutus (tiga tangan: mengajukan · memutuskan · membayar).
  B. Potongan dihitung dari KEADAAN NYATA (35% sebelum pembangunan / 50% saat berjalan) dan
     dari uang yang BENAR-BENAR diterima (saldo kewajiban kontrak `2-1400`).
  C. Keputusan menyetujui melahirkan JURNAL BERIMBANG: kewajiban kepada pembeli
     diselesaikan, potongan menjadi pendapatan lain-lain, sisanya menjadi UTANG REFUND.
  D. Unit kembali ke stok, termin yang belum dibayar dibatalkan, kuitansi lama TIDAK dihapus,
     tahap lead menjadi `lost`, dan Berita Acara Pembatalan bisa DICETAK (PDF).
  E. Refund tertahan sesuai ketentuan SPR ("menunggu unit terjual kembali"), hanya Manajer
     Keuangan yang boleh mengabaikan penahanan itu — dengan alasan tertulis.
  F. Pembayaran refund idempoten (`client_ref`) dan tidak bisa dibayar dua kali.
  G. Gerbang: rumah yang sudah diserahterimakan (BAST) dan kontrak yang sudah AJB TIDAK BISA
     dibatalkan lewat aplikasi; pengajuan ganda ditolak.
  H. Pembeli membaca keadaan pembatalannya sendiri di PORTAL dengan bahasa untuk pembeli.

Jalankan: python3 poc/poc_56.py
"""
import pathlib
import sys
import time

import requests

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
OTP = "000000"
OK, FAIL = [], []
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def check(cond: bool, label: str, detail: str = "") -> bool:
    if cond:
        OK.append(label)
        print(f"  OK    {label}")
    else:
        FAIL.append(f"{label} — {detail}")
        print(f"  MERAH {label} — {detail}")
    return bool(cond)


def head(t: str) -> None:
    print(f"\n{t}\n" + "-" * len(t))


def login(email: str) -> dict:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def j(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


def d(r) -> str:
    return f"{r.status_code} {str(j(r).get('detail'))[:180]}"


def akun(headers, code: str) -> int:
    """Saldo satu akun dari NERACA SALDO (bukan hitungan sendiri) — supaya POC menguji
    pembukuan yang sama dengan yang dibaca laporan keuangan."""
    r = requests.get(f"{BASE}/gl/trial-balance", headers=headers, timeout=30)
    for row in (j(r).get("data") or {}).get("rows") or j(r).get("rows") or []:
        if row.get("account_code") == code or row.get("code") == code:
            return int(row.get("balance") or 0)
    return 0


def main() -> int:  # noqa: C901
    print("POC FASE 56C — pembatalan kontrak & refund berjurnal")
    sa = login("superadmin@sipro.co.id")
    mgr = login("manager@sipro.co.id")        # MENGAJUKAN
    finlead = login("finlead@sipro.co.id")    # MEMUTUSKAN + boleh mengabaikan penahanan
    fin = login("finance@sipro.co.id")        # MEMBAYAR
    sales = login("sales@sipro.co.id")        # tidak boleh apa-apa selain melihat miliknya
    tanda = str(int(time.time()))[-6:]

    head("0. Bahan uji: lead POC56 → reservasi → booking → pembeli → kontrak")
    lead = requests.post(f"{BASE}/leads", headers=sa, json={
        "name": f"POC56 Ibu Ratna {tanda}", "phone": f"+62813{tanda}56",
        "source": "walk_in", "notes": "bahan uji POC Fase 56"}, timeout=30)
    check(lead.status_code == 200, "lead uji dibuat", d(lead))
    lead_id = (j(lead).get("data") or {}).get("id")
    units = requests.get(f"{BASE}/units", headers=sa,
                         params={"status": "available", "limit": 5}, timeout=30)
    rows = j(units).get("data") or []
    check(bool(rows), "ada unit tersedia", str(units.status_code))
    if not (lead_id and rows):
        return 1
    unit = rows[0]
    res = requests.post(f"{BASE}/deals/reserve", headers=sa, json={
        "lead_id": lead_id, "unit_id": unit["id"], "booking_fee": 5000000,
        "notes": "POC 56"}, timeout=30)
    check(res.status_code == 200, "unit di-reserve", d(res))
    deal_id = (j(res).get("data") or {}).get("id")
    book = requests.post(f"{BASE}/deals/{deal_id}/book", headers=sa, json={}, timeout=30)
    check(book.status_code == 200, "booking dikonfirmasi", d(book))
    cv = requests.post(f"{BASE}/deals/{deal_id}/convert", headers=sa, json={
        "scheme": "cash_bertahap", "nik": f"3299{tanda}000056",
        "address": "Jl. Uji Pembatalan 56"}, timeout=30)
    check(cv.status_code == 200, "lead menjadi PEMBELI + kontrak lahir", d(cv))
    contract = (j(cv).get("data") or {}).get("contract") or {}
    cust = (j(cv).get("data") or {}).get("customer") or {}
    cid = contract.get("id")
    if not cid:
        return 1
    act = requests.post(f"{BASE}/contracts/{cid}/activate", headers=fin, timeout=30)
    check(act.status_code == 200, "kontrak diaktifkan (termin AR lahir)", d(act))

    head("A. Pratinjau: hitungan dari keadaan NYATA, bukan dari yang diketik pengaju")
    pv = requests.get(f"{BASE}/cancellations/preview", headers=mgr,
                      params={"contract_id": cid}, timeout=30)
    p = j(pv).get("data") or {}
    check(pv.status_code == 200 and p.get("can_request") is True,
          "pembatalan boleh diajukan pada kontrak yang masih berjalan",
          f"{pv.status_code} blocks={p.get('blocks')}")
    check(p.get("basis") == "belum_mulai" and p.get("cut_pct") == 35,
          "dasar potongan = pembangunan belum dimulai → 35% (ketentuan SPR)",
          f"{p.get('basis')} {p.get('cut_pct')}%")
    check(p.get("received_total") == 0 and p.get("payable_total") == 0
          and "belum ada penerimaan" in str(p.get("note")).lower(),
          "belum ada uang masuk → dinyatakan SEBABNYA, bukan 'refund Rp 0' tanpa penjelasan",
          str(p.get("note"))[:120])
    check("cancellation.cut_before_build_pct" in str(p.get("rule_key")),
          "aturan yang dipakai DISEBUT sumbernya (Pusat Konfigurasi)", str(p.get("rule_key")))

    head("B. Uang pembeli masuk dulu — supaya pembatalan punya angka yang nyata")
    ar = j(requests.get(f"{BASE}/finance/ar/{deal_id}", headers=fin, timeout=30)).get("data") or {}
    inv = ar.get("invoice") or ar
    dp = int((inv.get("items") or [{}])[0].get("amount") or 0)
    pay = requests.post(f"{BASE}/finance/ar/receipts", headers=fin, json={
        "deal_id": deal_id, "amount": dp, "method": "transfer",
        "note": "POC 56 termin pertama"}, timeout=60)
    check(pay.status_code == 200, f"penerimaan Rp {dp:,} dicatat Keuangan".replace(",", "."),
          d(pay))
    liab_awal = akun(sa, "2-1400")
    pv2 = j(requests.get(f"{BASE}/cancellations/preview", headers=mgr,
                         params={"contract_id": cid}, timeout=30)).get("data") or {}
    check(pv2.get("received_total") == dp,
          "uang yang diterima dibaca dari saldo KEWAJIBAN KONTRAK (bukan hitungan kedua)",
          f"{pv2.get('received_total')} vs {dp}")
    harap_cut = round(dp * 35 / 100)
    check(pv2.get("cut_amount") == harap_cut
          and pv2.get("refund_amount") == dp - harap_cut,
          "potongan 35% & refund dihitung benar",
          f"cut={pv2.get('cut_amount')} refund={pv2.get('refund_amount')}")

    head("C. Pemisahan tugas: siapa boleh mengajukan, memutuskan, membayar")
    r = requests.post(f"{BASE}/cancellations", headers=sales,
                      json={"contract_id": cid, "reason": "pembeli mundur karena pindah kota"},
                      timeout=30)
    check(r.status_code == 403, "sales TIDAK boleh mengajukan pembatalan", d(r))
    r = requests.post(f"{BASE}/cancellations", headers=fin,
                      json={"contract_id": cid, "reason": "pembeli mundur karena pindah kota"},
                      timeout=30)
    check(r.status_code == 403, "Keuangan (kasir) TIDAK boleh mengajukan pembatalan", d(r))
    r = requests.post(f"{BASE}/cancellations", headers=mgr,
                      json={"contract_id": cid, "reason": "batal"}, timeout=30)
    check(r.status_code in (400, 422) and "10 huruf" in str(j(r).get("detail")),
          "alasan sepotong (<10 huruf) DITOLAK di lapis kontrak", d(r))
    req = requests.post(f"{BASE}/cancellations", headers=mgr, json={
        "contract_id": cid,
        "reason": "pembeli mundur karena pindah tugas ke luar kota"}, timeout=30)
    check(req.status_code == 200, "Manajer Sales mengajukan pembatalan", d(req))
    cx = j(req).get("data") or {}
    xid = cx.get("id")
    check(str(cx.get("number") or "").startswith("BTL/"),
          "pengajuan bernomor (bisa dirujuk dokumen & jurnal)", str(cx.get("number")))
    check(cx.get("state") == "diajukan", "keadaan awal = diajukan (belum ada jurnal)",
          str(cx.get("state")))
    check(akun(sa, "2-1400") == liab_awal,
          "PENGAJUAN belum menyentuh pembukuan (niat bukan peristiwa uang)",
          f"{akun(sa, '2-1400')} vs {liab_awal}")
    dup = requests.post(f"{BASE}/cancellations", headers=mgr, json={
        "contract_id": cid, "reason": "pengajuan kedua yang seharusnya ditolak"}, timeout=30)
    check(dup.status_code == 400 and "menunggu keputusan" in str(j(dup).get("detail")),
          "pengajuan GANDA ditolak selama yang pertama belum diputus", d(dup))
    r = requests.post(f"{BASE}/cancellations/{xid}/decision", headers=mgr,
                      json={"approved": True, "note": "disetujui oleh pengaju sendiri"},
                      timeout=30)
    check(r.status_code == 403, "Manajer Sales TIDAK boleh memutuskan pembatalan", d(r))
    r = requests.post(f"{BASE}/cancellations/{xid}/decision", headers=fin,
                      json={"approved": True, "note": "disetujui oleh kasir keuangan"},
                      timeout=30)
    check(r.status_code == 403,
          "Keuangan (kasir) TIDAK boleh memutuskan pembatalan (hanya Manajer Keuangan)", d(r))
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=fin,
                      json={"method": "transfer"}, timeout=30)
    check(r.status_code == 400 and "belum disetujui" in str(j(r).get("detail")).lower(),
          "refund tidak bisa dibayar sebelum ADA keputusan", d(r))

    head("D. Keputusan Manajer Keuangan → jurnal, unit kembali, dokumen lahir")
    dec = requests.post(f"{BASE}/cancellations/{xid}/decision", headers=finlead, json={
        "approved": True,
        "note": "disetujui: unit masih bisa dijual ulang, potongan sesuai SPR"}, timeout=60)
    check(dec.status_code == 200, "Manajer Keuangan MENYETUJUI pembatalan", d(dec))
    doc = j(dec).get("data") or {}
    st = doc.get("settlement") or {}
    check(doc.get("state") == "disetujui", "keadaan → disetujui", str(doc.get("state")))
    check(st.get("cut_amount") == harap_cut and st.get("payable_total") == dp - harap_cut,
          "hitungan DIHITUNG ULANG saat memutuskan (uang bisa bergerak sesudah pengajuan)",
          f"{st.get('cut_amount')} / {st.get('payable_total')}")
    check(len(doc.get("journal_ids") or []) == 1, "tepat SATU jurnal keputusan",
          str(doc.get("journal_ids")))
    jr = (doc.get("journals") or [{}])[0]
    lines = {ln.get("account_code"): (ln.get("debit"), ln.get("credit"))
             for ln in (jr.get("lines") or [])}
    check(lines.get("2-1400", (0, 0))[0] == dp,
          "Dr 2-1400 (kewajiban kepada pembeli DISELESAIKAN)", str(lines))
    check(lines.get("4-1200", (0, 0))[1] == harap_cut,
          "Cr 4-1200 (potongan menjadi pendapatan lain-lain)", str(lines))
    check(lines.get("2-1460", (0, 0))[1] == dp - harap_cut,
          "Cr 2-1460 (UTANG REFUND kepada pembeli — akun baru Fase 56)", str(lines))
    check(int(jr.get("total_debit") or 0) == dp, "jurnal BERIMBANG", str(jr.get("total_debit")))
    check(akun(sa, "2-1400") == liab_awal - dp,
          "saldo kewajiban kontrak turun tepat sebesar uang yang diterima",
          f"{akun(sa, '2-1400')} vs {liab_awal - dp}")
    unit_rows = j(requests.get(f"{BASE}/units", headers=sa,
                               params={"q": unit.get("code"), "limit": 5},
                               timeout=30)).get("data") or []
    unit_after = next((u for u in unit_rows if u.get("id") == unit["id"]), {})
    check(unit_after.get("status") == "available" and st.get("unit_released") is True,
          "unit KEMBALI ke stok (rumah tidak hilang karena satu pembeli mundur)",
          str(unit_after.get("status")))
    ar2 = j(requests.get(f"{BASE}/finance/ar/{deal_id}", headers=fin, timeout=30)).get("data") or {}
    inv2 = ar2.get("invoice") or ar2
    check(inv2.get("status") == "cancelled" and int(inv2.get("outstanding") or 0) == 0,
          "tagihan (AR) dibatalkan — tidak ada lagi termin yang ditagihkan",
          f"{inv2.get('status')} outstanding={inv2.get('outstanding')}")
    kwitansi = j(requests.get(f"{BASE}/finance/ar/{deal_id}", headers=fin,
                              timeout=30)).get("receipts") or []
    check(len(kwitansi) >= 1,
          "kuitansi yang sudah dipegang pembeli TIDAK dihapus (pembatalan ≠ hapus bukti)",
          str(len(kwitansi)))
    lead_after = j(requests.get(f"{BASE}/leads/{lead_id}", headers=sa,
                                timeout=30)).get("data") or {}
    check(lead_after.get("stage") == "lost",
          "tahap lead ditutup `lost` dengan alasan pembatalan", str(lead_after.get("stage")))
    c_after = j(requests.get(f"{BASE}/contracts/{cid}", headers=sa,
                             timeout=30)).get("data") or {}
    check(c_after.get("state") == "cancelled", "kontrak berstatus dibatalkan",
          str(c_after.get("state")))
    bap = requests.get(f"{BASE}/cancellations/by-contract/{cid}/document", headers=mgr,
                       timeout=30)
    bdoc = j(bap).get("data") or {}
    check(bap.status_code == 200 and str(bdoc.get("doc_number") or "").count("/") == 4,
          "Berita Acara Pembatalan terbit dengan nomor format owner",
          str(bdoc.get("doc_number")))
    pdf = requests.get(f"{BASE}/documents/{bdoc.get('id')}/pdf", headers=mgr, timeout=60)
    check(pdf.status_code == 200
          and pdf.headers.get("content-type", "").startswith("application/pdf")
          and len(pdf.content) > 1500,
          "Berita Acara BISA DICETAK (PDF berisi)",
          f"{pdf.status_code} {len(pdf.content)}b")
    full = j(requests.get(f"{BASE}/documents/{bdoc.get('id')}", headers=mgr,
                          timeout=30)).get("data") or {}
    isi = str(full.get("content") or "")
    check(f"{35}%" in isi and "Rp" in isi and "belum ditetapkan" not in isi.split("2.")[1][:400],
          "dokumen memuat perhitungan NYATA (persentase + rupiah), bukan placeholder",
          [ln for ln in isi.split("\n") if "Potongan" in ln][:1])
    check("[" not in isi.split("Nomor:")[0], "tidak ada placeholder bocor di judul dokumen")

    head("E. Refund tertahan sesuai ketentuan SPR — dan yang boleh mengabaikan hanya satu")
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=fin,
                      json={"method": "transfer"}, timeout=30)
    check(r.status_code == 400 and "penjualan ulang" in str(j(r).get("detail")),
          "refund DITAHAN karena unit belum terjual kembali (ketentuan SPR, bukan bug)",
          d(r))
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=fin, json={
        "method": "transfer", "override": True,
        "override_reason": "pembeli mengancam ke pengadilan, direksi minta dibayar"},
        timeout=30)
    check(r.status_code == 400 and "Manajer Keuangan" in str(j(r).get("detail")),
          "Keuangan TIDAK boleh mengabaikan penahanan refund (wewenang manajer)", d(r))
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "transfer", "override": True, "override_reason": "urgent"}, timeout=30)
    check(r.status_code in (400, 422) and "10 huruf" in str(j(r).get("detail")),
          "alasan pengabaian sepotong (<10 huruf) DITOLAK", d(r))
    sisa = dp - harap_cut
    pay1 = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "transfer", "amount": int(sisa / 2), "client_ref": f"poc56-{tanda}-1",
        "override": True,
        "override_reason": "diputus direksi: dibayar lebih dahulu tanpa menunggu penjualan"},
        timeout=60)
    check(pay1.status_code == 200, "Manajer Keuangan membayar refund SEBAGIAN dengan alasan",
          d(pay1))
    after1 = j(pay1).get("data") or {}
    check(after1.get("state") == "refund_sebagian",
          "keadaan → refund dibayar sebagian", str(after1.get("state")))
    check(akun(sa, "2-1460") > 0, "utang refund masih bersisa di pembukuan",
          str(akun(sa, "2-1460")))

    head("F. Idempotensi & tidak bisa dibayar dua kali")
    ulang = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "transfer", "amount": int(sisa / 2), "client_ref": f"poc56-{tanda}-1",
        "override": True, "override_reason": "kiriman ulang penanda yang sama"}, timeout=30)
    check(ulang.status_code == 200 and j(ulang).get("replay") is True,
          "kiriman ulang `client_ref` yang sama dijawab REPLAY (bukan pembayaran kedua)",
          d(ulang))
    cek = j(requests.get(f"{BASE}/cancellations/{xid}", headers=finlead,
                         timeout=30)).get("data") or {}
    check(len(cek.get("refund_payments") or []) == 1,
          "tetap SATU baris pembayaran sesudah kiriman ulang",
          str(len(cek.get("refund_payments") or [])))
    kelebihan = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "tunai", "amount": sisa, "client_ref": f"poc56-{tanda}-x",
        "override": True, "override_reason": "mencoba membayar lebih dari sisa utang"},
        timeout=30)
    check(kelebihan.status_code == 400 and "melebihi sisa" in str(j(kelebihan).get("detail")),
          "pembayaran yang MELEBIHI sisa utang refund ditolak", d(kelebihan))
    pay2 = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "tunai", "client_ref": f"poc56-{tanda}-2", "override": True,
        "override_reason": "pelunasan refund sesuai keputusan direksi"}, timeout=60)
    check(pay2.status_code == 200, "sisa refund dilunasi (kas)", d(pay2))
    lunas = j(pay2).get("data") or {}
    check(lunas.get("state") == "selesai" and lunas.get("refund_outstanding") == 0,
          "keadaan → selesai, sisa utang refund nol",
          f"{lunas.get('state')} sisa={lunas.get('refund_outstanding')}")
    check(akun(sa, "2-1460") == 0,
          "akun 2-1460 kembali NOL — tidak ada utang refund yang menggantung",
          str(akun(sa, "2-1460")))
    r = requests.post(f"{BASE}/cancellations/{xid}/refund", headers=finlead, json={
        "method": "tunai", "override": True,
        "override_reason": "mencoba membayar untuk ketiga kalinya"}, timeout=30)
    check(r.status_code == 400 and "sudah dibayar penuh" in str(j(r).get("detail")),
          "refund yang sudah lunas tidak bisa dibayar lagi", d(r))

    head("G. Gerbang: rumah yang sudah diserahterimakan tidak bisa dibatalkan di aplikasi")
    ctrs = j(requests.get(f"{BASE}/contracts", headers=sa, timeout=30)).get("data") or []
    bast_ctr = None
    for c in ctrs:
        cek2 = j(requests.get(f"{BASE}/cancellations/preview", headers=finlead,
                              params={"contract_id": c["id"]}, timeout=30)).get("data") or {}
        codes = [b["code"] for b in cek2.get("blocks") or []]
        if "sudah_bast" in codes:
            bast_ctr = (c, cek2)
            break
    check(bast_ctr is not None,
          "kontrak yang rumahnya SUDAH diserahterimakan ditahan dengan sebab `sudah_bast`",
          "tidak ada kontrak ber-BAST di data demo")
    if bast_ctr:
        c, cek2 = bast_ctr
        r = requests.post(f"{BASE}/cancellations", headers=mgr, json={
            "contract_id": c["id"],
            "reason": "mencoba membatalkan rumah yang sudah diserahkan"}, timeout=30)
        check(r.status_code == 400 and "diserahterimakan" in str(j(r).get("detail")),
              "…dan pengajuannya DITOLAK server, bukan hanya tombol yang mati", d(r))
    pv3 = j(requests.get(f"{BASE}/cancellations/preview", headers=mgr,
                         params={"contract_id": cid}, timeout=30)).get("data") or {}
    check(any(b["code"] == "kontrak_sudah_batal" for b in pv3.get("blocks") or []),
          "kontrak yang sudah dibatalkan tidak bisa dibatalkan dua kali",
          str(pv3.get("blocks")))

    head("H. Pembeli membaca keadaannya sendiri di PORTAL (bahasa untuk pembeli)")
    phone = (cust.get("phone") or "").strip()
    otp = requests.post(f"{BASE}/portal/auth/request-otp", json={"identifier": phone},
                        timeout=30)
    ver = requests.post(f"{BASE}/portal/auth/verify-otp",
                        json={"identifier": phone, "code": OTP}, timeout=30)
    token = j(ver).get("token") or (j(ver).get("data") or {}).get("token")
    check(otp.status_code == 200 and bool(token), "pembeli masuk portal (OTP master uji)",
          f"{otp.status_code}/{ver.status_code}")
    if token:
        ph = {"Authorization": f"Bearer {token}"}
        pc = requests.get(f"{BASE}/portal/cancellations", headers=ph, timeout=30)
        rows2 = j(pc).get("data") or []
        check(pc.status_code == 200 and len(rows2) == 1,
              "portal menampilkan pembatalan milik pembeli ini", d(pc))
        if rows2:
            row = rows2[0]
            check(row.get("cut_pct") == 35 and row.get("payable_total") == sisa
                  and row.get("refund_outstanding") == 0,
                  "angka di portal SAMA dengan angka di pembukuan (satu sumber)",
                  str({k: row.get(k) for k in ("cut_pct", "payable_total",
                                               "refund_outstanding")}))
            check("SPR" in str(row.get("rule_label")) or "Ketentuan" in str(row.get("rule_label")),
                  "portal menyebut DASAR ATURAN potongan (pembeli bisa memeriksanya)",
                  str(row.get("rule_label"))[:120])
            check(len(row.get("payments") or []) == 2,
                  "riwayat pembayaran refund terlihat pembeli", str(row.get("payments")))
            check(str(row.get("document_number") or "").count("/") == 4,
                  "berita acara pembatalan bisa dirujuk pembeli",
                  str(row.get("document_number")))
        pdocs = j(requests.get(f"{BASE}/portal/documents", headers=ph,
                              timeout=30)).get("data") or []
        check(any(x.get("template_code") == "BAP" for x in pdocs),
              "Berita Acara Pembatalan ikut muncul di daftar dokumen portal",
              str([x.get("template_code") for x in pdocs]))

    head("I. Lingkup data: sales lain tidak boleh membaca pembatalan yang bukan miliknya")
    lst = requests.get(f"{BASE}/cancellations", headers=sales, timeout=30)
    js = j(lst)
    check(lst.status_code == 200, "sales boleh membuka daftar pembatalan", d(lst))
    check(all(r.get("assigned_to") == "sales@sipro.co.id" for r in js.get("data") or []),
          "…tetapi hanya barisnya sendiri yang terlihat",
          str([r.get("assigned_to") for r in js.get("data") or []]))

    print("\n" + "=" * 66)
    print(f"HASIL POC 56: {len(OK)} PASS, {len(FAIL)} FAIL")
    import _fixture56
    print(f"Bahan uji dibersihkan: {_fixture56.purge()}")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("POC FASE 56 PASSED — pembatalan bisa dijalankan, berjurnal, dan bisa "
          "dipertanggungjawabkan kepada pembeli.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
