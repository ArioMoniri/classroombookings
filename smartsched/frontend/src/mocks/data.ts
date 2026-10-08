/**
 * Deterministic fake data modelled on docs/DATA_ANALYSIS.md.
 * Rooms, periods, programmes and course codes are the real ones; sections are generated
 * with a seeded PRNG so every reload (and every Playwright run) sees the same world.
 */
import { PERIODS, rangesOverlap } from "@/lib/time";
import type {
  Assignment,
  Block,
  Building,
  ChatMessage,
  Constraint,
  Diagnosis,
  ExamRequest,
  ImportJob,
  MeetingRequest,
  ParseWarning,
  Program,
  Room,
  RoomTag,
  ScheduleRun,
  Settings,
  Term,
  User,
  Week,
} from "@/lib/api/schemas";

/* ----------------------------------------------------------------------------------- PRNG */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rnd = mulberry32(20260207);
const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(rnd() * arr.length)];
const between = (min: number, max: number): number => min + Math.floor(rnd() * (max - min + 1));

/* --------------------------------------------------------------------------------- Terms */
export const terms: Term[] = [
  { id: 1, code: "2026-BAHAR", name: "2026 Bahar", kind: "REGULAR", start_date: "2026-02-02", end_date: "2026-05-31", week_count: 16, is_active: true },
  { id: 2, code: "2026-FINAL", name: "2026 Final", kind: "FINAL", start_date: "2026-06-01", end_date: "2026-06-14", week_count: 2, is_active: false },
  { id: 3, code: "2026-GUZ", name: "2026-2027 Güz", kind: "REGULAR", start_date: "2026-09-28", end_date: "2027-01-24", week_count: 16, is_active: false },
];

function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

export const weeks: Week[] = [
  ...Array.from({ length: 16 }, (_, i): Week => {
    const index = i + 1;
    const kind: Week["kind"] = index === 1 ? "LECTURE" : index === 15 || index === 16 ? "EXAM" : index === 9 ? "HOLIDAY" : "LECTURE";
    const label = index === 1 ? "2 - 8 Şubat Bahar Dönem Açılış" : index === 9 ? "Bayram tatili" : index >= 15 ? `Final ${index - 14}` : `${index}. hafta`;
    return { id: index, term_id: 1, index, start_date: addDays("2026-02-02", (index - 1) * 7), kind, label };
  }),
  { id: 101, term_id: 2, index: 1, start_date: "2026-06-01", kind: "EXAM", label: "Final 1 - 7 Haziran" },
  { id: 102, term_id: 2, index: 2, start_date: "2026-06-08", kind: "EXAM", label: "Final 8 - 14 Haziran" },
];

/* --------------------------------------------------------------------------------- Rooms */
export const buildings: Building[] = [
  { id: 1, code: "A", name: "A Blok" },
  { id: 2, code: "B", name: "B Blok" },
  { id: 3, code: "C", name: "C Blok" },
  { id: 4, code: "D", name: "D Blok" },
];

type RoomSeed = [code: string, capacity: number, tags?: RoomTag[], exam?: number, notes?: string];
const ROOM_SEEDS: RoomSeed[] = [
  ["A 204", 156, ["AMPHI"], 74], ["A 203", 148, ["AMPHI", "TIP"], 70, "Tıp Fakültesi — planlama için Gözde Ayrancıgil 4073"],
  ["C 201", 126, ["AMPHI"], 60], ["A 207", 120, ["AMPHI"], 58], ["A 102", 96, [], 46], ["A 201", 96, ["TIP"], 46, "Tıp Fakültesi"],
  ["A 202", 96, ["TIP"], 46, "Tıp Fakültesi"], ["A 205", 94, [], 46], ["A 206", 92, [], 44], ["D 106", 82, [], 40],
  ["A 307", 70, [], 34], ["C 301", 72, [], 36], ["C 302", 72, [], 36], ["C 401", 72, [], 36], ["C 402", 72, [], 36],
  ["C 501", 72, [], 36], ["C 502", 72, [], 36], ["C 601", 72, [], 36], ["C 602", 72, [], 36],
  ["A 305", 64, [], 32], ["B 202", 64, [], 32], ["B 203", 64, [], 32], ["B 204", 64, [], 32], ["B 205", 64, [], 32], ["B 206", 64, [], 32],
  ["A 101", 58, [], 30], ["A 106", 58, [], 30], ["A 107", 58, [], 30], ["A 108", 58, [], 30], ["A 109", 58, [], 30],
  ["A 306", 38, [], 20], ["A 308", 42, [], 22], ["C 303", 45, [], 22], ["C 403", 45, [], 22], ["C 503", 45, [], 22], ["C 603", 45, [], 22],
  ["C 304", 40, [], 20], ["C 404", 40, [], 20], ["C 504", 40, [], 20], ["C 604", 40, [], 20],
  ["B 201", 30, [], 16], ["B 406", 30, [], 16], ["B 407", 30, [], 16], ["C z01", 30, [], 16], ["C 205", 30, [], 16], ["C 306", 30, [], 16],
  ["C 406", 30, [], 16], ["C 506", 30, [], 16], ["C 606", 30, [], 16], ["C 305", 32, [], 16], ["C 405", 32, [], 16], ["C 505", 32, [], 16], ["C 605", 32, [], 16],
  ["A 103", 47, ["PC"], 47, "Bilgisayar laboratuvarı"], ["A 104", 41, ["PC"], 41, "Bilgisayar laboratuvarı"], ["A 105", 60, ["PC"], 60, "Bilgisayar laboratuvarı"],
  ["B 207", 60, ["PC"], 60, "Bilgisayar laboratuvarı"], ["B BİLGİ LAB", 30, ["PC"], 30],
  ["A 301", 40, ["LAB"], 20, "Multidisiplin laboratuvarı"], ["A 302", 40, ["LAB"], 20, "Multidisiplin laboratuvarı"],
  ["D 107", 10, [], 10],
];

