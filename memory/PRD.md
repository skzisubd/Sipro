# SIPRO — Property Development OS (PRD)

Aplikasi manajemen properti & konstruksi (React + FastAPI + MongoDB) dengan RBAC ketat,
keuangan/GL, konstruksi berbukti, portal pembeli, dan dokumen PDF ber-kop.
Bahasa produk & komunikasi: **Indonesia**.

## Aturan kerja yang tidak boleh dilanggar
- `bash scripts/run_all_gates.sh` adalah nyawa proyek. Semua gate harus PASS (sekarang **59 gate**).
- Batas ukuran berkas: Python < 800 baris, JS < 500 baris (`validate_compliance.py`).
- Form: tidak boleh `<Input>` bebas untuk nilai enum/relasi (`audit_forms_deep.py`); setiap
  `<Input>` wajib punya label/placeholder/aria-label.
- Kosakata enum hanya dari SSOT `/api/reference` (`reference_groups.py` + `reference_p<NN>.py`).
- Kredensial uji: `/app/memory/test_credentials.md` (sandi demo `Sipro#2026`).

## Riwayat implementasi (terbaru di atas)
### 5 Sep 2026 — Fase 94–95: Gateway WA tunggal, webhook Meta, Kontak WA → Lead (dedup) — SELESAI
- **Setup**: repo `pandeyoga/sipro050926` di-clone ke /app (rsync tanpa .env), `backend/.env` dipulihkan
  (JWT_SECRET, DEFAULT_ORG_ID, PORTAL_MASTER_OTP, BACKUP_DIR, STORAGE_PROVIDER, COOKIE_SECURE),
  deps terpasang, `memory/test_credentials.md` ditulis ulang.
- **94 Gateway** `wa_gateway.py`: `send(org,to,kind,body|template|document)` → `SimulationAdapter`
  (status `simulated`, wamid `sim-…`) / `MetaCloudAdapter` (Graph v21.0 `/messages`, `/media`,
  probe `GET /{phone_id}` + `/{waba_id}/message_templates`, retry 3× pada 429/5xx). Kredensial 5 kunci
  tersimpan **terenkripsi Fernet (dari JWT_SECRET)** di `channel_accounts.wa_main.credentials_enc`,
  fallback `.env`; `effective_mode` = live hanya bila mode live + token + phone_id. Setiap kirim menulis
  `messages` {kind, mode, status, provider_message_id, error_code/detail}; nomor non-+62 → `failed`.
  Pemanggil dimigrasi: `notifications.send_whatsapp` (OTP/komplain/bukti bayar/penawaran/pengingat),
  Inbox `POST /inbox/{id}/messages` (gagal → 502 + alasan), `engine.send_template_message` (playbook).
- **95 Webhook Meta** `wa_inbound.py` + `webhooks_router`: `GET /api/webhooks/wa` handshake verify_token;
  `POST` menerima payload Meta (`object=whatsapp_business_account`) — verifikasi `X-Hub-Signature-256`
  (ditolak 403 hanya di mode live), `messages[]` teks/gambar/dokumen/audio/lokasi/interaktif → percakapan
  per nomor (dipakai ulang), unread++, sesi 24 jam, media diunduh ke storage saat live, nama profil,
  opt-out (STOP/berhenti); `statuses[]` → `messages.status` by wamid; idempoten (indeks unik parsial
  `uq_messages_wamid`); field tak dikenal → `lead_capture_failures`. Kontrak lama `WebhookLead` tetap.
  Nomor tanpa lead masuk antrean `wa_contacts` (setting baru `wa.auto_capture_lead`, bawaan MATI).
- **Kontak WA → Lead** `wa_contacts.py` + `routers/wa_router.py` (`/api/wa/*`): antrean (status
  new/captured/linked/skipped/invalid, cocok lead/customer per E.164), impor tempel/CSV/VCF
  (`preview` tanpa tulis + `import`), `capture` {ids | all_new | phones} dengan kebijakan
  `policy_lead` skip|link dan `policy_customer` skip|create (repeat buyer), PIC opsional, skip/restore/
  delete, `simulate/inbound` (payload Meta asli → pemroses yang sama). RBAC: antrean `leads:view_all`,
  capture `leads:create`, config `settings:view/manage`.
- **UI**: halaman `/wa-capture` (menu CRM "Kontak WA → Lead"; KPI 6 kartu, tabel antrean + filter status/
  duplikasi + aksi massal, tab Impor dengan pratinjau dedup, dialog Jadikan lead berkebijakan,
  Simulasi pesan masuk), tombol "Capture dari WA" di Pipeline Lead, Inbox: badge status pesan keluar
  (simulasi/terkirim/sampai/dibaca/gagal+alasan), media masuk, "sisa HH:MM" sesi, tombol "Jadikan lead"
  untuk percakapan tanpa lead; Pusat Konfigurasi › **Integrasi WhatsApp** (5 kredensial tersamar, mode,
  Tes koneksi, Kirim pesan uji, status webhook, checklist go-live). TestIds `constants/testIds/p94.js`.
- Uji: `backend/tests/test_p94_95_wa.py` 8/8; testing agent iteration_142 lulus (1 temuan MEDIUM state
  dialog tidak reset → diperbaiki; 2 catatan desain diperbaiki). Gate `validate_compliance` hijau
  (engine.py tetap 800 baris). Baseline lama tetap: `verify_api_contract` 9 panggilan `${base}` RAB.
- **Belum (Fase 94 sisa / 96 / 97)**: kirim dokumen PDF via WA (`/doc-history/send-wa`), antrean
  `wa_outbox`, Broadcast lewat gateway, template Meta sinkron dua arah + kategori/approval, jam kirim &
  batas laju, dashboard pengiriman WA, notifikasi gagal kirim ke sales.
- Catatan jujur: Meta Cloud API **tidak menyediakan daftar kontak**; migrasi kontak lama = ekspor .vcf/.csv
  dari HP/Google Contacts atau tempel nomor → tab Impor.

### 4 Sep 2026 — Fase 93: Drill-down Marketing & Detail Proyek, ekspor CSV popup — SELESAI
- **Marketing**: kartu KPI di Kampanye › Kinerja (Biaya, Lead, Terkualifikasi, CPL, CAC, ROAS), Kampanye › Biaya
  Iklan (Total biaya, Impresi, Klik, Lead platform, CPC) dan Atribusi › Funnel (Lead, Terkualifikasi, Booking,
  Biaya terpetakan, CPL) bisa diklik → `DrilldownDialog`; kunci `ads:*` di `kpi_drilldown_ext.py`
  (memakai match_campaign/FUNNEL_* yang sama dengan laporan). Metrik non-uang membawa `unit:'count'`.
- **Bug pre-existing diperbaiki**: `ads_report.attribution` totals.spend digandakan per baris sumber (7×) →
  kini per campaign_id unik; kolom tabel atribusi diberi label "Biaya kampanye".
- **Detail Proyek**: 5 kartu (tersedia, dipegang/booking, terjual, nilai, progres) → popup daftar unit → Unit 360;
  "Buka tabel terfilter" → `?tab=units&status=a,b,c` (UnitsTab baca filter dari URL, chip status ganda,
  `/masterplan/units` menerima status ganda koma).
- **Ekspor CSV**: tombol "Unduh CSV" di setiap popup rincian (Item;Keterangan;Status;Nilai;Skor;Tautan).
- Uji: iteration_140 (temuan) → iteration_141 retest: backend 23/23 (`tests/test_p93.py`) + frontend lulus.
  Catatan: warning React `<option>` dalam `<span>` berasal dari Radix Select (pre-existing).


### 4 Sep 2026 — Fase 92: Drill-down KPI Beranda, Pipeline Lead, Pembangunan — SELESAI
- **Endpoint generik** `GET /drilldown/{key}` (`kpi_drilldown.py`, RBAC per kunci): tasks (scope/bucket/sla),
  leads (stage/band/sla/idle_days/new_hours), deals, projects, units_qc_hold, punch_open, retention_held,
  build:* (unscheduled/awaiting_verification/rework/late_items/blocked_items/at_risk/scheduled),
  board:* (all/unscheduled/running/late/ready/progress/awaiting — memakai mesin papan unit yang sama),
  kunci keuangan didelegasikan ke `finance_drilldown`. `GET /drilldown/_summary/leads` → 5 KPI lead.
- **Beranda**: KPI `/work/home` membawa `drill_key`+`drill_params`; `KpiCard` prop `onOpen` → `DrilldownDialog`
  (patterns) — baris tugas membuka TaskDetailSheet, lainnya navigasi.
- **Pipeline Lead**: `LeadKpiStrip` (Lead baru 24 jam, Hot, Melewati SLA, Diam ≥7 hari, Won) → popup → profil lead.
- **Pembangunan**: 6 kartu Papan Unit + Metric BuildMonitorPanel bisa diklik → popup → Unit 360 / UnitScheduleSheet.
- Uji: iteration_139 — backend 37/37 (`tests/test_p92.py`) + frontend lulus.


### 4 Sep 2026 — Fase 91: Dashboard keuangan interaktif, tab Piutang/Utang, Dokumen Terbit — SELESAI
- **91A Dashboard Keuangan interaktif**: kartu KPI & bucket aging bisa diklik → `KpiDrilldownDialog`
  (baris penyusun angka, klik baris → tabel terfilter, tombol "Buka tabel terfilter"); grafik
  `AgingChart` (recharts, AR vs AP, klik batang → rincian). Backend `GET /finance/drilldown/{key}`
  (`finance_drilldown.py`; key ar_outstanding, ar_overdue, ar_bucket, ap_outstanding, ap_pending,
  ap_bucket, contract_liability, customer_deposits, revenue_recognized).
- **91B Bug UI tabel**: `.col-actions` sticky kini mengikuti warna baris genap/hover (color-mix).
- **91C Penagihan**: baris tabel & tombol Detail membuka `ArDetailSheet`.
- **91D Tab gabungan**: FinancePage → Dashboard, Arus Kas, **Piutang** (Daftar Piutang, Penagihan,
  Titipan, Keringanan Denda, Pembatalan & Refund), **Utang** (Tagihan Vendor AP, Utang Refund,
  Komisi, Upah Harian), Rekonsiliasi Bank, Laporan, Konfigurasi. URL lama `?tab=ar|ap|…` dipetakan
  (LEGACY) ke `?tab=receivables|payables&sub=…`.
