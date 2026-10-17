"""Welcome guide wireframes (docs/design/v3/welcome-guide.md). Reuses the W3-DES kit in ./src/wf.py.
Usage, from docs/design/v3/wireframes:  python3 -I welcome-gen.py .
Purple text is an annotation, not UI copy. Names are initials only (KVKK)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from wf import *  # noqa: E402,F401

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
ACAD_TABS = ("Rezerve et", "Rezervasyonlarım", "Derslik bul", "Taleplerim", "Daha")
ACAD_NAV = ["Hızlı rezervasyon", "Rezervasyonlar", "Rezervasyonlarım", "Derslik bul", "Taleplerim", "§HESAP", "Profil"]
ADMIN_NAV = ["Panel", "Dosyalardan kur", "Talepler", "Oluştur", "Haftalık program", "§YÖNETİM", "Ayarlar",
             "Kullanıcılar", "Entegrasyonlar", "Yapay zekâ", "Sistem durumu", "Karşılama rehberi"]
SCRIM = "#0F172A"


def dots(s, cx, y, n, cur):
    x = cx - (n - 1) * 8
    for i in range(n):
        if i == cur:
            s.r(x - 9, y - 4, 18, 8, PRI, 4)
        else:
            s.c(x, y, 4, "#CBD5E1")
        x += 16


def hero(s, x, y, w, h, label="Lottie: rol kahramanı (bir kez oynar, poster karede durur)"):
    s.r(x, y, w, h, TINT, 16)
    # a tiny room x slot grid as the hero placeholder
    gx, gy = x + w / 2 - 110, y + 26
    for r in range(3):
        for c in range(6):
            fill = CAT[(r + c) % 5] if (r * 6 + c) % 4 == 0 else "#FFFFFF"
            s.r(gx + c * 38, gy + r * 30, 32, 24, fill, 6, LINE)
    s.c(gx + 5 * 38 + 16, gy + 2 * 30 + 12, 11, OKBG)
    s.poly([(gx + 5 * 38 + 10, gy + 72), (gx + 5 * 38 + 15, gy + 77), (gx + 5 * 38 + 23, gy + 67)], OK, 2.4)
    s.note(x + 12, y + h - 10, label, 10)


def card(s, x, y, w, h, icon_col, title, body, n=None):
    s.r(x, y, w, h, CARD, 14, LINE)
    s.r(x + 14, y + 14, 32, 32, icon_col, 9, op=.18)
    s.r(x + 22, y + 22, 16, 16, icon_col, 4)
    if n is not None:
        s.t(x + w - 14, y + 30, str(n), 11, 600, SOFT, "end")
    s.t(x + 14, y + 66, title, 14, 650)
    words, line, ly = body.split(), "", y + 86
    for wd in words:
        if len(line + " " + wd) * 6.9 > w - 28:
            s.t(x + 14, ly, line.strip(), 12, 400, MUTED); ly += 17; line = ""
        line += " " + wd
    if line.strip():
        s.t(x + 14, ly, line.strip(), 12, 400, MUTED)


ACAD_CARDS = [
    (PRI, "Hızlı rezervasyon", "Sıradaki boş saat hazır gelir: salonu seçin, Rezerve et."),
    (CAT[2], "Taleplerim", "Ders planlama talepleriniz ve onay durumları tek yerde."),
    (CAT[1], "Rezervasyonlarım", "Rezervasyonlarınızı görün, iptal edin ya da talebi geri çekin."),
    (CAT[3], "Takvimime ekle", "Derslerinizi Google, Outlook ya da Apple takviminize ekleyin."),
]


# 1 ----------------------------------------------------------------------------------- welcome sheet, desktop
def sheet1440():
    s = S(1440, 900, "Welcome sheet, desktop 1440, academician")
    s.desk_shell("Hızlı rezervasyon", 0, ACAD_NAV)
    s.r(0, 0, 1440, 900, SCRIM, 0, op=.38)
    x, y, w, h = 400, 96, 640, 708
    s.r(x, y, w, h, "#FFFFFF", 24, LINE)
    s.t(x + w - 28, y + 38, "✕", 16, 500, SOFT, "end")
    s.note(x + w - 200, y + 20, "✕ = Sonra (Esc), focus returns", 10)
    hero(s, x + 24, y + 56, w - 48, 150)
    s.t(x + 32, y + 246, "SmartSched'e hoş geldiniz, A. T.", 26, 700)
    s.t(x + 32, y + 274, "Derslerinizi görün, boş bir salonu üç dokunuşta ayırın, takviminize ekleyin.", 14, 400, MUTED)
    s.badge(x + 32, y + 288, "Öğretim elemanı · Psikoloji", PRI, TINT)
    cw = (w - 64 - 12) / 2
    for i, (col, t, b) in enumerate(ACAD_CARDS):
        cx = x + 32 + (i % 2) * (cw + 12); cy = y + 322 + (i // 2) * 128
        card(s, cx, cy, cw, 116, col, t, b)
    s.note(x + 32, y + 588, "3–5 cards per audience; stagger 30 ms on first reveal only (≤ 120 ms total)", 10)
    s.btn(x + 32, y + 612, 260, 48, "Kısa turu başlat (1 dk)")
    s.btn(x + 304, y + 612, 150, 48, "Sonra", "sec")
    s.t(x + w - 32, y + 642, "Başlarken listesi", 14, 600, PRI, "end")
    s.t(x + 32, y + 690, "Bu rehberi her zaman Yardım › Turu yeniden başlat ile açabilirsiniz.", 12, 400, SOFT)
    s.save(f"{OUT}/welcome-sheet-1440.svg")


# 2 ----------------------------------------------------------------------------------- welcome sheet, phone
def sheet390():
    s = S(390, 844, "Welcome sheet, phone 390, bottom sheet with step dots")
    s.phone_shell("Hızlı rezervasyon", 0, ACAD_TABS)
    s.r(0, 0, 390, 844, SCRIM, 0, op=.38)
    y0 = 214
    s.r(0, y0, 390, 844 - y0, "#FFFFFF", 28)
    s.r(171, y0 + 8, 48, 5, "#CBD5E1", 3)
    s.note(232, y0 + 16, "grabber: drag down = Sonra", 10)
    hero(s, 20, y0 + 30, 350, 132, "Lottie hero (poster on reduced motion)")
    s.t(20, y0 + 196, "Hoş geldiniz, A. T.", 24, 700)
    s.t(20, y0 + 220, "Salon ayırmak artık üç dokunuş.", 15, 400, MUTED)
    card(s, 20, y0 + 238, 350, 120, PRI, ACAD_CARDS[0][1], ACAD_CARDS[0][2], "1 / 4")
    s.note(20, y0 + 376, "one card per page; swipe or İleri; page-side-by-side recipe", 10)
    dots(s, 195, y0 + 398, 4, 0)
    s.btn(20, y0 + 420, 350, 50, "İleri")
    s.btn(20, y0 + 478, 168, 44, "Sonra", "sec")
    s.btn(202, y0 + 478, 168, 44, "Turu başlat", "sec")
    s.note(20, y0 + 540, "44 px targets · safe-area padding · tab bar hidden under the sheet", 10)
    s.save(f"{OUT}/welcome-sheet-390.svg")


# 3 ----------------------------------------------------------------------------------- guided tour, desktop
def tour1440():
    s = S(1440, 900, "Guided tour step, desktop 1440, spotlight on a sidebar entry")
    s.desk_shell("Hızlı rezervasyon", 0, ACAD_NAV)
    s.t(276, 84, "Ne zaman, nerede: üç adımda bir ders saati ayırın.", 14, 400, MUTED)
    s.r(276, 108, 1140, 760, CARD, 14, LINE)
    for i in range(6):
        s.r(300, 140 + i * 64, 520, 48, "#F8FAFC", 10, LINE)
    # scrim with a hole around "Taleplerim" (5th nav item, y = 80 + 4*36)
    hy = 80 + 4 * 36
    s.r(0, 0, 1440, hy - 6, SCRIM, 0, op=.45); s.r(0, hy + 38, 1440, 900 - hy - 38, SCRIM, 0, op=.45)
    s.r(0, hy - 6, 18, 44, SCRIM, 0, op=.45); s.r(238, hy - 6, 1202, 44, SCRIM, 0, op=.45)
    s.r(18, hy - 6, 220, 44, "none", 12, PRI, 3)
    s.note(24, 860, "ring = one overlay element moved by transform (spring smooth)", 10)
    x, y = 262, hy - 40
    s.r(x, y, 380, 214, "#FFFFFF", 18, LINE)
    s.poly([(x, y + 52), (x - 10, y + 60), (x, y + 68)], "#FFFFFF", 1, "#FFFFFF")
    s.t(x + 20, y + 32, "Adım 2 / 5", 12, 600, SOFT)
    s.t(x + 360, y + 32, "Turu bitir", 13, 600, PRI, "end")
    s.t(x + 20, y + 62, "Taleplerim", 18, 700)
    s.t(x + 20, y + 88, "Gelecek dönem için ders saati ve salon", 13, 400, MUTED)
    s.t(x + 20, y + 106, "taleplerinizi buradan gönderir, onay", 13, 400, MUTED)
    s.t(x + 20, y + 124, "durumlarını izlersiniz.", 13, 400, MUTED)
    dots(s, x + 60, y + 178, 5, 1)
    s.btn(x + 160, y + 156, 90, 44, "Geri", "sec"); s.btn(x + 262, y + 156, 100, 44, "İleri")
    s.note(x, y + 236, "role=dialog · aria-labelledby title · live: ‘Adım 2 / 5: Taleplerim’", 10)
    s.note(x, y + 252, "Esc = Turu bitir (state: dismissed at step 2) · ← → step · Tab trapped in card", 10)
    s.save(f"{OUT}/welcome-tour-1440.svg")


# 4 ----------------------------------------------------------------------------------- guided tour, phone
def tour390():
    s = S(390, 844, "Guided tour step, phone 390, spotlight on a tab bar item")
    s.phone_shell("Hızlı rezervasyon", 0, ACAD_TABS)
    for i in range(5):
        s.r(20, 120 + i * 68, 350, 56, CARD, 12, LINE)
    ty = 844 - 83
    cx = 390 / 5 * 3.5
    s.r(0, 0, 390, ty + 2, SCRIM, 0, op=.45)
    s.r(0, ty + 2, cx - 36, 81, SCRIM, 0, op=.45); s.r(cx + 36, ty + 2, 390 - cx - 36, 81, SCRIM, 0, op=.45)
    s.r(cx - 36, ty + 4, 72, 60, "none", 14, PRI, 3)
    y0 = 470
    s.r(8, y0, 374, ty - y0 - 14, "#FFFFFF", 24, LINE)
    s.poly([(cx - 10, ty - 14), (cx, ty - 4), (cx + 10, ty - 14)], "#FFFFFF", 1, "#FFFFFF")
    s.t(24, y0 + 30, "Adım 4 / 5", 12, 600, SOFT); s.t(366, y0 + 30, "Turu bitir", 14, 600, PRI, "end")
    s.t(24, y0 + 62, "Taleplerim", 20, 700)
    s.t(24, y0 + 88, "Ders planlama taleplerinizi buradan", 14, 400, MUTED)
    s.t(24, y0 + 108, "gönderir, onay durumlarını izlersiniz.", 14, 400, MUTED)
    dots(s, 195, y0 + 140, 5, 3)
    s.btn(24, y0 + 162, 160, 48, "Geri", "sec"); s.btn(198, y0 + 162, 168, 48, "İleri")
    s.note(20, y0 - 12, "phone: the step card is a bottom sheet above the target, never a floating tooltip", 10)
    s.note(20, y0 + 238, "no swipe-only path; buttons + dots carry the state", 10)
    s.save(f"{OUT}/welcome-tour-390.svg")


CHECK = [("Profilinizi tamamlayın", True, "Bölüm ve dil"), ("İlk rezervasyonunuzu yapın", True, "Hızlı rezervasyon"),
         ("Bildirim kanalı seçin", False, "E-posta, Telegram…"), ("Derslerinizi takviminize ekleyin", False, "Takvimime ekle"),
         ("Taleplerim sayfasına göz atın", False, "Taleplerim")]


def checklist_rows(s, x, y, w, rows=CHECK, row_h=60):
    for i, (t, done, sub) in enumerate(rows):
        yy = y + i * row_h
        s.r(x, yy, w, row_h - 8, "#F8FAFC" if done else CARD, 12, LINE)
        if done:
            s.c(x + 24, yy + 26, 11, OK); s.poly([(x + 19, yy + 26), (x + 23, yy + 30), (x + 30, yy + 21)], "#FFFFFF", 2.2)
        else:
            s.c(x + 24, yy + 26, 11, "#FFFFFF", "#94A3B8")
        s.t(x + 46, yy + 22, t, 14, 500 if not done else 400, SOFT if done else FG)
        s.t(x + 46, yy + 40, sub, 12, 400, MUTED)
        if not done:
            s.t(x + w - 16, yy + 30, "›", 18, 600, SOFT, "end")


# 5 ----------------------------------------------------------------------------------- checklist, desktop
def checklist1440():
    s = S(1440, 900, "Başlarken checklist, desktop 1440, sidebar pill and panel")
    s.desk_shell("Rezervasyonlarım", 2, ACAD_NAV)
    s.r(24, 780, 208, 92, TINT, 14, PRI)
    s.t(40, 806, "Başlarken", 14, 700, PRI); s.t(216, 806, "2 / 5", 13, 600, PRI, "end")
    s.r(40, 820, 176, 8, "#FFFFFF", 4); s.r(40, 820, 70, 8, PRI, 4)
    s.t(40, 852, "Sıradaki: Bildirim kanalı", 12, 500, FG)
    s.note(24, 770, "sidebar footer pill (button, aria-expanded)", 10)
    x, y, w = 256, 456, 420
    s.r(x, y, w, 420, "#FFFFFF", 20, LINE)
    s.t(x + 20, y + 36, "Başlarken", 18, 700); s.t(x + w - 20, y + 36, "Gizle", 13, 600, PRI, "end")
    s.t(x + 20, y + 60, "5 adımdan 2'si tamam", 13, 400, MUTED)
    s.r(x + 20, y + 72, w - 40, 8, "#E2E8F0", 4); s.r(x + 20, y + 72, (w - 40) * .4, 8, PRI, 4)
    checklist_rows(s, x + 16, y + 96, w - 32)
    s.note(x, y + 440, "items tick from server signals (a booking exists, a channel is linked…), not from clicks alone", 10)
    s.t(1060, 84, "Rezervasyonlarım", 14, 400, MUTED)
    s.save(f"{OUT}/welcome-checklist-1440.svg")


# 6 ----------------------------------------------------------------------------------- checklist, phone
def checklist390():
    s = S(390, 844, "Başlarken checklist, phone 390, Daha tab")
    s.phone_shell("Daha", 4, ACAD_TABS)
    y = 116
    s.r(20, y, 350, 92, TINT, 16, PRI)
    s.t(36, y + 30, "Başlarken", 16, 700, PRI); s.t(354, y + 30, "2 / 5", 14, 600, PRI, "end")
    s.r(36, y + 44, 318, 8, "#FFFFFF", 4); s.r(36, y + 44, 127, 8, PRI, 4)
    s.t(36, y + 76, "Sıradaki: Bildirim kanalı seçin  ›", 13, 500, FG)
    s.note(20, y + 108, "first row of Daha; never a floating button over the tab bar (G1)", 10)
    for i, t in enumerate(["Profil", "Bildirimler", "Takvimime ekle", "Yardım", "Çıkış yap"]):
        yy = y + 124 + i * 56
        s.r(20, yy, 350, 48, CARD, 12, LINE); s.t(36, yy + 30, t, 15, 500); s.t(354, yy + 30, "›", 18, 600, SOFT, "end")
    s.note(20, y + 420, "Yardım › Turu yeniden başlat · Başlarken listesi · Neler yeni · Klavye kısayolları", 10)
    s.save(f"{OUT}/welcome-checklist-390.svg")


# 7 ----------------------------------------------------------------------------------- hints + help menu
def hints():
    s = S(1440, 900, "Per-feature hints and the Help menu")
    s.t(32, 48, "Özellik ipuçları (wave 3) ve Yardım menüsü", 22, 700)
    # A: quick reserve hint anchored to nav entry
    s.r(32, 80, 660, 330, CARD, 16, LINE); s.t(52, 112, "A · Yeni özellik ipucu (masaüstü, bir kez)", 13, 600, SOFT)
    s.r(52, 132, 220, 36, TINT, 8); s.t(68, 156, "Hızlı rezervasyon", 13, 600, PRI)
    s.badge(196, 140, "Yeni", PRI, TINT)
    s.r(292, 128, 380, 176, "#FFFFFF", 16, PRI, 1.5)
    s.t(312, 158, "Yeni: Hızlı rezervasyon", 15, 700)
    s.t(312, 182, "Bugünün bir sonraki boş saati hazır gelir.", 13, 400, MUTED)
    s.t(312, 200, "Salonu seçin, Rezerve et'e dokunun.", 13, 400, MUTED)
    s.btn(312, 236, 120, 44, "Dene"); s.btn(444, 236, 120, 44, "Anladım", "sec")
    s.note(52, 330, "non-modal popover (role=dialog, aria-modal=false); focus is NOT moved; F6 / ‘?’ reaches it", 10)
    s.note(52, 346, "max one auto hint per page view; never while a sheet, tour or dialog is open", 10)
    s.note(52, 362, "dismiss = Anladım / Esc / click outside → state ‘seen’ on the server", 10)
    # B: admin hint as inline banner on /admin/ai
    s.r(716, 80, 692, 330, CARD, 16, LINE); s.t(736, 112, "B · Yönetici ipucu (sayfa içi şerit)", 13, 600, SOFT)
    s.r(736, 132, 652, 76, TINT, 12, PRI)
    s.t(756, 160, "Yeni: Yapay zekâ ayarları", 15, 700); s.t(756, 184, "Sağlayıcıları, özellik başına modeli ve aylık sınırı buradan seçin.", 13, 400, MUTED)
    s.t(1372, 160, "Anladım", 13, 600, PRI, "end")
    s.r(736, 220, 652, 160, "#F8FAFC", 12, LINE); s.t(756, 250, "/admin/ai içeriği", 13, 400, SOFT)
    s.note(736, 400, "same pattern for /admin/ops, /admin/integrations, calendar export (Profil › Takvim)", 10)
    # C: help menu
    s.r(32, 440, 660, 420, CARD, 16, LINE); s.t(52, 472, "C · Kullanıcı menüsü › Yardım", 13, 600, SOFT)
    s.r(52, 492, 300, 336, "#FFFFFF", 14, LINE)
    for i, (t, k) in enumerate([("Profil", ""), ("§YARDIM", ""), ("Turu yeniden başlat", ""), ("Başlarken listesi", "2 / 5"),
                                ("Neler yeni", "●"), ("Klavye kısayolları", "?"), ("§", ""), ("Çıkış yap", "")]):
        yy = 504 + i * 40
        if t.startswith("§"):
            s.t(68, yy + 24, t[1:], 11, 600, SOFT); continue
        if i == 2: s.r(60, yy, 284, 36, TINT, 8)
        s.t(72, yy + 23, t, 14, 500 if i == 2 else 400, PRI if i == 2 else FG)
        if k: s.t(332, yy + 23, k, 12, 600, SOFT, "end")
    s.note(372, 560, "also in ⌘K: ‘Turu yeniden başlat’", 10)
    s.note(372, 576, "restart opens the sheet for the current audience", 10)
    # D: phone hint = inline card at the top of the page, not a popover
    s.r(716, 440, 692, 420, CARD, 16, LINE); s.t(736, 472, "D · Telefonda ipucu (sayfa başında kart)", 13, 600, SOFT)
    s.r(880, 492, 300, 352, BG, 24, LINE); s.t(896, 530, "Profil", 20, 700)
    s.r(896, 548, 268, 108, TINT, 14, PRI); s.t(910, 574, "Yeni: Takvimime ekle", 14, 700)
    s.t(910, 596, "Derslerinizi kendi takviminize", 12, 400, MUTED); s.t(910, 612, "ekleyin.", 12, 400, MUTED)
    s.btn(910, 620, 110, 30, "Dene", size=13); s.btn(1030, 620, 120, 30, "Anladım", "sec", 13)
    s.note(736, 870, "phones: inline card, pushes content down, no overlay (mock at ~70 % scale; real buttons are 44 px)", 10)
    s.save(f"{OUT}/welcome-hints-help.svg")


# 8 ----------------------------------------------------------------------------------- admin control
def admin1440():
    s = S(1440, 900, "Admin: Karşılama rehberi settings, texts and completion")
    s.desk_shell("Karşılama rehberi", 11, ADMIN_NAV)
    x0 = 276
    s.t(x0, 84, "Yeni kullanıcıların ilk girişte gördüğü rehberi açın, metinlerini kurumunuza göre düzenleyin.", 14, 400, MUTED)
    x = x0
    for i, t in enumerate(["Genel", "Metinler", "Tamamlanma"]):
        x += s.chip(x, 104, t, sel=i == 0, h=36) + 8
    s.r(x0, 156, 540, 300, CARD, 14, LINE); s.t(x0 + 20, 188, "Rehber", 16, 700)
    rows = [("Karşılama rehberi", "İlk girişte rol kartları", True), ("Rehberli tur", "Gerçek ekranlarda 4–6 adım", True),
            ("Başlarken listesi", "Kenar çubuğu ve Daha sekmesi", True), ("Yeni özellik ipuçları", "Sürüm başına bir kez", True),
            ("Herkese ipucu göster", "Önceki ipuçlarını kapatmış olsalar da", False)]
    for i, (t, sub, on) in enumerate(rows):
        yy = 204 + i * 48
        s.t(x0 + 20, yy + 20, t, 14, 500); s.t(x0 + 20, yy + 38, sub, 12, 400, MUTED)
        s.r(x0 + 470, yy + 6, 50, 30, PRI if on else "#CBD5E1", 15); s.c(x0 + (505 if on else 485), yy + 21, 12, "#FFFFFF")
    s.r(x0 + 564, 156, 576, 300, CARD, 14, LINE); s.t(x0 + 584, 188, "Tamamlanma (son 30 gün)", 16, 700)
    s.t(x0 + 584, 212, "En az 5 kişilik gruplar gösterilir; kişi listesi yoktur.", 12, 400, MUTED)
    hdr = ["Kitle", "Gördü", "Tur", "Liste ≥ %80", "Kapattı"]
    xs = [x0 + 584, x0 + 790, x0 + 870, x0 + 950, x0 + 1060]
    for h, xx in zip(hdr, xs): s.t(xx, 244, h, 12, 600, SOFT)
    data = [("Öğretim elemanı", "412", "%58", "%41", "%12"), ("İdari personel", "96", "%47", "%52", "%9"),
            ("Onaylayıcı", "14", "%71", "%64", "%7"), ("Planlamacı", "6", "%83", "%50", "%0"), ("Yönetici", "<5", "–", "–", "–")]
    for i, row in enumerate(data):
        yy = 272 + i * 34
        for v, xx in zip(row, xs): s.t(xx, yy, v, 13, 500 if xx == xs[0] else 400)
        if row[2] != "–":
            s.r(xs[2] + 36, yy - 10, 30, 8, "#E2E8F0", 4); s.r(xs[2] + 36, yy - 10, 30 * int(row[2][1:]) / 100, 8, PRI, 4)
    s.note(x0 + 584, 446, "numbers illustrative", 10)
    s.r(x0, 476, 1140, 392, CARD, 14, LINE); s.t(x0 + 20, 508, "Metinler · Öğretim elemanı", 16, 700)
    x = x0 + 20
    for i, t in enumerate(["Öğretim elemanı", "İdari personel", "Onaylayıcı", "Bölüm yöneticisi", "Planlamacı", "Yönetici"]):
        x += s.chip(x, 522, t, sel=i == 0, h=34, size=12) + 6
    s.t(x0 + 20, 584, "Başlık (Türkçe)", 12, 600, SOFT); s.r(x0 + 20, 592, 540, 44, "#FFFFFF", 10, "#94A3B8")
    s.t(x0 + 34, 620, "SmartSched'e hoş geldiniz, {ad}", 15)
    s.t(x0 + 580, 584, "Title (English)", 12, 600, SOFT); s.r(x0 + 580, 592, 540, 44, "#FFFFFF", 10, "#94A3B8")
    s.t(x0 + 594, 620, "Welcome to SmartSched, {name}", 15)
    s.t(x0 + 20, 664, "Kart 1 · Hızlı rezervasyon", 12, 600, SOFT); s.r(x0 + 20, 672, 540, 64, "#FFFFFF", 10, "#94A3B8")
    s.t(x0 + 34, 700, "Bir sonraki boş saat hazır seçili gelir…", 14)
    s.t(x0 + 20, 756, "Varsayılana dön", 13, 600, PRI)
    s.btn(x0 + 760, 800, 170, 44, "Önizle", "sec"); s.btn(x0 + 942, 800, 178, 44, "Kaydet")
    s.t(x0 + 20, 826, "Son değişiklik: F. B., 17 Ekim 14:02", 12, 400, MUTED)
    s.r(x0 + 300, 790, 440, 64, WARNBG, 12); s.t(x0 + 316, 816, "Kaydedince bu kitleye rehber yeniden", 13, 500, WARN)
    s.t(x0 + 316, 836, "gösterilsin mi?  ☐ Evet, ‘Güncellendi’ etiketiyle", 13, 500, WARN)
    s.save(f"{OUT}/welcome-admin-1440.svg")


# 9 ----------------------------------------------------------------------------------- admin control, phone
def admin390():
    s = S(390, 844, "Admin: Karşılama rehberi on a phone")
    s.phone_shell("Karşılama rehberi", 4)
    x = 20
    for i, t in enumerate(["Genel", "Metinler", "Tamamlanma"]):
        x += s.chip(x, 112, t, sel=i == 2, h=44) + 8
    for i, (k, a, b) in enumerate([("Öğretim elemanı", "412 gördü", "Tur %58 · Liste %41"), ("İdari personel", "96 gördü", "Tur %47 · Liste %52"),
                                    ("Onaylayıcı", "14 gördü", "Tur %71 · Liste %64"), ("Planlamacı", "6 gördü", "Tur %83 · Liste %50"),
                                    ("Yönetici", "5'ten az", "Gizli (küçük grup)")]):
        yy = 176 + i * 92
        s.r(20, yy, 350, 80, CARD, 14, LINE); s.t(36, yy + 30, k, 15, 600); s.t(354, yy + 30, a, 13, 400, MUTED, "end")
        s.t(36, yy + 56, b, 13, 400, MUTED)
    s.note(20, 650, "one stat card per audience; texts edit in a full-screen page per audience", 10)
    s.save(f"{OUT}/welcome-admin-390.svg")


if __name__ == "__main__":
    for f in (sheet1440, sheet390, tour1440, tour390, checklist1440, checklist390, hints, admin1440, admin390):
        f()
    print("ok")
