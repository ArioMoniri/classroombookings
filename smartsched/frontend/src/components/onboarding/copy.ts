/**
 * Onboarding strings added by the design-system overhaul (2026-10-15) for the intake contract (rows, dry run,
 * memory, viewer mode). Kept beside the screen, not in messages/*.json, because other agents edit those files
 * concurrently; move them into the catalogues when the onboarding namespace is next touched.
 */
import { useI18n } from "@/lib/i18n/provider";

const tr = {
  steps: ["Dosyalar", "İnceleme", "Fark", "Kaydet"],
  stepsLabel: "Aşamalar",
  dropTitle: "Dosyaları bırakın veya seçin",
  dropHint: "Derslik listesi, ders/talep listesi, mevcut programlar, sınav listeleri, takvim, personel listesi, kural notları: .xlsx, .csv, .ods, .json, .xml, .ics, .docx, .pdf, .txt, .eml, görseller.",
  choose: "Dosya seç",
  colName: "Ad",
  colType: "Tür",
  colSize: "Boyut",
  colRoute: "Yol",
  colStatus: "Durum",
  colPhase: "Aşama",
  direct: "Doğrudan",
  ai: "YZ",
  directHint: "Sunucuda doğrudan okunur, dışarı bir şey gönderilmez",
  aiHint: "Yapay zekâ ile okunur",
  remove: (name: string) => `${name} dosyasını çıkar`,
  start: (n: number) => `Başlat · ${n} dosya`,
  startAi: "YZ ile oku ve başlat",
  attachment: "ek",
  summary: (ok: number, failed: number) => `${ok} dosya okundu · ${failed} başarısız`,
  rerunning: "Değiştirdiğiniz eşleme için dosyalar yeniden okunuyor. Bitince kaydedebilirsiniz.",
  remembered: (date: string, job: string | number) => `${date} tarihli ${job} numaralı işten hatırlandı`,
  stillDecide: "Yine de karar vermeniz gerekiyor.",
  applySuggestion: "Öneriyi uygula",
  viewerOnly: "Bu işin içeriğini görme izniniz yok; yalnız sayılar gösteriliyor.",
  rowsTitle: "YZ ile okunan satırlar",
  rowsHint: "Her YZ satırı siz karar verene kadar bekler. Toplu onay en çok 50 satır ve onay ister; düşük güvenli satırlar tek tek onaylanır.",
  rowsPending: (n: number) => `${n} satır bekliyor`,
  rowsNone: "Bekleyen YZ satırı yok.",
  accept: "Onayla",
  reject: "Reddet",
  acceptSelected: (n: number) => `Seçili ${n} satırı onayla`,
  bulkConfirm: (n: number) => `${n} YZ satırını birlikte onaylamak üzeresiniz. Satırlar dosyadaki değerlerle yazılacak.`,
  confirm: "Onayla",
  cancel: "Vazgeç",
  lowConfidence: "düşük güven",
  provenance: "Kaynak",
  select: (id: string) => `${id} satırını seç`,
  diff: "Farkı göster",
  diffTitle: "Kaydetmeden önce fark",
  diffHint: "Aynı yazıcı geri alınan bir işlemde çalıştı; veritabanı değişmedi.",
  diffCols: { entity: "Kayıt", create: "Yeni", update: "Değişecek", unchanged: "Aynı", conflict: "Çakışan" },
  onConflict: "Planlamacının düzelttiği bir değer dosyada değişmişse",
  keep: "Düzeltmeyi koru",
  take: "Dosyadakini al",
  conflictRows: (n: number) => `${n} çakışan satır`,
  pendingCommit: "Bekleyen YZ satırları var; kaydetmeden önce karar verin.",
}
type Copy = { [K in keyof typeof tr]: (typeof tr)[K] extends (...a: infer A) => string ? (...a: A) => string : (typeof tr)[K] }

const en: Copy = {
  steps: ["Files", "Review", "Diff", "Save"],
  stepsLabel: "Steps",
  dropTitle: "Drop files or choose them",
  dropHint: "Room lists, class/request lists, existing timetables, exam lists, calendars, staff lists, rule notes: .xlsx, .csv, .ods, .json, .xml, .ics, .docx, .pdf, .txt, .eml, images.",
  choose: "Choose files",
  colName: "Name",
  colType: "Type",
  colSize: "Size",
  colRoute: "Route",
  colStatus: "Status",
  colPhase: "Phase",
  direct: "Direct",
  ai: "AI",
  directHint: "Read on the server; nothing leaves it",
  aiHint: "Read with the AI model",
  remove: (name: string) => `Remove ${name}`,
  start: (n: number) => `Start · ${n} ${n === 1 ? "file" : "files"}`,
  startAi: "Read with AI and start",
  attachment: "attachment",
  summary: (ok: number, failed: number) => `${ok} files read · ${failed} failed`,
  rerunning: "The files are being read again for your mapping change. You can save when it finishes.",
  remembered: (date: string, job: string | number) => `remembered from ${date} / job ${job}`,
  stillDecide: "You still need to decide.",
  applySuggestion: "Apply the suggestion",
  viewerOnly: "You may not see this job's content; only the counts are shown.",
  rowsTitle: "Rows read by AI",
  rowsHint: "Every AI row waits until you decide. Bulk approval takes at most 50 rows and a confirmation; low-confidence rows are approved one at a time.",
  rowsPending: (n: number) => `${n} rows pending`,
  rowsNone: "No AI rows are pending.",
  accept: "Accept",
  reject: "Reject",
  acceptSelected: (n: number) => `Accept ${n} selected`,
  bulkConfirm: (n: number) => `You are about to accept ${n} AI rows together. They will be written with the values read from the files.`,
  confirm: "Confirm",
  cancel: "Cancel",
  lowConfidence: "low confidence",
  provenance: "Source",
  select: (id: string) => `Select row ${id}`,
  diff: "Show the diff",
  diffTitle: "Diff before saving",
  diffHint: "The same writer ran in a rolled-back transaction; the database did not change.",
  diffCols: { entity: "Record", create: "New", update: "Will change", unchanged: "Same", conflict: "Conflict" },
  onConflict: "When a planner's correction changed in the file",
  keep: "Keep the correction",
  take: "Take the file's value",
  conflictRows: (n: number) => `${n} conflicting rows`,
  pendingCommit: "AI rows are still pending; decide them before saving.",
}

export function useOnboardingCopy(): Copy {
  const { locale } = useI18n();
  return locale === "tr" ? tr : en;
}

const STRUCTURED = /\.(xlsx|xlsm|xls|csv|tsv|ods|json|xml|ics)$/i;
/** Predicted route from the extension (the server's intake agent confirms it): structured → Doğrudan, else YZ. */
export function predictedRoute(name: string): "direct" | "ai" {
  return STRUCTURED.test(name) ? "direct" : "ai";
}