- **91E Dokumen Terbit** (tab baru di profil lead & customer, `IssuedDocsTab`): riwayat dokumen
  per deal per tahap (Booking → SPR & Dokumen Owner → Tagihan & Kwitansi → Pajak & Biaya All-in →
  Legal → BAST) dengan status tahap, PDF, aksi cepat (POST generate template owner / tautan) dan
  alasan bila belum bisa terbit. Backend `GET /doc-history/{lead|customer}/{id}` (`doc_history.py`).
- Uji: iteration_138 — backend 18/18 (`backend/tests/test_p91.py`) + frontend lulus. Catatan:
  dashboard modul lain (Beranda, Lead, Pembangunan) menyusul bertahap (backlog P1).


### 4 Sep 2026 — Fase 90: Lanjutan dari repo GitHub (pandeyoga/sipro05) + catatan minor Fase 89 — SELESAI
- **Setup**: repo di-clone ke /app (rsync tanpa .env), `.env` backend dipulihkan (MONGO_URL, DB_NAME,
  CORS_ORIGINS, JWT_SECRET baru, COOKIE_SECURE), deps backend/frontend dipasang,
  `memory/test_credentials.md` ditulis ulang (sandi demo `Sipro#2026`).
- **90A Kalender shadcn di dialog aturan harga**: `PricingRuleDialog` memakai `DatePickerField`
  untuk Berlaku mulai/sampai (tampilan tanggal Indonesia, nilai ISO) — bukan input date browser.
- **90B Kontras tombol Rapikan**: saat 0 pending tombol tampil outline dashed + opacity penuh.
- **90C Tindak lanjut nomor ganda/tidak valid**: `phone_health` kini memuat `duplicate_samples`
  (id, name, phone, normalized, clash_id, clash_name) & `invalid_samples` (maks 20); nomor yang
  hasil normalisasinya tidak cocok `^\+62\d{8,13}$` dihitung invalid (tidak lagi diubah otomatis).
  Endpoint baru `POST /api/master/phone-fix {collection,id,phone}` (settings.manage; 400 invalid,
  409 bentrok, 404, kosong = hapus nomor, audit log). UI `PhoneFixDialog` via tombol "Perbaiki (n)"
  per koleksi: ubah/hapus nomor per baris + tautan Buka ke profil lead/customer.
- Uji: iteration_137 — backend 13/13 (`backend/tests/test_p90.py`) + frontend lulus semua.


### 4 Sep 2026 — Fase 88: Lanjutan dari repo GitHub (pandeyoga/sipro040926) — SELESAI
- **Setup**: repo di-clone ke /app, `.env` backend (JWT_SECRET, DEFAULT_ORG_ID, PORTAL_MASTER_OTP,
  BACKUP_DIR) dipulihkan, `memory/test_credentials.md` ditulis ulang (sandi demo `Sipro#2026`).
- **88A Telepon +62 otomatis** `components/patterns/PhoneInput.js` (awalan +62 tetap, pemakai
  mengetik nomor lokal, 0 depan/62 ganda dibuang, output E.164) dipakai AddLeadDialog,
  SimulateLeadDialog, AddCustomerDialog — nomor WA tidak lagi salah format.
- **88B Skor lead hidup** `lead_scoring.py`: bobot dari `lead.score.weights` + ambang
  `lead.score.bands` (Pusat Konfigurasi › Lead). Naik: kontak pertama, aktivitas 14 hari, agenda
  terjadwal/dihadiri, balasan WA masuk, disposisi positif. Turun: diam ≥7 hari (−5/minggu, maks
  −30), disposisi negatif/tidak merespons, lead ditutup. `GET /leads/{id}/score` (rincian "kenapa"),
  `POST /leads/{id}/rescore`, sapuan harian `lead_rescore_tick` (05:30 WIB). UI `LeadScoreCard`
  di tab ringkasan lead. Semua pemanggil `compute_lead_score` (stage/disposition/PUT lead) kini
  memakai `lead_scoring.rescore`.
- **88C Potongan bersasaran** aturan harga punya `target` (`price|dp|booking_fee|cost`) +
  `target_component`; reference group `discount_target`. `compute_discounts(bases=…)` menghitung
  persen dari komponen sasaran; DP/booking-fee dikurangkan dari termin uang muka
  (`pricing_engine.apply_component_discounts`, dipakai simulasi & `create_ar_for_deal` — satu
  kebenaran); booking fee deal berkurang; `cost:<KODE>` memotong komponen all-in saat reservasi
  (`apply_cost_discounts`, jejak `discount` di komponen; ditolak bila komponen tidak ada di skema).
  Dokumen: token `{{discount_rows}}` (rincian per aturan + sasaran) di semua naskah SPR; rincian
  kontrak `PROMO_DISCOUNT.meta.items`. Seed promo DEMO: PROMO-DP, PROMO-BF, PROMO-BPHTB. UI:
  PricingRuleDialog (sasaran + komponen), kolom Sasaran di tabel, label di dropdown & breakdown.
- **88D SPR per jenis pembayaran**: naskah bawaan SPR_CASH_STAGED kini berbeda (pasal cicilan),
  nomor `SPR-CASHB` terpisah dari `SPR-CASH`; `ensure_templates` TIDAK lagi menimpa naskah yang
  sudah disunting admin (`updated_by`) — dulu setiap restart mengembalikan suntingan.
- **88E Pelunasan → BAST**: `handover.settlement_policy` (`wajib_lunas` | `minimal_persen` +
  `handover.settlement_min_paid_pct` | `peringatan`) — sisa tagihan menjadi WARNING (BAST terbit
  tanpa terobosan) sesuai kebijakan; terobosan Manajer Keuangan tetap ada.
- Gate `validate_compliance` hijau (engine.py dirapatkan ke 800 baris).
### 3 Sep 2026 — Fase 85–87: Tutup periode kas per rekening, Giro mundur (PDC), Bukti Kas BKM/BKK — SELESAI (iteration_134)
- **Fase 85** `cash_period_lock.py` + `/cash-bank/locks*`: kunci (rekening, bulan) hanya bila rekonsiliasi
  bank akhir bulan `seimbang/dijelaskan` (kas: opname = saldo buku); bulan berjalan tidak bisa dikunci;
  `gl.post_journal` menolak jurnal manual ke sub-akun terkunci & menggeser posting otomatis (memo
  "posting digeser (kunci kas …)"). Buka kunci `bank:approve` beralasan. UI tab **Tutup Periode**.
- **Fase 86** `pdc_engine.py` + `/pdc`: CoA baru `1-1350 Giro/Cek Belum Cair`, `2-1480` kontra.
  Terima = memorandum Dr 1-1350/Cr 2-1480 (AR belum berkurang); kliring = balik + `apply_receipt
  (method=cheque, cash_account_id)` → KWT; tanpa deal → titipan 2-1450; tolakan/batal = balik +
  notifikasi. UI tab **Giro Mundur** (KPI, terima, cairkan, tolak, batal; bank dari SSOT `financing_bank`).
- **Fase 87** `cash_voucher.py` + `/cash-bank/vouchers*`: hook di `post_journal` — tiap baris ke sub-akun
  kas/bank menerbitkan BKM (debit) / BKK (kredit) bernomor, idempoten, backfill startup; PDF ber-kop
  (`doc_layout` kode BKM/BKK). UI tab **Bukti Kas (BKM/BKK)** (filter, cari, cetak).
- Pembenahan baseline kecil: `AccountDialog` field Bank kini `ReferenceSelect financing_bank`
  (temuan `audit_forms_deep` lama).
- Uji: `tests/test_p85_87_cash_control.py` 3/3; testing agent iteration_134 lulus penuh (frontend E2E
  ketiga fase + RBAC). Dokumen `52_KAS_BANK_SPEC.md` §6–9.
- Backlog Kas & Bank berikutnya (§9): P0 sisa = payment run AP massal, biaya tolakan giro, pengingat
  kasir kas kecil; P1 = arus kas per rekening, cash forecast vs posisi kas, limit otorisasi berjenjang,
  jurnal reklas antar sub-akun.

### 3 Sep 2026 — Fase 84: Kas kecil imprest — pengeluaran langsung berbukti + usulan pengisian — SELESAI (iteration_133)
- Lingkungan dipulihkan dari repo `pandeyoga/Sipro030926` di container baru: `backend/.env`
  dibuat ulang (`JWT_SECRET`, `DEFAULT_ORG_ID=org-sipro`, `PORTAL_MASTER_OTP=000000`,
  `BACKUP_DIR`), deps terpasang (requirements minus pin `emergentintegrations/litellm` yang
  konflik — paket sudah ada di env), seed jalan, Fase 83 diverifikasi ulang (p82+p83 8/8,
  `verify_bank_recon.py` PASSED), `memory/test_credentials.md` diisi ulang.
- **Backend** `petty_expense.py` + `routers/petty_expense_router.py` (`/petty-cash/imprest`,
  `/petty-cash/imprest/{id}/replenish`, `/petty-cash/expenses`, `/expenses/{id}/void`; RBAC
  resource `bank`). Pengeluaran langsung kas kecil: Dr beban/WIP (`CASHBON_ACCOUNT`) / Cr
  sub-akun kas, nomor `KK/…` (registry `petty_expense`), bukti wajib, batas satu pengeluaran,
  saldo cukup, void SoD dengan jurnal balik. Imprest per kas (`bank_accounts.imprest_limit`)
  atau bawaan org; status `cukup/perlu_isi/menunggu_isi/melebihi_batas`; usulan pengisian
  = batas − saldo − pending → transfer `isi_kas_kecil` pending (SoD Fase 82).
- Pusat Konfigurasi grup baru **Kas Kecil (Imprest)**: `petty_cash.imprest_limit`,
  `replenish_threshold_pct`, `max_expense`, `require_proof`.
- **UI** Kas & Bank › tab **Kas Kecil** (`PettyExpensePanel`, `ImprestCards`,
  `PettyExpenseDialog`); Master kas: field batas imprest. TestIds `constants/testIds/p84.js`.
- Uji: `backend/tests/test_p84_petty_expense.py` 4/4; testing agent iteration_133 lulus penuh
  (frontend E2E + smoke backend). Dokumen: `docs/v2/52_KAS_BANK_SPEC.md` §5–6.
- Baseline gate yang MASIH merah sejak sebelum sesi ini (bukan dari Fase 84): `engine.py`
  821>800, `verify_api_contract` 9 panggilan FE bertemplate (`${base}/…` RAB, jobdesks,
  booking-fee proofs), `audit_forms_deep` (AccountDialog 'Bank', studioPalette, CreateTaskDialog,
  KprPanel/SpkFromRabDialog). Perlu sesi pembenahan baseline tersendiri.
