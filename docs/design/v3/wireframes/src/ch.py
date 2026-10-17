"""Charts & telemetry wireframes (charts.md, owner request 2026-10-17). Usage (from this folder): python3 -I ch.py .."""
import sys, math, random; sys.path.insert(0, ".")
from wf import *
OUT = sys.argv[1]
SEQ = ["#BFDBFE", "#60A5FA", "#2563EB", "#1E3A8A"]
NAV = ["Panel", "Takvim", "Rezerve et", "§YÖNETİM", "Kullanıcılar", "Yapay zekâ", "Operasyon", "İstatistikler", "Ayarlar"]


def hatch(s, x, y, w, h, col, pid):
    s.o.append(f"<defs><pattern id='{pid}' width='6' height='6' patternUnits='userSpaceOnUse' patternTransform='rotate(45)'>"
               f"<rect width='6' height='6' fill='{col}' fill-opacity='.25'/><line x1='0' y1='0' x2='0' y2='6' stroke='{col}' stroke-width='2.5'/></pattern></defs>")
    s.o.append(f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='3' fill='url(#{pid})'/>")


def seg(s, x, y, labels, sel, h=36, w=None):
    w = w or 64 * len(labels); s.r(x, y, w, h, "#E8ECF2", h / 2); cw = w / len(labels)
    for i, l in enumerate(labels):
        if i == sel: s.r(x + i * cw + 3, y + 3, cw - 6, h - 6, CARD, (h - 6) / 2, LINE)
        s.t(x + i * cw + cw / 2, y + h / 2 + 4.5, l, 12, 600 if i == sel else 400, FG, "middle")
    return w


def axes(s, x, y, w, h, ticks, fmt=lambda v: str(v)):
    for i, v in enumerate(ticks):
        yy = y + h - h * i / (len(ticks) - 1)
        s.line(x, yy, x + w, yy, "#EEF2F6" if i else "#CBD5E1"); s.t(x - 6, yy + 4, fmt(v), 10, 400, SOFT, "end")


def stacked(s, x, y, w, h, n, seed, cols, labels=None, partial_last=True, gap=4):
    random.seed(seed); bw = (w - gap * (n - 1)) / n
    for i in range(n):
        bx = x + i * (bw + gap); top = y + h; tot = 0.25 + 0.6 * random.random()
        parts = [tot * p for p in (0.45, 0.25, 0.18, 0.12)][:len(cols)]
        for j, p in enumerate(parts):
            ph = p * h; top -= ph
            if partial_last and i == n - 1: hatch(s, bx, top, bw, ph - 2, cols[j], f"h{seed}{j}")
            else: s.r(bx, top, bw, ph - 2, cols[j], 2)
        if labels and (i % max(1, n // 6) == 0 and i <= n - max(1, n // 6)) or (labels and i == n - 1): s.t(bx + bw / 2, y + h + 16, labels[i], 10, 400, SOFT, "middle")


def card_head(s, x, y, w, title, sentence, period=("7 gün", "30 gün", "Dönem"), sel=1, menu=True):
    s.t(x + 20, y + 32, title, 16, 700)
    s.t(x + 20, y + 56, sentence, 13, 400, MUTED)
    pw = seg(s, x + w - 20 - 210 - (52 if menu else 0), y + 16, period, sel, w=210)
    if menu:
        s.r(x + w - 64, y + 16, 44, 36, CARD, 18, "#94A3B8"); s.t(x + w - 42, y + 39, "⋯", 16, 700, FG, "middle")


def shell1440():
    s = S(1440, 980, "Chart shell anatomy, desktop 1440"); s.desk_shell("Yapay zekâ · Kullanım", 5, NAV)
    x, y, w = 276, 96, 820
    s.r(x, y, w, 420, CARD, 16, LINE)
    card_head(s, x, y, w, "Günlük token kullanımı", "Son 30 günde 1,2 milyon token; en yoğun gün 14 Ekim (82 bin). Bugün henüz bitmedi.")
    lx = x + 20
    for i, (l, c) in enumerate(zip(["Sohbet", "Kurallar", "İçe aktarma", "Açıklama"], CAT)):
        s.r(lx, y + 78, 12, 12, c, 3); s.t(lx + 18, y + 89, l, 12, 500); lx += 18 + len(l) * 7 + 22
    s.t(x + w - 20, y + 89, "Biçim: yığılmış sütun · tek eksen", 11, 400, SOFT, "end")
    cx, cy, cwid, ch = x + 64, y + 110, w - 96, 230
    axes(s, cx, cy, cwid, ch, [0, 30, 60, 90], lambda v: f"{v} B")
    stacked(s, cx + 4, cy, cwid - 8, ch, 30, 7, CAT[:4], [f"{i + 18} Eyl" if i < 13 else f"{i - 12} Eki" for i in range(30)])
    # tooltip (frosted card, values right-aligned in text ink)
    tx, ty = cx + 470, cy + 30
    s.line(tx - 14, cy, tx - 14, cy + ch, "#94A3B8", 1, "3 3")
    s.r(tx, ty, 190, 112, "#FFFFFF", 12, LINE); s.t(tx + 12, ty + 22, "14 Ekim Çarşamba", 12, 700)
    for i, (l, v) in enumerate([("Sohbet", "37.120"), ("Kurallar", "20.400"), ("İçe aktarma", "14.950"), ("Açıklama", "9.830")]):
        s.r(tx + 12, ty + 34 + i * 18, 8, 8, CAT[i], 2); s.t(tx + 26, ty + 42 + i * 18, l, 11, 400); s.t(tx + 178, ty + 42 + i * 18, v, 11, 600, FG, "end")
    # footer: table toggle + updated
    s.line(x + 20, y + 372, x + w - 20, y + 372)
    s.t(x + 20, y + 400, "Tabloyu göster", 13, 600, PRI); s.t(x + w - 20, y + 400, "Güncellendi 19:42 · Europe/Istanbul", 12, 400, SOFT, "end")
    # annotations
    ax = x + w + 28
    notes = [(y + 32, "① Başlık: ne ölçülüyor (isim, birim yok)"), (y + 56, "② Özet cümle = aria-describedby; Intl tr-TR sayılar"),
             (y + 36, ""), (y + 140, "③ Dönem: SegmentedControl, URL ?period=30d"), (y + 160, "   (tabs-sliding free recipe, 250→180 ms)"),
             (y + 196, "④ ⋯ menü: Veriyi indir (CSV), PNG/SVG,"), (y + 214, "   Tabloyu göster, Yazdır"),
             (y + 260, "⑤ Lejant ≥ 2 seri; sıra sabit cat-1…cat-4"), (y + 300, "⑥ Bugün = taralı (decal), 'henüz bitmedi'"),
             (y + 340, "⑦ İpucu: tooltip free recipe 150/50 ms;"), (y + 358, "   klavye: ←/→ gün gün, Esc kapatır"),
             (y + 400, "⑧ Tablo ikizi: aynı veri, sr + görünür")]
    for yy, t in notes:
        if t: s.note(ax, yy, t, 12)
    # data-table twin (expanded state)
    ty0 = 540; s.r(x, ty0, w, 300, CARD, 16, LINE); s.t(x + 20, ty0 + 30, "Günlük token kullanımı · tablo", 15, 700)
    s.t(x + w - 20, ty0 + 30, "Grafiği göster", 13, 600, PRI, "end")
    cols = ["Gün", "Sohbet", "Kurallar", "İçe aktarma", "Açıklama", "Toplam"]
    for i, c in enumerate(cols): s.t(x + 20 + i * 132 + (0 if i == 0 else 100), ty0 + 66, c, 12, 600, MUTED, "start" if i == 0 else "end")
    rows = [("17 Eki Cmt (bugün, eksik)", "4.210", "1.020", "0", "312", "5.542"), ("16 Eki Cum", "21.004", "6.300", "2.100", "1.880", "31.284"),
            ("15 Eki Per", "32.330", "9.410", "7.000", "3.120", "51.860"), ("14 Eki Çar", "37.120", "20.400", "14.950", "9.830", "82.300"), ("…", "", "", "", "", "")]
    for r, row in enumerate(rows):
        yy = ty0 + 96 + r * 34; s.line(x + 20, yy - 22, x + w - 20, yy - 22)
        for i, c in enumerate(row): s.t(x + 20 + i * 132 + (0 if i == 0 else 100), yy, c, 12, 600 if i == 5 else 400, FG, "start" if i == 0 else "end")
    s.note(x + 20, ty0 + 286, "<table> with <caption>, <th scope>; the same rows the CSV writes (UTF-8 BOM, ';' separator for Excel tr-TR)", 11)
    s.save(f"{OUT}/charts-shell-1440.svg")


def states():
    s = S(1440, 760, "Chart shell states: loading, empty, error, partial, stale, too-few points")
    s.t(32, 48, "ChartCard durumları (aynı kabuk, aynı yükseklik: düzen kaymaz)", 22, 700)
    W, H = 440, 300
    boxes = [(32, 80), (500, 80), (968, 80), (32, 420), (500, 420), (968, 420)]
    def frame(i, title, sentence):
        x, y = boxes[i]; s.r(x, y, W, H, CARD, 16, LINE); s.t(x + 20, y + 30, title, 15, 700); s.t(x + 20, y + 52, sentence, 12, 400, MUTED); return x, y
    # 1 loading
    x, y = frame(0, "Yükleniyor", "")
    s.r(x + 20, y + 42, 260, 12, "#EEF2F6", 6)
    for i in range(12): s.r(x + 36 + i * 32, y + 250 - 40 - (i * 37 % 120), 22, 40 + (i * 37 % 120), "#EEF2F6", 3)
    s.note(x + 20, y + 284, "skeleton-reveal (free): pulse 1000 ms → reveal 400→180 ms; aria-busy", 11)
    # 2 empty
    x, y = frame(1, "Boş dönem", "Bu dönemde rezervasyon yok.")
    s.t(x + W / 2, y + 150, "Henüz gösterilecek veri yok", 14, 600, FG, "middle")
    s.t(x + W / 2, y + 172, "Dönemi değiştirin ya da ilk rezervasyonu yapın.", 12, 400, MUTED, "middle")
    s.btn(x + W / 2 - 80, y + 196, 160, 44, "Dönemi değiştir", "sec", 13)
    s.note(x + 20, y + 284, "eksen ve çerçeve çizilmez; yalnız cümle + tek eylem", 11)
    # 3 error
    x, y = frame(2, "Hata", "")
    s.r(x + 20, y + 80, W - 40, 72, BADBG, 12, "#FCA5A5"); s.t(x + 36, y + 108, "Veriler yüklenemedi.", 13, 700, BAD)
    s.t(x + 36, y + 130, "Sunucu yanıt vermedi (504). Önceki veriler gösterilmiyor.", 12, 400, BAD)
    s.btn(x + 20, y + 168, 140, 44, "Yeniden dene", "sec", 13)
    s.note(x + 20, y + 284, "role=alert yok: kartın içinde role=status; odak 'Yeniden dene'", 11)
    # 4 partial period
    x, y = frame(3, "Eksik dönem", "Bu hafta henüz bitmedi: Perşembe'den sonrası yok.")
    for i in range(5):
        hh = [120, 150, 135, 70, 0][i]; bx = x + 50 + i * 76
        if i < 3: s.r(bx, y + 250 - hh, 48, hh, SEQ[2], 3)
        elif i == 3: hatch(s, bx, y + 250 - hh, 48, hh, SEQ[2], "pp")
        s.t(bx + 24, y + 266, ["Pzt", "Sal", "Çar", "Per", "Cum"][i], 11, 400, SOFT, "middle")
    s.note(x + 20, y + 284, "decal (ECharts aria.decal) / CSS hatch + 'bugün, eksik' metni", 11)
    # 5 stale
    x, y = frame(4, "Eski veri", "")
    s.r(x + 20, y + 44, W - 40, 36, WARNBG, 10); s.t(x + 32, y + 67, "⚠ Son güncelleme 2 saat önce · Prometheus yanıt vermiyor", 12, 600, WARN)
    pts = [(x + 40 + i * 6.4, y + 200 - 60 * math.sin(i / 8) - 20) for i in range(60)]; s.poly(pts, SEQ[2], 2)
    s.line(x + 40, y + 250, x + W - 20, y + 250, "#CBD5E1")
    s.note(x + 20, y + 284, "grafik kalır, uyarı şeridi metinle; renk tek başına değil", 11)
    # 6 too few points -> stat
    x, y = frame(5, "Az veri → sayı", "2 gün veri var; grafik yerine sayı gösterilir.")
    s.t(x + 20, y + 140, "1.092", 36, 700); s.t(x + 20, y + 166, "token · son 2 gün", 13, 400, MUTED)
    s.note(x + 20, y + 284, "< 3 nokta: grafik yok, StatTile (choosing-a-form)", 11)
    s.save(f"{OUT}/charts-states.svg")


def surfaces():
    s = S(1440, 1000, "Chart per surface: admin, planner, user, desktop 1440"); s.desk_shell("İstatistikler (her rol kendi verisini görür)", 7, NAV)
    x = 276
    def box(bx, by, bw, bh, title, sentence, tag):
        s.r(bx, by, bw, bh, CARD, 16, LINE); s.t(bx + 16, by + 28, title, 14, 700); s.t(bx + 16, by + 48, sentence, 11, 400, MUTED)
        s.badge(bx + bw - 16 - (len(tag) * 6.6 + 16), by + 14, tag, LOCK, LOCKBG, 11)
    # ops line (canvas)
    box(x, 96, 560, 250, "İstekler ve 5xx (Operasyon)", "Dakikada ort. 42 istek; 19:21'de 5xx artışı.", "echarts-line · canvas")
    random.seed(3); pts = [(x + 50 + i * 8.2, 240 - 40 - 25 * math.sin(i / 9) - random.random() * 12) for i in range(60)]
    axes(s, x + 50, 160, 490, 80, [0, 50, 100], str); s.poly(pts, CAT[0], 2); s.t(x + 540, 156, "istek/dk", 10, 500, SOFT, "end")
    axes(s, x + 50, 262, 490, 50, [0, 5], str); s.t(x + 540, 258, "5xx/dk", 10, 500, SOFT, "end")
    e = [(x + 50 + i * 8.2, 312 - (40 if 38 <= i <= 41 else 1)) for i in range(60)]; s.poly(e, CAT[1], 2)
    s.note(x + 230, 340, "küçük çoklu grafik: istek · 5xx · p95 ayrı eksen", 11)
    # AI stacked
    box(x + 580, 96, 560, 250, "Günlük token (Yapay zekâ)", "30 günde 1,2 M token; en yoğun 14 Ekim.", "echarts-bar · stacked")
    axes(s, x + 630, 160, 490, 140, [0, 45, 90], str); stacked(s, x + 634, 160, 482, 140, 30, 11, CAT[:4], None)
    # bookings per week
    box(x, 366, 560, 250, "Haftalık rezervasyon (Rezervasyonlar)", "Bu dönem haftada ort. 412; 8. hafta sınav haftası.", "echarts-bar")
    axes(s, x + 50, 430, 490, 140, [0, 300, 600], str)
    for i in range(14):
        hh = [80, 95, 102, 110, 98, 104, 60, 135, 112, 100, 96, 90, 88, 40][i]; bx = x + 56 + i * 34.5
        if i == 13: hatch(s, bx, 570 - hh, 26, hh, SEQ[2], "bw")
        else: s.r(bx, 570 - hh, 26, hh, SEQ[3] if i == 7 else SEQ[2], 3)
        if i == 7: s.t(bx + 13, 570 - hh - 6, "Sınav haftası", 10, 600, FG, "middle")
    s.note(x + 16, 610, "8. hafta etiketi doğrudan: 'Sınav haftası'", 11)
    # dashboard area
    box(x + 580, 366, 560, 250, "Ders saatine göre doluluk (Panel)", "En yoğun saat 10:30 (%86).", "echarts-area · svg")
    axes(s, x + 630, 430, 490, 140, [0, 50, 100], lambda v: f"%{v}")
    ap = [(x + 630 + i * 490 / 17, 570 - 140 * [.2, .5, .78, .86, .8, .55, .62, .74, .7, .6, .45, .3, .22, .18, .12, .08, .05, .03][i]) for i in range(18)]
    s.o.append(f"<polygon points='{x + 630},570 " + " ".join(f"{a},{b}" for a, b in ap) + f" {x + 1120},570' fill='{SEQ[0]}' fill-opacity='.7'/>"); s.poly(ap, SEQ[2], 2)
    # not-a-chart row
    s.t(x, 650, "Grafik değil (bugünkü bileşen kalır)", 15, 700)
    box(x, 666, 360, 150, "Bina doluluğu", "BarList: değer çubuğun ucunda", "BarList")
    for i, (b, v) in enumerate([("A", 82), ("B", 64), ("C", 41)]):
        s.t(x + 16, 740 + i * 24, b, 12, 600); s.r(x + 40, 729 + i * 24, 240 * v / 100, 14, SEQ[2], 3); s.t(x + 330, 740 + i * 24, f"%{v}", 12, 600, FG, "end")
    box(x + 380, 666, 360, 150, "Kurum bütçesi", "Meter: kullanılan / sınır + tarih", "Meter")
    s.t(x + 396, 748, "%62 · 620 / 1.000 $", 18, 700); s.r(x + 396, 760, 328, 10, "#E2E8F0", 5); s.r(x + 396, 760, 203, 10, PRI, 5)
    s.t(x + 396, 794, "1 Kasım'da sıfırlanır", 12, 400, MUTED)
    box(x + 760, 666, 380, 150, "Doluluk ısı haritası", "HeatGrid (CSS ızgara, 1 katman)", "HeatGrid")
    for r in range(3):
        for c in range(10): s.r(x + 776 + c * 34, 726 + r * 28, 30, 24, SEQ[(r * 3 + c) % 4], 4)
    s.note(x, 850, "Kural: sıralama → BarList · tek değer/kota → StatTile/Meter · gün×saat → HeatGrid · zaman serisi → EvilCharts ECharts (bar/line/area)", 12)
    s.note(x, 872, "Pasta/halka, radar, sankey, radial yok: SmartSched'de parça-bütün sorusu ≤ 5 kalemle BarList'te daha okunur.", 12)
    s.save(f"{OUT}/charts-surfaces-1440.svg")


def phone():
    s = S(390, 844, "Chart card on a phone 390"); s.phone_shell("Kullanım", 4)
    y = 116; s.r(16, y, 358, 540, CARD, 16, LINE)
    s.t(32, y + 32, "Günlük token kullanımı", 16, 700)
    s.t(32, y + 54, "Son 7 günde 182 bin token;", 13, 400, MUTED); s.t(32, y + 72, "en yoğun gün Perşembe (54 bin).", 13, 400, MUTED)
    s.r(326, y + 14, 44, 44, CARD, 22, "#94A3B8"); s.t(348, y + 41, "⋯", 16, 700, FG, "middle")
    seg(s, 32, y + 88, ("7 gün", "30 gün", "Dönem"), 0, h=44, w=326)
    for i, (l, c) in enumerate(zip(["Sohbet", "Kurallar", "İçe akt.", "Diğer"], CAT[:3] + ["#94A3B8"])):
        s.r(32 + i * 82, y + 150, 10, 10, c, 3); s.t(48 + i * 82, y + 160, l, 11, 500)
    axes(s, 64, y + 180, 290, 200, [0, 30, 60], lambda v: f"{v} B")
    stacked(s, 70, y + 180, 280, 200, 7, 5, CAT[:3] + ["#94A3B8"], ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"], gap=10)
    s.r(150, y + 176, 120, 36, "#0F172A", 10); s.t(210, y + 199, "Per · 54.690", 12, 600, "#FFFFFF", "middle")
    s.t(32, y + 418, "Dokun ve kaydır: gün gün değer", 11, 400, SOFT)
    s.line(32, y + 440, 358, y + 440)
    s.r(32, y + 456, 326, 44, CARD, 22, "#94A3B8"); s.t(195, y + 483, "Tabloyu göster", 14, 600, PRI, "middle")
    s.note(24, 690, "• ≤ 7 sütun / 12 nokta; daha fazlası → haftalık topla", 11)
    s.note(24, 706, "• grafik 200 px, tam genişlik, yatay kaydırma yok", 11)
    s.note(24, 722, "• dataZoom/brush kapalı; dokunma 44 px şeritler", 11)
    s.note(24, 738, "• ⋯ → alt sayfa: Veriyi indir, Görsel, Yazdır", 11)
    s.save(f"{OUT}/charts-390.svg")


def user_phone():
    s = S(390, 844, "User and academician stats on a phone 390"); s.phone_shell("Profilim", 4)
    y = 136; s.t(20, y, "Rezervasyonlarım", 17, 700)
    for i, (n, l) in enumerate([("3", "aktif"), ("11", "bu dönem"), ("2", "açık talep")]):
        bx = 20 + i * 120; s.r(bx, y + 14, 110, 84, CARD, 14, LINE); s.t(bx + 14, y + 56, n, 28, 700); s.t(bx + 14, y + 82, l, 12, 400, MUTED)
    s.t(20, y + 120, "3 / 5 aktif rezervasyon hakkı kullanıldı.", 13, 400, MUTED)
    y2 = y + 150; s.t(20, y2, "Haftalık ders yüküm (akademisyen)", 17, 700)
    s.r(20, y2 + 14, 350, 296, CARD, 14, LINE); s.t(36, y2 + 42, "Bu hafta 14 saat; en yoğun gün Salı (5 saat).", 13, 400, MUTED)
    for i, (d, h) in enumerate([("Pzt", 3), ("Sal", 5), ("Çar", 2), ("Per", 4), ("Cum", 0)]):
        yy = y2 + 56 + i * 44; s.t(36, yy + 20, d, 13, 600); s.r(80, yy + 8, 220 * h / 5 if h else 0, 16, SEQ[2], 3) if h else None
        s.t(354, yy + 21, f"{h} sa" if h else "ders yok", 13, 600 if h else 400, FG if h else MUTED, "end")
    s.note(36, y2 + 300, "BarList (grafik kütüphanesi yok), satır 44 px → Takvim'de o gün", 11)
    y3 = y2 + 336; s.t(20, y3, "Yapay zekâ kullanımım", 17, 700)
    s.r(20, y3 + 14, 350, 100, CARD, 14, LINE); s.t(36, y3 + 42, "Bu ay %38 · 38 bin / 100 bin token", 14, 600)
    s.r(36, y3 + 56, 318, 10, "#E2E8F0", 5); s.r(36, y3 + 56, 121, 10, PRI, 5); s.t(36, y3 + 90, "1 Kasım'da sıfırlanır", 12, 400, MUTED)
    s.save(f"{OUT}/charts-user-390.svg")


shell1440(); states(); surfaces(); phone(); user_phone(); print("ok")