const PHOTO_SEEDS = ["A 204", "A 203", "C 201", "A 105", "B 207", "A 101", "C 301", "D 106"];

export const rooms: Room[] = ROOM_SEEDS.map(([display, capacity, tags = [], exam, notes], i) => {
  const bcode = display[0];
  const building = buildings.find((b) => b.code === bcode) ?? buildings[0];
  const code = display.replace(/\s+/g, "").toLocaleUpperCase("tr-TR");
  const floorMatch = /^[A-D]\s?([zZ]?)(\d)/.exec(display);
  const floor = floorMatch ? (floorMatch[1] ? 0 : Number(floorMatch[2])) : null;
  return {
    id: i + 1,
    building_id: building.id,
    building_code: building.code,
    code,
    display_name: display,
    floor,
    capacity,
    exam_capacity: exam ?? Math.round(capacity / 2),
    tags,
    is_bookable: !tags.includes("LAB"),
    notes: notes ?? null,
    photo_url: PHOTO_SEEDS.includes(display) ? `https://picsum.photos/seed/${code}/640/400` : null,
    legacy_crbs_room_id: 100 + i,
    utilisation: null,
  };
});

export const roomByCode = new Map(rooms.map((r) => [r.code, r]));
export function findRoom(text: string): Room | undefined {
  return roomByCode.get(text.replace(/\s+/g, "").toLocaleUpperCase("tr-TR"));
}

/* ----------------------------------------------------------------------------- Programs */
interface ProgramSeed {
  name: string;
  faculty: string;
  facultyId: number;
  evening?: boolean;
  prefix: string[];
}
const PROGRAM_SEEDS: ProgramSeed[] = [
  { name: "Tıp", faculty: "Tıp Fakültesi", facultyId: 1, prefix: ["TIP", "ANA", "FZY"] },
  { name: "Eczacılık", faculty: "Eczacılık Fakültesi", facultyId: 2, prefix: ["ECZ", "PHA"] },
  { name: "Hemşirelik", faculty: "Sağlık Bilimleri Fakültesi", facultyId: 3, prefix: ["HEM", "NRS"] },
  { name: "Fizyoterapi ve Rehabilitasyon", faculty: "Sağlık Bilimleri Fakültesi", facultyId: 3, prefix: ["FTR"] },
  { name: "Beslenme ve Diyetetik", faculty: "Sağlık Bilimleri Fakültesi", facultyId: 3, prefix: ["BES", "NUT"] },
  { name: "Biyomedikal Mühendisliği", faculty: "MDBF", facultyId: 4, prefix: ["BME"] },
  { name: "Bilgisayar Mühendisliği", faculty: "MDBF", facultyId: 4, prefix: ["BIL", "CSE"] },
  { name: "Elektrik-Elektronik Mühendisliği", faculty: "MDBF", facultyId: 4, prefix: ["EEE"] },
  { name: "Moleküler Biyoloji ve Genetik", faculty: "MDBF", facultyId: 4, prefix: ["MBG"] },
  { name: "Psikoloji", faculty: "İnsan ve Toplum Bilimleri Fakültesi", facultyId: 5, prefix: ["PSI", "PSY"] },
  { name: "Sosyoloji", faculty: "İnsan ve Toplum Bilimleri Fakültesi", facultyId: 5, prefix: ["SOS"] },
  { name: "İşletme", faculty: "İİSBF", facultyId: 6, prefix: ["ISL", "BUS"] },
  { name: "Uluslararası Ticaret ve Lojistik", faculty: "İİSBF", facultyId: 6, prefix: ["UTL"] },
  { name: "Hukuk", faculty: "Hukuk Fakültesi", facultyId: 7, prefix: ["HUK"] },
  { name: "Anestezi (İÖ)", faculty: "Sağlık Hizmetleri MYO", facultyId: 8, evening: true, prefix: ["ANS"] },
  { name: "İlk ve Acil Yardım (İÖ)", faculty: "Sağlık Hizmetleri MYO", facultyId: 8, evening: true, prefix: ["ACU"] },
  { name: "Optisyenlik", faculty: "Sağlık Hizmetleri MYO", facultyId: 8, prefix: ["OPT"] },
];
export const programs: Program[] = PROGRAM_SEEDS.map((p, i) => ({ id: i + 1, faculty_id: p.facultyId, faculty_name: p.faculty, name: p.name, is_evening: p.evening ?? false }));

