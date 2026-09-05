#!/usr/bin/env python3
"""poc_54.py — POC INTI Fase 54: RANTAI SESI (masuk → bekerja lama → diperpanjang → keluar).

Laporan pemakai yang ditutup fase ini (tercatat di `test_reports/iteration_85.json`,
prioritas MEDIUM, satu-satunya sisa Fase 53):

    "Login sessions expire frequently during testing. Users need to re-login multiple
     times during extended use."

Pembacaan kode membenarkannya, dan menemukan EMPAT cacat nyata — bukan satu:

  A. **`POST /api/auth/refresh` tidak pernah ada.** Baris pertama `auth_router.py` sendiri
     menulis "login, register, me, logout, refresh"; `create_refresh_token()` dipanggil di
     login DAN register; cookie `refresh_token` disetel dengan umur 7 hari — lalu TIDAK ADA
     satu baris pun yang membacanya. Jadi sesi mati keras di jam ke-24, dan token refresh
     adalah janji yang ditulis kode kepada dirinya sendiri lalu tidak pernah ditepati.

  B. **Cookie kedaluwarsa MENGALAHKAN Bearer yang masih sah.** `security._extract_token`
     membaca cookie dulu dan hanya turun ke header bila cookie KOSONG. Cookie yang ADA tapi
     KEDALUWARSA membuat `jwt.decode` melempar `ExpiredSignatureError` → 401, walau header
     membawa token yang sempurna. Ini juga penghalang keras bagi perbaikan (A): endpoint
     refresh menyerahkan token baru yang disimpan frontend di localStorage, sementara peramban
     tetap mengirim cookie `access_token` yang lama; tanpa perbaikan (B), sesi justru 401
     SELAMANYA sesudah diperpanjang.

  C. **Perpanjangan tidak boleh menghidupkan yang sudah dimatikan.** Kalau `/auth/refresh`
     lahir tanpa gerbang, akun yang dinonaktifkan dan penyewa yang disuspend bisa
     memperpanjang sesinya sampai 7 hari — pintu belakang yang dibuat oleh perbaikan sendiri.

  D. **Perpanjangan tidak boleh diam-diam memindahkan penyewa.** `super_admin` yang sedang
     "bertindak sebagai" organisasi lain membawa klaim `active_org_id`. Bila refresh
     menerbitkan token tanpa klaim itu, ia terlempar pulang ke org asalnya TANPA PESAN —
     layarnya tetap menulis nama penyewa yang lama sementara datanya sudah milik penyewa
     lain. Itu cacat data lintas penyewa yang tidak kelihatan.

Yang DIBUKTIKAN di sini dengan HTTP nyata (bukan unit test bohongan): sesi bisa diperpanjang,
tidak bisa dibangkitkan dari kubur, tidak berpindah penyewa, tidak bisa ditembus token salah
jenis, dan sebab kegagalannya bisa dibedakan mesin (`X-Session-State`) tanpa berhenti menjadi
kalimat manusia (`detail`).

Jalankan: python3 poc/poc_54.py
"""
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

import jwt
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = "http://localhost:8001/api"
PW = "Sipro#2026"
SECRET = os.environ["JWT_SECRET"]
ALG = "HS256"
OK, FAIL = [], []


# --------------------------------------------------------------------------- alat bantu
def check(cond: bool, label: str, detail: str = "") -> bool:
    if cond:
        OK.append(label)
        print(f"  OK    {label}")
    else:
        FAIL.append(f"{label} — {detail}")
        print(f"  MERAH {label} — {detail}")
    return bool(cond)


def head(t: str) -> None:
    print(f"\n{t}\n{'-' * len(t)}")


def detail(r) -> str:
    try:
        return f"HTTP {r.status_code} {str(r.json())[:220]}"
    except Exception:
        return f"HTTP {r.status_code} {r.text[:220]}"


def j(r):
    try:
        return r.json()
    except Exception:
        return {}


def login(email: str, pw: str = PW):
    """Kembalikan (token, cookies, body) — cookies dipakai menguji jalur peramban."""
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"login {email} gagal: {detail(r)}")
    return j(r).get("access_token"), r.cookies, j(r)


