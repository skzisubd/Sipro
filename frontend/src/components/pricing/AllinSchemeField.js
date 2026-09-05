import React, { useEffect, useState } from "react";
import { Lock, Receipt } from "lucide-react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { P75 } from "@/constants/testIds";

export const MANUAL_ROLES = ["finance_manager", "super_admin", "owner"];
const TR = { developer_borne: "ditanggung developer", customer_pass_through: "ditagih ke pembeli (titipan)" };

/**
 * AllinSchemeField — sales MEMILIH skema all-in; komponen ter-render read-only dari master.
 * Input manual hanya `finance_manager`/`superadmin`, wajib alasan, ter-audit di server.
 */
export default function AllinSchemeField({ value, onChange, unitId, price }) {
  const { user } = useAuth();
  const [schemes, setSchemes] = useState([]);
  const [preview, setPreview] = useState(null);
  const mayManual = MANUAL_ROLES.includes(user?.role);
  const v = value || { scheme_id: "", manual: false, items: [], reason: "" };

  useEffect(() => {
    api.get("/allin-schemes").then((r) => setSchemes(r.data.data || [])).catch(() => setSchemes([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!v.scheme_id || !price) { setPreview(null); onChange({ ...v, preview: null }); return; }
    api.get(`/allin-schemes/${v.scheme_id}/preview`, { params: { price } })
      .then((r) => { setPreview(r.data.data); onChange({ ...v, preview: r.data.data }); })
      .catch(() => setPreview(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v.scheme_id, price]);

  const set = (patch) => onChange({ ...v, ...patch });
  const setItem = (i, patch) => set({ items: v.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });

  return (
    <div className="space-y-2 rounded-lg border border-sky-200/70 bg-sky-50/40 p-3">
      <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-sky-900">
        <Receipt className="h-3.5 w-3.5" /> Biaya transaksi — skema all-in
      </p>
      {!v.manual ? (
        <>
          <Select value={v.scheme_id} onValueChange={(s) => set({ scheme_id: s })} disabled={!unitId}>
            <SelectTrigger data-testid={P75.allinSchemeSelect} aria-label="Skema all-in" className="bg-background">
              <SelectValue placeholder={unitId ? "Pilih skema biaya (all-in / exclude)" : "Pilih unit dulu"} />
            </SelectTrigger>
            <SelectContent>
              {schemes.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
          {preview ? (
            <div data-testid={P75.allinPreview} className="divide-y rounded-md border bg-background text-sm">
              {(preview.components || []).map((c) => (
                <div key={c.code} data-testid={P75.allinRow} data-code={c.code} data-treatment={c.treatment}
                  className="flex items-center justify-between gap-2 px-2 py-1.5">
                  <div className="min-w-0">
                    <p className="truncate">{c.name}</p>
                    <p className="text-[11px] text-muted-foreground">{c.formula} · {TR[c.treatment]}</p>
                  </div>
                  <span className="flex items-center gap-1 tabular-nums font-medium">
                    <Lock className="h-3 w-3 text-muted-foreground" /> {formatIDR(c.amount)}
                  </span>
                </div>
              ))}
              {!(preview.components || []).length ? (
                <p className="px-2 py-1.5 text-xs text-muted-foreground">Skema ini tidak punya komponen.</p>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              Nominal dihitung mesin dari master (rumus BPHTB memakai NPOPTKP proyek). Sales tidak mengetik angka.
            </p>
          )}
        </>
      ) : (
        <div className="space-y-2">
          {v.items.map((it, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2">
              <Input placeholder="Kode (mis. BPHTB)" value={it.code} className="bg-background uppercase"
                onChange={(e) => setItem(i, { code: e.target.value.toUpperCase() })} />
              <RupiahInput placeholder="Nominal" value={it.amount} className="bg-background"
                onChange={(e) => setItem(i, { amount: e.target.value })} />
              <Select value={it.treatment} onValueChange={(t) => setItem(i, { treatment: t })}>
                <SelectTrigger className="w-44 bg-background"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="developer_borne">Developer</SelectItem>
                  <SelectItem value="customer_pass_through">Pembeli (titipan)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ))}
          <Button type="button" size="sm" variant="secondary"
            onClick={() => set({ items: [...v.items, { code: "", amount: "", treatment: "customer_pass_through" }] })}>
            + Komponen
          </Button>
          <Label className="text-xs">Alasan input manual (wajib, ter-audit)</Label>
          <Textarea data-testid={P75.allinManualReason} rows={2} className="bg-background" value={v.reason}
            onChange={(e) => set({ reason: e.target.value })} />
        </div>
      )}
      {mayManual ? (
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" data-testid={P75.allinManualToggle} checked={!!v.manual}
            onChange={(e) => set({ manual: e.target.checked, scheme_id: "" })} />
          Input manual (khusus finance manager — wajib alasan)
        </label>
      ) : null}
    </div>
  );
}

export const allinPayload = (v) => {
  if (!v) return {};
  if (v.manual) {
    return {
      costs_manual: v.items.map((it) => ({ code: it.code, amount: Number(it.amount) || 0, treatment: it.treatment })),
      costs_manual_reason: v.reason || "",
    };
  }
  return v.scheme_id ? { allin_scheme_id: v.scheme_id } : {};
};
