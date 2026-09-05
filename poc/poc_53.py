#!/usr/bin/env python3
"""poc_53.py — POC INTI Fase 53: rantai LEAD → PEMBELI → KONTRAK → DOKUMEN TERCETAK.

Membuktikan (dengan HTTP nyata, tanpa menyentuh database langsung) bahwa empat cacat yang
dilaporkan pemilik produk benar-benar tertutup:

  A. Penawaran → reservasi memakai SATU jalur, sehingga deal hasil penawaran BISA di-booking
     (dulu `status="active"` → `POST /deals/{id}/book` menolaknya).
  B. Lead BISA menjadi pembeli: `customers` + `contracts` lahir, tertaut, dan idempoten.
  C. Tahap legal milik pembeli, dengan AKAD KREDIT pada skema KPR + gerbang bukti
     (SP3K wajib berkas & plafon; kelebihan tanah wajib lunas sebelum akad; AJB menyusul akad).
  D. Dokumen ASLI owner (SPR KPR + SPKT) bisa diterbitkan dengan angka kontrak dan DICETAK
     (PDF 200 · application/pdf), dan biaya yang belum diisi ditulis "belum ditetapkan"
     — bukan Rp 0.

Jalankan: python3 poc/poc_53.py
"""
import io
import pathlib
import sys
import time

import requests

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
OK, FAIL = [], []


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


def detail(r) -> str:
    return f"{r.status_code} {str(j(r).get('detail'))[:160]}"


