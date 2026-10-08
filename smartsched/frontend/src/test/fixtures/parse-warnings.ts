/**
 * Test fixture (vitest only, never imported by app code): import parse warnings in the shape the
 * backend import job returns, covering the info / warning / error severities.
 */
import type { ParseWarning } from "@/lib/api/schemas";

export function sampleWarnings(): ParseWarning[] {
  return [
    { row: 12, field: "Sınıf", value: "1.Sınıf ", message: "Sınıf değeri '1.Sınıf ' → 1 olarak normalleştirildi", severity: "info" },
    { row: 44, field: "Ders Kodu", value: " YENİ DERS\nACU 311", message: "Önek kaldırıldı → ACU 311", severity: "info" },
    { row: 87, field: "Derse Kayıtlanacak Öğrenci Sayısı", value: "12:30:00", message: "Satır kaymış görünüyor; öğrenci sayısı okunamadı", severity: "error" },
    { row: 103, field: "AKTS", value: "Çarşamba", message: "AKTS sütununda gün adı var; satır kaymış", severity: "error" },
    { row: 215, field: "Dersin Günü", value: "Perşembe/Cuma", message: "İki gün belirtilmiş; iki toplantı oluşturuldu", severity: "warning" },
    { row: 232, field: "Dersin Başlangıç Saati", value: "09.00", message: "Izgaraya uymayan saat → 09:20'ye yuvarlandı", severity: "warning" },
    { row: 310, field: "Derslik Talebi", value: "72 kişilik C blok 601-602 vb", message: "Kapasite + bina tercihi çıkarıldı (72, C)", severity: "info" },
    { row: 402, field: "Dersliğin Kullanılacağı Haftalar", value: "1-5. HAFTALAR DERSLİKTE, 6-14 UZEM", message: "Hafta deseni 1–5 olarak alındı", severity: "warning" },
    { row: 517, field: "K", value: "4..5", message: "Kredi '4..5' → 4.5", severity: "info" },
    { row: 640, field: "Dersin Öğretim Şekli", value: "Derslik", message: "'Derslik' → Yüz yüze olarak yorumlandı", severity: "info" },
    { row: 731, field: "Dönemin Tamamı Derslikte Yapılacak", value: "70% derslikte", message: "Yüzde değeri; haftalar belirsiz, hepsi varsayıldı", severity: "warning" },
    { row: 1288, field: "Yarıyıl", value: "Bilim Tarihi ", message: "Yarıyıl sütununda ders adı var; boş bırakıldı", severity: "error" },
  ];
}
