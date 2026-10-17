"""AI helper wireframes (docs/design/v3/helper.md). Reuses the W3-DES kit in ./src/wf.py.
Usage, from docs/design/v3/wireframes:  python3 -I helper-gen.py .
Purple text is an annotation, not UI copy. Names are initials only (KVKK)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from wf import *  # noqa: E402,F401

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
ADMIN_NAV = ["Panel", "Haftalık program", "Çalıştırmalar", "§REZERVASYONLAR", "Hızlı rezervasyon", "Rezervasyonlar",
             "§YÖNETİM", "Ayarlar", "Kullanıcılar", "Dönem ve saatler", "Yapay zekâ"]
ACAD_TABS = ("Rezerve et", "Rezervasyonlarım", "Derslik bul", "Taleplerim", "Daha")
SCRIM = "#0F172A"


def trigger(s, x, y, w=280):
    s.r(x, y, w, 36, "#EEF2F7", 18, LINE)
    s.c(x + 20, y + 18, 6, "none", SOFT)
    s.t(x + 36, y + 23, "Ara veya sor…", 13, 400, SOFT)
    s.r(x + w - 52, y + 8, 40, 20, CARD, 5, LINE)
    s.t(x + w - 32, y + 22, "⌘K", 11, 600, MUTED, "middle")


def topbar(s, x0=276, trig=True, crumb="Yönetim  /  Kullanıcılar"):
    s.r(x0, 16, 380, 40, CARD, 20, LINE)
    s.t(x0 + 18, 41, crumb, 13, 500, MUTED)
    s.r(s.w - 420, 16, 396, 40, CARD, 20, LINE)
    if trig:
        trigger(s, s.w - 414, 18, 300)
    s.c(s.w - 90, 36, 9, "none", SOFT)
    s.c(s.w - 56, 36, 9, "none", SOFT)


def chip_status(s, x, y, label="Bulut · Anthropic", dot=PRI):
    w = int(len(label) * 6.4) + 30
    s.r(x, y, w, 24, CARD, 12, LINE)
    s.c(x + 12, y + 12, 4, dot)
    s.t(x + 22, y + 16, label, 11, 600, FG)
    return w


def page_users(s, x=276, y=80, w=None):
    w = w or s.w - x - 24
    s.t(x, y + 30, "Kullanıcılar", 28, 700)
    s.btn(x + w - 150, y + 6, 140, 40, "Davet et", "pri", 14)
    s.r(x, y + 60, w, 44, CARD, 10, LINE)
    s.t(x + 16, y + 87, "Ad, e-posta ya da bölüm ara", 13, 400, SOFT)
    for i in range(7):
        yy = y + 120 + i * 48
        s.r(x, yy, w, 44, CARD, 8, LINE)
        s.t(x + 16, yy + 27, ["A. T.", "P. T.", "F. B.", "S. K.", "M. Y.", "E. D.", "H. Ö."][i], 13, 600)
        s.t(x + 120, yy + 27, ["Öğretim elemanı", "Personel", "Yönetici", "Öğretim elemanı", "Onaylayıcı", "Personel",
                               "Öğretim elemanı"][i], 13, 400, MUTED)


def bubble_user(s, x, y, w, txt):
    s.r(x, y, w, 36, "#E2E8F0", 16)
    s.t(x + 12, y + 23, txt, 13, 400)


def card_book(s, x, y, w, state="proposed"):
    h = 210 if state == "proposed" else 120
    s.r(x, y, w, h, "#F1F5F9", 14, LINE)
    s.t(x + 16, y + 26, "Salon rezervasyonu", 14, 650)
    if state == "proposed":
        for i, (lab, val) in enumerate([("Salon", "A 204 · 40 kişi · projeksiyon"), ("Gün", "Yarın, 18 Eki Cumartesi"),
                                         ("Ders saati", "3. saat · 10:00–10:50")]):
            yy = y + 42 + i * 38
            s.t(x + 16, yy + 20, lab, 12, 500, MUTED)
            s.r(x + 100, yy + 2, w - 116, 30, CARD, 8, "#94A3B8")
            s.t(x + 110, yy + 22, val, 12, 500)
            s.t(x + w - 26, yy + 22, "▾", 12, 500, SOFT)
        s.btn(x + 16, y + 162, w - 32, 36, "Rezerve et: A 204 · yarın 10:00", "pri", 13)
    else:
        s.c(x + 28, y + 52, 10, OKBG)
        s.poly([(x + 23, y + 52), (x + 27, y + 56), (x + 34, y + 47)], OK, 2.2)
        s.t(x + 46, y + 57, "A 204 yarın 10:00–10:50 için rezerve edildi.", 12, 500)
        s.t(x + 16, y + 92, "Rezervasyonu aç", 13, 600, PRI)
        s.t(x + w - 16, y + 92, "Geri al", 13, 600, PRI, "end")
    return h


# ---------------------------------------------------------------- 1. palette "Ara veya sor" (desktop)
def search_1440():
    s = S(1440, 900, "Ara veya sor: genişletilmiş komut paleti (masaüstü)")
    s.desk_shell("", 8, ADMIN_NAV)
    topbar(s)
    page_users(s)
    s.r(0, 0, 1440, 900, SCRIM, 0, op=.35)
    x, y, w = 400, 110, 640
    s.r(x, y, w, 620, CARD, 18, LINE)
    s.c(x + 26, y + 30, 7, "none", SOFT)
    s.t(x + 44, y + 36, "periods", 16, 500)
    s.t(x + w - 20, y + 36, "Esc", 11, 600, SOFT, "end")
    s.line(x, y + 58, x + w, y + 58)
    yy = y + 82
    s.t(x + 20, yy, "Sayfalar ve ayarlar", 11, 600, SOFT); yy += 10
    s.r(x + 10, yy, w - 20, 44, TINT, 10)
    s.t(x + 44, yy + 20, "Ders saatleri", 14, 600)
    s.t(x + 44, yy + 36, "Yönetim › Dönem ve saatler", 11, 400, SOFT)
    s.t(x + w - 30, yy + 27, "↵ Aç   ⇧↵ Göster", 11, 600, PRI, "end"); yy += 52
    s.t(x + 44, yy + 20, "Haftalar (A/B)", 14, 500); s.t(x + 44, yy + 36, "Yönetim › Dönem ve saatler", 11, 400, SOFT); yy += 60
    s.t(x + 20, yy, "Nerede?", 11, 600, SOFT); yy += 10
    s.t(x + 44, yy + 20, "“Yeni ders saati şeması” düğmesi", 14, 500)
    s.t(x + 44, yy + 36, "Yönetim › Dönem ve saatler › Ders saatleri", 11, 400, SOFT)
    s.t(x + w - 30, yy + 27, "Göster", 12, 600, PRI, "end"); yy += 60
    s.t(x + 20, yy, "Kısayollar", 11, 600, SOFT); yy += 10
    s.t(x + 44, yy + 24, "Ders saatlerini dönem için kopyala…", 14, 500); yy += 52
    s.t(x + 20, yy, "Yardımcıya sor", 11, 600, SOFT); yy += 10
    s.r(x + 10, yy, w - 20, 48, CARD, 10, LINE)
    s.t(x + 44, yy + 29, "Yardımcıya sor: “periods”", 14, 600)
    chip_status(s, x + w - 170, yy + 12, "Bulut · Anthropic")
    s.line(x, y + 580, x + w, y + 580)
    s.t(x + 20, y + 605, "↑↓ gezin   ↵ aç   ⇧↵ göster   Esc kapat", 11, 500, SOFT)
    s.note(1060, 140, "Tetikleyici: “Ara veya sor… ⌘K” (eski “Ara” düğmesi yerine)", 11)
    s.note(1060, 200, "CRBS kelimesi “periods” eş anlamlılarla", 11)
    s.note(1060, 216, "“Ders saatleri”ne eşlenir (yapay zekâ yok)", 11)
    s.note(1060, 276, "Nerede? = sayfa içindeki tek bir kontrol;", 11)
    s.note(1060, 292, "⇧↵ ya da “Göster” halkayla gösterir", 11)
    s.note(1060, 520, "Soru gibi yazılırsa (nasıl/nerede/?…)", 11)
    s.note(1060, 536, "bu satır en üste çıkar ve seçili gelir", 11)
    s.note(1060, 552, "Yetkisi olmayan hiçbir sonuç listelenmez", 11)
    s.save(os.path.join(OUT, "helper-search-1440.svg"))


# ---------------------------------------------------------------- 2. helper sheet with an action card (desktop)
def sheet_1440():
    s = S(1440, 900, "Yardımcı yan paneli ve eylem kartı (masaüstü)")
    s.desk_shell("", 4, ADMIN_NAV)
    topbar(s, crumb="Rezervasyonlar  /  Hızlı rezervasyon")
    s.t(276, 110, "Hızlı rezervasyon", 28, 700)
    for r in range(5):
        for c in range(5):
            s.r(276 + c * 120, 140 + r * 60, 112, 52, CARD if (r + c) % 3 else "#E2E8F0", 8, LINE)
    x, y, w = 1440 - 416, 68, 400
    s.r(x, y, w, 820, CARD, 20, LINE)
    s.t(x + 20, y + 34, "Yardımcı", 17, 700)
    chip_status(s, x + 112, y + 16, "Yerel model", OK)
    s.t(x + w - 60, y + 34, "⋯", 18, 700, MUTED); s.t(x + w - 24, y + 34, "✕", 16, 600, MUTED, "end")
    s.line(x, y + 54, x + w, y + 54)
    bubble_user(s, x + 150, y + 70, 230, "Yarın 10'da boş salon var mı?")
    s.r(x + 20, y + 118, w - 40, 36, "#F8FAFC", 10, LINE)
    s.t(x + 34, y + 141, "Derslik bul · 3 salon bulundu · katlandı", 12, 500, MUTED)
    bubble_user(s, x + 150, y + 170, 230, "A 204'ü ayır")
    s.t(x + 20, y + 232, "A 204 yarın 10:00–10:50 boş. Onay gerekmiyor.", 13, 400)
    card_book(s, x + 20, y + 248, w - 40, "proposed")
    s.r(x + 20, y + 660, w - 40, 30, WARNBG, 8)
    s.t(x + 32, y + 680, "Bu ayki kullanım hakkınızın %84'ü kullanıldı. 1 Kasım'da yenilenir.", 11, 500, WARN)
    s.r(x + 20, y + 698, 170, 26, TINT, 13)
    s.t(x + 32, y + 715, "Bu sayfa: Hızlı rezervasyon  ✕", 11, 500, PRI)
    s.r(x + 20, y + 732, w - 40, 48, CARD, 14, "#94A3B8")
    s.t(x + 36, y + 761, "Bir şey sorun ya da yapmak istediğinizi yazın…", 13, 400, SOFT)
    s.c(x + w - 44, y + 756, 14, PRI)
    s.t(x + 20, y + 802, "ⓘ Yanıtlar yapay zekâ ile üretilir; kontrol edin.", 11, 400, MUTED)
    s.note(276, 520, "Panel modal değil: sayfa açık ve kullanılabilir kalır (Göster için gerekli)", 11)
    s.note(276, 540, "400 px, sağda, kaydırma yok; cam yüzey 2/3 (kabuk çubuğu + panel)", 11)
    s.note(276, 560, "Kart = katalogdan tipli şema; düğme etkiyi ve nesneyi söyler (R1: tek dokunuş)", 11)
    s.note(276, 580, "Eski bekleyen kart tek satıra katlanır; aynı anda tek odak", 11)
    s.note(276, 600, "Kullanım bandı = mevcut AiUsageBanner; durum çipi: Yerel / Bulut / Kapalı", 11)
    s.note(276, 620, "⌘J doğrudan açar; Esc kapatır, odak açan düğmeye döner; F6 sayfa ↔ panel", 11)
    s.save(os.path.join(OUT, "helper-sheet-1440.svg"))


# ---------------------------------------------------------------- 3. "Nerede?" + Göster spotlight (desktop)
def where_1440():
    s = S(1440, 900, "“Nerede?” yanıtı ve Göster (masaüstü)")
    s.desk_shell("", 8, ADMIN_NAV)
    topbar(s)
    page_users(s, w=700)
    s.r(0, 0, 1024, 900, SCRIM, 0, op=.25)
    bx, by = 276 + 700 - 150, 86
    s.r(bx - 6, by - 6, 152, 52, "none", 26, PRI, 3)
    s.btn(bx, by, 140, 40, "Davet et", "pri", 14)
    s.r(bx - 230, by + 60, 360, 130, CARD, 16, LINE)
    s.t(bx - 214, by + 88, "Davet et", 15, 650)
    s.t(bx - 214, by + 110, "Yeni kişileri e-posta ile buradan davet edersiniz.", 12, 400, MUTED)
    s.btn(bx - 214, by + 130, 110, 40, "Anladım", "sec", 13)
    s.btn(bx - 94, by + 130, 200, 40, "Yardımcıya dön", "pri", 13)
    x, y, w = 1440 - 416, 68, 400
    s.r(x, y, w, 820, CARD, 20, LINE)
    s.t(x + 20, y + 34, "Yardımcı", 17, 700)
    chip_status(s, x + 112, y + 16, "Yapay zekâ kapalı", "#94A3B8")
    s.line(x, y + 54, x + w, y + 54)
    bubble_user(s, x + 150, y + 74, 230, "kullanıcı nasıl davet edilir")
    cy = y + 126
    s.r(x + 20, cy, w - 40, 236, "#F1F5F9", 14, LINE)
    s.t(x + 36, cy + 28, "Kullanıcı davet et", 14, 650)
    s.t(x + 36, cy + 52, "Yönetim › Kullanıcılar › Davet et", 12, 600, PRI)
    s.t(x + 36, cy + 80, "1. Kullanıcılar sayfasını açın.", 12, 400)
    s.t(x + 36, cy + 100, "2. Sağ üstte “Davet et”e basın.", 12, 400)
    s.t(x + 36, cy + 120, "3. E-posta ve rolü girip gönderin.", 12, 400)
    s.btn(x + 36, cy + 140, 110, 40, "Göster", "pri", 13)
    s.btn(x + 156, cy + 140, 120, 40, "Sayfayı aç", "sec", 13)
    s.btn(x + 36, cy + 188, 160, 36, "Burada yap", "link", 13)
    s.r(x + 20, y + 650, w - 40, 70, TINT, 12)
    s.t(x + 32, y + 676, "Rehber modu: yapay zekâ kapalıyken de sayfaları", 12, 500, PRI)
    s.t(x + 32, y + 694, "ve kısayolları bulabilirsiniz.", 12, 500, PRI)
    s.r(x + 20, y + 732, w - 40, 48, CARD, 14, "#94A3B8")
    s.t(x + 36, y + 761, "Ne arıyorsunuz?", 13, 400, SOFT)
    s.note(40, 860, "Yapay zekâ kapalı: yanıt özellik dizininden gelir (deterministik). Göster = WG-05 halkası, 1 adımlık tur; hedef tıklanabilir kalır; perde %25",
           11)
    s.save(os.path.join(OUT, "helper-where-1440.svg"))


# ---------------------------------------------------------------- 4. phone: search, thread, card, show
def phone_390():
    s = S(1640, 844, "Yardımcı telefonda: arama, konuşma, kart, Göster")
    s.o.append("<g>")
    # A search
    a = S(390, 844, "a")
    a.r(16, 56, 358, 48, CARD, 14, PRI, 2)
    a.t(32, 86, "yarın 10 a 204", 16, 500)
    a.t(358, 86, "İptal", 14, 600, PRI, "end")
    yy = 128
    for grp, rows in [("Salonlar", [("A 204", "B blok · 40 kişi")]),
                      ("Kısayollar", [("Yarın 10:00 için A 204'ü ayır", "Hızlı rezervasyon")]),
                      ("Yardımcıya sor", [("Yardımcıya sor: “yarın 10 a 204”", "Bulut · Anthropic")])]:
        a.t(20, yy, grp, 12, 600, SOFT); yy += 8
        for t1, t2 in rows:
            a.r(12, yy, 366, 56, CARD, 12, LINE)
            a.t(28, yy + 24, t1, 15, 600)
            a.t(28, yy + 44, t2, 12, 400, SOFT)
            yy += 64
        yy += 16
    a.note(20, 520, "Tam ekran palet; satırlar 56 px; giriş 16 px", 11)
    a.note(20, 536, "Tab çubuğundaki yuvarlak arama düğmesi açar", 11)
    a.note(20, 552, "Kısayol yapay zekâ çağırmadan kartı açar", 11)
    # B thread with card
    b = S(390, 844, "b")
    b.t(20, 30, "9:41", 14, 600)
    b.t(30, 78, "✕", 18, 600, MUTED)
    b.t(120, 78, "Yardımcı", 17, 700)
    chip_status(b, 208, 62, "Bulut · Anthropic")
    b.line(0, 100, 390, 100)
    bubble_user(b, 120, 116, 250, "Yarın 10:00 için A 204'ü ayır")
    b.t(20, 182, "A 204 yarın 10:00–10:50 boş.", 14, 400)
    card_book(b, 12, 196, 366, "proposed")
    b.r(12, 690, 366, 52, CARD, 16, "#94A3B8")
    b.t(28, 722, "Bir şey sorun…", 16, 400, SOFT)
    b.c(352, 716, 16, PRI)
    b.t(20, 770, "ⓘ Yanıtlar yapay zekâ ile üretilir.", 11, 400, MUTED)
    b.note(20, 440, "Tam ekran (aria-modal); tab çubuğu gizli", 11)
    b.note(20, 456, "Birincil 48 px tam genişlik; alanlar yerel seçiciler", 11)
    # C done state
    c = S(390, 844, "c")
    c.t(30, 78, "✕", 18, 600, MUTED); c.t(120, 78, "Yardımcı", 17, 700)
    c.line(0, 100, 390, 100)
    card_book(c, 12, 120, 366, "done")
    c.r(12, 770, 366, 52, FG, 14)
    c.t(28, 801, "Rezerve edildi", 14, 600, "#FFFFFF")
    c.t(362, 801, "Geri al (8 sn)", 14, 600, "#93C5FD", "end")
    c.note(20, 280, "Odak sonuç satırına gider; canlı bölge duyurur", 11)
    c.note(20, 296, "Geri al: kartta ve 8 sn'lik bildirimde", 11)
    c.note(20, 312, "Takip çipleri: “Takvimime ekle” · “Başka saat”", 11)
    c.chip(20, 330, "Takvimime ekle", h=44)
    c.chip(170, 330, "Başka saat", h=44)
    # D show-me on phone
    d = S(390, 844, "d")
    d.phone_shell("Profil", 4, ACAD_TABS)
    d.r(16, 120, 358, 56, CARD, 12, LINE); d.t(32, 154, "Bildirimler", 15, 500)
    d.r(16, 186, 358, 56, CARD, 12, LINE); d.t(32, 220, "Takvim", 15, 600)
    d.r(10, 180, 370, 68, "none", 16, PRI, 3)
    d.r(0, 0, 390, 844, SCRIM, 0, op=.25)
    d.r(0, 520, 390, 241, CARD, 24, LINE)
    d.t(20, 556, "Takvim", 17, 700)
    d.t(20, 582, "Derslerinizi ve rezervasyonlarınızı Google, Outlook", 13, 400, MUTED)
    d.t(20, 600, "ya da Apple takviminize buradan eklersiniz.", 13, 400, MUTED)
    d.btn(20, 630, 168, 48, "Anladım", "sec", 15)
    d.btn(200, 630, 170, 48, "Yardımcıya dön", "pri", 15)
    d.note(20, 700, "Panel kapanır, sayfa açılır, halka hedefte;", 11)
    d.note(20, 716, "adım kartı alta yaslanır (WG-05 telefon düzeni)", 11)
    for i, part in enumerate([a, b, c, d]):
        s.o.append(f"<g transform='translate({i * 410},0)'><rect width='390' height='844' rx='36' fill='{BG}' stroke='{LINE}'/>")
        s.o.extend(part.o[1:])
        s.o.append(f"<text x='16' y='838' font-size='12' font-weight='700' fill='#7C3AED'>{'ABCD'[i]}</text></g>")
    s.o.append("</g>")
    s.save(os.path.join(OUT, "helper-390.svg"))


# ---------------------------------------------------------------- 5. card catalogue (states and risk classes)
def cards():
    s = S(1440, 1010, "Eylem kartı kataloğu: risk sınıfları ve durumlar")
    s.t(24, 44, "Eylem kartları (katalog v1): yalnızca tipli şema, mevcut API, risk sınıfına göre onay", 22, 700)
    col = 330

    def frame(x, y, h, title, risk, accent=None):
        s.r(x, y, col, h, "#F1F5F9", 14, LINE)
        if accent:
            s.r(x, y, col, 8, accent, 4)
        s.t(x + 16, y + 30, title, 14, 650)
        s.badge(x + col - 54, y + 14, risk, PRI if risk != "R3" else WARN, TINT if risk != "R3" else WARNBG)

    # where R0
    x, y = 24, 70
    frame(x, y, 200, "Nerede? · where", "R0")
    s.t(x + 16, y + 56, "Yönetim › Dönem ve saatler › Tatiller", 12, 600, PRI)
    s.t(x + 16, y + 82, "1. Tatiller sekmesini açın.  2. “Tatil ekle”.", 12, 400)
    s.btn(x + 16, y + 140, 100, 40, "Göster", "pri", 13)
    s.btn(x + 126, y + 140, 120, 40, "Sayfayı aç", "sec", 13)
    # ask_choice
    x = 24 + col + 20
    frame(x, y, 200, "Hangi salon? · ask_choice", "R0")
    for i, o in enumerate(["A 204 · 40 kişi", "B 101 · 30 kişi", "Amfi 2 · 120 kişi"]):
        s.r(x + 16, y + 48 + i * 46, col - 32, 40, CARD, 10, LINE)
        s.t(x + 30, y + 73 + i * 46, f"{i + 1}  {o}", 13, 500)
    # find_room
    x = 24 + 2 * (col + 20)
    frame(x, y, 200, "Derslik bul · find_room", "R0")
    cx = x + 16
    for ch in ["Per 14:00", "12+ kişi", "Projeksiyon"]:
        cx += s.chip(cx, y + 46, ch, h=30, size=11) + 6
    for i, r in enumerate(["A 204 · 40", "B 101 · 30", "C 012 · 16"]):
        s.t(x + 16, y + 106 + i * 22, r, 12, 500)
        s.t(x + col - 16, y + 106 + i * 22, "Seç", 12, 600, PRI, "end")
    s.t(x + 16, y + 186, "Tümünü Derslik bul'da aç", 12, 600, PRI)
    # add_to_calendar R1
    x = 24 + 3 * (col + 20)
    frame(x, y, 200, "Takvimime ekle · add_to_calendar", "R1")
    for i, ch in enumerate(["Google", "Outlook", "Apple"]):
        s.chip(x + 16 + i * 92, y + 46, ch, sel=(i == 0), h=32, size=12)
    s.t(x + 16, y + 106, "Kapsam: Derslerim  ·  Rezervasyonlarım", 12, 500)
    s.t(x + 16, y + 126, "Takviminize yalnızca ders adı, salon, saat gider.", 11, 400, MUTED)
    s.btn(x + 16, y + 146, col - 32, 40, "Google takvimine ekle", "pri", 13)
    # book_room states
    y2 = 300
    card_book(s, 24, y2, col, "proposed")
    s.note(24, y2 + 226, "book_room R1: kart = onay; onay gerekirse düğme “Talep et”", 11)
    card_book(s, 24 + col + 20, y2, col, "done")
    s.note(24 + col + 20, y2 + 136, "done: sonuç + nesne bağlantısı + Geri al", 11)
    # error
    x = 24 + 2 * (col + 20)
    s.r(x, y2, col, 150, "#F1F5F9", 14, LINE)
    s.t(x + 16, y2 + 28, "Salon rezervasyonu", 14, 650)
    s.r(x + 16, y2 + 44, col - 32, 44, BADBG, 10)
    s.t(x + 28, y2 + 71, "Bu saat az önce doldu.", 12, 600, BAD)
    s.btn(x + 16, y2 + 100, 150, 36, "Başka saat öner", "sec", 12)
    s.note(x, y2 + 166, "error: API'nin message_tr metni; alanlar korunur; sallama yok", 11)
    # expired
    x = 24 + 3 * (col + 20)
    s.r(x, y2, col, 110, "#F8FAFC", 14, LINE)
    s.t(x + 16, y2 + 28, "Salon rezervasyonu", 14, 650, MUTED)
    s.t(x + 16, y2 + 56, "Bu öneri eskidi.", 12, 500, MUTED)
    s.btn(x + 16, y2 + 66, 100, 34, "Yenile", "sec", 12)
    s.note(x, y2 + 126, "10 dk ya da veri değişince (409) eskir", 11)
    # invite_user R2
    y3 = 560
    x = 24
    frame(x, y3, 300, "Kullanıcı davet et · invite_user", "R2")
    for i, (lab, val) in enumerate([("E-posta", "a.kaya@uni.edu.tr"), ("Ad", "A. K."), ("Rol", "Öğretim elemanı ▾"),
                                     ("Bölüm", "Psikoloji ▾")]):
        s.t(x + 16, y3 + 62 + i * 40, lab, 12, 500, MUTED)
        s.r(x + 90, y3 + 44 + i * 40, col - 106, 30, CARD, 8, "#94A3B8")
        s.t(x + 100, y3 + 64 + i * 40, val, 12, 500)
    s.r(x + 16, y3 + 206, col - 32, 30, WARNBG, 8)
    s.t(x + 28, y3 + 226, "Etkilenen: A. K.'ye davet e-postası gider", 12, 500, WARN)
    s.btn(x + 16, y3 + 246, col - 32, 40, "Davet gönder", "pri", 13)
    s.note(x, y3 + 316, "R2: etkilenen kişi gösterilmeden düğme etkin değil;", 11)
    s.note(x, y3 + 332, "rol listesi = yöneticinin verebildikleri", 11)
    # approvals_list R2
    x = 24 + col + 20
    frame(x, y3, 300, "Bekleyen talepler · approvals_list", "R2")
    for i, r in enumerate(["P. T. · A 204 · Per 14:00", "S. K. · Amfi 2 · Cum 09:00"]):
        yy = y3 + 50 + i * 100
        s.r(x + 16, yy, col - 32, 88, CARD, 10, LINE)
        s.t(x + 28, yy + 24, r, 12, 600)
        s.btn(x + 28, yy + 38, 110, 40, "Onayla", "pri", 12)
        s.btn(x + 148, yy + 38, 130, 40, "Reddet…", "sec", 12)
    s.note(x, y3 + 316, "Reddet gerekçe ister (sayfadaki seçim)", 11)
    # publish_run R3
    x = 24 + 2 * (col + 20)
    frame(x, y3, 300, "Planı yayınla · publish_run", "R3", WARN)
    s.t(x + 16, y3 + 58, "Çalıştırma #12 · puan 0,94", 12, 600)
    for i, l in enumerate(["Yayındaki plana göre 23 ders değişti", "4 salon değişti", "2 öğretim elemanı etkilenir",
                           "Engel yok"]):
        s.t(x + 16, y3 + 86 + i * 22, "• " + l, 12, 400)
    s.btn(x + 16, y3 + 246, col - 32, 40, "Yayınlama penceresini aç", "sec", 13)
    s.note(x, y3 + 316, "R3: sunucu önizlemesi; düğme çalıştırmalar sayfasının", 11)
    s.note(x, y3 + 332, "kendi onay penceresini açar (iki adım, asla tek tık)", 11)
    # download_report
    x = 24 + 3 * (col + 20)
    frame(x, y3, 200, "Raporu indir · download_report", "R0")
    s.t(x + 16, y3 + 58, "Rezervasyonlar · 7–13 Eki", 12, 600)
    for i, ch in enumerate(["CSV", "XLSX"]):
        s.chip(x + 16 + i * 80, y3 + 72, ch, sel=(i == 0), h=32, size=12)
    s.t(x + 16, y3 + 132, "≈ 1.240 satır", 12, 400, MUTED)
    s.btn(x + 16, y3 + 146, col - 32, 40, "İndir (CSV)", "pri", 13)
    s.note(24, 990, "Model yalnızca {kind, props} seçer; sunucu doğrular, adları kimliğe çözer, izni denetler, önizlemeyi hesaplar. HTML/JS/URL/kimlik modelden gelmez. “evet” yazmak onay sayılmaz.", 12)
    s.save(os.path.join(OUT, "helper-cards.svg"))


# ---------------------------------------------------------------- 6. states: limit, AI off, memory
def states():
    s = S(1440, 760, "Yardımcı durumları: sınır, yapay zekâ kapalı, bellek")
    s.t(24, 44, "Durumlar", 22, 700)
    # A limit
    x, y, w = 24, 70, 440
    s.r(x, y, w, 600, CARD, 20, LINE)
    s.t(x + 20, y + 34, "Yardımcı", 17, 700)
    chip_status(s, x + 112, y + 16, "Sınıra ulaşıldı", BAD)
    s.line(x, y + 54, x + w, y + 54)
    s.t(x + 20, y + 90, "Kısayollar hâlâ çalışır:", 13, 600)
    cx = x + 20
    for ch in ["Salon ayır", "Takvimime ekle", "Rezervasyonlarım"]:
        cx += s.chip(cx, y + 104, ch, h=44, size=12) + 8
    s.r(x + 20, y + 470, w - 40, 54, BADBG, 10)
    s.t(x + 32, y + 494, "Bu ayki yapay zekâ sınırınıza ulaştınız. 1 Kasım'da", 12, 500, BAD)
    s.t(x + 32, y + 512, "yenilenir. Arama ve kısayollar çalışıyor.", 12, 500, BAD)
    s.r(x + 20, y + 536, w - 40, 48, "#F1F5F9", 14, LINE)
    s.t(x + 36, y + 565, "Yapay zekâ sınırda", 13, 400, "#94A3B8")
    s.t(x + 20, y + 630, "A · %100 sınır: besteci kapalı, neden açıklamada", 12, 700, "#7C3AED")
    # B AI off / guide mode
    x = 24 + 460
    s.r(x, y, w, 600, CARD, 20, LINE)
    s.t(x + 20, y + 34, "Yardımcı", 17, 700)
    chip_status(s, x + 112, y + 16, "Yapay zekâ kapalı", "#94A3B8")
    s.line(x, y + 54, x + w, y + 54)
    s.r(x + 20, y + 74, w - 40, 60, TINT, 12)
    s.t(x + 32, y + 98, "Rehber modu: yapay zekâ kapalıyken de sayfaları", 12, 500, PRI)
    s.t(x + 32, y + 116, "ve kısayolları bulabilirsiniz.", 12, 500, PRI)
    s.r(x + 20, y + 150, w - 40, 48, CARD, 12, PRI, 2)
    s.t(x + 36, y + 180, "tatil", 15, 500)
    for i, (t1, t2) in enumerate([("Tatiller", "Yönetim › Dönem ve saatler"), ("“Tatil ekle” düğmesi", "Nerede? · Göster")]):
        s.r(x + 20, y + 212 + i * 60, w - 40, 52, "#F8FAFC", 10, LINE)
        s.t(x + 36, y + 234 + i * 60, t1, 13, 600)
        s.t(x + 36, y + 252 + i * 60, t2, 11, 400, SOFT)
    s.t(x + 20, y + 630, "B · kurum yapay zekâyı kapattı: dizin + kısayollar, besteci yok", 12, 700, "#7C3AED")
    # C memory
    x = 24 + 2 * 460
    s.r(x, y, w, 600, CARD, 20, LINE)
    s.t(x + 20, y + 40, "Profil › Yardımcı neleri hatırlıyor?", 16, 700)
    s.r(x + 20, y + 62, w - 40, 52, "#F8FAFC", 12, LINE)
    s.t(x + 36, y + 93, "Yardımcı yaptıklarımı hatırlasın", 13, 500)
    s.r(x + w - 76, y + 76, 44, 24, PRI, 12); s.c(x + w - 44, y + 88, 9, "#FFFFFF")
    for i, (t1, t2) in enumerate([("A 204 rezerve edildi", "Son görev · 17 Eki"), ("Takvimime ekle: Google", "Son görev · 15 Eki"),
                                   ("Tercih edilen bina: B blok", "Tercih · 12 Eki")]):
        yy = y + 132 + i * 60
        s.r(x + 20, yy, w - 40, 52, CARD, 10, LINE)
        s.t(x + 36, yy + 22, t1, 13, 600)
        s.t(x + 36, yy + 40, t2, 11, 400, SOFT)
        s.btn(x + w - 100, yy + 6, 64, 40, "Sil", "sec", 12)
    s.btn(x + 20, y + 330, 140, 44, "Tümünü sil", "sec", 13)
    s.t(x + 20, y + 400, "Yardımcı yalnızca bu listeyi hatırlar. Konuşmalarınız", 12, 400, MUTED)
    s.t(x + 20, y + 418, "kaydedilmez. Bu bilgiler hesabınız silinince silinir.", 12, 400, MUTED)
    s.t(x + 20, y + 630, "C · bellek: görünür, tek tek silinir, 90 gün, KVKK DSR", 12, 700, "#7C3AED")
    s.save(os.path.join(OUT, "helper-states.svg"))


if __name__ == "__main__":
    search_1440(); sheet_1440(); where_1440(); phone_390(); cards(); states()
    print("ok")