const COURSE_NAMES: Record<string, string[]> = {
  TIP: ["Tıbbi Biyokimya", "Anatomi", "Histoloji", "Fizyoloji", "Patoloji"],
  ANA: ["Anatomi I", "Anatomi II"],
  FZY: ["Fizyoloji I", "Fizyoloji II"],
  ECZ: ["Farmasötik Kimya", "Farmakognozi", "Farmasötik Teknoloji", "Klinik Eczacılık"],
  PHA: ["Pharmacology I", "Pharmacology II", "Toxicology"],
  HEM: ["Hemşirelik Esasları", "İç Hastalıkları Hemşireliği", "Cerrahi Hastalıklar Hemşireliği", "Halk Sağlığı Hemşireliği"],
  NRS: ["Fundamentals of Nursing", "Nursing Ethics", "Pediatric Nursing"],
  FTR: ["Kinezyoloji", "Elektroterapi", "Nörolojik Rehabilitasyon"],
  BES: ["Beslenme İlkeleri", "Toplu Beslenme Sistemleri", "Klinik Beslenme"],
  NUT: ["Nutrition Biochemistry", "Diet Therapy"],
  BME: ["Biyomedikal Enstrümantasyon", "Biyomalzemeler", "Tıbbi Görüntüleme", "Biyosinyal İşleme"],
  BIL: ["Programlamaya Giriş", "Veri Yapıları", "Veritabanı Sistemleri", "İşletim Sistemleri"],
  CSE: ["Algorithms", "Software Engineering"],
  EEE: ["Devre Teorisi", "Elektronik I", "Sinyaller ve Sistemler"],
  MBG: ["Genetik", "Hücre Biyolojisi", "Moleküler Biyoloji", "Biyoinformatik"],
  PSI: ["Psikolojiye Giriş", "Gelişim Psikolojisi", "Sosyal Psikoloji", "Araştırma Yöntemleri"],
  PSY: ["Cognitive Psychology", "Statistics for Psychology"],
  SOS: ["Sosyolojiye Giriş", "Toplumsal Cinsiyet", "Kent Sosyolojisi"],
  ISL: ["İşletmeye Giriş", "Pazarlama", "Finansal Muhasebe", "Örgütsel Davranış"],
  BUS: ["Business Statistics", "Strategic Management"],
  UTL: ["Lojistik Yönetimi", "Dış Ticaret İşlemleri", "Tedarik Zinciri"],
  HUK: ["Medeni Hukuk", "Anayasa Hukuku", "Borçlar Hukuku", "Ceza Hukuku"],
  ANS: ["Anestezi Uygulamaları", "Klinik Anestezi", "Reanimasyon"],
  ACU: ["Acil Hasta Bakımı", "Travma", "Resüsitasyon"],
  OPT: ["Optik", "Göz Hastalıkları", "Kontakt Lens"],
  MAT: ["Matematik I", "Matematik II", "Lineer Cebir"],
  ENG: ["English I", "English II"],
  FIZ: ["Fizik I", "Fizik II"],
};

const INSTRUCTORS = [
  "Prof. Dr. Ayşe Kaya", "Doç. Dr. Mehmet Yılmaz", "Dr. Öğr. Üyesi Elif Demir", "Öğr. Gör. Can Aksoy", "Prof. Dr. Zeynep Şahin",
  "Doç. Dr. Burak Çelik", "Dr. Öğr. Üyesi Selin Arslan", "Öğr. Gör. Deniz Koç", "Prof. Dr. İsmail Öztürk", "Dr. Öğr. Üyesi Gizem Yıldız",
  "Doç. Dr. Murat Aydın", "Dr. Öğr. Üyesi Nur Polat", "Öğr. Gör. Emre Kurt", "Prof. Dr. Hülya Erdoğan", "Dr. Öğr. Üyesi Okan Taş",
  "Biyofizik Anabilim Dalı", "Doç. Dr. Pınar Güneş", "Dr. Öğr. Üyesi Tolga Bulut",
];

