/**
 * PER-F05 (M-21): the importers write their warnings in English ("instructor value 'UZEM' names no person (mode); not
 * used as an instructor"). The common shapes read in Turkish here; an unknown shape stays as written.
 */
const WHY: Record<string, string> = { mode: "öğretim biçimi", placeholder: "yer tutucu", department: "bölüm adı", title_only: "yalnızca unvan", note: "not" };

const q = (s: string) => s.replace(/^'(.*)'$/, "$1").replace(/^"(.*)"$/, "$1");

const RULES: [RegExp, (m: RegExpExecArray) => string][] = [
  [/^instructor value (.+) names no person \((\w+)\); not used as an instructor$/, (m) => `“${q(m[1]!)}” bir kişi değil (${WHY[m[2]!] ?? m[2]}); öğretim elemanı sayılmadı`],
  [/^weeks value (\d+); assuming all$/, (m) => `Hafta değeri ${m[1]}; bütün haftalar varsayıldı`],
  [/^(?:boolean|fractional|non-week) weeks? value (.+); assuming all$/, (m) => `Hafta değeri anlaşılamadı (${q(m[1]!)}); bütün haftalar varsayıldı`],
  [/^non-week value (.+); assuming all$/, (m) => `Hafta değeri anlaşılamadı (${q(m[1]!)}); bütün haftalar varsayıldı`],
  [/^unparsed weeks text (.+); assuming all$/, (m) => `Hafta metni anlaşılamadı (${q(m[1]!)}); bütün haftalar varsayıldı`],
  [/^ambiguous weeks value (\d+); assuming first \d+ weeks$/, (m) => `Hafta değeri ${m[1]} belirsiz; ilk ${m[1]} hafta varsayıldı`],
  [/^weeks value (\d+) exceeds term length (\d+)$/, (m) => `Hafta değeri ${m[1]}, dönemin ${m[2]} haftasından uzun`],
  [/^weeks (.+) exceed term length (\d+); capped$/, (m) => `${m[1]}. haftalar dönemin ${m[2]} haftasını aşıyor; kırpıldı`],
  [/^'until midterm' approximated as weeks 1-7$/, () => "“Vizeye kadar” 1–7. haftalar olarak alındı"],
  [/^time (\d\d:\d\d)-(\d\d:\d\d) snapped to P(\d+)-P(\d+) \((\d\d:\d\d)-(\d\d:\d\d)\): .+$/, (m) => `${m[1]}–${m[2]} saati P${m[3]}–P${m[4]} ders saatlerine (${m[5]}–${m[6]}) yuvarlandı`],
  [/^time (\d\d:\d\d)-(\d\d:\d\d) is outside the period grid$/, (m) => `${m[1]}–${m[2]} saati ders saatlerinin dışında`],
  [/^start time (\d\d:\d\d) (?:not on the grid|falls in a break|is before the grid); snapped to P(\d+).*$/, (m) => `Başlangıç ${m[1]}, P${m[2]} ders saatine yuvarlandı`],
  [/^end time (\d\d:\d\d) snapped to P(\d+).*$/, (m) => `Bitiş ${m[1]}, P${m[2]} ders saatine yuvarlandı`],
  [/^start time (\d\d:\d\d) is after the last period$/, (m) => `Başlangıç ${m[1]}, son ders saatinden sonra`],
  [/^end time (\d\d:\d\d) is before the first period$/, (m) => `Bitiş ${m[1]}, ilk ders saatinden önce`],
  [/^unparseable start time (.+)$/, (m) => `Başlangıç saati okunamadı (${q(m[1]!)})`],
  [/^unrecognised day: (.+)$/, (m) => `Gün anlaşılamadı (${q(m[1]!)})`],
  [/^day cell contains a time value: (.+)$/, (m) => `Gün hücresinde saat var (${q(m[1]!)})`],
  [/^unparseable exam date (.+)$/, (m) => `Sınav tarihi okunamadı (${q(m[1]!)})`],
  [/^exam date range (\S+)\.\.(\S+); using first day$/, (m) => `Sınav tarihi aralığı ${m[1]}–${m[2]}; ilk gün alındı`],
  [/^rooms tagged PC because a row calls them a computer lab: (.+)$/, (m) => `Bir satır bilgisayar laboratuvarı dediği için PC etiketi eklenen derslikler: ${m[1]}`],
  [/^room (\S+): (.+) says (\w+) (\S+), room master keeps (\S+)$/, (m) => `${m[1]}: dosya ${m[3]} ${m[4]} diyor; derslik listesindeki ${m[5]} korundu`],
  [/^line (\d+): duplicate room (\S+); last one wins$/, (m) => `${m[1]}. satır: ${m[2]} iki kez var; sonuncusu alındı`],
  [/^(\d+) room\(s\) in the master still have no capacity: (.+)$/, (m) => `Derslik listesinde ${m[1]} dersliğin kapasitesi yok: ${m[2]}`],
];

export function warningTr(message: string): string {
  for (const [re, out] of RULES) {
    const m = re.exec(message.trim());
    if (m) return out(m);
  }
  return message;
}