def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def login_lunak(email: str, pw: str = PW):
    """Seperti `login()` tetapi TIDAK mematikan POC bila gagal.

    Dipakai pada bagian yang memakai akun bikinan: kalau akunnya gagal dibuat, POC harus
    MELAPORKAN merah pada pemeriksaan yang bersangkutan, bukan mati di tengah jalan dan
    menyembunyikan hasil bagian-bagian sesudahnya.
    """
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        return None, None, {}, r
    return j(r).get("access_token"), r.cookies, j(r), r


def mint(sub: str, email: str, role: str, *, typ: str = "access", ttl_seconds: int = 3600,
         active_org_id: str = None) -> str:
    """Terbitkan token SENDIRI supaya keadaan 'kedaluwarsa' bisa diuji tanpa menunggu 24 jam.

    Ini sah dilakukan POC: kuncinya sama dengan milik server (`JWT_SECRET`), jadi token yang
    dihasilkan IDENTIK dengan yang akan dibuat server pada detik itu. Yang dipalsukan hanyalah
    WAKTU, bukan kewenangan.
    """
    payload = {"sub": sub, "type": typ,
               "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)}
    if typ == "access":
        payload.update({"email": email, "role": role})
        if active_org_id:
            payload["active_org_id"] = active_org_id
    return jwt.encode(payload, SECRET, algorithm=ALG)


def sess_state(r) -> str:
    return r.headers.get("X-Session-State", "")


# ------------------------------------------------------------------- A. dasar & sanity
def bagian_a():
    head("A. Dasar: masuk, profil sesi, dan bekal cookie")
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "superadmin@sipro.co.id", "password": PW}, timeout=30)
    check(r.status_code == 200, "A1 login super admin berhasil", detail(r))
    body = j(r)
    tok = body.get("access_token")
    check(bool(tok), "A2 login menyerahkan access_token")
    check(bool((body.get("data") or {}).get("permissions")),
          "A3 jawaban login membawa izin efektif (warisan Fase 53)")
    check("access_token" in r.cookies, "A4 login menyetel cookie access_token")
    check("refresh_token" in r.cookies,
          "A5 login menyetel cookie refresh_token (bekal perpanjangan)")
    me = requests.get(f"{BASE}/auth/me", headers=bearer(tok), timeout=30)
    check(me.status_code == 200, "A6 /auth/me menerima Bearer", detail(me))
    return tok, r.cookies, j(me).get("data") or {}