const REQUEST_TEXTS = [
  "A 105", "A103 (Bilg. Lab. Zorunlu)", "A Blok'ta Derslik", "72 kişilik C blok 601-602 vb", "Derslik", "1 derslik", "C Blok", "B 207",
  "A 204", "A301-A302-A303 MULTİDİSİPLİN", "--", "A 2. kat amfi", "Büyük amfi", "DERSLİK+HASTANE", "C 301 veya C 302",
];

/* ------------------------------------------------------------------------- Meeting requests */
const MODES: MeetingRequest["mode"][] = ["F2F", "F2F", "F2F", "F2F", "F2F", "F2F", "HYBRID", "ONLINE", "UZEM", "HOSPITAL"];

function makeWarnings(id: number, start: string | null, roomText: string | null): ParseWarning[] {
  const w: ParseWarning[] = [];
  if (start && !["08:30", "09:20", "10:10", "11:00", "11:50", "12:40", "13:30", "14:20", "15:10", "16:00", "16:50", "17:30", "18:00", "18:50", "19:40", "20:30", "21:20", "22:10"].includes(start)) {
    w.push({ row: id + 1, field: "Dersin Başlangıç Saati", value: start, message: "Saat 50 dakikalık ızgaraya uymuyor; en yakın ders saatine yuvarlandı", severity: "warning" });
  }
  if (roomText === "--") w.push({ row: id + 1, field: "Derslik Talebi", value: roomText, message: "Derslik talebi boş; sadece kapasiteye göre planlanacak", severity: "info" });
  if (roomText === "DERSLİK+HASTANE") w.push({ row: id + 1, field: "Derslik Talebi", value: roomText, message: "Karma talep: derslik + hastane; sadece derslik kısmı planlanır", severity: "warning" });
  return w;
}

export const meetingRequests: MeetingRequest[] = [];
{
  let id = 1;
  let sectionId = 1;
  const DAYS = [1, 1, 2, 2, 3, 3, 4, 4, 5];
  for (const program of programs) {
    const seed = PROGRAM_SEEDS[program.id - 1];
    const perProgram = program.is_evening ? 8 : 14;
    for (let k = 0; k < perProgram; k++) {
      const prefix = k % 5 === 4 ? pick(["MAT", "ENG", "FIZ"]) : pick(seed.prefix);
      const names = COURSE_NAMES[prefix] ?? ["Ders"];
      const number = 100 * between(1, 4) + between(1, 30);
      const code = `${prefix} ${number}`;
      const mode = pick(MODES);
      const roomed = mode === "F2F" || mode === "HYBRID";
      const day = roomed ? pick(DAYS) : null;
      const duration = between(2, 4);
      const startBase = program.is_evening ? between(13, 16 - duration + 1) : between(1, 11 - duration + 1);
      const start = roomed ? startBase : null;
      const end = roomed && start !== null ? start + duration - 1 : null;
      const enrolment = between(12, program.name === "Tıp" ? 150 : 90);
      const roomText = roomed ? pick(REQUEST_TEXTS) : null;
      const startTime = start !== null ? (rnd() < 0.08 ? "09:00" : PERIODS[start - 1].start) : null;
      const warnings = makeWarnings(id, startTime, roomText);
      const needsReview = warnings.some((w) => w.severity === "warning") || rnd() < 0.05;
      const pinned = roomText ? findRoom(roomText.replace(/\(.*\)/, "").trim()) : undefined;
      const tags: RoomTag[] = roomText?.includes("Bilg") ? ["PC"] : [];
      meetingRequests.push({
        id,
        section_id: sectionId,
        course_code: code,
        course_name: pick(names),
        section_label: k % 7 === 6 ? "2" : "1",
        program_id: program.id,
        program_name: program.name,
        class_year: Math.floor(number / 100),
        enrolment,
        instructor: pick(INSTRUCTORS),
        mode,
        day,
        start_period: start,
        end_period: end,
        start_time: startTime,
        end_time: end !== null ? PERIODS[end - 1].end : null,
        weeks: rnd() < 0.1 ? [1, 2, 3, 4, 5, 6, 7] : Array.from({ length: 14 }, (_, i) => i + 1),
        requested_room_text: roomText,
        requested_room_ids: pinned ? [pinned.id] : [],
        requested_building: roomText?.includes("Blok") ? roomText[0] : null,
        requested_tags: tags,
        requested_capacity: roomText?.includes("72") ? 72 : null,
        flexible_day: rnd() < 0.08,
        definitive_room_text: null,
        definitive_room_ids: [],
        notes: rnd() < 0.1 ? "1. ve 2. öğretim birlikte" : null,
        status: needsReview ? "NEEDS_REVIEW" : rnd() < 0.06 ? "LOCKED" : "PARSED",
        parse_warnings: warnings,
      });
      id++;
      sectionId++;
    }
  }
  // The documented hard case: BME 419 needs 102 seats on Wed P7–P9.
  meetingRequests.push({
    id: id++,
    section_id: sectionId++,
    course_code: "BME 419",
    course_name: "Biyomedikal Tasarım Projesi",
    section_label: "1",
    program_id: 6,
    program_name: "Biyomedikal Mühendisliği",
    class_year: 4,
    enrolment: 102,
    instructor: "Prof. Dr. Ayşe Kaya",
    mode: "F2F",
    day: 3,
    start_period: 7,
    end_period: 9,
    start_time: "13:30",
    end_time: "15:50",
    weeks: Array.from({ length: 14 }, (_, i) => i + 1),
    requested_room_text: "A 204",
    requested_room_ids: [1],
    requested_building: null,
    requested_tags: [],
    requested_capacity: 102,
    flexible_day: false,
    definitive_room_text: "A 204",
    definitive_room_ids: [1],
    notes: "Tüm şubeler birlikte (26+25+19 → toplam 102)",
    status: "PARSED",
    parse_warnings: [],
  });
  meetingRequests.push({
    id: id++,
    section_id: sectionId++,
    course_code: "HEM 334 / NRS 304",
    course_name: "İç Hastalıkları Hemşireliği (birleşik)",
    section_label: "1",
    program_id: 3,
    program_name: "Hemşirelik",
    class_year: 3,
    enrolment: 88,
    instructor: "Doç. Dr. Pınar Güneş",
    mode: "F2F",
    day: 2,
    start_period: 2,
    end_period: 5,
    start_time: "09:20",
    end_time: "12:30",
    weeks: Array.from({ length: 14 }, (_, i) => i + 1),
    requested_room_text: "A 102",
    requested_room_ids: [5],
    requested_building: "A",
    requested_tags: [],
    requested_capacity: null,
    flexible_day: false,
    definitive_room_text: null,
    definitive_room_ids: [],
    notes: "HEM 334 ve NRS 304 aynı derslikte",
    status: "LOCKED",
    parse_warnings: [],
  });
}

