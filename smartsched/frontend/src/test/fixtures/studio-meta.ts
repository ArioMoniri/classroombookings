/**
 * Test fixture (vitest only, never imported by app code): the Generator Studio `GET /studio/meta`
 * payload transcribed from the backend (`app/services/studio_rules.py::TEMPLATES / meta()` and
 * `app/services/studio.py::BUILTINS`), so the studio components can be rendered in jsdom.
 */
import { PERIODS } from "@/lib/time";

const t = (tr: string, en: string) => ({ tr, en });
const W = { low: 2, normal: 5, high: 8 } as const;
type Field = { name: string; type: string; param: string; required: boolean } & Record<string, unknown>;
const f = (name: string, type: string, param?: string, required = false, extra: Record<string, unknown> = {}): Field => ({ name, type, param: param ?? name, required, ...extra });
const APPLIES_TO = f("applies_to", "applies_to", "selector");

export const TEMPLATES = [
  { id: "keep_in_building", topic: "buildings", kind: "building_preference", title: t("Belirli blokta tut", "Keep in a building"), sentence: t("{applies_to} derslerini {building} blokta tut [{days}]", "Keep {applies_to} in building {building} [on {days}]"), fields: [APPLIES_TO, f("building", "building", undefined, true), f("days", "days")], default_hardness: "soft", default_weight: W.normal },
  { id: "no_classes_after", topic: "times", kind: "day_window", title: t("Belirli saatten sonra ders olmasın", "No classes after a time"), sentence: t("{applies_to} için {latest}'den sonra [veya {earliest}'den önce] ders olmasın", "No classes after {latest} [or before {earliest}] for {applies_to}"), fields: [APPLIES_TO, f("latest", "period", undefined, false, { min: 1, max: 18 }), f("earliest", "period", undefined, false, { min: 1, max: 18 })], default_hardness: "hard", default_weight: W.normal, note: t("Ders saatleri 40 dakikadır; 17:30, 12. dersin başlangıcıdır.", "Periods are 40 minutes. 17:30 is the start of P12.") },
  { id: "room_only_for", topic: "rooms", kind: "room_tags", title: t("Derslik sadece belirli program için", "Room only for a programme"), sentence: t("{tag} derslikleri sadece {applies_to} için", "{tag} rooms only for {applies_to}"), fields: [f("tag", "tag", "forbidden_tags", true), f("applies_to", "applies_to_others", "selector", false, { note: "the rule is stored for everyone *else*" })], default_hardness: "hard", default_weight: W.normal, note: t("Dersliği bir etiketle (ör. TIP) işaretleyin; diğer programlar bu etiketi kullanamaz.", "Tag the rooms (e.g. TIP); every other programme is kept out of that tag.") },
  { id: "never_use_room", topic: "rooms", kind: "room_forbid", title: t("Dersliği kullanma", "Never use a room"), sentence: t("{rooms} dersliğini {applies_to} için kullanma", "Never use room {rooms} for {applies_to}"), fields: [f("rooms", "rooms", "room_ids", true), APPLIES_TO], default_hardness: "hard", default_weight: W.normal },
  { id: "always_in_room", topic: "rooms", kind: "room_pin", title: t("Her zaman bu derslikte", "Always in a room"), sentence: t("{course} her zaman {rooms} dersliğinde [{from_date}'den itibaren]", "Always put {course} in room {rooms} [from {from_date}]"), fields: [f("course", "courses", "event_ids", true), f("rooms", "rooms", "room_ids", true), f("from_date", "date", "weeks")], default_hardness: "hard", default_weight: W.normal },
  { id: "prefer_rooms", topic: "rooms", kind: "room_preference", title: t("Derslik tercihi", "Prefer rooms"), sentence: t("{applies_to} için {rooms} tercih et", "Prefer room(s) {rooms} for {applies_to}"), fields: [f("rooms", "rooms", "room_ids", true, { ordered: true }), APPLIES_TO], default_hardness: "soft", default_weight: W.normal },
  { id: "same_room_as", topic: "rooms", kind: "same_room_group", title: t("Başka dersle aynı derslik", "Same room as another course"), sentence: t("{courses} dersleri aynı derslikte", "Same room as course {courses}"), fields: [f("courses", "courses", "event_ids", true, { min_items: 2 })], default_hardness: "soft", default_weight: W.high },
  { id: "same_room_every_week", topic: "rooms", kind: "same_room_across_weeks", title: t("Her hafta aynı derslik", "Same room every week"), sentence: t("{applies_to} her hafta aynı derslikte", "Same room every week for {applies_to}"), fields: [APPLIES_TO], default_hardness: "soft", default_weight: W.normal },
  { id: "needs_lab", topic: "rooms", kind: "room_tags", title: t("Bilgisayar laboratuvarı gerekli", "Needs a computer lab"), sentence: t("{applies_to} için {tag} gerekli", "{applies_to} needs a {tag} room"), fields: [APPLIES_TO, f("tag", "tag", "required_tags", true, { default: ["PC"] })], default_hardness: "hard", default_weight: W.normal },
  { id: "room_closed", topic: "rooms", kind: "room_closed", title: t("Derslik kapalı", "Room closed"), sentence: t("{room} {days} {periods} [{weeks}] kapalı", "Room {room} closed on {days} {periods} [{weeks}]"), fields: [f("room", "room", "room_id", true), f("days", "days", undefined, true), f("periods", "periods"), f("weeks", "weeks")], default_hardness: "hard", default_weight: W.normal },
  { id: "evening_in_buildings", topic: "programmes", kind: "evening_programs_in_buildings", title: t("İkinci öğretim belirli bloklarda", "Evening programmes in buildings"), sentence: t("İkinci öğretim {buildings} bloklarında", "Evening programmes in buildings {buildings}"), fields: [f("buildings", "buildings", undefined, true)], default_hardness: "soft", default_weight: W.normal },
  { id: "no_small_in_big", topic: "rooms", kind: "min_capacity_waste", title: t("Küçük sınıfları büyük amfiye koyma", "Don't put small classes in big halls"), sentence: t("Küçük sınıfları büyük amfiye koyma", "Don't put small classes in big halls"), fields: [f("unit", "number", undefined, false, { min: 1, max: 100, advanced: true, default: 10 })], default_hardness: "soft", default_weight: W.low },
  { id: "exam_gap", topic: "exams", kind: "exam_gap", title: t("Sınavlar arasında boşluk", "Gap between exams"), sentence: t("Aynı sınıfın sınavları arasında en az {n} ders saati", "Exams: at least {n} periods between exams of {applies_to}"), fields: [f("n", "number", "min_periods", true, { min: 0, max: 6 }), APPLIES_TO], default_hardness: "hard", default_weight: W.normal },
  { id: "max_exams_per_day", topic: "exams", kind: "max_exams_per_day", title: t("Günlük sınav sınırı", "Exams per day"), sentence: t("{applies_to} için günde en fazla {n} sınav", "Exams: at most {n} exams per day for {applies_to}"), fields: [f("n", "number", "n", true, { min: 1, max: 6 }), APPLIES_TO], default_hardness: "hard", default_weight: W.normal },
];