# ------------------------------------------------- B. prioritas token (cacat B) ------
def bagian_b(user: dict, cookies):
    head("B. Prioritas token: cookie basi TIDAK BOLEH mengalahkan Bearer yang sah")
    uid, email, role = user["id"], user["email"], user["role"]
    sah = mint(uid, email, role, ttl_seconds=3600)
    basi = mint(uid, email, role, ttl_seconds=-60)          # sudah kedaluwarsa 1 menit
    sampah = "ini.bukan.jwt"
    refresh_sah = mint(uid, email, role, typ="refresh", ttl_seconds=3600)

    r = requests.get(f"{BASE}/auth/me", cookies={"access_token": sah}, timeout=30)
    check(r.status_code == 200, "B1 cookie SAH tanpa header tetap diterima (kompatibel mundur)",
          detail(r))

    r = requests.get(f"{BASE}/auth/me", cookies={"access_token": basi}, timeout=30)
    check(r.status_code == 401, "B2 cookie KEDALUWARSA sendirian ditolak 401", detail(r))
    check(sess_state(r) == "expired",
          "B3 sebab ditolak dibedakan mesin: X-Session-State=expired", sess_state(r) or "(kosong)")

    # ---- INTI CACAT B ----
    r = requests.get(f"{BASE}/auth/me", cookies={"access_token": basi},
                     headers=bearer(sah), timeout=30)
    check(r.status_code == 200,
          "B4 cookie KEDALUWARSA + Bearer SAH = 200 (header menang) [INTI CACAT]", detail(r))

    r = requests.get(f"{BASE}/auth/me", cookies={"access_token": sampah},
                     headers=bearer(sah), timeout=30)
    check(r.status_code == 200, "B5 cookie SAMPAH + Bearer SAH = 200", detail(r))

    r = requests.get(f"{BASE}/auth/me", cookies={"access_token": sah},
                     headers=bearer(basi), timeout=30)
    check(r.status_code == 200,
          "B6 Bearer KEDALUWARSA + cookie SAH = 200 (kandidat lain dicoba)", detail(r))

    r = requests.get(f"{BASE}/auth/me", timeout=30)
    check(r.status_code == 401, "B7 tanpa token apa pun = 401", detail(r))
    check(sess_state(r) == "missing",
          "B8 X-Session-State=missing membedakan 'belum masuk' dari 'sesi berakhir'",
          sess_state(r) or "(kosong)")

    r = requests.get(f"{BASE}/auth/me", headers=bearer(sampah), timeout=30)
    check(r.status_code == 401 and sess_state(r) == "invalid",
          "B9 token cacat = 401 + X-Session-State=invalid", f"{r.status_code}/{sess_state(r)}")

    # Token refresh TIDAK boleh dipakai sebagai token kerja (kalau boleh, umur sesi
    # efektif menjadi 7 hari dan seluruh gunanya access token hilang).
    r = requests.get(f"{BASE}/auth/me", headers=bearer(refresh_sah), timeout=30)
    check(r.status_code == 401,
          "B10 token REFRESH ditolak sebagai token kerja (jenis token dipaksa)", detail(r))

    # `detail` harus tetap KALIMAT: layar repo ini mencetak `detail` apa adanya, jadi kalau
    # ia menjadi objek, pengguna melihat "[object Object]" — cacat yang dilarang di repo ini.
    r = requests.get(f"{BASE}/auth/me", cookies={"access_token": basi}, timeout=30)
    d = j(r).get("detail")
    check(isinstance(d, str) and len(d) > 8,
          "B11 pesan 401 tetap kalimat manusia (bukan objek yang jadi [object Object])",
          repr(d))
    check(isinstance(d, str) and "token" not in d.lower() and "jwt" not in d.lower(),
          "B12 pesan 401 tidak menceramahi pemakai soal istilah internal (token/JWT)", repr(d))