/* ---------------------------------------------------------------------------- Exam requests */
const EXAM_DATES = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05", "2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"];
const VENUE_TEXTS = ["1 Derslik", "2 büyük sınıf veya 3 küçük sınıf", "1 adet sınav kapasitesi minimum 60 kişilik derslik", "Bilgisayar laboratuvarı", "1 Gözetmen Talebi", "Amfi", "-"];
export const examRequests: ExamRequest[] = meetingRequests
  .filter((m) => m.mode !== "ONLINE" && m.mode !== "UZEM")
  .filter((_, i) => i % 2 === 0)
  .map((m, i) => {
    const start = pick([2, 4, 7, 9, 13]);
    const venue = pick(VENUE_TEXTS);
    const noExam = rnd() < 0.04;
    return {
      id: i + 1,
      term_id: 2,
      course_code: m.course_code,
      course_name: m.course_name,
      program_id: m.program_id,
      program_name: m.program_name,
      class_year: m.class_year,
      enrolment: m.enrolment,
      instructor_text: m.instructor,
      date: noExam ? null : pick(EXAM_DATES),
      start_time: noExam ? null : PERIODS[start - 1].start,
      end_time: noExam ? null : PERIODS[start].end,
      start_period: noExam ? null : start,
      end_period: noExam ? null : start + 1,
      requested_venue_text: venue,
      requested_room_count: venue.startsWith("2") ? 2 : 1,
      requested_min_capacity: venue.includes("60") ? 60 : null,
      requested_tags: venue.includes("Bilgisayar") ? ["PC"] : [],
      invigilators_requested: venue.includes("Gözetmen") ? 1 : null,
      on_campus_written: rnd() < 0.15,
      no_exam: noExam,
      definitive_room_text: null,
      definitive_room_ids: [],
      merge_key: m.course_code === "BME 419" ? "BME419" : null,
      status: noExam ? "PARSED" : rnd() < 0.1 ? "NEEDS_REVIEW" : "PARSED",
      parse_warnings: venue === "-" ? [{ row: i + 2, field: "Sınavın Yapılacağı Yer (Talep)", value: "-", message: "Yer talebi yok", severity: "info" }] : [],
    };
  });