def main() -> int:
    print("POC FASE 53 — dari lead menjadi pembeli, lalu dokumennya bisa dicetak")
    sa = login("superadmin@sipro.co.id")
    fin = login("finance@sipro.co.id")

    # ------------------------------------------------ bahan uji: lead baru + unit tersedia
    head("0. Bahan uji")
    # Nomor telepon dibuat UNIK per jalannya skrip: sistem menolak lead dengan nomor yang
    # sama (dedup nyata, bukan bug), jadi POC yang memakai nomor tetap hanya bisa dijalankan
    # sekali — dan POC yang tidak bisa diulang tidak berguna sebagai jaring pengaman.
    tanda = str(int(time.time()))[-6:]
    lead = requests.post(f"{BASE}/leads", headers=sa, json={
        "name": f"POC53 Bapak Hendra {tanda}", "phone": f"+62812{tanda}53",
        "source": "walk_in", "notes": "bahan uji POC Fase 53"}, timeout=30)
    check(lead.status_code == 200, "lead uji dibuat", detail(lead))
    lead_id = (j(lead).get("data") or {}).get("id")
    units = requests.get(f"{BASE}/units", headers=sa,
                         params={"status": "available", "limit": 5}, timeout=30)
    rows = j(units).get("data") or []
    check(bool(rows), "ada unit tersedia untuk diuji", str(units.status_code))
    if not (lead_id and rows):
        return 1
    unit = rows[0]

    # ------------------------------------------------ A. penawaran → reservasi → booking
    head("A. Penawaran → reservasi → booking (satu jalur reservasi)")
    q = requests.post(f"{BASE}/quotations", headers=sa, json={
        "lead_id": lead_id, "unit_id": unit["id"],
        # kelebihan tanah 12 m² → memicu kewajiban SPKT (ketentuan dokumen owner)
        "addons": [{"code": "ADD-TANAH", "qty": 12}, {"code": "ADD-HOOK", "qty": 1}],
        "note": "POC 53"}, timeout=30)
    check(q.status_code == 200, "penawaran dibuat", detail(q))
    quotation = j(q).get("data") or {}
    conv = requests.post(f"{BASE}/quotations/{quotation.get('id')}/convert", headers=sa,
                         json={"note": "POC 53"}, timeout=30)
    check(conv.status_code == 200, "penawaran dikonversi menjadi reservasi", detail(conv))
    deal = (j(conv).get("data") or {}).get("deal") or {}
    deal_id = deal.get("id")
    check(deal.get("status") == "reserved",
          "deal hasil penawaran berstatus 'reserved' (bentuk deal SAMA dengan jalur biasa)",
          f"status={deal.get('status')}")
    check(bool(deal.get("reserved_until")),
          "masa keep unit (reserved_until) terisi", str(deal.get("reserved_until")))
    lead_now = j(requests.get(f"{BASE}/leads/{lead_id}", headers=sa, timeout=30)).get("data") or {}
    check(lead_now.get("stage") == "booking",
          "tahap lead maju ke 'booking' karena ada BUKTI reservasi",
          f"stage={lead_now.get('stage')}")
    book = requests.post(f"{BASE}/deals/{deal_id}/book", headers=sa, json={}, timeout=30)
    check(book.status_code == 200,
          "deal hasil penawaran BISA di-booking (cacat utama Fase 53A tertutup)",
          detail(book))

    # ------------------------------------------------ B. konversi lead → pembeli
    head("B. Lead menjadi PEMBELI (customers + contracts, idempoten)")
    pre = requests.get(f"{BASE}/deals/{deal_id}/convert-preview", headers=sa, timeout=30)
    pdata = j(pre).get("data") or {}
    check(pre.status_code == 200 and pdata.get("can_convert") is True,
          "pratinjau konversi menyatakan boleh (booking sudah dikonfirmasi)",
          f"{pre.status_code} blocks={pdata.get('blocks')}")
    check(pdata.get("suggested_scheme") in ("cash_keras", "cash_bertahap", "kpr"),
          "skema diusulkan, bukan dipaksakan", str(pdata.get("suggested_scheme")))
    cv = requests.post(f"{BASE}/deals/{deal_id}/convert", headers=sa,
                       json={"scheme": "kpr", "nik": f"3201{tanda}0000{tanda[-2:]}",
                             "address": "Jl. Uji Coba 53, Sumedang"}, timeout=30)
    check(cv.status_code == 200, "konversi berhasil", detail(cv))
    out = j(cv).get("data") or {}
    cust = out.get("customer") or {}
    contract = out.get("contract") or {}
    check(out.get("created") is True, "pembeli & kontrak DIBUAT", str(out.get("note")))
    # Pembeli boleh saja DEDUP ke baris yang sudah ada (satu orang bisa beli unit kedua):
    # yang wajib benar adalah lead ini TERTAUT pada pembeli tersebut.
    check(cust.get("lead_id") == lead_id or lead_id in (cust.get("lead_ids") or []),
          "pembeli tertaut ke lead (tautan yang dulu tidak pernah ada)",
          f"lead_id={cust.get('lead_id')} lead_ids={cust.get('lead_ids')}")
    check(bool(contract.get("number")), "kontrak punya nomor", str(contract.get("number")))
    cv2 = requests.post(f"{BASE}/deals/{deal_id}/convert", headers=sa, json={}, timeout=30)
    check(cv2.status_code == 200 and (j(cv2).get("data") or {}).get("created") is False,
          "konversi IDEMPOTEN (dijalankan dua kali tidak membuat kontrak kembar)",
          detail(cv2))
    lead_after = j(requests.get(f"{BASE}/leads/{lead_id}", headers=sa, timeout=30)).get("data") or {}
    check(lead_after.get("stage") == "won",
          "tahap lead menjadi 'won' (akhir domain lead)", f"stage={lead_after.get('stage')}")
    cid = contract.get("id")

    # ------------------------------------------------ kontrak: rincian & kejujuran angka
    head("C1. Kontrak: satu baris per komponen, biaya kosong TIDAK ditulis 0")
    det = requests.get(f"{BASE}/contracts/{cid}", headers=sa, timeout=30)
    data = j(det).get("data") or {}
    bd = data.get("breakdown") or {}
    codes = [r["code"] for r in bd.get("rows") or []]
    check(det.status_code == 200, "kontrak bisa dibaca", detail(det))
    for c in ("UNIT_PRICE", "EXCESS_LAND", "HOOK_FEE", "BOOKING_FEE", "BPHTB", "NOTARY_FEE",
              "BANK_FEE", "PLAFON_KREDIT"):
        check(c in codes, f"komponen {c} muncul sebagai BARIS tersendiri", str(codes))
    kosong = [r for r in bd.get("rows") or [] if r["state"] == "empty"]
    check(all(r["amount"] is None for r in kosong),
          "komponen yang belum diisi bernilai null (bukan 0)",
          str([(r["code"], r["amount"]) for r in kosong]))
    check(bd.get("total_is_provisional") is True,
          "total ditandai SEMENTARA selama ada biaya yang belum diisi")
    check(bd.get("has_excess_land") is True, "kelebihan tanah terbaca dari add-on penawaran")

    head("C2. Gerbang bukti tahap legal & KPR (uji NEGATIF lebih dulu)")
    ppjb_early = requests.post(f"{BASE}/contracts/{cid}/legal/ppjb", headers=sa, json={},
                               timeout=30)
    check(ppjb_early.status_code == 400, "PPJB DITOLAK sebelum DP terbayar",
          detail(ppjb_early))
    sp3k_nofile = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/sp3k", headers=sa,
                                json={"plafon": 150000000}, timeout=30)
    check(sp3k_nofile.status_code == 400, "SP3K DITOLAK tanpa berkas bukti",
          detail(sp3k_nofile))
    akad_early = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/akad_kredit", headers=sa,
                               json={}, timeout=30)
    check(akad_early.status_code == 400, "akad kredit DITOLAK sebelum SP3K sah",
          detail(akad_early))

    head("C3. Isi komponen biaya (Keuangan) lalu aktifkan kontrak")
    costs = requests.post(f"{BASE}/contracts/{cid}/costs", headers=fin, json={
        "bphtb": 4300000, "notary_fee": 13200000, "bank_fee": 10500000,
        "insurance": 2500000, "pph_seller": 0, "promo_discount": 2000000,
        "plafon_kredit": 160340000}, timeout=30)
    check(costs.status_code == 200, "Keuangan boleh mengisi komponen biaya", detail(costs))
    bd2 = (j(costs).get("data") or {}).get("breakdown") or {}
    check(bd2.get("total_is_provisional") is False,
          "total tidak lagi 'sementara' setelah semua biaya diisi",
          str(bd2.get("costs_incomplete")))
    check(bd2.get("self_funding") is not None,
          "selisih pendanaan (harga nett − plafon) dihitung untuk skema KPR",
          str(bd2.get("self_funding")))
    act = requests.post(f"{BASE}/contracts/{cid}/activate", headers=fin, timeout=30)
    check(act.status_code == 200, "kontrak diaktifkan (termin AR mengikuti skema kontrak)",
          detail(act))
    plan = ((j(act).get("data") or {}).get("payment_plan") or {})
    check(plan.get("state") == "ada" and len(plan.get("terms") or []) >= 1,
          "rencana bayar terbaca dari AR (satu mesin termin, bukan rumus kedua)",
          str(plan.get("state")))

    # ------------------------------------------------ D. dokumen owner + cetak
    head("D. Dokumen ASLI owner: terbitkan & cetak")
    avail = requests.get(f"{BASE}/contracts/{cid}/documents/available", headers=sa, timeout=30)
    ad = {a["code"]: a for a in j(avail).get("data") or []}
    check(avail.status_code == 200 and ad, "daftar template bisa dibaca", detail(avail))
    check(j(avail).get("recommended_code") == "SPR_KPR",
          "varian SPR dipilih dari SKEMA kontrak (bukan pilihan bebas)",
          str(j(avail).get("recommended_code")))
    check(ad.get("SPR_CASH", {}).get("can_generate") is False,
          "SPR Cash DITOLAK untuk kontrak KPR (dokumen tidak boleh bertentangan dg kontrak)",
          str(ad.get("SPR_CASH", {}).get("blocks")))
    check(ad.get("SPKT", {}).get("can_generate") is True,
          "SPKT boleh diterbitkan karena ADA kelebihan tanah",
          str(ad.get("SPKT", {}).get("blocks")))
    spr = requests.post(f"{BASE}/contracts/{cid}/documents", headers=sa,
                        json={"template_code": "SPR_KPR"}, timeout=30)
    check(spr.status_code == 200, "SPR KPR diterbitkan", detail(spr))
    sdoc = j(spr).get("data") or {}
    num = str(sdoc.get("doc_number") or "")
    check(num.count("/") == 4 and "SPR-KPR" in num,
          "nomor mengikuti format dokumen owner {urut}/{kode}/{proyek}/{bulan romawi}/{tahun}",
          num)
    body = str(sdoc.get("content") or "")
    check("166" in body or "Rp" in body, "isi dokumen memuat angka rupiah", body[:80])
    check("Rp 160.340.000" in body, "plafon kredit dari KONTRAK ikut tercetak",
          [ln for ln in body.split("\n") if "Plafon" in ln][:1])
    check("Rp 4.300.000" in body, "BPHTB dari kontrak ikut tercetak",
          [ln for ln in body.split("\n") if "BPHTB" in ln][:1])
    check("[" not in body.split("Nomor:")[0], "tidak ada placeholder yang bocor di judul")
    biaya_lines = [ln for ln in body.split("\n")
                   if ln.startswith(("BPHTB", "Biaya notaris", "Biaya bank", "Booking fee"))]
    check(biaya_lines and all("belum ditetapkan" not in ln for ln in biaya_lines),
          "biaya yang SUDAH diisi tidak lagi berbunyi 'belum ditetapkan'", str(biaya_lines))
    pdf = requests.get(f"{BASE}/documents/{sdoc.get('id')}/pdf", headers=sa, timeout=60)
    check(pdf.status_code == 200 and pdf.headers.get("content-type", "").startswith(
        "application/pdf"), "dokumen BISA DICETAK (PDF)",
        f"{pdf.status_code} {pdf.headers.get('content-type')}")
    check(len(io.BytesIO(pdf.content).getvalue()) > 1500, "berkas PDF berisi",
          f"{len(pdf.content)} byte")
    spkt = requests.post(f"{BASE}/contracts/{cid}/documents", headers=sa,
                         json={"template_code": "SPKT"}, timeout=30)
    check(spkt.status_code == 200, "SPKT diterbitkan", detail(spkt))
    sk = str((j(spkt).get("data") or {}).get("content") or "")
    check(num in sk, "SPKT merujuk NOMOR SPR yang sudah terbit", sk[:120])
    check("12 m²" in sk or "12 m" in sk, "luas kelebihan tanah (12 m²) tercetak sebagai estimasi",
          [ln for ln in sk.split("\n") if "Kelebihan" in ln][:2])

    # ------------------------------------------------ C4. bayar DP → PPJB → SP3K → akad → AJB
    head("C4. Bukti membuka tahap legal (SP3K → akad kredit → PPJB → AJB)")
    up = requests.post(f"{BASE}/files/upload", headers=sa,
                       files={"file": ("sp3k-poc53.txt", b"DEMO SP3K POC 53", "text/plain")},
                       data={"owner_type": "contract", "owner_id": cid, "doc_type": "sp3k"},
                       timeout=60)
    fid = (j(up).get("data") or {}).get("id")
    check(up.status_code == 200 and fid, "berkas SP3K diunggah", detail(up))
    for stage, payload in (("diajukan_ke_bank", {"bank": "BTN"}),
                           ("appraisal", {"amount": 170000000}),
                           ("sp3k", {"number": "SP3K/POC/53", "plafon": 160340000,
                                     "tenor_months": 180, "rate": 8.5, "file_id": fid})):
        r = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/{stage}", headers=sa,
                          json=payload, timeout=30)
        check(r.status_code == 200, f"tahap KPR '{stage}' berhasil", detail(r))
    # NEGATIF: SP3K sudah sah, tetapi kelebihan tanah belum dibayar sepeser pun.
    akad_unpaid = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/akad_kredit", headers=sa,
                                json={"notary": "Notaris Uji"}, timeout=30)
    check(akad_unpaid.status_code == 400,
          "akad kredit DITOLAK karena kelebihan tanah belum lunas (ketentuan SPKT)",
          detail(akad_unpaid))
    ppjb_early2 = requests.post(f"{BASE}/contracts/{cid}/legal/ppjb", headers=sa, json={},
                                timeout=30)
    check(ppjb_early2.status_code == 400, "PPJB masih ditolak selama DP belum masuk",
          detail(ppjb_early2))

    ar = j(requests.get(f"{BASE}/finance/ar/{deal_id}", headers=fin, timeout=30)).get("data") or {}
    inv = ar.get("invoice") or ar
    outstanding = int(inv.get("outstanding") or 0)
    dp = int((inv.get("items") or [{}])[0].get("amount") or 0)
    bayar = min(dp, outstanding) if dp else outstanding
    pay = requests.post(f"{BASE}/finance/ar/receipts", headers=fin, json={
        "deal_id": deal_id, "amount": bayar, "method": "transfer",
        "note": "POC 53 DP"}, timeout=60)
    check(pay.status_code == 200, f"pembayaran DP Rp {bayar:,} dicatat Keuangan".replace(",", "."),
          detail(pay))
    ppjb = requests.post(f"{BASE}/contracts/{cid}/legal/ppjb", headers=sa,
                         json={"note": "POC 53"}, timeout=30)
    check(ppjb.status_code == 200, "PPJB bisa ditandatangani SETELAH DP masuk", detail(ppjb))
    ajb_early = requests.post(f"{BASE}/contracts/{cid}/legal/ajb", headers=sa, json={},
                              timeout=30)
    check(ajb_early.status_code == 400,
          "AJB DITOLAK sebelum akad kredit (aturan skema KPR, bukan aturan tunai)",
          detail(ajb_early))
    akad = requests.post(f"{BASE}/contracts/{cid}/kpr/stage/akad_kredit", headers=sa,
                         json={"notary": "Notaris Uji", "place": "Sumedang",
                               "file_id": fid}, timeout=30)
    check(akad.status_code == 200, "AKAD KREDIT tercatat setelah semua bukti lengkap",
          detail(akad))
    c_after = j(requests.get(f"{BASE}/contracts/{cid}", headers=sa, timeout=30)).get("data") or {}
    check((c_after.get("legal") or {}).get("akad_kredit") is not None,
          "akad kredit juga tercatat sebagai TAHAP LEGAL kontrak (milik pembeli, D4)")
    ajb = requests.post(f"{BASE}/contracts/{cid}/legal/ajb", headers=sa,
                        json={"notary": "Notaris Uji"}, timeout=30)
    check(ajb.status_code == 200, "AJB bisa ditandatangani SETELAH akad kredit", detail(ajb))
    final = j(requests.get(f"{BASE}/contracts/{cid}", headers=sa, timeout=30)).get("data") or {}
    check(final.get("legal_stage") == "ajb", "tahap legal kontrak = ajb",
          str(final.get("legal_stage")))
    d_final = j(requests.get(f"{BASE}/deals/{deal_id}", headers=sa, timeout=30)).get("data") or {}
    check(d_final.get("legal_stage") == "ajb" and d_final.get("status") == "completed",
          "deal lama ikut dicerminkan (layar & gate lama tetap benar)",
          f"{d_final.get('status')}/{d_final.get('legal_stage')}")

    print("\n" + "=" * 66)
    print(f"HASIL POC 53: {len(OK)} PASS, {len(FAIL)} FAIL")
    # --- TIDAK MENINGGALKAN JEJAK ---------------------------------------------------
    # POC ini menjalankan rantai penuh sampai AJB, artinya satu unit demo berakhir `sold`
    # dan lahir pembeli/kontrak/dokumen sintetis. Dijalankan beberapa kali, seluruh unit
    # demo habis dan aplikasi tampak rusak ("tidak ada unit untuk direservasi") padahal itu
    # jejak perangkat uji. Karena itu bahan ujinya dibersihkan di sini, dan KEBERSIHANNYA
    # ikut diperiksa. `--sisakan` dipakai saat perlu memeriksa hasilnya di layar.
    if "--sisakan" in sys.argv:
        print("Bahan uji DIBIARKAN (--sisakan): bersihkan nanti dengan "
              "`python3 scripts/_fixture53.py`.")
    else:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import _fixture53
        hitung = _fixture53.purge()
        unit_after = requests.get(f"{BASE}/units", headers=sa,
                                  params={"status": "available", "limit": 100}, timeout=30)
        tersedia = len(j(unit_after).get("data") or [])
        print(f"Bahan uji dibersihkan: {hitung} \u00b7 unit tersedia sekarang: {tersedia}")
        if tersedia < 1:
            print("  MERAH unit uji TIDAK kembali tersedia \u2014 pembersih perlu diperbaiki")
            FAIL.append("unit uji tidak kembali tersedia setelah pembersihan")
    if FAIL:
        print("YANG GAGAL:")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("POC FASE 53 PASSED — lead bisa menjadi pembeli, kontraknya hidup, "
          "akad kredit ada, dan dokumen owner bisa dicetak.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
