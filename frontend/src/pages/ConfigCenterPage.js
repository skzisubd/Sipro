import React from "react";
import { SlidersHorizontal } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import SettingsPanel from "@/components/config/SettingsPanel";
import DocRequirementsPanel from "@/components/config/DocRequirementsPanel";
import PriceComponentPanel from "@/components/config/PriceComponentPanel";
import AddonPanel from "@/components/config/AddonPanel";
import PricingPanel from "@/components/config/PricingPanel";
import UnitTypePanel from "@/components/config/UnitTypePanel";
import NumberingPanel from "@/components/config/NumberingPanel";
// Fase 57A — termin pembayaran berhenti menjadi angka mati di dalam kode.
import PaymentSchemePanel from "@/components/config/PaymentSchemePanel";
import IntegrationHealthTab from "@/components/ads/IntegrationHealthTab";
import CostComponentPanel from "@/components/config/CostComponentPanel";
import AllinSchemePanel from "@/components/config/AllinSchemePanel";
import KprDisbursementSchemePanel from "@/components/config/KprDisbursementSchemePanel";
import LeadScorePanel from "@/components/config/LeadScorePanel";
import WaIntegrationPanel from "@/components/config/WaIntegrationPanel";
import { CONFIG, LEADSCORE, NUMBERING, P57, P75, PRICING, P94 } from "@/constants/testIds";

/**
 * PUSAT KONFIGURASI (Fase 39) — satu menu untuk semua kendali bisnis, sesuai permintaan
 * owner: "buatkan satu menu khusus konfigurasi, semua fitur konfigurasi kontrolnya di menu
 * dedicated ini".
 *
 * Sebelumnya kendali tersebar: sebagian di Admin › Master Data, sebagian hanya ada sebagai
 * angka mati di dalam kode (tidak bisa diubah tanpa deploy).
 */
export default function ConfigCenterPage() {
  return (
    <div data-testid={CONFIG.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <SlidersHorizontal className="h-5 w-5 text-primary" />
        <div>
          <h1 className="page-title">Pusat Konfigurasi</h1>
          <p className="page-desc">
            Aturan bisnis, dokumen syarat, komponen biaya, skema pembayaran, spek tambahan, tipe unit, penomoran, dan
            kesiapan integrasi pihak ketiga — semuanya bisa diubah tanpa mengubah kode.
          </p>
        </div>
      </div>

      <Tabs defaultValue="rules" className="space-y-4">
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={CONFIG.tabRules} value="rules">Aturan Bisnis</TabsTrigger>
          <TabsTrigger data-testid={CONFIG.tabDocs} value="docs">Dokumen Syarat</TabsTrigger>
          <TabsTrigger data-testid={CONFIG.tabPrice} value="price">Komponen Biaya</TabsTrigger>
          <TabsTrigger data-testid={P75.tabAllin} value="allin">Biaya All-in</TabsTrigger>
          <TabsTrigger data-testid={P75.tabKprDisb} value="kprdisb">Pencairan KPR</TabsTrigger>
          <TabsTrigger data-testid={P57.configTab} value="scheme">
            Skema Pembayaran
          </TabsTrigger>
          <TabsTrigger data-testid={CONFIG.tabAddon} value="addon">Spek Tambahan</TabsTrigger>
          <TabsTrigger data-testid={PRICING.tab} value="pricing">Harga &amp; Promo</TabsTrigger>
          <TabsTrigger data-testid={LEADSCORE.tab} value="leadscore">Skor Lead</TabsTrigger>
          <TabsTrigger data-testid={CONFIG.tabUnitType} value="types">Tipe Unit</TabsTrigger>
          <TabsTrigger data-testid={NUMBERING.tab} value="numbering">Penomoran</TabsTrigger>
          <TabsTrigger data-testid={CONFIG.tabIntegration} value="integration">
            Integrasi
          </TabsTrigger>
          <TabsTrigger data-testid={P94.configTab} value="whatsapp">Integrasi WhatsApp</TabsTrigger>
        </TabsList>
        <TabsContent value="rules"><SettingsPanel /></TabsContent>
        <TabsContent value="docs"><DocRequirementsPanel /></TabsContent>
        <TabsContent value="price"><PriceComponentPanel /></TabsContent>
        <TabsContent value="allin" className="space-y-6"><CostComponentPanel /><AllinSchemePanel /></TabsContent>
        <TabsContent value="kprdisb"><KprDisbursementSchemePanel /></TabsContent>
        <TabsContent value="scheme"><PaymentSchemePanel /></TabsContent>
        <TabsContent value="addon"><AddonPanel /></TabsContent>
        <TabsContent value="pricing"><PricingPanel /></TabsContent>
        <TabsContent value="leadscore"><LeadScorePanel /></TabsContent>
        <TabsContent value="types"><UnitTypePanel /></TabsContent>
        <TabsContent value="numbering"><NumberingPanel /></TabsContent>
        {/* Fase 43 — kesiapan kredensial integrasi (spec docs/v2/30 §2) memakai KOMPONEN YANG
            SAMA dengan tab "Status Integrasi" di halaman Atribusi & CAPI: satu sumber tampilan,
            supaya admin dan tim marketing tidak pernah melihat status yang berbeda. */}
        <TabsContent value="integration"><IntegrationHealthTab /></TabsContent>
        <TabsContent value="whatsapp"><WaIntegrationPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