/* ----------------------------------------------------------------------------------- Blocks */
export const blocks: Block[] = [];
{
  let id = 1;
  const allWeeks = Array.from({ length: 14 }, (_, i) => i + 1);
  for (const code of ["A101", "A106", "A107", "A108", "A109", "B202", "B203", "B204"]) {
    const room = roomByCode.get(code);
    if (!room) continue;
    for (const day of [1, 2, 3, 4, 5]) {
      blocks.push({ id: id++, room_id: room.id, day, start_period: 1, end_period: 6, weeks: allWeeks, label: "HAZIRLIK", source: "GRID_IMPORT" });
    }
  }
  const d107 = roomByCode.get("D107");
  if (d107) for (const day of [1, 2, 3, 4, 5]) blocks.push({ id: id++, room_id: d107.id, day, start_period: 1, end_period: 18, weeks: allWeeks, label: "UZEM", source: "GRID_IMPORT" });
  const a204 = roomByCode.get("A204");
  if (a204) blocks.push({ id: id++, room_id: a204.id, day: 5, start_period: 10, end_period: 12, weeks: [7], label: "ETKİNLİK", source: "ADMIN" });
}

/* ------------------------------------------------------------------------------ Assignments */
interface Occupancy {
  isFree(roomId: number, day: number, start: number, end: number, weeks: number[]): boolean;
  take(roomId: number, day: number, start: number, end: number, weeks: number[]): void;
}
function createOccupancy(): Occupancy {
  const taken: { roomId: number; day: number; start: number; end: number; weeks: Set<number> }[] = blocks.map((b) => ({
    roomId: b.room_id,
    day: b.day,
    start: b.start_period,
    end: b.end_period,
    weeks: new Set(b.weeks),
  }));
  return {
    isFree: (roomId, day, start, end, wks) =>
      !taken.some((t) => t.roomId === roomId && t.day === day && rangesOverlap(t.start, t.end, start, end) && wks.some((w) => t.weeks.has(w))),
    take: (roomId, day, start, end, wks) => taken.push({ roomId, day, start, end, weeks: new Set(wks) }),
  };
}

const sortedRooms = [...rooms].filter((r) => r.is_bookable).sort((a, b) => a.capacity - b.capacity);

function solve(runId: number, opts: { breakSome: boolean }): { assignments: Assignment[]; unplaced: MeetingRequest[]; conflicts: number } {
  const occ = createOccupancy();
  const assignments: Assignment[] = [];
  const unplaced: MeetingRequest[] = [];
  let conflicts = 0;
  let id = runId * 10_000 + 1;
  const roomed = meetingRequests.filter((m) => m.day !== null && m.start_period !== null && m.end_period !== null);
  // Locked / pinned first, then biggest classes (hardest to place).
  roomed.sort((a, b) => Number(b.status === "LOCKED") - Number(a.status === "LOCKED") || (b.enrolment ?? 0) - (a.enrolment ?? 0));
  for (const m of roomed) {
    const day = m.day as number;
    const start = m.start_period as number;
    const end = m.end_period as number;
    const size = m.enrolment ?? 0;
    const isMedicine = m.program_name === "Tıp";
    const candidates = sortedRooms.filter((r) => {
      if (r.capacity < size) return false;
      if (m.requested_tags.includes("PC") && !r.tags.includes("PC")) return false;
      if (!m.requested_tags.includes("PC") && r.tags.includes("PC") && size > 0) return rnd() < 0.15;
      if (r.tags.includes("TIP") && !isMedicine) return false;
      return true;
    });
    const preferred = candidates.filter((r) => m.requested_room_ids.includes(r.id));
    const inBuilding = m.requested_building ? candidates.filter((r) => r.building_code === m.requested_building) : [];
    const ordered = [...preferred, ...inBuilding, ...candidates];
    let placed: Room | undefined;
    for (const r of ordered) {
      if (occ.isFree(r.id, day, start, end, m.weeks)) {
        placed = r;
        break;
      }
    }
    if (opts.breakSome && (m.course_code === "BME 419" || m.course_code.startsWith("TIP") && size > 120)) placed = undefined;
    if (!placed) {
      if (opts.breakSome && ordered.length > 0) {
        // Best-effort: drop it on the requested room anyway and flag the conflict.
        const r = ordered[0];
        conflicts++;
        assignments.push(toAssignment(id++, runId, m, r, { conflict: true, reason: `${r.display_name} ${size}>${r.capacity} veya dolu` }));
      } else {
        unplaced.push(m);
      }
      continue;
    }
    occ.take(placed.id, day, start, end, m.weeks);
    assignments.push(toAssignment(id++, runId, m, placed, { conflict: false }));
  }
  return { assignments, unplaced, conflicts };
}