# ------------------------------------------------- C. /auth/refresh (cacat A) --------
def bagian_c(user: dict):
    head("C. Perpanjangan sesi: /auth/refresh ada, bekerja, dan bentuknya sama")
    uid, email, role = user["id"], user["email"], user["role"]

    tok, cookies, _ = login("superadmin@sipro.co.id")
    # JWT hanya berketelitian DETIK: kalau refresh terjadi pada detik yang sama dengan login,
    # `exp`-nya identik sehingga rangkaian tokennya pun identik — itu bukan cacat. Yang
    # BENAR-BENAR harus dibuktikan adalah sesinya MEMANG diperpanjang, jadi tunggu satu detik
    # lalu bandingkan `exp`, bukan membandingkan teks token.
    exp_lama = jwt.decode(tok, SECRET, algorithms=[ALG], options={"verify_exp": False})["exp"]
    time.sleep(1.2)
    r = requests.post(f"{BASE}/auth/refresh", cookies=cookies, timeout=30)
    check(r.status_code == 200, "C1 POST /auth/refresh dengan cookie refresh = 200", detail(r))
    body = j(r)
    baru = body.get("access_token")
    check(bool(baru), "C2 refresh menyerahkan access_token BARU")
    exp_baru = jwt.decode(baru, SECRET, algorithms=[ALG],
                          options={"verify_exp": False})["exp"] if baru else 0
    check(exp_baru > exp_lama,
          "C3 sesi BENAR-BENAR diperpanjang (batas waktu bergeser ke depan)",
          f"lama={exp_lama} baru={exp_baru}")

    me = requests.get(f"{BASE}/auth/me", headers=bearer(baru), timeout=30)
    check(me.status_code == 200, "C4 token hasil refresh benar-benar bisa dipakai", detail(me))

    prof = body.get("data") or {}
    wajib = ("permissions", "active_org", "home_org_id", "is_switched", "level", "role", "email")
    kurang = [k for k in wajib if k not in prof]
    check(not kurang,
          "C5 jawaban refresh memuat profil sesi LENGKAP (satu bentuk dgn /login & /me)",
          f"kurang: {kurang}")

    check("access_token" in r.cookies,
          "C6 refresh MENYETEL ULANG cookie access_token (jebakan cookie basi tidak kembali)")

    # --- skenario nyata: yang bekerja lama, access token habis, refresh menyelamatkan
    habis = mint(uid, email, role, ttl_seconds=-5)
    kerja = requests.get(f"{BASE}/leads", headers=bearer(habis), params={"limit": 1}, timeout=30)
    check(kerja.status_code == 401 and sess_state(kerja) == "expired",
          "C7 access token habis -> 401 'expired' (isyarat yang boleh diperpanjang)",
          f"{kerja.status_code}/{sess_state(kerja)}")
    r2 = requests.post(f"{BASE}/auth/refresh", cookies=cookies, timeout=30)
    check(r2.status_code == 200, "C8 sesi diperpanjang tanpa pemakai mengetik sandi lagi",
          detail(r2))
    lanjut = requests.get(f"{BASE}/leads", headers=bearer(j(r2).get("access_token")),
                          params={"limit": 1}, timeout=30)
    check(lanjut.status_code == 200, "C9 pekerjaan bisa DILANJUTKAN sesudah diperpanjang",
          detail(lanjut))

    # --- penolakan yang benar
    r = requests.post(f"{BASE}/auth/refresh", timeout=30)
    check(r.status_code == 401, "C10 refresh tanpa bekal apa pun = 401", detail(r))
    check(sess_state(r) == "missing", "C11 sebabnya 'missing', bukan 'expired'", sess_state(r))

    akses = mint(uid, email, role, ttl_seconds=3600)
    r = requests.post(f"{BASE}/auth/refresh", cookies={"refresh_token": akses}, timeout=30)
    check(r.status_code == 401,
          "C12 token AKSES dipakai sebagai refresh ditolak (jenis token dipaksa)", detail(r))

    kadaluarsa = mint(uid, email, role, typ="refresh", ttl_seconds=-10)
    r = requests.post(f"{BASE}/auth/refresh", cookies={"refresh_token": kadaluarsa}, timeout=30)
    check(r.status_code == 401 and sess_state(r) == "expired",
          "C13 refresh yang KEDALUWARSA tidak bisa dibangkitkan (batas 7 hari nyata)",
          f"{r.status_code}/{sess_state(r)}")

    # Klien non-peramban (skrip, gate, aplikasi lapangan) tidak punya cookie jar.
    segar = mint(uid, email, role, typ="refresh", ttl_seconds=3600)
    r = requests.post(f"{BASE}/auth/refresh", json={"refresh_token": segar}, timeout=30)
    check(r.status_code == 200,
          "C14 refresh juga bisa lewat badan permintaan (klien tanpa cookie jar)", detail(r))
    return cookies