/** value = may an ADMIN switch it off in a draft? */
export const BUILTINS: Record<string, boolean> = { no_room_overlap: false, capacity: true, no_cohort_overlap: true, no_instructor_overlap: true };
export const BUILTIN_TEXT: Record<string, { tr: string; en: string }> = {
  no_room_overlap: t("Bir derslikte aynı anda tek ders", "One class per room at a time"),
  capacity: t("Derslik öğrencilere yetmeli", "The room must seat the class"),
  no_cohort_overlap: t("Aynı program ve sınıfın dersleri çakışmaz", "No clash for a programme-year"),
  no_instructor_overlap: t("Bir öğretim elemanı aynı anda iki derste olamaz", "No clash for an instructor"),
};

const ONLY_HARD = new Set(["room_closed"]);
const CATALOG_TITLES: Record<string, { tr: string; en: string }> = {
  building_preference: t("Bina tercihi", "Building preference"),
  day_window: t("Gün penceresi", "Day window"),
  room_tags: t("Derslik etiketleri", "Room tags"),
  room_forbid: t("Derslik yasağı", "Room forbid"),
  room_pin: t("Derslik sabitleme", "Room pin"),
  room_preference: t("Derslik tercihi", "Room preference"),
  same_room_group: t("Aynı derslik grubu", "Same room group"),
  same_room_across_weeks: t("Haftalar arası aynı derslik", "Same room across weeks"),
  room_closed: t("Derslik kapalı", "Room closed"),
  evening_programs_in_buildings: t("İkinci öğretim binaları", "Evening programmes in buildings"),
  min_capacity_waste: t("Kapasite uyumu", "Capacity fit"),
  exam_gap: t("Sınav arası boşluk", "Exam gap"),
  max_exams_per_day: t("Günlük sınav sınırı", "Max exams per day"),
  fixed_time: t("Sabit zaman", "Fixed time"),
};

