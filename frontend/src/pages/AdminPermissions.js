import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ShieldCheck, Info, Save, RotateCcw, Search, Lock, GitBranch, Ban } from "lucide-react";
import { toast } from "sonner";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { roleLabel } from "@/utils/formatters";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { ADMIN } from "@/constants/testIds";

/**
 * Layar Hak Akses (RBAC).
 *
 * Dua cacat nyata yang ditutup berkas ini:
 *
 * 1. **Layar keamanan yang berbohong.** Versi lama membaca `matrix[resource][role]`
 *    langsung, sehingga peran turunan (Supervisor/Staf Digital Marketing, Supervisor
 *    Keuangan) tampil "—" alias tanpa izin — padahal API-nya menjawab 200 karena izinnya
 *    datang dari warisan peran (`ROLE_INHERITS`) atau tambahan di kode (`ROLE_GRANTS`).
 *    Admin yang membaca layar itu akan menyimpulkan hal yang salah tentang siapa boleh
 *    melihat apa. Sekarang yang ditampilkan adalah izin EFEKTIF beserta ASAL-USULNYA.
 *
 * 2. **Janji fase yang tidak pernah datang.** Layar lama menulis "Penyuntingan matriks
 *    tersedia di fase berikut" padahal `PUT /api/admin/permissions` SUDAH ADA dan bekerja.
 *    Kemampuan backend tanpa pintu di layar sama saja dengan tidak ada.
 */

const ACTION_LABEL = {
  all: "semua", manage: "kelola", view: "lihat", view_all: "lihat semua",
  view_own: "lihat sendiri", create: "buat", update: "ubah", delete: "hapus",
  approve: "setujui", assign: "tugaskan", sign: "tanda tangan", verify: "verifikasi",
  override: "terobos", cancel: "batalkan",
};

const SOURCE_BADGE = {
  matrix: { text: "matriks", cls: "border-slate-300 bg-slate-100 text-slate-700" },
  inherited: { text: "warisan", cls: "border-violet-300 bg-violet-50 text-violet-700" },
  granted: { text: "dari kode", cls: "border-sky-300 bg-sky-50 text-sky-700" },
  full_access: { text: "akses penuh", cls: "border-emerald-300 bg-emerald-50 text-emerald-700" },
  revoked: { text: "dicabut admin", cls: "border-rose-300 bg-rose-50 text-rose-700" },
};

const sortActions = (list) => [...new Set(list)].sort();
const sameSet = (a, b) => sortActions(a || []).join("|") === sortActions(b || []).join("|");