# ------------------------------------- D. penyewa: refresh tidak boleh memindahkan ---
def bagian_d():
    head("D. Multi-penyewa: perpanjangan TIDAK BOLEH memulangkan super admin diam-diam")
    tok, cookies, _ = login("superadmin@sipro.co.id")
    sw = requests.post(f"{BASE}/admin/orgs/org-nusa/switch", headers=bearer(tok), timeout=30)
    check(sw.status_code == 200, "D1 super admin bertindak sebagai org-nusa", detail(sw))
    tok_sw = j(sw).get("access_token")
    me = j(requests.get(f"{BASE}/auth/me", headers=bearer(tok_sw), timeout=30)).get("data") or {}
    check(me.get("is_switched") is True and (me.get("active_org") or {}).get("id") == "org-nusa",
          "D2 profil sesi mengakui sedang bertindak sebagai penyewa lain",
          f"{me.get('is_switched')}/{(me.get('active_org') or {}).get('id')}")

    # Cookie access_token milik sesi 'switched' disetel oleh endpoint switch; refresh harus
    # membaca klaim itu dan MEMPERTAHANKANNYA.
    ck = {"refresh_token": cookies.get("refresh_token"), "access_token": tok_sw}
    r = requests.post(f"{BASE}/auth/refresh", cookies=ck, timeout=30)
    check(r.status_code == 200, "D3 refresh saat 'bertindak sebagai' berhasil", detail(r))
    tok_baru = j(r).get("access_token")
    me2 = j(requests.get(f"{BASE}/auth/me", headers=bearer(tok_baru), timeout=30)).get("data") or {}
    check(me2.get("is_switched") is True
          and (me2.get("active_org") or {}).get("id") == "org-nusa",
          "D4 sesudah diperpanjang MASIH di org-nusa [INTI CACAT D]",
          f"{me2.get('is_switched')}/{(me2.get('active_org') or {}).get('id')}")
    prof = j(r).get("data") or {}
    check((prof.get("active_org") or {}).get("id") == "org-nusa",
          "D5 jawaban refresh sendiri sudah menyebut penyewa aktif yang benar",
          str(prof.get("active_org")))

    home = requests.post(f"{BASE}/admin/orgs/org-sipro/switch", headers=bearer(tok_baru),
                         timeout=30)
    check(home.status_code == 200, "D6 kembali ke organisasi asal", detail(home))
    tok_home = j(home).get("access_token")
    r = requests.post(f"{BASE}/auth/refresh",
                      cookies={"refresh_token": cookies.get("refresh_token"),
                               "access_token": tok_home}, timeout=30)
    me3 = j(requests.get(f"{BASE}/auth/me", headers=bearer(j(r).get("access_token")),
                         timeout=30)).get("data") or {}
    check(me3.get("is_switched") is False,
          "D7 sesudah pulang, perpanjangan tidak melemparnya kembali ke penyewa lain",
          str(me3.get("is_switched")))


# ---------------------------- E. gerbang: yang dimatikan tidak boleh diperpanjang ----
def bagian_e():
    head("E. Gerbang perpanjangan: akun/penyewa yang dimatikan TIDAK boleh hidup 7 hari lagi")
    sa, _, _ = login("superadmin@sipro.co.id")
    nama = "ZZ Uji Sesi F54 Penyewa"
    surel = "owner.f54@ujisesif54.co.id"
    r = requests.post(f"{BASE}/admin/orgs", headers=bearer(sa), timeout=30,
                      json={"name": nama, "owner_name": "Owner Uji F54",
                            "owner_email": surel, "owner_password": PW})
    check(r.status_code == 200, "E1 organisasi sementara + ownernya dibuat", detail(r))
    org_id = (j(r).get("data") or {}).get("id")
    if not org_id:
        return

    tok, ck, _, lr = login_lunak(surel)
    if not check(ck is not None, "E2 owner penyewa sementara bisa masuk", detail(lr)):
        return
    check(bool(ck.get("refresh_token")), "E2b owner penyewa sementara punya bekal perpanjangan")

    # -- penyewa disuspend
    up = requests.put(f"{BASE}/admin/orgs/{org_id}", headers=bearer(sa),
                      json={"status": "suspended"}, timeout=30)
    check(up.status_code == 200, "E3 penyewa disuspend", detail(up))
    lg = requests.post(f"{BASE}/auth/login", json={"email": surel, "password": PW}, timeout=30)
    check(lg.status_code == 403, "E4 login penyewa disuspend ditolak (perilaku lama, sanity)",
          detail(lg))
    rf = requests.post(f"{BASE}/auth/refresh", cookies=ck, timeout=30)
    check(rf.status_code in (401, 403),
          "E5 PERPANJANGAN penyewa disuspend juga ditolak [pintu belakang ditutup]", detail(rf))
    check(sess_state(rf) == "revoked",
          "E6 sebabnya dibedakan: 'revoked' (dicabut), bukan 'expired'", sess_state(rf))

    requests.put(f"{BASE}/admin/orgs/{org_id}", headers=bearer(sa),
                 json={"status": "active"}, timeout=30)
    rf = requests.post(f"{BASE}/auth/refresh", cookies=ck, timeout=30)
    check(rf.status_code == 200, "E7 penyewa diaktifkan lagi -> perpanjangan boleh lagi",
          detail(rf))

    # -- akun dinonaktifkan
    # Dibuat DI ORGANISASI SENDIRI: `GET /admin/users` ber-scope organisasi, jadi owner
    # penyewa sementara di atas TIDAK pernah muncul di daftar super admin. Versi pertama POC
    # ini memakainya dan akibatnya tiga pemeriksaan (E8..E10) DIAM-DIAM TERLEWAT — POC
    # melaporkan hijau untuk gerbang yang belum pernah diuji sama sekali.
    surel_u = "staf.f54@ujisesif54.co.id"
    cu = requests.post(f"{BASE}/admin/users", headers=bearer(sa), timeout=30,
                       json={"name": "ZZ Uji Sesi F54 Staf", "email": surel_u,
                             "password": PW, "role": "sales"})
    uid = (j(cu).get("data") or {}).get("id")
    if check(bool(uid), "E8a akun staf sementara dibuat", detail(cu)):
        _, ck3, _, _ = login_lunak(surel_u)
        requests.put(f"{BASE}/admin/users/{uid}", headers=bearer(sa),
                     json={"is_active": False}, timeout=30)
        rf = requests.post(f"{BASE}/auth/refresh", cookies=ck3, timeout=30)
        check(rf.status_code in (401, 403),
              "E8 akun dinonaktifkan tidak bisa memperpanjang sesi", detail(rf))
        check(sess_state(rf) == "revoked", "E9 sebabnya 'revoked'", sess_state(rf))
        kerja = requests.get(f"{BASE}/auth/me", cookies=ck3, timeout=30)
        check(kerja.status_code == 403 and sess_state(kerja) == "revoked",
              "E9b token yang masih sah pun berhenti bekerja saat akun dimatikan",
              f"{kerja.status_code}/{sess_state(kerja)}")
        requests.put(f"{BASE}/admin/users/{uid}", headers=bearer(sa),
                     json={"is_active": True}, timeout=30)
        rf = requests.post(f"{BASE}/auth/refresh", cookies=ck3, timeout=30)
        check(rf.status_code == 200, "E10 akun diaktifkan lagi -> boleh lagi", detail(rf))


