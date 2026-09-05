#!/usr/bin/env python3
"""poc_48.py — POC inti Fase 48 (Pengadaan & Subkon lanjutan) TANPA UI.

Membuktikan enam janji yang sebelumnya TIDAK PUNYA JALAN di aplikasi (hasil audit
`scripts/_audit48.py` terhadap API nyata):

  A. Vendor bukan lagi teks bebas: master vendor + daftar harga + PEMBANDING harga, dan
     harga yang belum pernah dicatat menjawab "belum ada data" (bukan "wajar" palsu).
  B. Permintaan material lapangan punya jalan resmi ke pembelian: kekurangan dihitung
     (diminta − keluar − stok − sudah dipesan) dan PO dari permintaan yang sama TIDAK
     bisa lahir dua kali.
  C. Barang bisa DIRETUR: stok & nilai diterima ikut turun; retur yang membuat nilai
     diterima jatuh di bawah nilai yang sudah ditagih DITOLAK (bukan diam-diam).
  D. 3-way match MENAHAN tagihan yang melebihi barang diterima; hanya manajer keuangan
     yang boleh menerobos dengan alasan tertulis.
  E. Uang subkon lengkap: uang muka (berjurnal) → potongan (angsuran + denda) yang
     memotong termin dengan jurnal SEIMBANG → retensi masuk daftar → pencairan
     BERGERBANG (masa pemeliharaan & punch list) dan tidak bisa dua kali.
  F. Stok antar proyek: transfer tidak menciptakan/menghilangkan barang, peringatan stok
     minimum menyala, dan nilai persediaan memakai harga rata-rata bergerak (material
     tanpa harga masuk dilaporkan apa adanya).

Semua bahan dibuat sendiri lewat API resmi (bertanda `gate48`) lalu dibuang; antrean event
ditunggu kosong sebelum pemeriksaan & pembersihan supaya tidak meninggalkan jurnal
menggantung (pelajaran Fase 47).
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import _fixture48 as fx  # noqa: E402

PASS, FAIL = [], []


def check(ok: bool, label: str, detail: str = ""):
    (PASS if ok else FAIL).append(label)
    print(f"  {'PASS ' if ok else 'GAGAL'} {label}" + (f" — {detail}" if detail else ""))
    return ok


def rp(n) -> str:
    return f"Rp {int(n or 0):,}"


def head(title: str):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# ============================================================ A. vendor & harga
def flow_a(pm, ctx):
    head("A. Master vendor, daftar harga, dan pembanding (48A)")
    mat = ctx["mat_semen"]
    v1 = fx.api("POST", "/vendors", pm, json={
        "code": "G48-V1", "name": "PT Uji Beton Gate48", "category": "material",
        "payment_terms_days": 30, "note": "vendor uji"}).json()["data"]
    v2 = fx.api("POST", "/vendors", pm, json={
        "code": "G48-V2", "name": "CV Uji Baja Gate48", "category": "material",
        "payment_terms_days": 45}).json()["data"]
    fx.db.vendors.update_many({"id": {"$in": [v1["id"], v2["id"]]}}, {"$set": {fx.TAG: True}})
    ctx["v1"], ctx["v2"] = v1, v2
    check(bool(v1.get("code") == "G48-V1"), "vendor terdaftar sebagai MASTER (bukan teks bebas)",
          f"{v1['code']} {v1['name']}")

    dup = fx.api("POST", "/vendors", pm, json={
        "code": "G48-V1", "name": "Vendor kembar", "category": "material"})
    check(dup.status_code == 400, "kode vendor kembar ditolak", dup.text[:90])

    # Harga belum ada → pembanding JUJUR mengaku belum ada data.
    empty = fx.api("GET", "/vendors/price-compare", pm,
                   params={"material_id": mat["id"]}).json()["data"]
    check(empty["state"] == "missing_data",
          "pembanding harga kosong menjawab 'belum ada data' (bukan Rp 0)", empty["detail"][:70])

    for vendor, price in ((v1, 100_000), (v2, 118_000)):
        fx.api("POST", "/vendors/price-list", pm, json={
            "vendor_id": vendor["id"], "material_id": mat["id"], "uom": mat["uom"],
            "unit_price": price, "source": "penawaran", "valid_from": fx.day(-7),
            "valid_until": fx.day(60)})
    cmp_ = fx.api("GET", "/vendors/price-compare", pm,
                  params={"material_id": mat["id"], "qty": 10}).json()["data"]
    best = cmp_["best"]
    check(cmp_["state"] == "complete" and best["vendor_id"] == v1["id"]
          and best["unit_price"] == 100_000,
          "pembanding harga menunjuk penawaran termurah",
          f"{best['vendor_name']} {rp(best['unit_price'])} (2 penawaran)")
    check(cmp_["rows"][1]["delta_vs_best"] == 18_000,
          "selisih terhadap termurah dihitung apa adanya",
          f"+{rp(cmp_['rows'][1]['delta_vs_best'])} ({cmp_['rows'][1]['delta_pct']}%)")

    chk = fx.api("GET", "/vendors/price-check", pm, params={
        "material_id": mat["id"], "unit_price": 130_000, "vendor_id": v1["id"]}).json()["data"]
    check(chk["state"] == "di_atas_acuan" and chk["variance_pct"] == 30.0,
          "harga 30% di atas acuan diberi peringatan beralasan", chk["detail"][:90])
    wajar = fx.api("GET", "/vendors/price-check", pm, params={
        "material_id": mat["id"], "unit_price": 105_000, "vendor_id": v1["id"]}).json()["data"]
    check(wajar["state"] == "wajar", "harga di dalam ambang dinyatakan wajar",
          wajar["detail"][:80])

    # Koreksi harga = update berjejak, bukan baris kembar.
    fx.api("POST", "/vendors/price-list", pm, json={
        "vendor_id": v1["id"], "material_id": mat["id"], "uom": mat["uom"],
        "unit_price": 102_000, "source": "penawaran", "valid_from": fx.day(-7)})
    rows = fx.api("GET", "/vendors/price-list", pm,
                  params={"vendor_id": v1["id"], "material_id": mat["id"]}).json()["data"]
    check(len(rows) == 1 and rows[0]["unit_price"] == 102_000 and rows[0]["history"],
          "koreksi harga = satu baris + riwayat (bukan harga kembar)",
          f"{len(rows)} baris, riwayat {len(rows[0]['history'])}")


# ============================================================ B. permintaan → PO
def flow_b(pm, fin, ctx):
    head("B. Permintaan material lapangan → PO (48B)")
    req, mat = ctx["req"], ctx["mat_semen"]
    sh = fx.api("GET", f"/materials/requisitions/{req['id']}/shortage", pm).json()["data"]
    row = sh["rows"][0]
    check(row["shortage"] == 100 and row["stock"] == 0,
          "kekurangan dihitung dari permintaan − keluar − stok − sudah dipesan",
          f"minta {row['qty_requested']:g}, stok {row['stock']:g}, kurang {row['shortage']:g}")
    check(row.get("reference_price") == 102_000,
          "harga acuan ikut ditawarkan agar PO tidak mengarang harga",
          f"{rp(row.get('reference_price'))} — {row.get('reference_basis')}")

    r = fx.api("POST", f"/materials/requisitions/{req['id']}/to-po", pm, json={
        "vendor_id": ctx["v1"]["id"], "due_date": fx.day(3),
        "items": [{"material_id": mat["id"], "qty": 100, "unit_price": 102_000}]})
    check(r.status_code == 200, "PO lahir dari permintaan lapangan", r.text[:120])
    po = r.json()["data"]
    ctx["po"] = po
    check(po["requisition_id"] == req["id"] and po["po_source"] == "requisition"
          and po["total"] == 10_200_000,
          "PO membawa jejak permintaan asalnya", f"{po['po_number']} {rp(po['total'])}")

    again = fx.api("POST", f"/materials/requisitions/{req['id']}/to-po", pm, json={
        "vendor_id": ctx["v1"]["id"],
        "items": [{"material_id": mat["id"], "qty": 100, "unit_price": 102_000}]})
    check(again.status_code == 400, "PO kedua dari permintaan yang sama DITOLAK (idempoten)",
          again.json().get("detail", "")[:110])

    ap = fx.api("POST", f"/procurement/pos/{po['id']}/approve", fin, json={"note": "uji"})
    check(ap.status_code == 200, "PO disetujui keuangan", ap.text[:80])

    g = fx.api("POST", "/procurement/grns", pm, json={
        "po_id": po["id"], "items": [{"po_item_index": 0, "qty_received": 60}],
        "note": "penerimaan sebagian"})
    check(g.status_code == 200, "penerimaan sebagian (GRN parsial) tercatat", g.text[:80])
    ctx["grn"] = g.json()["data"]
    stock = fx.api("GET", f"/materials/project/{ctx['project']['id']}", pm).json()["data"]
    semen = next(m for m in stock if m["id"] == mat["id"])
    po_now = fx.api("GET", f"/procurement/pos/{po['id']}", pm).json()["data"]
    check(semen["stock"] == 60 and po_now["received_value"] == 6_120_000,
          "stok & nilai diterima ikut naik sesuai penerimaan",
          f"stok {semen['stock']:g}, diterima {rp(po_now['received_value'])}")


# ============================================================ C. retur barang
def flow_c(pm, ctx):
    head("C. Retur barang membalik penerimaan (48B)")
    grn, mat = ctx["grn"], ctx["mat_semen"]
    bad = fx.api("POST", "/procurement/returns", pm, json={
        "grn_id": grn["id"], "kind": "rusak",
        "items": [{"grn_item_index": 0, "qty_returned": 999}],
        "reason": "coba mengembalikan lebih banyak daripada yang diterima"})
    check(bad.status_code == 400, "retur melebihi jumlah diterima ditolak",
          bad.json().get("detail", "")[:100])

    r = fx.api("POST", "/procurement/returns", pm, json={
        "grn_id": grn["id"], "kind": "rusak",
        "items": [{"grn_item_index": 0, "qty_returned": 10}],
        "reason": "10 sak mengeras karena terkena air saat pengiriman"})
    check(r.status_code == 200, "retur barang tercatat beralasan", r.text[:90])
    ret = r.json()["data"]
    ctx["return"] = ret
    stock = fx.api("GET", f"/materials/project/{ctx['project']['id']}", pm).json()["data"]
    semen = next(m for m in stock if m["id"] == mat["id"])
    po_now = fx.api("GET", f"/procurement/pos/{ctx['po']['id']}", pm).json()["data"]
    check(semen["stock"] == 50 and po_now["received_value"] == 5_100_000,
          "stok & nilai diterima IKUT TURUN setelah retur",
          f"stok {semen['stock']:g}, diterima {rp(po_now['received_value'])}")
    check(ret["returned_value"] == 1_020_000, "nilai retur dihitung dari harga PO",
          rp(ret["returned_value"]))


# ============================================================ D. 3-way MENAHAN
def flow_d(pm, fin, finlead, ctx):
    head("D. 3-way match MENAHAN tagihan yang melebihi barang diterima (48B)")
    po = ctx["po"]
    over = fx.api("POST", "/procurement/bills", pm, json={
        "po_id": po["id"], "claimed": 9_000_000, "retention_pct": 0, "due_date": fx.day(30)})
    check(over.status_code == 400, "tagihan melebihi barang diterima DITAHAN (bukan sekadar ditandai)",
          over.json().get("detail", "")[:130])

    ok = fx.api("POST", "/procurement/bills", pm, json={
        "po_id": po["id"], "claimed": 5_100_000, "retention_pct": 0, "due_date": fx.day(30),
        "note": "tagihan sesuai barang diterima"})
    check(ok.status_code == 200 and ok.json()["match"]["state"] == "matched",
          "tagihan sesuai barang diterima lolos", ok.text[:80])
    ctx["bill_po"] = ok.json()["data"]

    forced = fx.api("POST", "/procurement/bills", pm, json={
        "po_id": po["id"], "claimed": 2_000_000, "retention_pct": 0,
        "override_hold": True, "override_reason": "dicoba diterobos oleh pengaju sendiri"})
    check(forced.status_code == 403, "pengaju biasa TIDAK boleh menerobos tahanan",
          forced.json().get("detail", "")[:100])

    noreason = fx.api("POST", "/procurement/bills", finlead, json={
        "po_id": po["id"], "claimed": 2_000_000, "retention_pct": 0,
        "override_hold": True, "override_reason": "ok"})
    check(noreason.status_code == 400, "terobosan tanpa alasan memadai ditolak",
          noreason.json().get("detail", "")[:100])

    forced_ok = fx.api("POST", "/procurement/bills", finlead, json={
        "po_id": po["id"], "claimed": 2_000_000, "retention_pct": 0,
        "override_hold": True,
        "override_reason": "Barang sisa sudah di jalan & dijamin surat jalan vendor 18/08."})
    check(forced_ok.status_code == 200
          and forced_ok.json()["data"]["match_state"] == "overridden",
          "manajer keuangan boleh menerobos DENGAN alasan (berjejak)",
          forced_ok.json()["data"].get("override_reason", "")[:70])
    ctx["bill_override"] = forced_ok.json()["data"]

    blocked = fx.api("POST", "/procurement/returns", pm, json={
        "grn_id": ctx["grn"]["id"], "kind": "mutu",
        "items": [{"grn_item_index": 0, "qty_returned": 40}],
        "reason": "retur besar setelah barangnya terlanjur ditagih penuh"})
    check(blocked.status_code == 400,
          "retur yang membuat 'diterima' < 'ditagih' ditolak (minta nota koreksi dulu)",
          blocked.json().get("detail", "")[:120])


# ============================================================ E. uang subkon
def flow_e(pm, fin, finlead, ctx):
    head("E. Uang muka, potongan, dan retensi subkon (48C)")
    spk = ctx["spk"]
    a = fx.api("POST", "/subcon/advances", pm, json={
        "spk_id": spk["id"], "amount": 20_000_000,
        "reason": "Mobilisasi alat & upah minggu pertama di lokasi."})
    check(a.status_code == 200, "uang muka diajukan PM", a.text[:90])
    adv = a.json()["data"]
    too_big = fx.api("POST", "/subcon/advances", pm, json={
        "spk_id": spk["id"], "amount": 90_000_000,
        "reason": "Uang muka melebihi kebijakan agar bisa diuji penolakannya."})
    check(too_big.status_code == 400, "uang muka melebihi 30% nilai kontrak ditolak",
          too_big.json().get("detail", "")[:110])

    self_ok = fx.api("POST", f"/subcon/advances/{adv['id']}/decision", fin,
                     json={"approve": True, "reason": "coba disetujui finance biasa"})
    check(self_ok.status_code == 403, "finance biasa tidak boleh memutuskan uang muka",
          self_ok.json().get("detail", "")[:90])

    d = fx.api("POST", f"/subcon/advances/{adv['id']}/decision", finlead,
               json={"approve": True, "reason": "Sesuai kontrak: uang muka 20% mobilisasi."})
    check(d.status_code == 200 and d.json()["data"]["state"] == "approved",
          "manajer keuangan menyetujui uang muka", d.text[:70])
    p = fx.api("POST", f"/subcon/advances/{adv['id']}/pay", fin, json={"note": "transfer"})
    check(p.status_code == 200 and p.json()["data"]["state"] == "paid",
          "uang muka dibayar & berjurnal", f"jurnal {p.json()['data'].get('journal_no')}")
    je = fx.db.journal_entries.find_one({"source_id": adv["id"],
                                         "source_type": "subcon_advance"}, {"_id": 0})
    dr = {ln["account_code"]: ln["debit"] for ln in (je or {}).get("lines", [])}
    check(bool(je) and dr.get("1-1800") == 20_000_000,
          "uang muka masuk ASET (1-1800), bukan biaya (tidak dihitung dua kali)",
          f"Dr 1-1800 {rp(dr.get('1-1800'))}")

    fx.api("POST", "/subcon/deductions", pm, json={
        "spk_id": spk["id"], "kind": "advance", "advance_id": adv["id"], "amount": 5_000_000,
        "reason": "Angsuran uang muka ke-1 sesuai jadwal potongan pada SPK."})
    fx.api("POST", "/subcon/deductions", pm, json={
        "spk_id": spk["id"], "kind": "penalty", "amount": 1_000_000,
        "reason": "Denda keterlambatan 2 hari kalender atas pekerjaan struktur."})
    over_amort = fx.api("POST", "/subcon/deductions", pm, json={
        "spk_id": spk["id"], "kind": "advance", "advance_id": adv["id"], "amount": 50_000_000,
        "reason": "Angsuran melebihi sisa uang muka agar penolakannya bisa diuji."})
    check(over_amort.status_code == 400, "angsuran melebihi sisa uang muka ditolak",
          over_amort.json().get("detail", "")[:100])

    c = fx.api("POST", "/subcon/claims", pm, json={
        "spk_id": spk["id"], "period": "Termin 1", "progress_pct": 50,
        "due_date": fx.day(21), "note": "uji"})
    check(c.status_code == 200, "termin subkon diajukan", c.text[:90])
    claim = c.json()["data"]
    ap = fx.api("POST", f"/subcon/claims/{claim['id']}/approve", fin)
    check(ap.status_code == 200, "termin disetujui keuangan", ap.text[:120])
    claim = ap.json()["data"]
    gross, ret_held = int(claim["gross"]), int(claim["retention_held"])
    ded = int(claim.get("deduction_total", 0))
    net = int(claim["net"])
    check(gross == 50_000_000 and ret_held == 2_500_000 and ded == 6_000_000
          and net == gross - ret_held - ded,
          "net termin = bruto − retensi − potongan (bisa direkonstruksi)",
          f"{rp(gross)} − {rp(ret_held)} − {rp(ded)} = {rp(net)}")

    fx.settle()
    bill_je = fx.wait_journal(claim["ap_bill_id"], "ap_bill")
    lines = {ln["account_code"]: (ln["debit"], ln["credit"]) for ln in (bill_je or {}).get("lines", [])}
    total_dr = sum(ln["debit"] for ln in (bill_je or {}).get("lines", []))
    total_cr = sum(ln["credit"] for ln in (bill_je or {}).get("lines", []))
    check(bool(bill_je) and total_dr == total_cr == gross,
          "jurnal termin SEIMBANG walau ada potongan", f"D {rp(total_dr)} = K {rp(total_cr)}")
    check(lines.get("1-1800", (0, 0))[1] == 5_000_000 and lines.get("4-1200", (0, 0))[1] == 1_000_000,
          "angsuran uang muka & denda masuk akun yang benar",
          f"Cr 1-1800 {rp(5_000_000)}, Cr 4-1200 {rp(1_000_000)}")
    adv_now = fx.db.subcon_advances.find_one({"id": adv["id"]}, {"_id": 0})
    check(adv_now["amortized"] == 5_000_000 and adv_now["outstanding"] == 15_000_000,
          "sisa uang muka berkurang persis sebesar angsuran",
          f"terangsur {rp(adv_now['amortized'])}, sisa {rp(adv_now['outstanding'])}")

    rets = fx.api("GET", "/subcon/retentions", pm, params={"spk_id": spk["id"]}).json()
    check(rets["total"] == 1 and rets["data"][0]["amount"] == ret_held,
          "retensi otomatis masuk DAFTAR (dulu hanya menumpuk di tagihan)",
          f"{rets['data'][0]['retention_number']} {rp(rets['data'][0]['amount'])}")
    ctx["retention"] = rets["data"][0]


def flow_e2(pm, finlead, ctx):
    head("E2. Gerbang pencairan retensi (48C)")
    ret = ctx["retention"]
    punch = fx.make_punch(ctx["project"]["id"], title="Retak rambut dinding (uji)")
    blocked = fx.api("POST", f"/subcon/retentions/{ret['id']}/request-release", pm,
                     json={"reason": "Pekerjaan sudah selesai dan diserahterimakan."})
    check(blocked.status_code == 400 and "punch" in blocked.text.lower(),
          "pencairan ditolak selama masih ada temuan punch list terbuka",
          blocked.json().get("detail", "")[:110])

    fx.db.punch_items.update_one({"id": punch["id"]}, {"$set": {"status": "closed"}})
    spk2 = fx.make_spk(ctx["project"], ctx["sub"], 40_000_000, maintenance_days=180,
                       end_offset=0)
    fx.db.subcon_retentions.insert_one({
        "id": fx.new_id(), "org_id": fx.ORG, fx.TAG: True,
        "retention_number": "RET/GATE48/BLOCK", "spk_id": spk2["id"],
        "spk_number": spk2["spk_number"], "project_id": ctx["project"]["id"],
        "subcontractor_id": ctx["sub"]["id"], "subcontractor_name": ctx["sub"]["name"],
        "claim_id": None, "claim_number": None, "ap_bill_id": None, "amount": 2_000_000,
        "retention_pct": 5, "state": "held", "maintenance_days": 180,
        "maintenance_until": fx.day(180), "created_at": fx.now_iso(), "updated_at": fx.now_iso()})
    still = fx.api("GET", "/subcon/retentions", pm, params={"spk_id": spk2["id"]}).json()["data"]
    gate = still[0]["gate"]
    check(not gate["ok"] and any(b["code"] == "maintenance_active" for b in gate["blocks"]),
          "retensi yang masa pemeliharaannya belum lewat DITAHAN",
          gate["detail"][:100])

    req = fx.api("POST", f"/subcon/retentions/{ret['id']}/request-release", pm,
                 json={"reason": "Masa pemeliharaan lewat & seluruh temuan sudah ditutup."})
    check(req.status_code == 200 and req.json()["data"]["state"] == "release_requested",
          "pencairan bisa diajukan setelah syarat terpenuhi", req.text[:70])

    self_rel = fx.api("POST", f"/subcon/retentions/{ret['id']}/release", pm,
                      json={"reason": "Mencoba mencairkan retensi yang saya ajukan sendiri."})
    check(self_rel.status_code == 403, "pengaju tidak boleh mencairkan sendiri (SoD)",
          self_rel.json().get("detail", "")[:90])

    rel = fx.api("POST", f"/subcon/retentions/{ret['id']}/release", finlead,
                 json={"reason": "Masa pemeliharaan selesai, tidak ada temuan tersisa."})
    check(rel.status_code == 200, "manajer keuangan mencairkan retensi", rel.text[:110])
    je = fx.db.journal_entries.find_one({"source_id": ret["id"],
                                         "source_type": "subcon_retention"}, {"_id": 0})
    lines = {ln["account_code"]: (ln["debit"], ln["credit"]) for ln in (je or {}).get("lines", [])}
    check(bool(je) and lines.get("2-1200", (0, 0))[0] == int(ret["amount"])
          and lines.get("2-1100", (0, 0))[1] == int(ret["amount"]),
          "pencairan memindahkan Utang Retensi → Utang Usaha (siap dibayar)",
          f"Dr 2-1200 {rp(ret['amount'])} / Cr 2-1100 {rp(ret['amount'])}")
    twice = fx.api("POST", f"/subcon/retentions/{ret['id']}/release", finlead,
                   json={"reason": "Mencoba mencairkan retensi yang sama untuk kedua kalinya."})
    check(twice.status_code == 400, "retensi tidak bisa dicairkan dua kali",
          twice.json().get("detail", "")[:90])


# ============================================================ F. stok
def flow_f(pm, ctx):
    head("F. Transfer antar proyek, batas stok minimum, nilai persediaan (48E)")
    mat, proj_b = ctx["mat_semen"], ctx["project_b"]
    too_much = fx.api("POST", "/materials/transfers", pm, json={
        "from_project_id": ctx["project"]["id"], "to_project_id": proj_b["id"],
        "material_id": mat["id"], "qty": 999,
        "reason": "Mencoba memindahkan lebih banyak daripada stok yang ada."})
    check(too_much.status_code == 400, "transfer melebihi stok ditolak (barang tidak diciptakan)",
          too_much.json().get("detail", "")[:100])

    t = fx.api("POST", "/materials/transfers", pm, json={
        "from_project_id": ctx["project"]["id"], "to_project_id": proj_b["id"],
        "material_id": mat["id"], "qty": 20,
        "reason": "Pengecoran di proyek sebelah dimajukan, stok dipinjam sementara."})
    check(t.status_code == 200, "transfer antar proyek tercatat", t.text[:90])
    doc = t.json()["data"]
    check(doc["stock_from_after"] == 30 and doc["stock_to_after"] == 20,
          "stok asal turun dan stok tujuan naik dengan jumlah yang SAMA",
          f"asal {doc['stock_from_after']:g}, tujuan {doc['stock_to_after']:g}")
    check(doc["value"] == 2_040_000,
          "nilai transfer memakai harga rata-rata bergerak", rp(doc["value"]))

    fx.api("PUT", f"/materials/{mat['id']}/min-stock", pm, json={"min_qty": 100})
    al = fx.api("GET", "/materials/stock-alerts", pm,
                params={"project_id": ctx["project"]["id"]}).json()
    row = next(r for r in al["data"] if r["material_id"] == mat["id"])
    check(row["state"] == "below_min" and row["shortfall"] == 70,
          "stok di bawah batas minimum menyalakan peringatan",
          f"stok {row['stock']:g} < min {row['min_qty']:g}, kurang {row['shortfall']:g}")
    kosong = next((r for r in al["data"] if r["material_id"] == ctx["mat_besi"]["id"]), None)
    check(bool(kosong) and kosong["state"] in ("no_min", "empty"),
          "material tanpa batas minimum dilaporkan apa adanya, bukan 'aman' palsu",
          kosong["detail"][:80] if kosong else "")

    val = fx.api("GET", "/materials/valuation", pm,
                 params={"project_id": ctx["project"]["id"]}).json()
    semen = next(r for r in val["data"] if r["material_id"] == mat["id"])
    besi = next(r for r in val["data"] if r["material_id"] == ctx["mat_besi"]["id"])
    check(semen["avg_cost"] == 102_000 and semen["value"] == 3_060_000,
          "nilai persediaan = stok × harga rata-rata bergerak",
          f"{semen['stock']:g} × {rp(semen['avg_cost'])} = {rp(semen['value'])}")
    check(besi["state"] == "missing_price" and besi["value"] is None
          and val["summary"]["state"] == "partial",
          "material tanpa harga masuk TIDAK dikarang nilainya",
          val["summary"]["detail"][:90])


# ============================================================ G. evaluasi
def flow_g(pm, ctx):
    head("G. Evaluasi vendor berbukti (48D)")
    ev = fx.api("GET", f"/vendors/{ctx['v1']['id']}/evaluation", pm).json()["data"]
    check(ev["state"] == "complete" and ev["score"] is not None,
          "vendor dengan riwayat transaksi mendapat skor berbukti",
          f"skor {ev['score']} ({ev['grade']}) dari {ev['evidence']}")
    check(ev["components"]["quality"]["score"] is not None
          and "retur" in ev["components"]["quality"]["detail"].lower(),
          "komponen mutu dihitung dari nilai RETUR nyata",
          ev["components"]["quality"]["detail"][:90])
    check(ev["components"]["service"]["score"] is None and "service" in ev["missing"],
          "komponen tanpa sumber data masuk daftar 'belum ada data'",
          ev["components"]["service"]["detail"][:80])

    kosong = fx.api("GET", f"/vendors/{ctx['v2']['id']}/evaluation", pm).json()["data"]
    check(kosong["state"] == "missing_data" and kosong["score"] is None
          and kosong["grade"] == "missing_data",
          "vendor tanpa transaksi TIDAK diberi skor 0 karangan", kosong["detail"][:90])

    a = fx.api("POST", f"/vendors/{ctx['v1']['id']}/assessment", pm, json={
        "period": "2026-08", "scores": {"quality": 4, "timeliness": 3, "service": 5},
        "note": "Kirim tepat waktu, satu batch semen sempat rusak tetapi diganti cepat."})
    check(a.status_code == 200 and a.json()["data"]["average"] == 4.0,
          "penilaian manusia disimpan berdampingan (bukan menggantikan bukti)",
          f"rata-rata {a.json()['data']['average']}")


def build_context(pm, fin):
    proj = fx.make_project("Proyek Uji Fase 48", f"G48-{fx.new_id()[:4].upper()}")
    proj_b = fx.make_project("Proyek Uji Fase 48 (B)", f"G48B-{fx.new_id()[:4].upper()}")
    mat = fx.make_material(proj["id"], "G48-SMN", "Semen uji Gate48", "sak")
    besi = fx.make_material(proj["id"], "G48-BSI", "Besi uji Gate48", "batang")
    req = fx.make_requisition(proj["id"], proj["name"], [fx.req_item(mat, 100)])
    sub = fx.make_subcontractor(f"G48-{fx.new_id()[:4].upper()}", "CV Uji Subkon Gate48")
    spk = fx.make_spk(proj, sub, 100_000_000, retention_pct=5, maintenance_days=0,
                      end_offset=-1)
    return {"project": proj, "project_b": proj_b, "mat_semen": mat, "mat_besi": besi,
            "req": req, "sub": sub, "spk": spk}


def main() -> int:
    print("=" * 78)
    print("POC FASE 48 — pengadaan & subkon yang bisa dipertanggungjawabkan")
    print("=" * 78)
    pm = fx.login("pm@sipro.co.id")
    fin = fx.login("finance@sipro.co.id")
    finlead = fx.login("finlead@sipro.co.id")
    ctx = build_context(pm, fin)
    try:
        flow_a(pm, ctx)
        flow_b(pm, fin, ctx)
        flow_c(pm, ctx)
        flow_d(pm, fin, finlead, ctx)
        flow_e(pm, fin, finlead, ctx)
        flow_e2(pm, finlead, ctx)
        flow_f(pm, ctx)
        flow_g(pm, ctx)
    finally:
        head("Bersih-bersih (jangan meninggalkan jurnal menggantung)")
        fx.settle()
        left = fx.orphans()
        fx.purge()
        after = fx.orphans()
        print(f"  sebelum dibuang: {left}")
        print(f"  sesudah dibuang: {after}")
        check(all(v == 0 for v in after.values()),
              "POC tidak meninggalkan dokumen/jurnal menggantung", str(after))
    print("\n" + "=" * 78)
    if FAIL:
        print(f"HASIL: GAGAL — {len(FAIL)} pemeriksaan merah dari {len(PASS) + len(FAIL)}")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"HASIL: PASS — {len(PASS)} pemeriksaan hijau. Inti Fase 48 terbukti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