function toAssignment(id: number, runId: number, m: MeetingRequest, room: Room, flag: { conflict: boolean; reason?: string }): Assignment {
  return {
    id,
    run_id: runId,
    meeting_request_id: m.id,
    exam_request_id: null,
    label: `${m.course_code} §${m.section_label}`,
    course_code: m.course_code,
    section_label: m.section_label,
    program_name: m.program_name,
    instructor: m.instructor,
    size: m.enrolment ?? 0,
    week: null,
    weeks: m.weeks,
    day: m.day as number,
    date: null,
    start_period: m.start_period as number,
    end_period: m.end_period as number,
    room_ids: [room.id],
    is_locked: m.status === "LOCKED",
    origin: m.status === "LOCKED" ? "IMPORT" : "SOLVER",
    conflict: flag.conflict,
    conflict_reason: flag.reason ?? null,
  };
}

/* ------------------------------------------------------------------------------------ Runs */
const feasible = solve(1, { breakSome: false });
const infeasible = solve(2, { breakSome: true });

const BME = meetingRequests.find((m) => m.course_code === "BME 419");

export const diagnosesRun2: Diagnosis[] = [
  {
    id: "d1",
    index: 0,
    event_ids: BME ? [BME.id] : [],
    event_labels: ["BME 419 §1"],
    constraint_kinds: ["capacity", "room_tags", "fixed_time"],
    message: "BME 419 needs 102 seats on Wed P7–P9 but only A 204 (156) is free and it is reserved for ETKİNLİK in week 7; A 203 (148) is a TIP room.",
    suggestions: [
      { applicable: true, id: "s1", text: "Release A 203 (TIP) for non-medicine lectures on Wednesdays", action: "release_room", params: { room: "A 203", day: 3 } },
      { applicable: true, id: "s2", text: "Move BME 419 to Wed P10–P12 (A 204 free)", action: "move", params: { day: 3, start_period: 10, end_period: 12, room: "A 204" } },
      { applicable: true, id: "s3", text: "Split across A 101 + A 106 + A 107 (58 + 58 + 58)", action: "split", params: { rooms: ["A 101", "A 106", "A 107"] } },
    ],
    severity: "critical",
  },
  {
    id: "d2",
    index: 1,
    event_ids: meetingRequests.filter((m) => m.course_code.startsWith("TIP") && (m.enrolment ?? 0) > 120).map((m) => m.id).slice(0, 2),
    event_labels: meetingRequests.filter((m) => m.course_code.startsWith("TIP") && (m.enrolment ?? 0) > 120).map((m) => `${m.course_code} §${m.section_label}`).slice(0, 2),
    constraint_kinds: ["no_room_overlap", "capacity"],
    message: "Two Faculty of Medicine lectures (>120 students) overlap on the same day and only A 203 (148) and A 204 (156) can hold them; A 204 is taken by ETKİNLİK.",
    suggestions: [
      { applicable: true, id: "s4", text: "Allow one of them in C 201 (126) with 10 % remote share", action: "relax", params: { constraint: "capacity", slack: 0.1 } },
      { applicable: true, id: "s5", text: "Shift the second lecture by one period", action: "move", params: { delta: 1 } },
    ],
    severity: "high",
  },
  {
    id: "d3",
    index: 2,
    event_ids: [],
    event_labels: [],
    constraint_kinds: ["evening_programs_in_buildings"],
    message: "İÖ (evening) programmes requested A block but the soft rule keeps evening lectures in B/C blocks; 6 lectures moved — soft score −4.",
    suggestions: [{ applicable: true, id: "s6", text: "Make the evening-building rule hard", action: "add_constraint", params: { kind: "evening_programs_in_buildings", hardness: "hard" } }],
    severity: "low",
  },
];