# ------------------------------------------ F. semua peran & izin tidak berubah ------
def bagian_f():
    head("F. Semua peran bisa diperpanjang, dan izinnya TIDAK berubah karena diperpanjang")
    for surel in ("owner@sipro.co.id", "sales@sipro.co.id", "finance@sipro.co.id",
                  "pm@sipro.co.id", "site@sipro.co.id", "finlead@sipro.co.id"):
        tok, ck, body = login(surel)
        sebelum = (body.get("data") or {}).get("permissions") or {}
        rf = requests.post(f"{BASE}/auth/refresh", cookies=ck, timeout=30)
        if not check(rf.status_code == 200, f"F {surel} bisa memperpanjang sesi", detail(rf)):
            continue
        sesudah = (j(rf).get("data") or {}).get("permissions") or {}
        check(sebelum == sesudah,
              f"F {surel} izinnya SAMA sesudah diperpanjang (tidak naik, tidak turun)",
              f"{len(sebelum)} vs {len(sesudah)} sumber daya")
        # Peran terbatas harus tetap terbatas memakai token hasil refresh — perpanjangan
        # bukan celah naik pangkat.
        if surel == "sales@sipro.co.id":
            baru = j(rf).get("access_token")
            r = requests.get(f"{BASE}/tax/records", headers=bearer(baru), timeout=30)
            check(r.status_code == 403,
                  "F sales tetap ditolak di modul pajak memakai token hasil refresh",
                  detail(r))