- Backlog Kas & Bank berikutnya (§6 spec): P0 #3 tutup periode Kas & Bank + kunci setelah
  rekonsiliasi seimbang; P0 #4 giro mundur (PDC); P0 #5 BKK/BKM bernomor & payment run.

### 2 Sep 2026 — Fase 74: Studio — mode warna diingat, palet terkonfigurasi, dua status paralel (penjualan × pembangunan) — SELESAI (iteration_124)
- Mode warna: Pemetaan / Status penjualan / Progres pembangunan / **Gabungan** (isi = tahapan
  customer, garis tebal = bucket progres bangun, teks kedua = %); diingat per browser
  (`localStorage sipro.studio.colorMode`). Legenda dua kelompok pada mode gabungan.
- Palet per organisasi: `GET/PUT /api/site-plan-studio/palette` (validasi #rrggbb, label ≤40),
  dialog "Atur warna" (isi/garis/teks/label per status, reset per kelompok, read-only tanpa
  `projects:update`). Dipakai kanvas, legenda, ekspor PNG. `studioPalette.js` = sumber tunggal.
- `units_light` kini memuat `construction_progress` & `legal_stage`.
- Uji: `tests/test_p74_palette.py` (7, testing agent) + p73/p72 → 15/15; UI iteration_124 lulus.

### 2 Sep 2026 — Fase 73: Studio — edit titik poligon + undo, PDF → latar, warna status + legenda, ekspor PNG — SELESAI (iteration_123)
- Kanvas: kavling terpilih menampilkan titik sudut yang bisa diseret (`StudioCanvas` vtx/editPts →
  `PUT shapes/{sid}` points); flag `manual` dipertahankan saat edit titik.
- Undo (tombol + Ctrl+Z, 30 langkah) untuk titik, tambah bentuk, hapus bentuk (`useStudio.undoStack`).
- Latar PDF: `pdf_to_png` (PyMuPDF, halaman dipilih, di-clamp, sisi ≤3000px) → object storage;
  metadata `background.source/pdf_page/pdf_pages`; input "hal. PDF" di toolbar.
- Mode warna "status unit" (SALES_COLORS + Serah Terima/Lainnya) + legenda berhitung (`StudioLegend`).
- Ekspor PNG 2400px (`exportPng.js`: SVG mandiri dengan latar base64 → canvas → unduh) berjudul nama proyek.
- Uji: `tests/test_p73_studio_pdf.py` (2) + `test_p73_extra.py` (3, testing agent) lulus; UI iteration_123
  lulus; temuan (status handed_over di legenda, clamp halaman PDF, alat Berurutan saat peta kosong) diperbaiki.

### 2 Sep 2026 — Fase 72: Studio Site Plan (killer feature) + kode master opsional + pratinjau penomoran per proyek — SELESAI (iteration_122)
- **Studio Site Plan halaman penuh** `/site-plan/studio/:projectId` (menggantikan popup MappingStudio):
  toolbar (Pilih / Gambar kavling / Berurutan, unggah SVG, gambar latar PNG/JPG + opasitas,
  cocokkan otomatis, peta contoh / hapus peta), kanvas zoom-pan (`StudioCanvas`), sidebar tab
  Bentuk / Unit belum punya bentuk / Buat unit.
- **Parser SVG kaya** `site_plan_parse.py`: `<g transform>` bersarang, `<path d>` → poligon,
  `<text>` di dalam bentuk = label kavling, deteksi kavling berbasis luas, batas lahan otomatis.
  `parse_code` membaca "A-01", "B12", "Q9 3", "A1-05" → (blok, no).
- **Backend** `site_plan_studio.py` + `routers/site_plan_studio_router.py` (`/api/site-plan-studio/*`):
  studio payload, svg, background (object storage, PIL dims), shapes CRUD (tracing manual),
  auto-match toleran (tanda pisah/nol depan), suggest-units, **create-units** (per baris; blok baru
  hanya bila `create_blocks`; kode yang sudah ada → dipetakan, bukan digandakan).
- Form master (proyek, cluster, blok, tipe unit, vendor, subkon) boleh kosongkan kode → hint
  "otomatis dari aturan penomoran bila kosong". Panel Penomoran: pemilih proyek → pratinjau &
  urut berikutnya dari counter proyek itu (`preview_in_context`).
- Uji: `tests/test_p72_studio.py` (4) + `test_p72_ui_backend.py` (5, testing agent) + p71 (6) lulus;
  UI iteration_122 lulus (1 bug validasi kode proyek diperbaiki setelahnya).

### 2 Sep 2026 — Fase 71: Penomoran terkonfigurasi (pola + token) + kode master otomatis — SELESAI (iteration_121)
- Repo di-clone ulang dari `akskdidj/sipro`; `backend/.env` dipulihkan (JWT_SECRET, DEFAULT_ORG_ID,
  PORTAL_MASTER_OTP, BACKUP_DIR), deps terpasang, `memory/test_credentials.md` diisi ulang.
- Pekerjaan yang terhenti (konteks `project_id`/`category` pada `seq.next_number` di labor_engine,
  petty_cash, fixed_assets) dilengkapi; konteks ditambah juga di marketing_fee (partner_engine),
  booking_fee_refund, warranty_claim.
- **Router baru** `routers/numbering_router.py` (`/api/numbering`): daftar 41 aturan (`numbering_registry`),
  katalog token per aturan, pratinjau dari rancangan (counter tidak naik), simpan/reset per organisasi.
  RBAC: baca `settings:view`, ubah `settings:update`. Token asing → 400.
- **Kode master otomatis** bila kolom kode dikosongkan: proyek (PRJ-01), cluster (C01 per proyek),
  blok (A,B,… per cluster), unit (`{BLOCK_CODE}-{NO:2}`), tipe unit (T01), add-on (ADD-001),
  vendor (VND-001), subkon (SUB-001), material (MAT-001 per proyek). Registry punya `parent` =
  kunci konteks induk yang selalu memisahkan counter (temuan iteration_121 diperbaiki).
- **UI**: /config → tab "Penomoran" (`NumberingPanel`, `NumberingRuleDialog`): tabel per kelompok,
  filter & cari, dialog dengan token chip, pratinjau hidup, kembalikan bawaan, badge "disesuaikan".
- Uji: `backend/tests/test_p71_numbering.py` (6) + `test_p71_numbering_ext.py`, `test_p71_scope_probe.py`
  dari testing agent → 19/19 lulus; frontend 100%.
- Catatan: kolom "Contoh nomor berikutnya" memakai counter dasar org (bukan per proyek/vendor) —
  ditandai di UI. Baseline belum dibenahi (bukan sesi ini): engine.py 818>800; audit form
  PaymentSchemePanel.js:305.

### 2 Sep 2026 — Fase 70: Manajemen Data (migrasi Excel + backup/restore) — SELESAI (iteration_120)
- **Permintaan**: migrasi master data via Excel agar sistem bisa diisi data nyata klien; menu
  Manajemen Data untuk backup, restore, migrate; template siap diberikan ke klien.
- Menu **Admin → Manajemen Data** (`/admin/data-management`, khusus `super_admin`/`owner`,
  API `/api/data-mgmt/*`). Tiga tab: Migrasi Excel, Backup & Snapshot, Restore dari Berkas.
- **Template Excel** (`GET /data-mgmt/template.xlsx`): sheet PETUNJUK + DAFTAR NILAI (enum SSOT
  dari `reference.py`) + 15 sheet master berurutan dependensi: Pengguna, Proyek, Cluster, Blok,
  Tipe Unit, Unit, Add-on, Pelanggan, Vendor, Subkontraktor, Mitra, Material, Tenaga Kerja,
  Bagan Akun, Rekening Bank. Baris 1 = kunci teknis, baris 2 = label/aturan, baris 3 = contoh;
  dropdown validasi untuk kolom enum/bool. Skema tunggal di `data_mgmt_schema.py`.
- **Impor** (`POST /data-mgmt/import` multipart `file, mode=upsert|skip, dry_run`): pratinjau
  = validasi penuh tanpa menulis (tipe, wajib, enum, rujukan kode proyek/cluster/blok/tipe,
  duplikat dalam berkas), laporan per sheet/baris (insert/update/skip/error + peringatan). Rujukan
  antar-sheet dalam berkas yang sama terselesaikan. Unit memakai `masterplan._new_unit_doc` +
  `recompute_stats`; mitra baru diberi kode `AGN/…` dari `sequences`. Sandi pengguna baru kosong →
  `Sipro#2026` (peringatan).
- **Ekspor master** (`GET /data-mgmt/export.xlsx`) = backup Excel yang bisa diimpor ulang (0 error).
- **Backup JSON** per organisasi (`GET /data-mgmt/backup.json?include_files=`), **snapshot server**
  (`POST/GET/DELETE /data-mgmt/snapshots`, berkas di `BACKUP_DIR/<org>/`, metadata `data_backups`),
  **restore** (`POST /data-mgmt/restore`, `POST /snapshots/{id}/restore`; mode `replace`/`merge`,
  wajib `confirm=RESTORE`; snapshot "pra-restore" otomatis; akun admin pelaku tidak hilang;
  merge memakai kunci `_id`→`id`→indeks unik koleksi). `POST /restore/inspect` membaca meta.
- Env baru: `BACKUP_DIR`. Dependensi: `openpyxl`. Uji: `backend/tests/test_datamgmt_fase56.py` (11 lulus).
- Belum: migrasi data TRANSAKSI (deal/kontrak/AR lama) — unit terjual hanya ditandai status.


### 2 Sep 2026 (69C) — aturan booking fee ditegakkan, bukti bayar portal, refund, pengingat WA
- **Ditegakkan**: `booking_fee.require_paid_before_booking` bawaan TRUE (aktif untuk org-sipro);
  `POST /deals/{id}/book` → 400 sampai INV-BF lunas; tombol Konfirmasi Booking di Lead 360
  dinonaktifkan + tooltip. 7 gate lama (`_fixture47`, `verify_29b/30…`) kini membayar booking
  fee via `/booking-fee/deals/{id}/pay` sebelum book.
- **Bukti bayar pembeli (portal)**: `_find_portal_user` juga memprovisikan dari LEAD pemegang
  reservasi (booking fee dibayar sebelum jadi pelanggan); `/portal/payments` membawa
  `booking_fee` (tagihan, kwitansi, bukti, refund); `POST /portal/booking-fee/proof`
  (router terpisah `portal_booking_fee_router.py`) menyimpan klaim ke `payment_intakes`
  (`kind=booking_fee`). Keuangan verifikasi SATU KLIK `POST /booking-fee/deals/{id}/proofs/{iid}/verify`
  (→ `pay` → kwitansi + LUNAS) atau tolak beralasan. UI: `PortalBookingFeeCard`,
  `BookingFeeProofs`.
- **Refund**: `booking_fee.refund` untuk deal cancelled/expired dengan fee terbayar — kas keluar
  via `_deposit_move("refund")` (jurnal), sisa yang tidak dikembalikan dicatat HANGUS
  (2-1450 → 4-1200) bila `finalize`; bukti pengembalian bernomor RF-BF (`receipts.kind=
  booking_fee_refund`) + PDF `/refunds/{rid}/pdf`. Status tagihan → refunded/forfeited;
  `deals.booking_fee_status` ikut. UI `BookingFeeRefund` (dibayar/dikembalikan/hangus, dialog,
  cetak).
- **Pengingat WA**: jenis baru `booking_fee_due` di `wa_reminder_engine` (referensi
  `reminder_kind`), H-`booking_fee.reminder_days_before` (bawaan 1) sebelum `due_date`;
  penerima = lead (WA, simulasi tanpa kredensial) + tembusan sales pemilik deal (in-app
  `notifications`, WA bila nomor ada). Kedaluwarsa DIKONFIGURASI: `booking_fee.due_days`
  (bawaan 3, tidak melewati masa keep), `reservation.hold_days` kini benar-benar dipakai
  `sales_reserve` (dulu env `BOOKING_HOLD_DAYS` saja), template `booking_fee.reminder_template`.
  Sweeper reservasi kedaluwarsa menutup tagihan yang belum dibayar.
- Testing agent iteration_119: backend 8/8, frontend 100%; gate verify_29b (58/58),
  verify_payment_schemes, verify_rbac hijau. Baseline belum dibenahi: `engine.py` 818>800.

### 2 Sep 2026 (69B) — booking fee sebagai komponen pembayaran + KPR disembunyikan untuk tunai
- **Booking fee = komponen pembayaran terpisah** (`booking_fee.py`, `routers/booking_fee_router.py`
  prefix `/api/booking-fee`): reservasi dengan booking fee > 0 melahirkan TAGIHAN
  `booking_fee_invoices` (INV-BF/…, status unpaid/partial/paid/cancelled, jatuh tempo = batas
  hold). Pembayaran (`POST /booking-fee/deals/{id}/pay`, `finance:create`) → KWITANSI bernomor
  (`receipts.kind=booking_fee`) + TITIPAN pelanggan berjurnal 2-1450 lewat `_deposit_move`
  (dialihkan ke termin saat booking, mekanisme lama). `deals.booking_fee_status`
  unverified→recorded→verified; deal batal menutup tagihan yang belum dibayar. PDF tagihan
  (`/invoice/pdf`, layout FAKTUR) & PDF kwitansi (`/finance/ar/receipts/{id}/pdf`).
  Setting baru `booking_fee.require_paid_before_booking` (bawaan MATI; bila nyala, Konfirmasi
  Booking ditahan sampai lunas — dibiarkan mati agar gate lama tidak berubah).
- UI: `BookingFeePanel` (status lunas/belum, sisa, tombol PDF, dialog "Catat pembayaran" untuk
  Keuangan) tampil di Lead 360 tab Unit & SPR (deal reserved) dan di atas `DealPricingSheet`;
  kolom Booking fee di daftar deal & Lead 360 menampilkan Lunas/Sebagian/Belum dibayar.
- `DealPricingSheet` menyembunyikan blok KPR bila `pricing.scheme.type` diawali `cash`
  (`QuotationBreakdown hideKpr`) dan menulis catatan "skema tunai". Perbaikan: snapshot
  `scheme.type` kini dibaca dari `payment_schemes.kind` (sebelumnya selalu null).
- Testing agent iteration_118: backend 8/8, frontend 100%.

### 2 Sep 2026 (lanjutan) — rincian harga deal, aturan multi-proyek, BI potongan (PRC-01..04)
- **Rincian harga deal** (`DealPricingSheet` + `DealPricingButton`, testid `deal-pricing-*`):
  sheet menampilkan `deals.pricing` yang TERSIMPAN (harga dasar, add-on, baris potongan
  skema/promo/kupon, termin, KPR) + asal (penawaran/reservasi langsung). Tombol "Rincian
  harga" ada di daftar deal (`DealsListTab`, tidak memicu navigasi baris), Lead 360 tab
  "Unit & SPR", dan Unit 360 tab penjualan (kolom "Potongan" baru). Deal lama tanpa
  `pricing` → pesan jujur `deal-pricing-empty`. `pricing_snapshot` kini ikut menyimpan
  `discount_limit_pct` (hint breakdown tidak lagi "undefined%"; deal lama di-backfill).
- **Aturan multi-proyek/tipe**: `MultiCheckList` (checkbox, kosong = semua) menggantikan
  select tunggal di `PricingRuleDialog` untuk `applies_project_ids` & `applies_unit_types`;
  kolom "Berlaku untuk" di tabel menampilkan NAMA proyek + tipe.
- **BI**: modul metrik baru `metrics/pricing.py` — PRC-01 potongan per proyek (deret bulanan),
  PRC-02 per sales, PRC-03 komposisi per sumber (pie), PRC-04 pemakaian kupon; dipasang di
  dashboard Eksekutif (PRC-01) & Penjualan (PRC-01..04). Sumber: `deals.pricing.discount_lines`
  & `coupon_redemptions` (deal tanpa rincian dilaporkan sebagai cakupan sebagian).
- Gate `verify_analytics.py` kembali HIJAU: 2 temuan bawaan `MetricDetailDialog.js` (label
  "Jumlah" = kosakata `metric_unit`, `value ?? 0`) dibenahi; key duplikat SLS-11 (unit code
  ganda) diganti id deal. Testing agent iteration_117: backend 11/11, frontend 100%.

### 2 Sep 2026 — Fase 69: mesin harga (skema diskon, promo, kupon) + reservasi ber-breakdown

- Repo di-clone ulang dari `pandeyoga/sipro` ke container baru: `backend/.env` dipulihkan
  (JWT_SECRET, DEFAULT_ORG_ID=org-sipro, PORTAL_MASTER_OTP=000000), deps terpasang, seed jalan,
  `memory/test_credentials.md` diisi ulang.
- **Reservasi = penawaran**: `ReserveDialog` kini memakai `PricingFields` (komponen bersama
  dengan `QuotationForm`): skema bayar, add-on master, skema diskon, promo, kupon, KPR opsional,
  tombol "Hitung rincian harga" → `QuotationBreakdown`. `POST /deals/reserve` menerima
  `addons/scheme_id/discount_scheme_id/promo_id/coupon_code/kpr`, menghitung lewat
  `quotation_engine.simulate` (satu mesin) dan menyimpan `deals.pricing` (snapshot rincian),
  `price` netto, `discount`, `addons`. Potongan yang butuh persetujuan → 400 (arahkan ke penawaran).
- **Diskon tidak bisa diketik**: `discount_amount > 0` DITOLAK di simulate/create. Potongan hanya
  dari aturan: `pricing_engine.compute_discounts` (skema diskon + promo + kupon; cap per aturan,
  total ≤ harga; `requires_approval` pada skema → penawaran menunggu manajer; aturan lama
  `quotation.discount_max_pct_sales` tetap berlaku atas TOTAL potongan).
- **Master baru** (`pricing_engine.py`, `routers/pricing_router.py`, prefix `/api/pricing`,
  RBAC resource `pricing`: sales view; sales_manager/marketing_admin/finance_manager kelola):
  `discount_schemes`, `promos` (`stackable`), `coupons` (periode, `quota_total`,
  `quota_per_customer`, `used_count`), `coupon_redemptions` (used/released; dilepas otomatis
  saat deal dibatalkan; redeem atomik via `find_one_and_update`). Endpoint
  `/pricing/options?unit_id=`, `/pricing/coupons/validate`, `/pricing/coupons/{id}/redemptions`.
  Setting baru `pricing.allow_stack_promo_coupon` (bool). Referensi `reference_p69.py`
  (`discount_kind`, `pricing_rule_kind`, `coupon_redemption_state`). Seed DEMO: DISC-CASH 2%,
  DISC-MGR 5% (perlu persetujuan), PROMO-LAUNCH Rp2jt, kupon SIPRO2026 Rp5jt kuota 50/1×.
- **UI konfigurasi**: /config → tab "Harga & Promo" (`PricingPanel` → `PricingRuleTable`,
  `PricingRuleDialog`, `CouponRedemptionsDialog`). Penawaran menampilkan baris potongan per
  sumber (`discount_lines`) di breakdown & PDF; baris deal di Lead 360 menampilkan potongan.
- Gate `verify_quotation_labor.py` diperbarui (Q3 memakai skema diskon, uji "diskon manual ditolak").
  Testing agent iteration_116: backend 27/27, frontend 100%. Test regresi baru
  `backend/tests/test_p69_pricing.py`.
- Baseline repo yang belum dibenahi (bukan sesi ini): engine.py 817>800 baris; E5 CreateTaskDialog.

### 31 Agu 2026 (lanjutan) — pemulihan repo + lonceng ringkasan, izin klik-able & jenis izin konfigurable, tautan skema komisi
- Repo di-clone ulang ke container baru: `backend/.env` dipulihkan (JWT_SECRET, PORTAL_MASTER_OTP,
  DEFAULT_ORG_ID), deps terpasang, seed otomatis jalan; `memory/test_credentials.md` diisi ulang.
- **Lonceng TopBar** kini dropdown ringkasan (`BellSummary.js`): jumlah belum dibaca + perlu
  tindakan, chip per kategori berwarna (CATEGORY_TONE), 6 notifikasi terbaru (klik → link
  notifikasinya), tombol "Buka halaman notifikasi" → /notifications.
- **Perizinan pada Unit/Proyek**: baris `PermitCoveragePanel` bisa DIKLIK → `PermitDetailDialog`
  (info lengkap + riwayat perpanjangan + aksi ubah status/perpanjang + link /permits);
  tombol Perpanjang lama tetap (stopPropagation).
- **Jenis izin konfigurable**: grup `permit_type` jadi non-strict + dynamic (nilai terpakai di DB
  tetap muncul), setting baru `permit.types_custom` (list, grup konstruksi) di-merge ke
  /api/reference (`_org_values` di reference_router); UI `PermitTypesDialog` (tombol "Jenis izin",
  gated settings:manage) untuk tambah/hapus jenis organisasi.
- **Komisi**: skema komisi memang sudah konfigurable di Keuangan → Konfigurasi; kartu "Komisi Saya"
  kini punya tautan "Atur skema" (gated finance:update) → /finance?tab=config.
- Checklist mutu pembangunan DIKONFIRMASI sudah konfigurable via Pembangunan → tab Template
  (BuildTemplateEditor: tambah/hapus poin, tandai kritis) — tidak perlu perubahan kode.
- Testing agent iteration_115: backend 5/5 pytest, frontend 100%, data uji dibersihkan.
- Penutup sesi lama yang terhenti: label "Fase 50/51C" DIHAPUS TUNTAS — 5 string tersisa di
  `seed_phase50.py` (notes deal, note kwitansi pelunasan, note BAST, 2 deskripsi klaim garansi)
  diganti "Data DEMO", dan seluruh baris DB yang sudah terlanjur ter-seed dibersihkan
  (deals/receipts/unit_handovers/warranty_claims/punch_items/tasks) — sisa label = 0.
- **Checklist survey konfigurable**: setting baru `survey.checklist_items` (list, grup
  Lead & Lifecycle, bawaan = 7 poin standar) diedit dari Pusat Konfigurasi (/config);
  `survey_router.create_survey` membangun checklist dari setting (`_default_checklist`,
  key di-slug dari label). Survey berjalan memakai salinan saat dibuat. Diverifikasi curl:
  setting kustom → survey baru memuat poin kustom → reset ke bawaan.
- Catatan gate bawaan repo (bukan sesi ini): engine.py 817>800 baris; E5 CreateTaskDialog.

### 31 Agu 2026 (lanjutan) — combobox kaitan + tombol Buat tugas di halaman record + RBAC hide menu
- `RelatedRecordCombobox.js` (Popover+cmdk): record kaitan di dialog Tugas Baru bisa DICARI;
  filter hanya pada label (value `label||id`, uuid tidak mencemari pencarian); limit endpoint
  dinaikkan (leads 300, units 500, customers 300, deals 200, projects 100).
- `CreateTaskDialog.js`: cache record dibuang tiap dialog dibuka (data baru muncul tanpa
  reload) + refetch jenis tersisa saat reopen; prop `preset {type,id,label}` + `triggerLabel`.
- Tombol "Buat tugas" (gated `can('work_tasks','create')`) di `/units/:id`, `/customers/:id`,
  `/projects/:id` — kaitan otomatis terisi.
- RBAC: sidebar kini disaring izin EFEKTIF — item nav diberi `resource`, `buildNavGroups(role,
  can)`; pencabutan izin di /admin/permissions benar-benar menyembunyikan menunya (perlu login
  ulang). AdminPermissions: tombol baru "Kembalikan ke bawaan" (batalkan pencabutan TERSIMPAN;
  backend GET /admin/permissions kirim `defaults`), "Batalkan suntingan" untuk undo belum
  tersimpan; label checkbox editor tidak terpotong.
- Testing agent iteration_112 (2 bug HIGH ditemukan → diperbaiki) + iteration_113 (100% pass).
- Catatan: gate `validate_compliance` gagal BAWAAN repo (`engine.py` 817 > 800 baris) — bukan
  dari perubahan sesi ini.

### 31 Agu 2026 — pemulihan repo + penutup fitur "Kaitan Selain Lead" (temuan iteration_111)
- Repo di-clone ulang ke container baru: `backend/.env` dipulihkan (`JWT_SECRET`,
  `PORTAL_MASTER_OTP`, `DEFAULT_ORG_ID`), `REACT_APP_BACKEND_URL` disetel ke preview pod ini,
  deps terpasang, seed idempoten jalan saat startup.
- `GET /api/work/tasks/{id}` kini mengembalikan blok `related` (type/label/name/link) untuk
  kelima jenis kaitan — `_related_info()` di `routers/workhub_router.py`.
- `TaskDetailSheet.js`: baris "Kaitan" (`data-testid="task-related-entity"`) + tombol
  "Buka halaman kerja" memakai `t.link || related.link` (lead→/leads/:id, unit→/units/:id,
  customer→/customers/:id, project→/projects/:id, deal→/deals); artefak "- ·" di header
  sheet dihilangkan (segmen kosong disembunyikan, fallback "Detail tugas").
- Verifikasi: curl E2E (related terisi, fake customer id → 404) + screenshot UI detail sheet.

### 29 Agu 2026 (lanjutan) — filter proyek & tanggal kustom BI + kartu lebih besar/interaktif
- Filter bar lintas tab di `/bi`: rentang cepat + filter **Proyek** (select) dan **Tanggal
  kustom** (daterange, menang atas rentang cepat sesuai `resolve_range` server) memakai pola
  `FilterBar` (`bi-filter-bar`). Filter proyek hanya dikirim ke Eksekutif/Penjualan/Proyek;
  saat aktif, hint `bi-project-hint` menjelaskan Marketing & Tim tidak per-proyek.
- Grid kartu 4 kolom → maks 3 (`md:grid-cols-2 xl:grid-cols-3`, md agar tidak sempit di
  tablet); sparkline lebih tinggi (h-16) dan interaktif (hover = periode+nilai), bilah persen
  berlabel "% tercapai", bilah kategori top-4 + hint "+n kategori lain".
- Diverifikasi testing agent (iteration_106): 100% skenario lulus, 0 error konsol.

### 29 Agu 2026 — visualisasi mini di kartu BI + desain grafik lanjutan
- Kartu metrik `/bi` kini memuat visualisasi mini (`MetricSpark.js`): sparkline area
  bergradien untuk deret waktu (pakai `cumulative` bila ada, domain diberi napas agar deret
  datar tidak jadi balok), bilah progres gradien untuk metrik persen, bilah proporsi top-3
  untuk rincian kategori; plus badge tren naik/turun vs periode sebelumnya
  (`bi-metric-spark`, `bi-metric-trend`). Aturan kejujuran tetap: metrik `kosong` tidak digambar.
- `MetricChart.js` didesain ulang: warna token tema `--chart-1..5` (mode gelap ikut benar),
  fill gradien, tooltip kaca buram kustom (`ChartTip`), donat dengan total di tengah,
  opasitas bar mengikuti nilainya, sumbu tanpa garis. Angka besar diringkas via
  `formatCompact` ("2,3 M", "212,5 jt") di sumbu & bilah mini.
- Kartu diberi hover lift + garis aksen gradien. Diverifikasi testing agent (5 hub, 0 error
  konsol) + 3 temuan visual (angka terpotong, sumbu Y terpotong, sparkline balok) diperbaiki.

### 28 Agu 2026 (lanjutan) — sidebar bisa di-collapse/expand
- Tombol ciut/perlebar di kepala sidebar (`sidebar-collapse-toggle`, ikon PanelLeft):
  mode ciut = 64px ikon-saja dengan `title` tooltip per menu, grup dipisah garis tipis;
  mode lebar = 256px seperti semula. Pilihan tersimpan di
  `localStorage["sipro.sidebar.collapsed"]` dan bertahan antar sesi.
- Drawer mobile tetap selalu tampil penuh. Diverifikasi browser: collapse 64px →
  reload tetap ciut → expand 256px; 0 error konsol.

### 28 Agu 2026 (lanjutan) — warna ikon kategori di pusat notifikasi
- `CATEGORY_TONE` (kelas LITERAL, bukan dirakit dinamis — pelajaran regresi pill) di
  `NotificationRows.js`: tugas amber, keuangan emerald, penjualan sky, proyek oranye,
  layanan violet, sebutan pink, sistem slate. Baris yang sudah dibaca memudar (opacity),
  bukan kehilangan warnanya.
- Dipakai di 3 tempat: lingkaran ikon baris notifikasi, chip filter kategori
  (NotificationsPage), dan baris dialog Preferensi. Diverifikasi visual: computed bg
  per kategori benar, tanpa error konsol.

### 28 Agu 2026 (perbaikan) — regresi Fase 67: warna status pill hilang (flat abu)
- Akar masalah: blok `.status-*` di `index.css` dipindah ke dalam `@layer components`,
  padahal kelasnya dirakit DINAMIS oleh `StatusPill` (`status-${tone}`) — isi @layer
  di-tree-shake Tailwind berdasarkan kelas literal di sumber, jadi SEMUA warna status
  terbuang saat build dan pill tampil putih/abu seragam.
- Perbaikan: blok `.status-pill` + seluruh `.status-*` dikeluarkan dari `@layer` (CSS polos
  selalu terkompilasi) + komentar penjaga agar tidak dipindah kembali. ATURAN: kelas yang
  dirakit dinamis TIDAK boleh berada di dalam `@layer`.
- Verifikasi: iterasi 104 (frontend 100%) — /leads, AR, kas bon, subcon, tasks, agenda
  semuanya berwarna semantik lagi; dot ::before tetap; 0 error console; gaya Fase 67 utuh.

### 28 Agu 2026 (lanjutan) — Fase 68: denda terjadwal + pengingat tunggakan pra-SP (gate 59)
- **Denda otomatis terjadwal** (`late_fee_auto.py` + `scheduler_p68.py`, cron 09:30 WIB):
  opsi per organisasi `payment.late.auto_apply` (bawaan MATI — keputusan bisnis) + dua rem
  `payment.late.auto_min_days` & `payment.late.auto_min_amount`. Tidak ada mesin kedua:
  yang menagihkan tetap `late_fee_engine.apply` (berjurnal, idempoten per termin/bulan).
  Panel di Keuangan → Penagihan: status, aturan, pratinjau (siap vs ditahan + sebab),
  riwayat putaran, "Jalankan sekarang" (`late_fee:create`).
  Endpoint: `GET/POST /api/finance/late-fee-auto[/run]`.
- **Pengingat tunggakan pra-SP** (`wa_reminder_engine` jenis baru `arrears_warning`):
  pesan WA disiapkan otomatis begitu tunggakan MELEWATI TOLERANSI kontrak (hitungan bulan
  = mesin SP/arrears yang sama), menyebut keadaan SP ("SEBELUM SP1"). Nominal & aturan
  bisa disetel: `reminder.arrears_enabled/min_amount/min_months/every_days/template_arrears`.
  Tiap kandidat membawa tautan `wa.me` siap kirim (tombol "Kirim manual" di panel
  pengingat); kirim otomatis tetap jujur `simulasi` tanpa kredensial WhatsApp.
- **Bug laten ditutup:** `scheduler_p59` diimpor tetapi tidak pernah `register()` —
  tugas peninjauan tunggakan harian tidak pernah terjadwal. Kini terdaftar.
- Gate baru `scripts/verify_p68.py` (gate 59, 39 pemeriksaan) HIJAU.

### 28 Agu 2026 — Fase 67: kedalaman & konsistensi tampilan / anti-flat (gate 58) + pemulihan lingkungan
- Lingkungan dipulihkan dari repo `akahdbeben/sipro` di container baru: `backend/.env`
  dibuat ulang (`JWT_SECRET`, `DEFAULT_ORG_ID=org-sipro`, `PORTAL_MASTER_OTP=000000` —
  gate memakai OTP master `000000`), dependensi backend+frontend dipasang, seed jalan,
  login OK, `run_all_gates.sh` → **OVERALL PASS (58 gates)**.
- **Fase 67 dirampungkan** (kode sudah ada saat sesi terputus, sisanya ditutup sekarang):
  token kedalaman di `index.css` (kanvas vs kartu, bayangan token, aksen teal + hover),
  primitif ui (button/input/select/card/tabs/table) membawa kedalaman & fokus 2px,
  `page-title`/`page-desc`/`section-title` menyeragamkan tulisan antar halaman,
  `SearchInput` ber-ikon, status pill bertitik warna, KPI bergaris aksen.
- **Temuan uji iterasi 102 ditutup**: kolom AKSI kini STICKY kanan saat tabel digulir
  mendatar — `.col-actions`/`.col-actions-head` di ~20 tabel + dukungan `sticky: true`
  pada kolom `DataTable` (AR, Deals, Dokumen, Agenda, Mitra, Bank Rekonsiliasi, Config,
  CAPI); header sticky dilengkapi di FakturPanel/VendorsPanel/CancellationsPanel/
  ArrearsCandidatesPanel; diverifikasi visual di 1366px (tombol Detail/Pertanggungjawaban
  terlihat tanpa menggulir). Empty-state pencarian notifikasi, testId SearchInput, dan
  skip-link/a11y sudah dikerjakan sebelumnya.
- Gate `scripts/verify_p67.py` (gate 58, 32 pemeriksaan) HIJAU.

### 27 Jun 2026 (lanjutan) — Fase 66: Template Dokumen disatukan (gate 57)
- **Satu layar per jenis dokumen**: dua sub-tab lama ("Isi template" vs "Tampilan & kop
  surat") dihapus; naskah, kop/kertas, baris biaya, GAYA TABEL, dan tanda tangan disetel
  berdampingan dengan pratinjau yang memakai naskah yang sedang disunting.
- **Naskah per jenis dokumen** (`backend/doc_script.py`, `GET/PUT /api/doc-layouts/{code}/script`):
  placeholder diturunkan dari konteks mesin penerbit sungguhan, token asing ditolak 400 +
  diperingatkan saat mengetik. Naskah tersimpan di `document_templates` sehingga benar-benar
  tercetak; dokumen yang dirakit sistem (SPK/PO/SP/BA) memakainya sebagai pembuka.
- **Gaya tabel bisa dikonfigurasi**: `layout.table` (garis penuh/mendatar/TRANSPARAN, nama
  kolom bisa disembunyikan, zebra, sorot total, ukuran huruf, warna garis) berlaku pada semua
  tabel dokumen. Naskah resmi butuh izin `settings:update`.
- Gate baru `scripts/verify_p66.py` (57 gate, 53 pemeriksaan — memeriksa ISI PDF) +
  `backend/tests/test_doc_p66.py` (17 uji).

### 27 Jun 2026 (lanjutan) — Fase 65: notifikasi kembar berkelompok & preferensi (gate 56)
- **Pengelompokan kembar**: `notif_center.group_key()` (jenis + entitas + judul yang
  dinormalkan — nomor dokumen/kode jadi `#`) + `group_rows()`; `GET /api/notifications?group=true`
  mengirim wakil terbaru + `group_count/group_unread/group_ids/group_members/group_oldest_at`.
  Aksi kelompok: `POST /api/notifications/group/read|dismiss` (dari kunci, bukan daftar id).
- **Preferensi per pemakai** (`notif_prefs.py`, koleksi `notification_prefs`): tiga saluran
  `inapp`/`push`/`wa` per kategori. Ditegakkan di SATU pintu (`engine.create_notification`)
  sehingga ~30 pemanggil lama ikut patuh. Notifikasi yang MENUNTUT TINDAKAN tidak bisa
  dibungkam dari daftar; yang dibungkam ditandai `muted_at` + `muted_reason` (tidak dihapus).
- **Ringkasan WhatsApp manual** (`GET /api/notifications/wa-digest`): teks + tautan `wa.me`,
  dikirim manusia (tidak ada kredensial WhatsApp yang diklaim sistem).
- UI: baris kelompok berjumlah "5×" yang bisa dibuka + `NotificationPrefsDialog`; pilihan
  pengelompokan hidup di URL. Gate baru `scripts/verify_p65.py` (56 gate, 59 pemeriksaan) +
  `backend/tests/test_notif_p65.py` (12 uji).

### 27 Jun 2026 — Fase 61: cetak SPK & PO (SELESAI, gate 52 hijau)
- `backend/docgen_p61.py`: isi SPK (identitas pihak, nilai kontrak, retensi, masa
  pemeliharaan, rincian lingkup dari `spk_scope_items`, 5 ketentuan) & PO (penyedia, jenis,
  jatuh tempo, rincian item + total, 4 ketentuan). Dokumen berstatus `draft` DIPAKSA
  bertanda watermark DRAFT. Nama pihak kedua = subkontraktor/vendor (bukan "Pemesan").
- `pdf_layout.render_letter(..., item_table=...)` + helper `_grid` (dipakai bersama laporan).
- Endpoint: `GET /api/subcon/spk/{id}/pdf`, `GET /api/procurement/pos/{id}/pdf`.
- UI: `patterns/PrintDocButton.js` dipakai di `SPKDetailSheet` & `PODetailSheet`
  (testId `spk-print-pdf`, `po-print-pdf`).
- Target layout baru di Pusat Konfigurasi Dokumen: `SPK`, `PO`.
- Gate baru `scripts/verify_p61.py` (24 pemeriksaan). Uji UI: iteration_97 (bersih).
- PDF diperiksa visual (render PNG): kop, rincian, ketentuan, dua kolom tanda tangan OK.

### 27 Jun 2026 (lanjutan) — Fase 64: pusat notifikasi yang bisa habis (SELESAI, gate 55)
- Keluhan pemakai: kartu notifikasi besar, daftar memanjang tanpa akhir, tanpa kategori,
  tanpa jalan ke pekerjaannya, dan notifikasi tetap berdiri walau tindakannya sudah selesai.
- **Baris padat** (`components/notifications/NotificationRows.js`): satu notifikasi = satu
  baris (~52px) dengan ikon kategori, judul, isi terpangkas, waktu, tombol buka/tandai/
  sembunyikan; penanda **PERLU TINDAKAN** dan **sudah ditangani**.
- **Kategori & keadaan** (`backend/notif_center.py`): kategori (tugas, keuangan, penjualan,
  proyek, layanan, sebutan, sistem) & penanda `needs_action` **diturunkan dari data yang
  sudah ada** (`type` + `related_entity_type`) sehingga ~300 notifikasi lama ikut
  berkategori tanpa migrasi. Tab keadaan: Perlu tindakan · Belum dibaca · Sudah dilihat ·
  Semua (label dari SSOT `reference_p64.notification_state`).
- **Navigasi**: `link_of()` — SATU peta entitas/jenis → rute; notifikasi tugas selalu ke
  papan tugas (`TYPE_LINK_WINS`).
- **Auto-cabut**: `resolve_done()` mencabut notifikasi yang tindakannya sudah dilakukan
  (tugas ditutup, kas bon/PO/termin/klaim diputus, tagihan dibayar, temuan selesai, fee
  diputus, entitas hilang) — ditandai `resolved_at` + alasan, TIDAK dihapus.
- **Endpoint**: `GET /api/notifications?state=&category=&q=` (kirim `summary` + `auto_resolved`),
  `POST /notifications/{id}/dismiss`, `POST /notifications/clear-read`,
  `POST /notifications/read-all?category=`; kontrak lama `unread_only` (lonceng TopBar) utuh.
- Gate baru `scripts/verify_p64.py` (45 pemeriksaan) → **OVERALL PASS (55 gates)**. Uji:
  iteration_100 (12/12 pytest + UI 1440×900 & 390×844, 0 isu) — berkas uji
  `backend/tests/test_notif_p64.py` men-snapshot & memulihkan data.

### 27 Jun 2026 (lanjutan) — Fase 63: agenda kerja lengkap (SELESAI, gate 54 hijau)
- Halaman **Agenda & Survey** dulu hanya kalender + daftar SATU hari (dua pertiga layar kosong,
  agenda minggu depan hanya bisa ditemukan dengan menebak tanggal). Sekarang: kalender +
  agenda hari terpilih + **TABEL agenda** (`AgendaTable.js`, pola DataTable+FilterBar) dengan
  cari, filter (rentang 7/30 hari & riwayat, golongan, jenis, status), urut & paginasi
  **server-side**, ekspor CSV, dan seluruh filter hidup di URL (`useListQuery`).
- **Buat/ubah agenda dari halaman ini** (`AgendaFormDialog.js`): golongan `sales` (wajib
  menyebut lead, dicari bukan digulir) vs `internal` (TANPA lead) + peserta dipilih dari
  `GET /api/appointments/staff`.
- Jenis agenda non-penjualan masuk SSOT (`reference_p63.py`): rapat internal, kunjungan
  proyek, rapat vendor/subkontraktor, lain-lain + grup `agenda_kind`.
- Backend (`routers/leads_router.py`): `GET /api/appointments` menerima
  `q/status/type/kind/assigned_to/date_from/date_to/sort/direction`; `POST` menerima
  `lead_id` OPSIONAL (agenda internal tidak menaikkan tahap lead & tidak menerbitkan tugas
  survei); `PUT /api/appointments/{id}` (agenda `done`/`cancelled` **tidak bisa diubah**);
  peserta wajib pengguna nyata; `_appt_scope()` membuat staf yang **diundang** melihat
  agendanya.
- RBAC: `project_manager` & `site_engineer` kini boleh melihat/membuat agenda (rapat &
  kunjungan proyek); agenda yang MENYEBUT LEAD tetap ditolak untuk peran tanpa `leads:view`;
  keuangan tetap **hanya membaca** (SoD Fase 52 utuh).
- Gate baru `scripts/verify_p63.py` (44 pemeriksaan) → `run_all_gates.sh` **OVERALL PASS (54
  gates)**. Uji UI: iteration_99 (semua alur PASS). Perbaikan dari temuan uji: sheet detail
  tidak lagi menawarkan "Mulai Survey" pada agenda internal; pencarian lead diberi debounce.

### 27 Jun 2026 (lanjutan) — Fase 62: dokumen penagihan & lapangan (SELESAI, gate 53 hijau)
- **Surat Peringatan SP1/SP2/SP3** (`warning_letters.py` + `docgen_p62.sp_pdf`): angka & termin
  dari mesin denda (`late_fee_engine` via `arrears_engine.months_in_arrears`), tingkat TIDAK
  boleh melompat, SP3 hanya sah setelah tunggakan mencapai `payment.staged.arrears_months_to_cancel`,
  nomor atomik `SP{n}/TAHUN/URUT`, idempoten per (kontrak, tingkat, bulan) + indeks unik.
  Endpoint: `GET/POST /api/docs/warning-letters`, `GET /api/docs/warning-letters/state`,
  `GET /api/docs/warning-letters/{id}/pdf`. Terbit = `late_fee:create` (Keuangan); baca =
  `late_fee:view` (sales ber-scope hanya transaksinya). Surat MEMPERINGATKAN, tidak membatalkan.
- **Berita Acara Opname** (`GET /api/subcon/claims/{id}/pdf`): rincian dari BARIS TERMIN yang sama
  dengan tagihan AP, pekerjaan yang DIKELUARKAN opname tercetak beserta alasannya, retensi &
  netto disebut, termin yang belum di-opname dipaksa bertanda DRAFT.
- **Berita Acara Punch List** (`GET /api/field/punchlist/pdf`): lingkup = filter yang sedang
  dilihat (proyek/kavling/status), kolom bukti perbaikan, 3 ketentuan lapangan.
- **Lampiran SPK**: `spk_attachments` + `GET/POST/DELETE /api/subcon/spk/{id}/attachments`
  (`subcon:update`); gambar/spesifikasi tercetak sebagai HALAMAN LAMPIRAN pada PDF SPK
  (`pdf_layout._attachment_flow`, gambar dirender apa adanya; berkas hilang tidak menggagalkan
  cetak).
- **Kirim dokumen ke pihak luar** (`doc_share.py`): tautan berbatas waktu (14 hari, token acak,
  bisa dicabut, pembukaan tercatat) + pesan `wa.me` siap kirim. `POST /api/docs/share`,
  `GET /api/public/docs/{token}` (tanpa login, satu token = satu dokumen, dirender ULANG dari
  data terkini). TIDAK memakai API Meta — manusia yang menekan kirim. Hak berbagi = hak atas
  dokumennya (`doc_share.PERMISSION`).
- Target layout baru: `SP`, `BA_OPNAME`, `PUNCHLIST`. Kamus SSOT baru: `warning_level`,
  `spk_attachment_kind` (`reference_p62.py`).
- Gate baru `scripts/verify_p62.py` (59 pemeriksaan) → `run_all_gates.sh` **OVERALL PASS (53
  gates)**. Uji UI: iteration_98 (10/10 alur bersih). Keempat PDF diperiksa visual per halaman.

### 27 Jun 2026 — Fase 60: konfigurasi tampilan dokumen (SELESAI, gate 51 hijau)
- Panel `Master Data → Template Dokumen → Tampilan & kop surat` (`DocLayoutPanel`) dengan
  pratinjau PDF BERDAMPINGAN yang dirender mesin cetak yang sama (`pdf_layout.py`).
- Kop/footer 2 mode (dirakit sistem / gambar desain), watermark, kertas & margin, baris
  biaya (urut, sembunyikan, sembunyikan bila Rp 0, baris manual), tanda tangan dinamis.
- Hak akses ubah = `settings:update` (identitas perusahaan = pengaturan organisasi);
  baca = `documents:view`.
- Bidang usaha jadi dropdown SSOT (`reference_p60.business_field`).
- Jalur cetak yang memakai layout: dokumen staf, **portal pembeli** (diperbaiki), kwitansi,
  penawaran, BAST.
- Gate baru `scripts/verify_p61.py`→(60) `scripts/verify_p60.py` (38 pemeriksaan). UI: iteration_96.
- Perbaikan gate lain: `audit_forms_deep.py` (tagline → dropdown; aria-label RowsForm &
  CostsDialog) dan `verify_analytics.py` (`analytics_engine.rebuild_snapshots` sekarang
  MEMPERBAIKI seluruh riwayat snapshot, bukan hanya hari ini).

### Sebelumnya
- Fase 59: laporan keringanan denda, kandidat tunggakan (2 bulan → usulan pembatalan), utang refund.
- Fase 58: toleransi & keringanan denda keterlambatan.
- Fase ≤57: CRM, kontrak & skema pembayaran, konstruksi berbukti, pengadaan 3-way match,
  subkon/opname/retensi, GL & pajak, portal pembeli, WA/omnichannel, analitik BI.

## Backlog
### P1
- ~~Surat Peringatan Tunggakan (SP1/SP2/SP3)~~ — SELESAI Fase 62.
- ~~Berita Acara Opname / Punch List PDF~~ — SELESAI Fase 62.
- ~~Lampiran gambar/spesifikasi pada SPK~~ — SELESAI Fase 62.
- Mutasi Fase 62 (`scripts/mutasi_62.py`) belum ada — gate 53 menjaga, ketangguhannya belum
  diuji dengan mutan.
### P2
- Pengingat WhatsApp untuk pembeli menunggak (kirim SP1 otomatis sesudah H+N lewat toleransi).
- Riwayat pengiriman dokumen di layar (data `GET /api/docs/share` sudah ada, panelnya belum).
- Agenda: pengingat WhatsApp H-1 ke peserta, tampilan minggu/bulan, dan ekspor .ics.
- Notifikasi: pengelompokan notifikasi kembar ("5× Persetujuan diskon penawaran") dan
  preferensi per pemakai (kategori mana yang boleh mengirim push).
- Peringatan dini tunggakan 1 bulan sebelum batas pembatalan kontrak.
- Ringkasan direksi: email digest laporan keringanan & utang refund setiap awal bulan.

## 2026-06 (lanjutan setelah re-clone dari GitHub)
- Environment di-setup ulang dari repo gabavacafa/sipro (deps terpasang, .env dipulihkan + JWT_SECRET, seed otomatis jalan).
- Retest BI MetricDetailDialog (iteration_108): 6/6 target PASS, smoke 15/15 dialog, 0 console error. Defect iteration_107 (breakdown chart jadi series) terkonfirmasi FIXED.
- Catatan LOW opsional: label breakdown SLS-01 duplikat ("Tipe 45/90" x3) — soal data seed, bukan logika chart.

## 2026-06 — Verifikasi WA Manual (bypass integrasi)
- Gerbang lifecycle yang butuh WA = kontak pertama (acquisition→nurturing). Ditambahkan jalur manual: POST /api/leads/{id}/wa/manual — chat via WA pribadi dicatat WAJIB dengan foto bukti (screenshot), efek sama dengan kirim WA in-system (kontak pertama, naik tahap, tutup tugas kontak).
- Frontend: panel WA lead punya seksi "Catat manual + bukti foto"; pesan manual tampil di thread dengan badge MANUAL + link bukti.
- Teruji iteration_109: backend 10/10 pytest, frontend E2E pass. Regression suite: backend/tests/test_wa_manual_p29c.py.
- Backlog kecil: substitusi variabel template WA selain {{nama}} (mis. {{date}}) masih literal.

## 2026-06 — Fase 29c: Variabel Template WA + WA Manual di Work Hub + Sinkron Form Tugas
- engine.py: render_wa_body + wa_template_vars — {{date}} terisi jadwal survey terdekat (format Indonesia WIB, fallback "(waktu akan dikonfirmasi)"); berlaku di WA lead, Inbox, dan playbook/automation.
- wa/manual menerima task_id: tugas contact/follow_up terkait lead ditutup done/approved dengan bukti note+foto; blok WA manual ada di TaskDetailSheet Work Hub.
- POST /work/tasks tervalidasi: jobdesk_code harus ada di katalog (mewarisi bukti/verifikasi/SLA/divisi), related_entity dicek ke record nyata (404/400); CreateTaskDialog kini pilih jobdesk & lead dari dropdown, bukan nilai bebas.
- Teruji iteration_110 (frontend 100%) + fix defect jobdesk palsu → 22/22 pytest (tests/test_p110_wa_vars_tasks.py + test_wa_manual_p29c.py).

## 2026-09 — Fase 75b–78: hotfix P75 + akuntansi biaya all-in & pencairan KPR terkonfigurasi
- **Koreksi konsep**: "all-in" = biaya ditanggung developer (beban penjualan via AP); "exclude" = pembeli bayar terpisah → developer menampung sebagai **titipan (2-1470)** lalu menyalurkan ke notaris/BPN. Perlakuan dikunci **per komponen** di master, bukan checkbox.
- Fase 75b: QuotationBreakdown fix + uji render; guard pencairan 409 bila AR belum terbit/outstanding 0; AR sinkron saat convert/skema; `GET /gl/journals?source_id`; hint hitung ulang; date picker shadcn.
- Fase 76: master `cost_components` & `allin_schemes` (seed All-in Standar / Exclude), SPR memilih skema (manual hanya finance_manager+alasan), migrasi kontrak lama → LEGACY.
- Fase 77: invoice biaya INB → kuitansi KWB → titipan → penyaluran; beban developer via AP (6-1700); `CostBillingPanel`; add-on Rp0 diblokir, override manajer = diskon 100%.
- Fase 78: `kpr_disbursement_schemes` per bank, tahapan dari plafon, pencairan dipilih dari tahap (validasi plafon/outstanding/toleransi/2×), pembatalan berjurnal; gate 60 `verify_p75-78.py`.
- Uji: 16 pytest (tests/test_p76_78_allin_kpr.py + P75) hijau, 3 uji jest, gate 60 23/23.
- Backlog: amandemen skema all-in pasca kontrak; PDF INB/KWB; mutasi gate 60.

## 2026-09 — Fase 79: amandemen skema all-in, PDF INB/KWB, pengingat tahap KPR
- Repo di-clone ulang dari `daseady/sipro` ke container baru; `backend/.env` dipulihkan (JWT_SECRET, DEFAULT_ORG_ID=org-sipro, PORTAL_MASTER_OTP=000000, BACKUP_DIR), deps terpasang, seed jalan; `memory/test_credentials.md` diisi ulang.
- Amandemen: skema biaya kontrak terbit = snapshot terkunci (edit langsung → 409). Finance mengajukan (alasan ≥10) → finance_manager/superadmin LAIN memutuskan (pengaju ≠ pemutus; tolak wajib catatan) → `contracts.costs` + `costs_history`, INB unpaid di-void, notifikasi & aktivitas. Ditolak sistem bila sudah ada kuitansi KWB.
- PDF: `GET /cost-invoices/{id}/pdf`, `GET /cost-receipts/{id}/pdf` memakai mesin dokumen existing.
- Pengingat tahap pencairan KPR: banner "Siap dicairkan" di kotak Pencairan bertahap, panel Keuangan › Penagihan + "Kirim pengingat sekarang" (idempoten per tahap), cron harian 08:15 WIB; pembatalan pencairan mereset penanda pengingat.
- Perbaikan dari iteration_127: RBAC `view_own` kini dipenuhi `view_all` (finance/finance_manager tidak lagi 403), tombol Setujui/Tolak disembunyikan untuk pengaju, error state daftar skema & panel pengingat, testid input dialog biaya.
- Uji: pytest 14/14 (`test_p79_amend_pdf_reminder.py`, `test_p79_ui_api.py`); testing agent iteration_127 (super_admin lulus) + iteration_128 (finance/finlead 8/8 lulus, 0 bug).
- Backlog: gate 61 `verify_p79.py`; paginasi panel pengingat; amandemen komponen manual dari UI; input Rp bermasker.

## 2026-09 — Fase 79b: Input Rupiah bermasker
- Komponen `RupiahInput` (`components/ui/rupiah-input.jsx`): `Rp 1.500.000` saat mengetik, tolak huruf, tanpa desimal; nilai ke handler tetap string digit → payload API tidak berubah.
- 70 field nominal Rp di 55 file dikonversi sekali jalan (`scripts/convert_rupiah_inputs.py`); field %/Rp dwi-mode hanya bermasker saat mode nominal; Aturan Bisnis memasker aturan berlabel "(Rp)".
- Ikutan: kolom Kredit jurnal manual dilebarkan; SheetTitle saat loading (ProjectsPage, AppointmentDetailSheet) → 0 console error Radix.
- Uji: iteration_129 100% lulus (masker + 5 alur simpan end-to-end).

## 2026-09 (3 Sep) — Fase 82: Kas & Bank — rekening/kas sebagai entitas akuntansi (spec `docs/v2/52_KAS_BANK_SPEC.md`)
- Lingkungan: repo `ajsjdhhs/sipro` di-clone ke container baru; `backend/.env` dipulihkan (JWT_SECRET, STORAGE_PROVIDER=mongo, BACKUP_DIR), deps terpasang, seed jalan.
- Gap fatal yang ditutup: semua rekening menumpang `1-1200`, aliran uang tidak menyebut rekening, tidak ada transfer/setor/tarik, saldo awal tidak dijurnal, tidak ada buku kas/bank & posisi kas.
- Backend: `cash_bank.py` (engine: sub-akun otomatis `1-12xx`/`1-11xx`, default per jenis, saldo awal → `3-1950`, migrasi startup baris jurnal akun induk → rekening default, transfer internal SoD `TRF/…`, buku & posisi), `routers/cash_bank_router.py` (`/cash-bank/*`, RBAC `bank`), `models_p82.py`, `seed_phase82.py` (Rekening Escrow BCA, Kas Kecil Site, 1 transfer diposting + 1 menunggu). `gl_engine.post_journal` menolak posting ke akun induk (dialihkan ke sub-akun). `cash_account_id` di AR receipt, AP pay (+withholding), komisi, kas bon (+pengembalian sisa), setor pajak, refund, pencairan KPR (`kpr_disburse`, `financing_router`), rekonsiliasi bank (`bank_match`).
- Frontend: halaman `/cash-bank` (Posisi Kas, Buku Kas & Bank + CSV, Transfer Internal, Master Rekening & Kas); `CashAccountSelect` disematkan di ReceiptDialog, PayBillDialog, DisburseAdvanceDialog, TaxRecordsPanel, CancellationPanel (refund), KprPanel (pencairan). testIds `constants/testIds/p82.js`.
- Uji: pytest `tests/test_p82_cash_bank.py` 4/4 + `tests/test_p82_ext.py` (testing agent) 10/10; UI end-to-end (posisi, buku+CSV, transfer approve/reject SoD, master, kuitansi AR → sub-akun escrow) lulus; 3 bug UI dari QA diperbaiki (RupiahInput onChange di TransferDialog/AccountDialog, jenis kas 'kas' di DisburseAdvanceDialog). Gate lama disesuaikan ke sub-akun (f26, p27, quotation_labor, tax_compliance, p76/78) + perbaikan bug gate `verify_bank_recon.py` (memilih kuitansi booking fee). Catatan: gate `_fixture47/48 purge()` meninggalkan jurnal titipan yatim (source_type deposit) → invarian 2-1450 gagal setelah gate; dibersihkan manual, perlu perbaikan purge (backlog).
- Backlog gap akunting (lihat spec §4): rekonsiliasi per sub-akun, kas kecil imprest, tutup periode kas, giro mundur, BKK/BKM & payment run, cash forecast vs posisi kas, otorisasi berjenjang, pemilih rekening untuk upah/marketing fee/pinjaman/aset/cost_receipt.


## 2026-09 (3 Sep) — Fase 81b: RAB terstruktur masuk BI & Analitik
- Modul metrik baru `metrics/rab.py` (RAB-01..06) membungkus `rab_engine` — angka BI = angka `/boq` › Ringkasan & HPP: RAB-01 RAB total terstruktur (komposisi unit/add-on/fasum/umum/lama), RAB-02 margin HPP proyeksi, RAB-03 margin HPP per tipe (+ unit margin tipis <10%), RAB-04 SPK fasum melampaui progres fase, RAB-05 selisih SPK vs dasar RAB (override), RAB-06 revisi RAB tipe/add-on (versi, deret harian). Kejujuran: unit tanpa RAB tipe → `coverage`/`sebagian`, tanpa data → `kosong`.
- Dashboard: eksekutif +RAB-02, RAB-03; proyek +RAB-01 (pie), RAB-04, RAB-05, RAB-06 (deret). Snapshot harian untuk RAB-01..05. `BGT-06` margin proyeksi kini memakai RAB terstruktur (`project_summary.total_rab`), bukan Σ `boq_items` flat. Spec `docs/v2/31` §5 diperbarui.
- Uji: `tests/test_p81b_rab_metrics.py` 4/4; gate `scripts/verify_analytics.py` PASSED (63 metrik, 40 snapshot); layar BI eksekutif & proyek merender grafik RAB.

## 2026-09 (3 Sep) — Fase 81: Versi RAB (riwayat + pulihkan), salin dari tipe lain, impor Excel, kendali fasum vs progres fase
- Menyelesaikan 3 dari 4 "tugas berikutnya sesudah Fase 80": (1) Gate 61 `scripts/verify_p80_81.py` 32/32 → `run_all_gates.sh`; (2) kendali fasum: termin SPK fasum lump-sum ≤ progres fase konstruksi tertaut (ditolak 400 dengan pesan fase/batas; batas ikut naik saat fase maju; tabel kendali di Ringkasan & HPP; hint di dialog Ajukan Termin); (3) RAB tipe/add-on: setiap Simpan yang mengubah baris menyimpan versi lama (`rab_template_versions`) + catatan perubahan, riwayat dengan selisih total, Pulihkan; salin dari tipe lain × faktor harga (pratinjau → Simpan); impor Excel (template unduh + pratinjau tervalidasi dengan kesalahan/peringatan).
- Backend: `rab_templates_ext.py` (baru), `rab_engine.py` (save_template versi, fasum_phase_cap/fasum_control), `routers/rab_router.py`, `routers/subcon_claims_router.py`. Frontend: `boq/{RabTemplateTools,RabVersionHistory,RabFasumControl}.js`, `RabTemplateDialog`, `RabTypePanel`, `RabSummaryPanel`, `subcon/SubmitClaimDialog`; testIds `p81.js`.
- Uji: pytest `tests/test_p81_rab_ext.py` 4/4 + `test_p81_frontend_support.py` 5/5; gate 61 32/32; testing agent iteration_131 7/7 UI lulus (temuan kosmetik diperbaiki: hydration `<option label>`, input file → tombol design system, hint tombol salin disabled).
- Tersisa dari daftar Fase 80: amandemen komponen manual dari UI; paginasi panel pengingat tahap; engine.py 821>800; audit form 6 `<Input>` tanpa label (pre-existing).

## 2026-09 — Fase 80: RAB terstruktur (tipe / add-on / fasum-fasos / umum) + SPK dari RAB
- Jawaban pertanyaan user: RAB lama = daftar flat per proyek, tidak per unit, fasum tidak terpisah dan tidak masuk HPP. Kini: RAB **tertempel pada tipe unit** (proyek = RAB tipe × jumlah unit), RAB add-on (HPP add-on), RAB fasum/fasos per fasilitas (tautan fase konstruksi), RAB umum; alokasi biaya bersama per proyek (rata/luas tanah/harga jual) → HPP & margin per unit; ringkasan total RAB vs nilai jual.
- SPK dari RAB: unit + add-on / unit saja / hanya add-on (rumah jadi, pembeli menambah add-on → dari deal aktif unit) / fasum / umum; nilai boleh dioverride dengan alasan; jejak RAB vs nilai di SPK; baris bertaut langkah otomatis masuk lingkup jadwal; item fasum tidak bisa dikontrakkan 2×.
- Uji: pytest 6/6 (`tests/test_p80_rab.py`), iteration_130 lulus semua alur + perbaikan temuan.