export function catalogTitle(kind: string) {
  return CATALOG_TITLES[kind] ?? t(kind, kind);
}
export function allowedHardness(kind: string): ("hard" | "soft")[] {
  return ONLY_HARD.has(kind) ? ["hard"] : ["hard", "soft"];
}

export const MAPPING_ROLES = {
  course: t("Ders kodu", "Course code"),
  section: t("Şube", "Section"),
  program: t("Program / bölüm", "Programme / department"),
  year: t("Sınıf", "Class year"),
  enrolment: t("Öğrenci sayısı", "Students"),
  day: t("Gün", "Day"),
  time: t("Saat", "Time"),
  room: t("Derslik", "Room"),
  building: t("Blok", "Building"),
  mode: t("Eğitim şekli", "Mode"),
  note: t("Not / talep", "Note / request"),
};

export function studioMeta() {
  return {
    weight_scale: { ...W, default: W.normal, labels: { low: t("Düşük", "Low"), normal: t("Normal", "Normal"), high: t("Yüksek", "High") }, custom_range: [1, 10] },
    templates: TEMPLATES.map((tpl) => {
      const allowed = allowedHardness(tpl.kind);
      return { ...tpl, allowed_hardness: allowed, default_hardness: allowed.includes(tpl.default_hardness as "hard") ? tpl.default_hardness : allowed[0], params_schema: {}, catalog_title: catalogTitle(tpl.kind) };
    }),
    builtins: Object.entries(BUILTINS).map(([kind, disableable]) => ({ kind, title: BUILTIN_TEXT[kind], disableable, admin_only: true })),
    sources: { FILE: t("Dosya", "File"), ADMIN: t("Yönetici", "Admin"), AI: t("YZ", "AI"), UPLOAD: t("Yükleme", "Upload"), BUILTIN: t("Sistem", "Built-in") },
    hardness: {
      hard: { label: t("Kesin", "Must"), help: t("SmartSched bunu asla bozmaz. Mümkün değilse durur ve nedenini söyler.", "SmartSched will never break this. If it can't be done, it stops and tells you why.") },
      soft: { label: t("Mümkünse", "Try to"), help: t("SmartSched mümkün olduğunda uyar ve uyamadığı yerleri gösterir.", "SmartSched follows this whenever it can and shows you where it couldn't.") },
    },
    periods: PERIODS.map((p) => ({ index: p.index, start: p.start, end: p.end, label: `P${p.index}` })),
    mapping_roles: MAPPING_ROLES,
    catalog: Object.keys(CATALOG_TITLES).map((kind) => ({ kind, title: catalogTitle(kind), description: t("", ""), allowed_hardness: allowedHardness(kind), default_hardness: "soft" })),
  };
}