# ----------------------------------------------- G. portal pembeli tidak terganggu ---
def bagian_g():
    head("G. Portal pembeli: sesi OTP-nya terpisah dan tidak ikut terguncang")
    r = requests.post(f"{BASE}/portal/auth/request-otp",
                      json={"identifier": "+6281250000502"}, timeout=30)
    check(r.status_code == 200, "G1 permintaan OTP portal masih berjalan", detail(r))
    v = requests.post(f"{BASE}/portal/auth/verify-otp",
                      json={"identifier": "+6281250000502", "code": "000000"}, timeout=30)
    check(v.status_code == 200, "G2 OTP master portal masih berlaku", detail(v))
    ptok = j(v).get("token") or j(v).get("access_token")
    if ptok:
        me = requests.get(f"{BASE}/portal/me", headers=bearer(ptok), timeout=30)
        check(me.status_code == 200, "G3 sesi portal bisa dipakai", detail(me))
        x = requests.get(f"{BASE}/auth/me", headers=bearer(ptok), timeout=30)
        check(x.status_code == 401,
              "G4 token portal TIDAK bisa masuk ke sesi internal (dua dunia terpisah)",
              detail(x))
        # Kelas cacat yang sama seperti sesi staf, dibuktikan juga di portal: cookie portal
        # yang KEDALUWARSA tidak boleh mengalahkan Bearer portal yang masih sah.
        basi = jwt.encode({"sub": "x", "type": "portal",
                           "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                          SECRET, algorithm=ALG)
        r2 = requests.get(f"{BASE}/portal/me", cookies={"portal_token": basi},
                          headers=bearer(ptok), timeout=30)
        check(r2.status_code == 200,
              "G6 cookie portal basi + Bearer portal sah = 200 (kelas cacat ikut ditutup)",
              detail(r2))
    itok, _, _ = login("superadmin@sipro.co.id")
    x = requests.get(f"{BASE}/portal/me", headers=bearer(itok), timeout=30)
    check(x.status_code in (401, 403),
          "G5 token internal TIDAK bisa menyusup ke portal pembeli", detail(x))


# ------------------------------------------------- H. jendela geser yang berbatas ----
def bagian_h(user: dict):
    head("H. Jendela geser: yang masih bekerja tidak diusir, yang menganggur tetap habis")
    uid = user["id"]
    # Refresh yang sisa hidupnya TINGGAL SEDIKIT harus ikut diperbarui, supaya orang yang
    # memang sedang bekerja tidak diusir tepat di hari ke-7.
    hampir = mint(uid, "", "", typ="refresh", ttl_seconds=3600)          # sisa 1 jam dari 7 hari
    r = requests.post(f"{BASE}/auth/refresh", cookies={"refresh_token": hampir}, timeout=30)
    check(r.status_code == 200, "H1 refresh yang hampir habis masih diterima", detail(r))
    check("refresh_token" in r.cookies,
          "H2 bekal perpanjangan DIPERBARUI saat sisanya sedikit (jendela bergeser)")

    # Yang masih panjang tidak perlu diperbarui — supaya jendela tidak menjadi tak terbatas
    # hanya karena aplikasi ramai memanggil refresh.
    panjang = mint(uid, "", "", typ="refresh", ttl_seconds=7 * 24 * 3600 - 60)
    r = requests.post(f"{BASE}/auth/refresh", cookies={"refresh_token": panjang}, timeout=30)
    check(r.status_code == 200, "H3 refresh yang masih panjang tetap diterima", detail(r))
    check("refresh_token" not in r.cookies,
          "H4 bekal yang masih panjang TIDAK diperbarui (batas 7 hari tetap nyata)",
          str(list(r.cookies.keys())))


def main() -> int:
    print("=" * 78)
    print("POC FASE 54 — RANTAI SESI: masuk, bekerja lama, diperpanjang, dan keluar dengan benar")
    print("=" * 78)
    try:
        requests.get(f"{BASE}/health", timeout=10)
    except Exception as e:
        print(f"Backend tidak menjawab di {BASE}: {e}")
        return 1

    tok, cookies, user = bagian_a()
    bagian_b(user, cookies)
    bagian_c(user)
    bagian_d()
    bagian_e()
    bagian_f()
    bagian_g()
    bagian_h(user)

    print("\n" + "=" * 78)
    print(f"HASIL POC 54: {len(OK)} PASS, {len(FAIL)} FAIL")
    if "--sisakan" not in sys.argv:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import _fixture54
        print(f"Bahan uji dibersihkan: {_fixture54.purge()}")
    if FAIL:
        print("YANG GAGAL:")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("POC FASE 54 PASSED — sesi bisa diperpanjang tanpa mengetik sandi, cookie basi tidak "
          "lagi mengalahkan token sah, yang dicabut tetap mati, dan penyewa tidak berpindah.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