export const runs: ScheduleRun[] = [
  {
    id: 1,
    term_id: 1,
    term_code: "2026-BAHAR",
    kind: "COURSE",
    horizon: "TERM",
    horizon_params: { weeks: Array.from({ length: 14 }, (_, i) => i + 1), dates: [] },
    status: "FEASIBLE",
    progress: 100,
    params: { time_limit_s: 120, seed: 42, workers: 8, stability: true, weights: { room_preference: 5, building_preference: 3, min_capacity_waste: 2, same_room_across_weeks: 4, stability: 3, exam_gap: 0 } },
    objective_value: 1834,
    soft_score: 91,
    hard_score: 100,
    stats: { solve_time_s: 74.2, events: feasible.assignments.length, rooms: rooms.length, branches: 1_204_552, conflicts: 0, unplaced: feasible.unplaced.length },
    objective_breakdown: { room_preference: 420, building_preference: 210, min_capacity_waste: 980, same_room_across_weeks: 64, stability: 160 },
    diagnosis: [],
    parent_run_id: null,
    prompt_text: "TIP derslikleri sadece Tıp için. İkinci öğretim B/C bloklarda kalsın.",
    created_at: "2026-02-01T09:12:00Z",
    finished_at: "2026-02-01T09:13:14Z",
  },
  {
    id: 2,
    term_id: 1,
    term_code: "2026-BAHAR",
    kind: "COURSE",
    horizon: "WEEK",
    horizon_params: { weeks: [7], dates: [] },
    status: "INFEASIBLE",
    progress: 100,
    params: { time_limit_s: 60, seed: 7, workers: 8, stability: true, weights: { room_preference: 5, building_preference: 3, min_capacity_waste: 2, same_room_across_weeks: 4, stability: 3, exam_gap: 0 } },
    objective_value: null,
    soft_score: 78,
    hard_score: 97,
    stats: { solve_time_s: 60, events: infeasible.assignments.length, rooms: rooms.length, conflicts: infeasible.conflicts, unplaced: infeasible.unplaced.length },
    objective_breakdown: { room_preference: 510, building_preference: 290, min_capacity_waste: 1210, same_room_across_weeks: 80, stability: 400 },
    diagnosis: diagnosesRun2,
    parent_run_id: 1,
    prompt_text: "A 204 Cuma öğleden sonra etkinlik için kapalı.",
    created_at: "2026-03-14T14:02:00Z",
    finished_at: "2026-03-14T14:03:00Z",
  },
];

export const assignmentsByRun = new Map<number, Assignment[]>([
  [1, feasible.assignments],
  [2, infeasible.assignments],
]);

export const constraints: Constraint[] = [
  // params in the backend's solver shapes (app/ai/catalog.py): "TIP only for medicine" = forbidden for everyone else
  { id: 1, term_id: 1, run_id: null, kind: "room_tags", params: { forbidden_tags: ["TIP"], programs: programs.filter((p) => p.name !== "Tıp").map((p) => p.name) }, hardness: "hard", weight: 5, source: "FILE", nl_text: "TIP rooms only for the Faculty of Medicine", enabled: true },
  { id: 2, term_id: 1, run_id: null, kind: "evening_programs_in_buildings", params: { buildings: ["B", "C"] }, hardness: "soft", weight: 5, source: "AI", nl_text: "İkinci öğretim B/C bloklarda kalsın", enabled: true },
  { id: 3, term_id: 1, run_id: null, kind: "room_closed", params: { room_id: 1, days: [5], periods: [10, 11, 12], weeks: [7] }, hardness: "hard", weight: 5, source: "ADMIN", nl_text: "A 204 Cuma öğleden sonra etkinlik için kapalı", enabled: true },
  { id: 4, term_id: 1, run_id: null, kind: "same_room_across_weeks", params: {}, hardness: "soft", weight: 8, source: "ADMIN", nl_text: null, enabled: true },
];

export const chatSeed: ChatMessage[] = [
  { id: 1, run_id: 1, role: "assistant", content: "Çizelge hazır: 100/100 katı kısıt, 91/100 yumuşak tercih. Ne değiştirmek istersiniz?", proposal: null, created_at: "2026-02-01T09:13:20Z" },
];

export const users: User[] = [
  { id: 1, email: "fatih.demir@example.edu.tr", full_name: "Fatih Demir", role: "ADMIN", is_active: true },
  { id: 2, email: "gozde.ayrancigil@example.edu.tr", full_name: "Gözde Ayrancıgil", role: "PLANNER", is_active: true },
  { id: 3, email: "viewer@example.edu.tr", full_name: "Dekanlık Görüntüleyici", role: "VIEWER", is_active: false },
];

export const settingsSeed: Settings = {
  anthropic_api_key_masked: "sk-ant-…7Qx2",
  anthropic_model: "claude-opus-5-5",
  available_models: ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
  solver_default_time_limit: 120,
  solver_default_workers: 8,
  solver_default_seed: 0,
  default_weights: { room_preference: 5, building_preference: 3, min_capacity_waste: 2, same_room_across_weeks: 4, stability: 3, exam_gap: 2 },
};

export const importJobsSeed: ImportJob[] = [
  {
    id: 1,
    kind: "planning-list",
    filename: "Bahar Derslik Planlama Listesi v5.xlsx",
    status: "DONE",
    summary: { rows: 1529, created: 1497, updated: 0, skipped: 32, warnings: sampleWarnings() },
    created_at: "2026-01-28T10:04:00Z",
  },
  {
    id: 2,
    kind: "weekly-grid",
    filename: "2026 bahar derslikler takvimi.xlsx",
    status: "DONE",
    summary: { rows: 19, created: 660, updated: 0, skipped: 0, warnings: [{ row: 2, field: "Oda başlığı", value: "22.10-22-50", message: "Saat yazımı düzeltildi (22:10-22:50)", severity: "info" }] },
    created_at: "2026-01-28T10:09:00Z",
  },
];

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