export default function AdminPermissions() {
  const { can } = useAuth();
  const editable = can("permissions", "manage");

  const [server, setServer] = useState(null);      // jawaban backend apa adanya
  const [draft, setDraft] = useState(null);        // matriks yang sedang disunting
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [openCell, setOpenCell] = useState(null);  // "resource::role" yang sedang dibuka

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/admin/permissions");
      setServer(res.data.data);
      setDraft(JSON.parse(JSON.stringify(res.data.data.matrix || {})));
      setOpenCell(null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat hak akses.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const roles = useMemo(
    () => (server?.roles || []).filter((r) => !(server?.full_access_roles || []).includes(r)),
    [server],
  );
  const resources = useMemo(() => {
    const all = server?.resources || [];
    const needle = q.trim().toLowerCase();
    return needle ? all.filter((r) => r.toLowerCase().includes(needle)) : all;
  }, [server, q]);

  /** Izin efektif hasil SUNTINGAN (bukan hanya jawaban server) — meniru `rbac._role_perms`
   *  supaya pratinjau di layar sama dengan yang akan ditegakkan backend setelah disimpan. */
  const effective = useCallback((resource, role) => {
    if (!server) return { perms: [], sources: [] };
    const res = draft?.[resource] || {};
    const grants = (server.code_grants?.[role] || {})[resource] || [];
    const denied = server.denied_actions?.[role] || [];
    const inheritFrom = server.inherits?.[role];
    let perms = [];
    const sources = [];
    if (Object.prototype.hasOwnProperty.call(res, role)) {
      perms = res[role] || [];
      if (!perms.length) {
        return { perms: [], sources: ["revoked"], inheritedFrom: null, deniedByCode: [] };
      }
      sources.push("matrix");
    } else if (inheritFrom && (res[inheritFrom] || []).length) {
      perms = res[inheritFrom] || [];
      sources.push("inherited");
    }
    let out = [...perms];
    if (grants.length) { out = out.concat(grants); sources.push("granted"); }
    const blocked = sortActions(out.filter((p) => denied.includes(p)));
    out = out.filter((p) => !denied.includes(p));
    return {
      perms: sortActions(out),
      sources,
      inheritedFrom: sources.includes("inherited") ? inheritFrom : null,
      deniedByCode: blocked,
    };
  }, [draft, server]);

  const written = (resource, role) => {
    const res = draft?.[resource] || {};
    return Object.prototype.hasOwnProperty.call(res, role) ? (res[role] || []) : null;
  };

  const toggle = (resource, role, action) => {
    setDraft((prev) => {
      const next = { ...prev, [resource]: { ...(prev[resource] || {}) } };
      const base = written(resource, role);
      const eff = effective(resource, role);
      // Saat baris belum pernah ditulis, titik awal penyuntingan adalah izin EFEKTIF —
      // kalau dimulai dari kosong, mencentang satu aksi malah MENCABUT sisanya tanpa
      // admin menyadarinya (warisan peran ikut hilang).
      const current = base === null ? eff.perms : base;
      const has = current.includes(action);
      next[resource][role] = has
        ? current.filter((a) => a !== action)
        : sortActions([...current, action]);
      return next;
    });
  };

  const resetCell = (resource, role) => {
    setDraft((prev) => {
      const next = { ...prev, [resource]: { ...(prev[resource] || {}) } };
      const original = (server?.matrix?.[resource] || {});
      if (Object.prototype.hasOwnProperty.call(original, role)) {
        next[resource][role] = [...(original[role] || [])];
      } else {
        delete next[resource][role];
      }
      return next;
    });
  };

  /** Kembalikan sel ke NILAI BAWAAN KODE (bukan ke nilai tersimpan). Tanpa ini pencabutan
   *  yang SUDAH disimpan tidak bisa dibatalkan dari layar: `resetCell` hanya menyalin
   *  `server.matrix` yang kini justru berisi pencabutan itu, sehingga tombol Simpan tidak
   *  pernah aktif dan admin terpaksa mencentang ulang satu-satu. */
  const restoreDefault = (resource, role) => {
    setDraft((prev) => {
      const next = { ...prev, [resource]: { ...(prev[resource] || {}) } };
      const def = server?.defaults?.[resource] || {};
      if (Object.prototype.hasOwnProperty.call(def, role)) {
        next[resource][role] = [...(def[role] || [])];
      } else {
        // Bawaan tidak menulis baris untuk peran ini — hapus kuncinya supaya warisan
        // peran / tambahan kode hidup kembali.
        delete next[resource][role];
      }
      return next;
    });
  };

  const changes = useMemo(() => {
    if (!server || !draft) return [];
    const out = [];
    const seen = new Set([...Object.keys(server.matrix || {}), ...Object.keys(draft || {})]);
    seen.forEach((res) => {
      const a = server.matrix?.[res] || {};
      const b = draft?.[res] || {};
      new Set([...Object.keys(a), ...Object.keys(b)]).forEach((role) => {
        if ((server.full_access_roles || []).includes(role)) return;
        const av = Object.prototype.hasOwnProperty.call(a, role) ? (a[role] || []) : null;
        const bv = Object.prototype.hasOwnProperty.call(b, role) ? (b[role] || []) : null;
        if (av === null && bv === null) return;
        if (av !== null && bv !== null && sameSet(av, bv)) return;
        if (av === null || bv === null || !sameSet(av, bv)) {
          out.push({ resource: res, role, from: av, to: bv });
        }
      });
    });
    return out;
  }, [server, draft]);

  const save = async () => {
    if (!changes.length) { toast.info("Tidak ada perubahan untuk disimpan."); return; }
    setSaving(true);
    try {
      const res = await api.put("/admin/permissions", { matrix: draft });
      const n = (res.data.data.changes || []).length;
      toast.success(n
        ? `${n} perubahan hak akses tersimpan dan langsung berlaku.`
        : "Matriks tersimpan (izin efektif tidak berubah).");
      setServer((prev) => ({ ...prev, matrix: res.data.data.matrix,
        effective: res.data.data.effective }));
      setDraft(JSON.parse(JSON.stringify(res.data.data.matrix || {})));
      setOpenCell(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan hak akses.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingCards count={6} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={ADMIN.permsPage} className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <h1 className="page-title">Hak Akses (RBAC)</h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input data-testid={ADMIN.permsSearch} value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Cari resource…" className="search-field h-9 w-56 pl-9" />
          </div>
          {editable ? (
            <>
              <Button data-testid={ADMIN.permsReset} variant="outline" size="sm"
                disabled={!changes.length || saving}
                onClick={() => { setDraft(JSON.parse(JSON.stringify(server.matrix || {}))); setOpenCell(null); }}>
                <RotateCcw className="mr-1.5 h-4 w-4" /> Kembalikan
              </Button>
              <Button data-testid={ADMIN.permsSave} size="sm" disabled={!changes.length || saving}
                onClick={save}>
                <Save className="mr-1.5 h-4 w-4" />
                {saving ? "Menyimpan…" : `Simpan${changes.length ? ` (${changes.length})` : ""}`}
              </Button>
            </>
          ) : null}
        </div>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-1">
          <p>
            Yang ditampilkan adalah izin <b>efektif</b> — hasil akhir yang ditegakkan backend
            lewat <span className="font-mono text-xs">require_permission</span>, termasuk{" "}
            <b>warisan peran</b> dan <b>tambahan dari kode</b>, bukan hanya baris yang tertulis
            di matriks.
          </p>
          <p>{server?.notes?.revoke}</p>
          <p className="text-sky-800/80">{server?.notes?.full_access}</p>
          {!editable ? (
            <p data-testid={ADMIN.permsReadonly} className="font-medium">
              Peran Anda hanya boleh MELIHAT matriks ini; penyuntingan butuh izin
              “kelola hak akses”.
            </p>
          ) : null}
        </div>
      </div>

      {(server?.full_access_roles || []).length ? (
        <div data-testid={ADMIN.permsFullAccess}
          className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          <Lock className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            <b>{(server.full_access_roles || []).map(roleLabel).join(" & ")}</b> selalu
            berakses penuh dan sengaja tidak ditampilkan sebagai kolom — membatasi mereka dari
            layar ini bisa mengunci semua orang keluar.
          </p>
        </div>
      ) : null}

      {changes.length ? (
        <div data-testid={ADMIN.permsPending}
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <p className="font-medium">{changes.length} perubahan belum disimpan</p>
          <ul className="mt-1 space-y-0.5 text-[12px]">
            {changes.slice(0, 8).map((c) => (
              <li key={`${c.resource}-${c.role}`} data-testid={ADMIN.permsPendingRow}>
                <span className="font-mono">{c.resource}</span> · {roleLabel(c.role)}:{" "}
                {c.from === null ? "mengikuti bawaan" : (c.from.length ? c.from.map((a) => ACTION_LABEL[a] || a).join(", ") : "tidak boleh")}
                {" → "}
                <b>{c.to === null ? "mengikuti bawaan" : (c.to.length ? c.to.map((a) => ACTION_LABEL[a] || a).join(", ") : "tidak boleh")}</b>
              </li>
            ))}
            {changes.length > 8 ? <li>…dan {changes.length - 8} lainnya</li> : null}
          </ul>
        </div>
      ) : null}

      {!resources.length ? (
        <div data-testid={ADMIN.permsEmpty}
          className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground shadow-[var(--shadow-card)]">
          Tidak ada resource yang cocok dengan “{q}”. Kosongkan pencarian untuk melihat
          seluruh {server?.resources?.length || 0} resource.
        </div>
      ) : (
        <div data-testid={ADMIN.permsMatrix} className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <table className="w-full min-w-[1100px] text-sm">
            <thead className="bg-secondary/60 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="sticky left-0 z-10 bg-secondary/60 px-4 py-2.5 font-medium">Resource</th>
                {roles.map((r) => (
                  <th key={r} className="whitespace-nowrap px-3 py-2.5 font-medium">{roleLabel(r)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {resources.map((res) => (
                <tr key={res} data-testid={ADMIN.permsRow} className="align-top hover:bg-secondary/20">
                  <td className="sticky left-0 z-10 bg-card px-4 py-2.5 font-mono text-xs font-medium">{res}</td>
                  {roles.map((role) => {
                    const key = `${res}::${role}`;
                    const eff = effective(res, role);
                    const isOpen = openCell === key;
                    return (
                      <td key={role} className="px-3 py-2.5">
                        <button type="button" data-testid={ADMIN.permsCell}
                          data-resource={res} data-role={role}
                          onClick={() => setOpenCell(isOpen ? null : key)}
                          className={`w-full rounded-md border px-2 py-1.5 text-left transition ${
                            isOpen ? "border-primary bg-primary/5" : "border-transparent hover:border-slate-200 hover:bg-secondary/40"}`}>
                          {eff.perms.length ? (
                            <div className="flex flex-wrap gap-1">
                              {eff.perms.map((p) => (
                                <span key={p} className="rounded border bg-secondary px-1.5 py-0.5 text-[10px]">
                                  {ACTION_LABEL[p] || p}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span data-testid={ADMIN.permsCellNone}
                              className="text-[11px] text-muted-foreground">
                              {eff.sources.includes("revoked") ? "dicabut admin" : "tidak boleh"}
                            </span>
                          )}
                          {eff.sources.length ? (
                            <div className="mt-1 flex flex-wrap items-center gap-1">
                              {eff.sources.map((s) => (
                                <span key={s} data-testid={ADMIN.permsSource}
                                  className={`inline-flex items-center gap-1 rounded border px-1 py-0.5 text-[9px] uppercase ${SOURCE_BADGE[s]?.cls || ""}`}>
                                  {s === "inherited" ? <GitBranch className="h-2.5 w-2.5" /> : null}
                                  {s === "revoked" ? <Ban className="h-2.5 w-2.5" /> : null}
                                  {SOURCE_BADGE[s]?.text || s}
                                  {s === "inherited" && eff.inheritedFrom
                                    ? `: ${roleLabel(eff.inheritedFrom)}` : ""}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          {eff.deniedByCode.length ? (
                            <p className="mt-1 text-[9px] uppercase text-rose-600">
                              dilarang kode: {eff.deniedByCode.map((a) => ACTION_LABEL[a] || a).join(", ")}
                            </p>
                          ) : null}
                        </button>

                        {isOpen ? (
                          <div data-testid={ADMIN.permsEditor}
                            className="mt-2 min-w-[260px] rounded-lg border bg-background p-2 shadow-sm">
                            <p className="mb-1.5 text-[11px] font-medium">
                              {roleLabel(role)} · <span className="font-mono">{res}</span>
                            </p>
                            {!editable ? (
                              <p className="text-[11px] text-muted-foreground">
                                Hanya bisa dilihat — Anda tidak punya izin mengubah hak akses.
                              </p>
                            ) : (
                              <>
                                <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                                  {(server?.actions || []).map((a) => {
                                    const w = written(res, role);
                                    const checkedList = w === null ? eff.perms : w;
                                    const fromCode = ((server.code_grants?.[role] || {})[res] || []).includes(a);
                                    const blocked = (server.denied_actions?.[role] || []).includes(a);
                                    return (
                                      <label key={a}
                                        className={`flex items-center gap-1.5 text-[11px] ${blocked ? "opacity-50" : ""}`}>
                                        <input type="checkbox" data-testid={ADMIN.permsAction}
                                          data-action={a}
                                          disabled={blocked}
                                          checked={checkedList.includes(a)}
                                          onChange={() => toggle(res, role, a)} />
                                        <span className="whitespace-nowrap">{ACTION_LABEL[a] || a}</span>
                                        {fromCode ? (
                                          <span className="rounded border border-sky-300 bg-sky-50 px-1 text-[8px] uppercase text-sky-700">
                                            kode
                                          </span>
                                        ) : null}
                                      </label>
                                    );
                                  })}
                                </div>
                                {((server.code_grants?.[role] || {})[res] || []).length ? (
                                  <p className="mt-1.5 text-[10px] text-sky-700">
                                    Aksi bertanda “kode” dipasang di{" "}
                                    <span className="font-mono">rbac.ROLE_GRANTS</span> dan akan
                                    tetap berlaku kecuali seluruh aksi peran ini dikosongkan
                                    (pencabutan penuh).
                                  </p>
                                ) : null}
                                <div className="mt-2 flex items-center justify-between gap-2">
                                  <div className="flex items-center gap-2.5">
                                    <button type="button" data-testid={ADMIN.permsCellReset}
                                      onClick={() => resetCell(res, role)}
                                      title="Buang suntingan yang belum disimpan pada sel ini"
                                      className="text-[11px] font-medium text-primary hover:underline">
                                      Batalkan suntingan
                                    </button>
                                    <button type="button" data-testid={ADMIN.permsCellDefault}
                                      onClick={() => restoreDefault(res, role)}
                                      title="Kembalikan sel ini ke izin bawaan kode (termasuk membatalkan pencabutan yang sudah tersimpan)"
                                      className="text-[11px] font-medium text-primary hover:underline">
                                      Kembalikan ke bawaan
                                    </button>
                                  </div>
                                  <button type="button" data-testid={ADMIN.permsCellClose}
                                    onClick={() => setOpenCell(null)}
                                    className="text-[11px] text-muted-foreground hover:underline">
                                    Tutup
                                  </button>
                                </div>
                              </>
                            )}
                          </div>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
