"""Setting Fase 88 — skor lead terkonfigurasi & kebijakan pelunasan serah terima.

Dipisah dari `settings_store.py` karena berkas itu mendekati batas 800 baris; dimuat dan
digabung ke `DEFAULTS` oleh `settings_store` (SSOT tetap satu registry).
"""


def _d(key, value, type_, group, label, help_, *, impact="", sensitive=False, minimum=None,
       maximum=None, options=None, src="SISTEM"):
    return {
        "key": key, "value": value, "type": type_, "group": group, "label": label,
        "help": help_, "impact": impact, "sensitive": sensitive, "min": minimum,
        "max": maximum, "options": options or [], "source": src,
    }


DEFAULTS_P88: dict = {d["key"]: d for d in [
    # ============ Fase 88B/89: skor lead berbasis event terkonfigurasi ============
    _d("lead.score.events", [], "list", "lead", "Event skor lead",
       ("Daftar event yang menaikkan/menurunkan skor lead beserta poin, parameter (jendela hari, "
        "batas, ambang), status aktif, dan event kustom. Kosong = bawaan sistem. Disunting lewat "
        "Pusat Konfigurasi › Skor Lead (bukan JSON mentah)."),
       impact="Mengubah poin/aktif event mengubah urutan prioritas follow-up seluruh sales."),
    _d("lead.score.bands", {"hot_min": 70, "warm_min": 45}, "obj", "lead",
       "Ambang band skor (hot/warm)",
       "Skor ≥ hot_min = HOT, ≥ warm_min = WARM, di bawahnya COLD.",
       impact="Menurunkan ambang membuat lebih banyak lead tampak panas dari kenyataannya."),
    # ============ Fase 88E: pelunasan sebelum BAST ============
    _d("handover.settlement_policy", "wajib_lunas", "enum", "garansi",
       "Kebijakan pelunasan sebelum BAST",
       ("wajib_lunas: sisa tagihan > 0 MENAHAN BAST (hanya bisa diterobos Manajer Keuangan). "
        "minimal_persen: menahan hanya bila pembayaran < persen minimum. "
        "peringatan: sisa tagihan hanya menjadi PERINGATAN — BAST bisa terbit tanpa terobosan."),
       impact="Melonggarkan kebijakan ini berarti kunci bisa diserahkan sebelum rumah lunas.",
       sensitive=True, options=["wajib_lunas", "minimal_persen", "peringatan"], src="DOC"),
    _d("handover.settlement_min_paid_pct", 90, "pct", "garansi",
       "Minimum terbayar sebelum BAST (%)",
       "Dipakai hanya bila kebijakan = minimal_persen.", sensitive=True, minimum=0, maximum=100),
]}
