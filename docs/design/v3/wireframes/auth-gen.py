"""Sign-in, 2FA and passkey wireframes (docs/design/v3/auth.md). Reuses the W3-DES kit in ./src/wf.py.
Usage, from docs/design/v3/wireframes:  python3 -I auth-gen.py .
Purple text is an annotation, not UI copy. Names are illustrative initials (KVKK)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from wf import *  # noqa: E402,F401,F403

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
GREY = "#94A3B8"
FIELD = "#F1F5F9"
EDGE = "#8A94A6"
FOCUS = "#2563EB"
SCRIM = "#0F172A"
ADMIN_NAV = ["Panel", "Talepler", "Haftalık program", "§YÖNETİM", "Ayarlar", "Kullanıcılar", "Entegrasyonlar",
             "Sistem durumu"]
ACCT_NAV = ["Rezerve et", "Rezervasyonlarım", "Derslik bul", "§HESAP", "Profil"]


# --- small parts -------------------------------------------------------------------------------------------------
def field(s, x, y, w, label, value="", h=44, state="default", right=None, hint=None, msg=None, link=None, mono=False):
    s.t(x, y - 8, label, 14, 600)
    if link:
        s.t(x + w, y - 8, link, 13, 500, PRI, "end")
    edge = {"default": EDGE, "focus": FOCUS, "error": BAD, "ok": OK, "auto": EDGE, "ro": EDGE}[state]
    fill = {"auto": "#EAF1FD", "focus": "#FFFFFF", "ro": "#FFFFFF"}.get(state, FIELD)
    s.r(x, y, w, h, fill, 10, edge, 2 if state in ("focus", "error", "ok") else 1, dash="4 3" if state == "ro" else None)
    if state == "focus":
        s.r(x - 3, y - 3, w + 6, h + 6, "none", 12, "#BFD3FB", 3)
    if value:
        s.t(x + 14, y + h / 2 + 5, value, 15, 500 if mono else 400, FG if state != "ro" else MUTED)
    if right:
        s.t(x + w - 16, y + h / 2 + 5, right, 13, 600, MUTED, "end")
    yy = y + h + 18
    if hint:
        s.t(x, yy, hint, 12, 400, MUTED); yy += 18
    if msg:
        col = BAD if state == "error" else OK if state == "ok" else WARN
        s.t(x, yy, msg, 12, 600, col)
    return s


def slots(s, x, y, digits="", coarse=False, state="default", active=None):
    w, h, g, mid = (48, 56, 8, 12) if coarse else (44, 52, 8, 16)
    cx = x
    for i in range(6):
        edge = {"default": EDGE, "error": BAD, "ok": OK}[state]
        sw = 2 if state in ("error", "ok") else 1
        if active == i:
            edge, sw = FOCUS, 2
        s.r(cx, y, w, h, FIELD if state == "default" else "#FFFFFF", 10, edge, sw)
        if i < len(digits):
            s.t(cx + w / 2, y + h / 2 + 9, digits[i], 24, 600, FG, "middle")
        elif active == i:
            s.r(cx + w / 2 - 1, y + h / 2 - 12, 2, 24, FOCUS, 1)
        cx += w + (mid if i == 2 else g)
    return cx - x - g


def checkbox(s, x, y, label, on=False, hint=None):
    s.r(x, y, 20, 20, PRI if on else "#FFFFFF", 5, PRI if on else EDGE, 1.5)
    if on:
        s.poly([(x + 5, y + 10), (x + 9, y + 14), (x + 15, y + 6)], "#FFFFFF", 2)
    s.t(x + 30, y + 15, label, 14, 500)
    if hint:
        s.t(x + 30, y + 34, hint, 12, 400, MUTED)


def ms_button(s, x, y, w, h=44):
    s.r(x, y, w, h, "#FFFFFF", 12, "#8C8C8C")
    bx = x + w / 2 - 110
    for dx, dy, col in ((0, 0, "#F25022"), (10, 0, "#7FBA00"), (0, 10, "#00A4EF"), (10, 10, "#FFB900")):
        s.r(bx + dx, y + h / 2 - 10 + dy, 9, 9, col, 0)
    s.t(bx + 30, y + h / 2 + 5, "Microsoft ile giriş yap", 15, 600, "#5E5E5E")


def g_button(s, x, y, w, h=44):
    s.r(x, y, w, h, "#FFFFFF", 12, "#747775")
    bx = x + w / 2 - 100
    s.c(bx + 9, y + h / 2, 9, "none", "#4285F4")
    s.t(bx + 9, y + h / 2 + 4, "G", 11, 700, "#4285F4", "middle")
    s.t(bx + 30, y + h / 2 + 5, "Google ile oturum açın", 14, 500, "#1F1F1F")


def key_glyph(s, x, y, col=FG):
    s.c(x + 5, y + 8, 5, "none", col)
    s.line(x + 10, y + 8, x + 20, y + 8, col, 2).line(x + 17, y + 8, x + 17, y + 12, col, 2)


def brand(s, x, y, w):
    s.r(x, y, 96, 32, "#F1F5F9", 8).t(x + 48, y + 21, "Üniversite logosu", 10, 500, MUTED, "middle")
    s.line(x + 108, y + 4, x + 108, y + 28, "#CBD5E1")
    s.r(x + 120, y + 4, 24, 24, PRI, 6).t(x + 132, y + 21, "S", 13, 700, "#FFFFFF", "middle")
    s.t(x + 152, y + 22, "SmartSched", 15, 700)


def footer(s, x, y, w):
    s.t(x, y, "KVKK Aydınlatma Metni   v1.4.0", 12, 400, MUTED)
    s.r(x + w - 140, y - 18, 84, 32, "#F1F5F9", 16).t(x + w - 98, y + 3, "TR | EN", 12, 600, FG, "middle")
    s.r(x + w - 44, y - 18, 32, 32, "#F1F5F9", 16).t(x + w - 28, y + 3, "◐", 13, 600, FG, "middle")


def sheet_desktop(s, title):
    s.r(0, 0, 1440, 900, "#E8EEF6", 0)
    s.r(8, 8, 480, 884, "#FFFFFF", 22, LINE, op=.96)
    return 48, 400


def hero(s, x, y, w, h):
    s.r(x, y, w, h, "#FFFFFF", 18, LINE, op=.55)
    cols, rows = 8, 5
    cw, ch = (w - 80) / cols, (h - 90) / rows
    for r in range(rows):
        s.t(x + 28, y + 52 + r * ch + ch / 2, f"B-{201 + r}", 10, 600, SOFT)
        for c in range(cols):
            fill = CAT[(r * 3 + c) % 5] if (r * 7 + c * 3) % 4 else "#FFFFFF"
            s.r(x + 64 + c * cw, y + 40 + r * ch, cw - 6, ch - 6, fill, 6, LINE, op=.85 if fill != "#FFFFFF" else 1)
    s.r(x + 64, y + h - 34, w - 160, 8, "#E2E8F0", 4).r(x + 64, y + h - 34, w - 160, 8, OK, 4)
    s.badge(x + w - 86, y + h - 40, "100/100", OK, OKBG)


# --- 1. sign-in ---------------------------------------------------------------------------------------------------
def signin_body(s, x, w, y, phone):
    brand(s, x, y, w)
    y += 84 if not phone else 64
    s.t(x, y, "Giriş yap", 30 if not phone else 28, 700)
    s.t(x, y + 26, "Örnek Üniversitesi · ders programı, sınavlar ve derslik", 13, 400, MUTED)
    s.t(x, y + 44, "rezervasyonu", 13, 400, MUTED)
    y += 66
    h = 48 if phone else 44
    ms_button(s, x, y, w, h)
    g_button(s, x, y + h + 12, w, h)
    y += 2 * h + 34
    s.line(x, y, x + w, y)
    s.t(x, y + 30, "Kullanıcı adı ve parolayla giriş yap", 15, 600)
    s.t(x + w - 8, y + 30, "⌃", 15, 600, FG, "end")
    y += 62
    field(s, x, y + 14, w, "Kullanıcı adı veya e-posta", "ay", h, "focus")
    # passkey autofill dropdown (browser UI, drawn as a sketch)
    dy = y + 14 + h + 6
    s.r(x, dy, w, 92, "#FFFFFF", 10, "#CBD5E1")
    s.t(x + 12, dy + 20, "Tarayıcının öneri listesi (bizim çizimimiz değil)", 10, 500, "#7C3AED")
    key_glyph(s, x + 14, dy + 34, PRI)
    s.t(x + 44, dy + 46, "ayse.yilmaz · geçiş anahtarı", 14, 600)
    s.t(x + 44, dy + 64, "iCloud Anahtar Zinciri", 12, 400, MUTED)
    s.t(x + 44, dy + 84, "Başka bir cihazdaki geçiş anahtarını kullan", 12, 500, PRI)
    y = dy + 120
    field(s, x, y, w, "Parola", "", h, right="👁", link="Parolamı unuttum")
    y += h + 18
    s.btn(x, y, w, h, "Giriş yap", "sec")
    y += h + 22
    s.line(x, y, x + w / 2 - 24, y).line(x + w / 2 + 24, y, x + w, y)
    s.t(x + w / 2, y + 4, "veya", 12, 500, MUTED, "middle")
    y += 18
    s.r(x, y, w, h, "#FFFFFF", h / 2, "#94A3B8")
    key_glyph(s, x + w / 2 - 110, y + h / 2 - 8)
    s.t(x + w / 2 + 12, y + h / 2 + 5, "Geçiş anahtarıyla giriş yap", 15, 600, FG, "middle")
    y += h + 22
    s.t(x, y, "Son girişinizi geçiş anahtarıyla yaptınız.", 12, 400, SOFT)
    return y


def signin_1440():
    s = S(1440, 900, "Giriş sayfası, geçiş anahtarı otomatik doldurma, 1440")
    x, w = sheet_desktop(s, "")
    y = signin_body(s, x, w, 40, False)
    footer(s, x, 868, w)
    hero(s, 640, 330, 640, 380)
    s.t(660, 740, "Güz 2026–27 · 3. hafta", 15, 600)
    s.t(660, 760, "15 Ekim 2026, Perşembe", 13, 400, MUTED)
    for i, n in enumerate([
        "Kahraman: hero-solver Lottie, ≥ 1024 px, boşta kalınca 300 ms sonra bir kez oynar (0→140, 4,7 s), poster karede durur.",
        "Azaltılmış hareket / Save-Data: yalnızca poster PNG. aria-hidden, pointer-events none, cam yok (glass-tint çerçeve).",
        "Kapı 2: kimlik alanı autocomplete='username webauthn' → koşullu get() kapı açılınca başlar.",
        "Geçiş anahtarı düğmesi sağlayıcı değildir: yalnız yerel hesaplar içindir, bu yüzden kapı 2'nin içinde.",
        "Microsoft/Google: eşit ağırlık, marka kuralları değişmedi (integrations.md §6)."]):
        s.note(560, 60 + i * 20, n)
    s.save(f"{OUT}/auth-signin-1440.svg")


def signin_390():
    s = S(390, 1080, "Giriş sayfası, geçiş anahtarı, 390")
    s.t(20, 30, "9:41", 14, 600)
    x, w = 16, 358
    y = signin_body(s, x, w, 56, True)
    footer(s, x, y + 50, w)
    for i, n in enumerate(["Sayfa = sayfa (inset 0). Kahraman yok (< 1024 px).",
                           "Alanlar 48 px, 16 px yazı; odaklanan alan klavyenin üstünde ortalanır.",
                           "Düğmeler tam genişlik, sabitlenmez; gönder parolanın hemen altında."]):
        s.note(x, y + 100 + i * 18, n)
    s.save(f"{OUT}/auth-signin-390.svg")


# --- 2. 2FA step --------------------------------------------------------------------------------------------------
def mfa_body(s, x, w, y, coarse, error=False):
    s.t(x, y, "İki aşamalı doğrulama", 28, 700)
    s.t(x, y + 30, "ay•••@ornek.edu.tr olarak giriş yapılıyor", 14, 400, MUTED)
    s.t(x + 300 if not coarse else x, y + 30 if not coarse else y + 50, ("· " if not coarse else "") + "Farklı bir hesap", 14, 600, PRI)
    y += 64 if not coarse else 82
    s.t(x, y, "Doğrulama uygulamanızdaki 6 haneli kodu girin.", 15, 400)
    y += 34
    s.t(x, y, "Doğrulama kodu", 14, 600)
    y += 12
    if error:
        slots(s, x, y, "", coarse, "error", active=0)
        s.t(x, y + (56 if coarse else 52) + 22, "⚠ Kod doğru değil. Uygulamadaki güncel kodu girin.", 13, 600, BAD)
        s.t(x, y + (56 if coarse else 52) + 42, "Kodlar telefonunuzun saatine bağlıdır. Saatin otomatik", 12, 400, MUTED)
        s.t(x, y + (56 if coarse else 52) + 58, "ayarlı olduğundan emin olun.", 12, 400, MUTED)
        y += (56 if coarse else 52) + 82
    else:
        slots(s, x, y, "4821", coarse, active=4)
        y += (56 if coarse else 52) + 28
    checkbox(s, x, y, "Bu cihazı 30 gün hatırla", False, "Yalnızca kendi cihazınızda işaretleyin. Parolanız yine sorulur.")
    y += 60
    h = 48 if coarse else 44
    s.btn(x, y, w, h, "Doğrula")
    y += h + 30
    s.t(x, y, "Başka bir yöntem  ⌃", 15, 600, PRI)
    return y


def other_panel(s, x, w, y):
    s.r(x, y, w, 150, "#FFFFFF", 12, LINE)
    key_glyph(s, x + 16, y + 18, PRI)
    s.t(x + 48, y + 31, "Geçiş anahtarı kullan", 15, 600)
    s.line(x + 16, y + 50, x + w - 16, y + 50)
    s.t(x + 16, y + 81, "#", 16, 700, PRI)
    s.t(x + 48, y + 81, "Kurtarma kodu kullan", 15, 600)
    s.line(x + 16, y + 100, x + w - 16, y + 100)
    s.t(x + 16, y + 131, "?", 16, 700, PRI)
    s.t(x + 48, y + 131, "Hiçbirine erişemiyor musunuz?", 15, 600)


def mfa_1440():
    s = S(1440, 900, "İki aşamalı doğrulama adımı, 1440")
    x, w = sheet_desktop(s, "")
    brand(s, x, 40, w)
    y = mfa_body(s, x, w, 150, False)
    other_panel(s, x, w, y + 18)
    footer(s, x, 868, w)
    # error inset
    s.r(560, 120, 440, 470, "#FFFFFF", 18, LINE)
    s.t(580, 148, "Durum: hatalı kod (slotlar temizlenir, odak alanda kalır)", 12, 600, "#7C3AED")
    mfa_body(s, 580, 400, 190, False, error=True)
    # recovery variant inset
    s.r(1030, 120, 380, 300, "#FFFFFF", 18, LINE)
    s.t(1050, 148, "Değişken: kurtarma kodu", 12, 600, "#7C3AED")
    field(s, 1050, 196, 340, "Kurtarma kodu", "7K3M-Q9PX-", 44, "focus", mono=True,
          hint="Kaydettiğiniz kodlardan birini girin. Her kod bir kez kullanılır.")
    s.btn(1050, 290, 340, 44, "Doğrula")
    s.t(1050, 370, "Doğrulama uygulamasını kullan", 14, 600, PRI)
    for i, n in enumerate([
        "Tek gerçek <input> 6 slot olarak çizilir (input-otp, MIT): bir ad, bir sekme durağı, one-time-code, yapıştırma.",
        "6. hanede otomatik gönderir; 'Doğrula' düğmesi kalır. Hatalı kod: sarsıntı 280 ms (azaltılmış: yok).",
        "Parola → bu adım: sayfa yan yana 220 ms, bulanıklık 0 (azaltılmış: 100 ms opaklık).",
        "'Başka bir yöntem' paneli: Panel reveal 240/160 ms, yerinde açılır.",
        "Hatırla: varsayılan kapalı; politika kapatırsa gizli. Yalnız ikinci adımı atlar."]):
        s.note(560, 640 + i * 20, n)
    s.save(f"{OUT}/auth-2fa-1440.svg")


def keypad(s, y):
    s.r(0, y, 390, 291, "#D1D5DB", 0)
    keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"]
    for i, k in enumerate(keys):
        cx, cy = 6 + (i % 3) * 128, y + 8 + (i // 3) * 54
        if k:
            s.r(cx, cy, 122, 46, "#FFFFFF" if k != "⌫" else "#D1D5DB", 6)
            s.t(cx + 61, cy + 30, k, 22, 400, FG, "middle")
    s.r(0, y - 40, 390, 40, "#E5E7EB", 0).t(195, y - 15, "Mesajlar'dan: 482 913", 14, 600, PRI, "middle")


def mfa_390():
    s = S(780, 844, "İki aşamalı doğrulama adımı, 390 (sol: uygulama kodu ve klavye; sağ: kurtarma kodu)")
    # left phone
    s.r(0, 0, 390, 844, "#FFFFFF", 0)
    s.t(20, 30, "9:41", 14, 600)
    brand(s, 16, 48, 358)
    mfa_body(s, 16, 358, 132, True)
    keypad(s, 553)
    # right phone
    s.r(390, 0, 390, 844, "#F8FAFC", 0, LINE)
    s.t(410, 30, "9:41", 14, 600)
    s.t(406, 92, "İki aşamalı doğrulama", 26, 700)
    s.t(406, 120, "ay•••@ornek.edu.tr olarak giriş yapılıyor", 14, 400, MUTED)
    field(s, 406, 170, 358, "Kurtarma kodu", "7K3M-Q9PX-2DTA-8WRB", 48, "default", mono=True,
          hint="Kaydettiğiniz kodlardan birini girin. Her kod bir kez kullanılır.")
    s.btn(406, 272, 358, 48, "Doğrula")
    s.t(406, 350, "Doğrulama uygulamasını kullan", 15, 600, PRI)
    s.r(406, 390, 358, 120, "#FFFFFF", 12, LINE)
    s.t(422, 418, "Hiçbirine erişemiyor musunuz?", 14, 700)
    for i, l in enumerate(["Kurum yöneticinizden iki aşamalı doğrulamanızı", "sıfırlamasını isteyin. Kimliğiniz doğrulandıktan",
                           "sonra parolanızla girip yeniden kurabilirsiniz.", "İletişim: bilgi-islem@ornek.edu.tr"]):
        s.t(422, 442 + i * 18, l, 12, 400 if i < 3 else 600, MUTED if i < 3 else PRI)
    for i, n in enumerate(["Klavye açıkken slotlar ve 'Doğrula' görünür kalır (844 px).",
                           "iOS kodu klavyenin üstünde önerir (one-time-code).",
                           "Kurtarma alanı: büyük harf, otomatik düzeltme kapalı,", "boşluk/tire yok sayılır; otomatik gönderim yok."]):
        s.note(406, 560 + i * 18, n)
    s.save(f"{OUT}/auth-2fa-390.svg")


# --- 3. Profil › Giriş ve güvenlik -----------------------------------------------------------------------------
def sec_rows(s, x, w, y, phone=False):
    s.t(x, y, "Giriş ve güvenlik", 22, 700)
    y += 18
    rows = [
        ("Parola", "Son değişiklik: 2 Eylül 2026", "Değiştir", "sec"),
        ("İki aşamalı doğrulama", "Kapalı · Girişte parolanıza ek olarak telefonunuzdaki bir kod sorulur.", "Aç", "pri"),
        ("Geçiş anahtarları (passkey)", None, "Geçiş anahtarı ekle", "sec"),
        ("Oturumlar ve cihazlar", None, "Diğer tüm oturumları kapat", "sec"),
        ("Son girişler", "Son girişleri göster  ⌄", None, None),
    ]
    rh = {0: 64, 1: 72, 2: 170, 3: 150, 4: 56}
    if phone:
        rh = {0: 108, 1: 132, 2: 230, 3: 214, 4: 56}
    s.r(x, y, w, sum(rh.values()), "#FFFFFF", 16, LINE)
    yy = y
    for i, (title, status, action, kind) in enumerate(rows):
        s.t(x + 16, yy + 26, title, 15, 700)
        if status:
            s.t(x + 16, yy + 46, status if not phone or len(status) < 46 else status[:44] + "…", 13, 400 if i != 4 else 600,
                MUTED if i != 4 else PRI)
        if action:
            bw = max(90, int(len(action) * 8.2) + 30)
            if phone:
                s.btn(x + 16, yy + rh[i] - 58, w - 32, 44, action, kind, 14)
            else:
                s.btn(x + w - 16 - bw, yy + 14, bw, 36, action, kind, 13)
        if i == 2:
            ly = yy + 58
            for n, (prov, meta, tag) in enumerate([("iCloud Anahtar Zinciri", "Eklendi 18 Eki 2026 · Son kullanım 2 saat önce", None),
                                                   ("Güvenlik anahtarı", "Eklendi 1 Eki 2026 · Hiç kullanılmadı", "Yalnızca bu cihazda")]):
                s.r(x + 16, ly, 24, 24, LOCKBG, 6)
                key_glyph(s, x + 18, ly + 4, LOCK)
                s.t(x + 52, ly + 12, prov, 14, 600)
                s.t(x + 52, ly + 30, meta if not phone else meta[:34] + "…", 12, 400, MUTED)
                if tag and not phone:
                    s.badge(x + 52 + 150, ly - 2, tag, MUTED, "#F1F5F9")
                s.t(x + w - 30, ly + 18, "⋯", 18, 700, FG, "middle")
                ly += 50
        if i == 3:
            ly = yy + 58
            for dev, meta, tag in [("Chrome · Windows", "Son etkinlik şimdi · Parola + uygulama kodu", "Bu cihaz"),
                                   ("Safari · iPhone", "Son etkinlik 3 saat önce · Geçiş anahtarı", "2FA hatırlanıyor" if phone else "2FA 17 Kas'a kadar hatırlanıyor")]:
                s.r(x + 16, ly, 24, 18, "none", 3, FG, 1.5)
                s.t(x + 52, ly + 12, dev, 14, 600)
                s.badge(x + 52 + 130, ly - 2, tag, PRI if tag == "Bu cihaz" else MUTED, TINT if tag == "Bu cihaz" else "#F1F5F9")
                s.t(x + 52, ly + 30, meta if not phone else meta[:32] + "…", 12, 400, MUTED)
                if tag != "Bu cihaz" and not phone:
                    s.t(x + w - 24, ly + 18, "Oturumu kapat", 13, 600, BAD, "end")
                ly += 46
        yy += rh[i]
        if i < 4:
            s.line(x + 16, yy, x + w - 16, yy)
    return yy


def security_1440():
    s = S(1440, 900, "Profil › Giriş ve güvenlik ve 2FA kurulum sayfası, 1440")
    s.desk_shell("Profil", 4, ACCT_NAV)
    sec_rows(s, 276, 640, 100)
    # setup sheet
    s.r(0, 0, 1440, 900, SCRIM, 0, op=.28)
    sx = 948
    s.r(sx, 8, 484, 884, "#FFFFFF", 22, LINE)
    s.t(sx + 24, 52, "İki aşamalı doğrulamayı açın", 20, 700)
    s.t(sx + 24, 76, "Adım 1–2 / 3", 13, 600, MUTED)
    s.t(sx + 460, 52, "✕", 18, 600, FG, "end")
    s.t(sx + 24, 116, "1 · Uygulamayı bağlayın", 15, 700)
    for i, l in enumerate(["Telefonunuzdaki doğrulama uygulamasını açın", "(Microsoft Authenticator, Google Authenticator,",
                           "1Password ya da benzeri) ve bu kodu tarayın."]):
        s.t(sx + 24, 140 + i * 18, l, 13, 400, MUTED)
    s.r(sx + 24, 204, 176, 176, "#FFFFFF", 4, FG, 2)
    for r in range(11):
        for c in range(11):
            if (r * 5 + c * 3 + r * c) % 3 == 0:
                s.r(sx + 34 + c * 14.2, 214 + r * 14.2, 12, 12, FG, 1)
    s.t(sx + 220, 224, "SmartSched (Örnek Üniv.)", 13, 600)
    s.t(sx + 220, 242, "ayse.yilmaz", 13, 400, MUTED)
    s.t(sx + 220, 280, "QR kodunu tarayamıyor", 13, 600, PRI)
    s.t(sx + 220, 298, "musunuz?  ⌃", 13, 600, PRI)
    s.r(sx + 220, 312, 240, 80, FIELD, 10, EDGE)
    s.t(sx + 232, 334, "JBSW Y3DP EHPK 3PXP", 13, 600)
    s.t(sx + 232, 352, "KR4S M5QG YZTN 7WAE", 13, 600)
    s.t(sx + 232, 378, "Kopyala", 13, 600, PRI)
    s.line(sx + 24, 404, sx + 460, 404)
    s.t(sx + 24, 436, "2 · Kodu girin", 15, 700)
    s.t(sx + 24, 458, "Uygulamanın gösterdiği 6 haneli kodu girin.", 13, 400, MUTED)
    slots(s, sx + 24, 476, "482913", False, "ok")
    s.t(sx + 24, 552, "✓ Doğrulandı", 13, 700, OK)
    s.line(sx + 24, 584, sx + 460, 584)
    s.t(sx + 24, 616, "3 · Kurtarma kodlarınızı kaydedin", 15, 700, MUTED)
    s.t(sx + 24, 638, "(doğrulamadan sonra açılır; sayfa yan yana 220 ms)", 12, 500, "#7C3AED")
    for i, n in enumerate([
        "Sayfa açılmadan önce: 'Kimliğinizi doğrulayın' (10 dk geçerli).",
        "≥ 1024: adım 1 ve 2 tek görünümde (QR + anahtar yan yana, kod altta);",
        "kod doğrulanınca 2FA açılır, ✓ Success check 240 ms; sonra adım 3.",
        "QR her temada siyah-beyaz, 4 modül sessiz alan.",
        "Sol: tek birincil eylem 'Aç' (bölümdeki tek tint düğme)."]):
        s.note(sx + 24, 690 + i * 20, n)
    s.save(f"{OUT}/auth-security-1440.svg")


def security_390():
    s = S(780, 1180, "Profil › Giriş ve güvenlik (sol) ve kurtarma kodları adımı (sağ), 390")
    s.r(0, 0, 390, 1180, BG, 0)
    s.t(20, 30, "9:41", 14, 600)
    s.t(16, 80, "Profil", 30, 700)
    sec_rows(s, 16, 358, 120, phone=True)
    s.r(390, 0, 390, 1180, "#FFFFFF", 0, LINE)
    x = 406
    s.t(410, 30, "9:41", 14, 600)
    s.t(x, 80, "İki aşamalı doğrulamayı açın", 18, 700)
    s.t(x, 102, "Adım 3 / 3", 13, 600, MUTED)
    s.t(x, 142, "Kurtarma kodlarınızı kaydedin", 20, 700)
    for i, l in enumerate(["Telefonunuza erişemezseniz bu kodlarla giriş", "yaparsınız. Her kod bir kez kullanılır.",
                           "Bu kodlar bir daha gösterilmez."]):
        s.t(x, 168 + i * 18, l, 13, 400 if i < 2 else 700, MUTED if i < 2 else FG)
    s.r(x, 226, 358, 228, FIELD, 12, LINE)
    codes = ["7K3M-Q9PX-2DTA-8WRB", "H4ZN-6CEV-P1KQ-3MTS", "R8WD-2YFJ-K5NA-9XQE", "C6TP-4HMB-Z7RW-1DKG",
             "N2QX-8VSE-J3FL-6PAT", "W9KC-5RDY-M2HV-7BNQ", "E1LS-3GTW-X8PD-4ZMC", "Y5FB-7NKQ-C2RJ-8VHT",
             "P3DM-9WXA-T6EK-2LGS", "K7RV-1ZPC-H4NQ-5WYD"]
    for i, c in enumerate(codes):
        s.t(x + 16, 254 + i * 20, f"{i + 1:>2}.  {c}", 13, 600, FG)
    s.btn(x, 470, 114, 44, "İndir (.txt)", "sec", 13)
    s.btn(x + 122, 470, 114, 44, "Kopyala", "sec", 13)
    s.btn(x + 244, 470, 114, 44, "Yazdır", "sec", 13)
    checkbox(s, x, 540, "Kodları güvenli bir yere kaydettim", True)
    s.btn(x, 590, 358, 48, "Bitir")
    for i, n in enumerate(["'Bitir' kutu işaretlenmeden pasif.", "Kodlar ≥ 64 bit (NIST), 4'lü gruplar; ekran",
                           "okuyucu 10 öğelik liste olarak duyurur.", "Tam ekran sayfa; adım başlığı yapışkan.",
                           "'Kopyala' → 'Kopyalandı ✓' (Text swap 150 ms)."]):
        s.note(x, 680 + i * 18, n)
    s.save(f"{OUT}/auth-security-390.svg")


# --- 4. Admin --------------------------------------------------------------------------------------------------
def admin_1440():
    s = S(1440, 1360, "Yönetim › Kullanıcılar: 2FA sıfırlama, bağlantı gönderme, giriş güvenliği politikası, 1440")
    s.desk_shell("Kullanıcılar", 5, ADMIN_NAV)
    tx = 276
    cols = [("Ad", 0), ("Rol", 220), ("Giriş yöntemi", 360), ("Durum", 560), ("", 700)]
    s.r(tx, 100, 1140, 420, "#FFFFFF", 14, LINE)
    for lab, dx in cols:
        s.t(tx + 16 + dx, 128, lab, 12, 700, SOFT)
    rows = [("A. Yılmaz", "Planlamacı", "Yerel · 2FA", "Etkin"), ("M. Demir", "Öğretim elemanı", "Microsoft", "Etkin"),
            ("S. Kaya", "Onaylayıcı", "Yerel · 2FA bekleniyor (1 Kas)", "Etkin"), ("E. Arslan", "Personel", "LDAP", "Etkin")]
    for i, r in enumerate(rows):
        y = 150 + i * 56
        s.line(tx + 16, y - 6, tx + 1124, y - 6)
        s.t(tx + 16, y + 22, r[0], 14, 600)
        s.t(tx + 236, y + 22, r[1], 14, 400)
        col = WARN if "bekleniyor" in r[2] else FG
        s.t(tx + 376, y + 22, r[2], 14, 500, col)
        s.c(tx + 584, y + 17, 4, OK).t(tx + 594, y + 22, r[3], 13, 500)
        s.t(tx + 1110, y + 22, "⋯", 18, 700, FG, "end")
    # menu for local row
    mx, my = tx + 820, 172
    s.r(mx, my, 300, 176, "#FFFFFF", 12, LINE)
    for i, l in enumerate(["Düzenle", "Erişimi denetle"]):
        s.t(mx + 16, my + 28 + i * 30, l, 14, 500)
    s.line(mx + 8, my + 80, mx + 292, my + 80)
    s.t(mx + 16, my + 104, "Parola sıfırlama bağlantısı gönder", 14, 600)
    s.t(mx + 16, my + 134, "2FA'yı sıfırla", 14, 600, BAD)
    s.t(mx + 16, my + 162, "Sıfırlama kodunu ekranda göster", 13, 500, MUTED)
    # SSO explanation menu
    mx2 = tx + 800
    s.r(mx2, 360, 320, 120, "#FFFFFF", 12, LINE)
    s.t(mx2 + 16, 386, "Düzenle", 14, 500)
    s.line(mx2 + 8, 402, mx2 + 312, 402)
    for i, l in enumerate(["Bu hesap Microsoft ile giriş yapıyor.", "Parola ve iki aşamalı doğrulama orada",
                           "yönetilir.  (metin, düğme değil)"]):
        s.t(mx2 + 16, 426 + i * 18, l, 13, 400, MUTED)
    s.note(tx + 16, 400, "Sağ alt: M. Demir (Microsoft) satırının menüsü. İki eylem yerine tek açıklama satırı; devre dışı düğme yok.")
    # reset dialog (aligned with AU-B §6)
    dx, dy = tx + 40, 550
    s.r(dx, dy, 560, 560, "#FFFFFF", 18, LINE)
    s.t(dx + 24, dy + 40, "A. Yılmaz için iki aşamalı doğrulama sıfırlansın mı?", 17, 700)
    for i, l in enumerate(["Doğrulama uygulaması, kurtarma kodları, geçiş anahtarları ve hatırlanan",
                           "cihazlar silinir; tüm oturumları kapatılır. A. Yılmaz bir sonraki girişinde",
                           "yalnızca parolasıyla girer ve iki aşamalı doğrulamayı hemen yeniden kurar."]):
        s.t(dx + 24, dy + 68 + i * 19, l, 13, 400, MUTED)
    cx = dx + 24
    for l, sel in [("Telefonunu kaybetti", True), ("Kodlarına erişemiyor", False), ("Ele geçirilmiş olabilir", False)]:
        cx += s.chip(cx, dy + 136, l, sel=sel, h=32, size=12) + 6
    field(s, dx + 24, dy + 202, 512, "Gerekçe (10–500 karakter)", "Telefonunu kaybetti ya da değiştirdi; yüz yüze geldi.", 44)
    field(s, dx + 24, dy + 290, 512, "Kimliği nasıl doğrulandı?", "Yüz yüze", 44, right="⌄")
    checkbox(s, dx + 24, dy + 360, "Geçiş anahtarlarını koru (2)", False)
    s.note(dx + 24, dy + 400, "'Hesap ele geçirilmiş olabilir' seçilince 'koru' kutusu gizlenir.")
    s.btn(dx + 300, dy + 440, 110, 44, "Vazgeç", "sec", 14)
    s.r(dx + 420, dy + 440, 116, 44, BAD, 22).t(dx + 478, dy + 467, "2FA'yı sıfırla", 14, 600, "#FFFFFF", "middle")
    s.note(dx + 24, dy + 512, "Denetim auth.mfa_reset_by_admin · kişiye mfa_reset_by_admin (gerekçe metni yok)")
    s.note(dx + 24, dy + 532, "Kendi hesabında yok (409 own_account) · SSO hesabında yok (409 sso_account)")
    # policy tab
    px, py = tx + 640, 550
    s.r(px, py, 500, 600, "#FFFFFF", 18, LINE)
    s.t(px + 24, py + 36, "Ayarlar › Giriş güvenliği", 17, 700)
    s.t(px + 24, py + 72, "İki aşamalı doğrulama", 14, 700)
    sx = px + 24
    for i, l in enumerate(["Kapalı", "İsteğe bağlı", "Zorunlu"]):
        w = s.chip(sx, py + 86, l, sel=(i == 2), w=140)
        sx += w + 6
    for i, l in enumerate(["Zorunlu: seçtiğiniz rollerdeki yerel hesaplar", "kurmadan giriş yapamaz."]):
        s.t(px + 24, py + 144 + i * 17, l, 12, 400, MUTED)
    s.t(px + 24, py + 194, "Hangi roller için?", 13, 700)
    cx = px + 24
    for l, sel in [("Yönetici", True), ("Planlamacı", True), ("Onaylayıcı", False), ("Öğretim elemanı", False)]:
        cx += s.chip(cx, py + 206, l, sel=sel, h=32, size=12) + 6
    s.t(px + 24, py + 274, "Kurulum için süre", 13, 700)
    cx = px + 24
    for l, sel in [("7 gün", False), ("14 gün", True), ("30 gün", False)]:
        cx += s.chip(cx, py + 286, l, sel=sel, h=32, size=12) + 6
    s.r(px + 24, py + 334, 452, 44, TINT, 10)
    s.t(px + 36, py + 361, "Bu ayarla 12 kişi 1 Kasım'a kadar kurmalı; 3 kişi zaten kurdu.", 12, 600, PRI)
    s.t(px + 24, py + 410, "Geçiş anahtarları", 14, 700)
    s.r(px + 420, py + 396, 52, 30, OK, 15).c(px + 457, py + 411, 11, "#FFFFFF")
    s.t(px + 24, py + 430, "Parmak izi, yüz ya da cihaz PIN'iyle ikinci adım.", 12, 400, MUTED)
    checkbox(s, px + 24, py + 444, "Parolasız girişe de izin ver", True)
    s.t(px + 24, py + 496, "Gelişmiş  ⌄", 14, 600, PRI)
    for i, l in enumerate(["Kurum hesabıyla (Microsoft, Google…) giriş yapanlar bu kurallardan", "etkilenmez; onları kurumunuzun kimlik sağlayıcısı korur."]):
        s.t(px + 24, py + 522 + i * 17, l, 12, 400, MUTED)
    s.btn(px + 356, py + 548, 120, 40, "Kaydet", "pri", 14)
    s.note(px, py + 626, "Segmented: glass-morph (pattern 2). Gelişmiş: Bu cihazı hatırla 0/7/30 gün.")
    s.save(f"{OUT}/auth-admin-1440.svg")


def admin_390():
    s = S(1170, 844, "Yönetim › Kullanıcılar ve politika, 390 (düzenleme sayfası, bağlantı gönderme, politika)")
    # 1 edit sheet block
    s.r(0, 0, 390, 844, BG, 0)
    s.t(20, 30, "9:41", 14, 600)
    s.r(0, 90, 390, 754, "#FFFFFF", 22, LINE)
    s.r(171, 100, 48, 5, "#CBD5E1", 3)
    s.t(16, 140, "A. Yılmaz", 22, 700)
    s.t(16, 186, "Giriş ve güvenlik", 15, 700)
    for i, (k, v) in enumerate([("Yöntem", "Yerel (kullanıcı adı ve parola)"), ("2FA", "Açık · uygulama + 2 geçiş anahtarı"),
                                ("Son giriş", "3 saat önce")]):
        s.t(16, 216 + i * 26, k, 13, 600, MUTED).t(120, 216 + i * 26, v, 13, 500)
    s.btn(16, 300, 358, 48, "Parola sıfırlama bağlantısı gönder", "sec", 14)
    s.r(16, 360, 358, 48, "#FFFFFF", 24, BAD).t(195, 389, "2FA'yı sıfırla", 14, 600, BAD, "middle")
    s.t(16, 440, "Sıfırlama kodunu ekranda göster", 14, 600, PRI)
    s.r(16, 480, 358, 92, FIELD, 12)
    for i, l in enumerate(["Microsoft hesabında bu blok:", "\"Bu hesap Microsoft ile giriş yapıyor. Parola ve",
                           "iki aşamalı doğrulama orada yönetilir.\""]):
        s.t(28, 504 + i * 20, l, 12, 500 if i else 700, "#7C3AED" if i == 0 else MUTED)
    # 2 send link sheet
    s.r(390, 0, 390, 844, BG, 0, LINE)
    s.r(390, 0, 390, 844, SCRIM, 0, op=.3)
    s.r(390, 440, 390, 404, "#FFFFFF", 22)
    s.r(561, 450, 48, 5, "#CBD5E1", 3)
    s.t(406, 492, "A. Yılmaz adına parola sıfırlama", 18, 700)
    s.t(406, 514, "bağlantısı gönderilsin mi?", 18, 700)
    for i, l in enumerate(["a•••@ornek.edu.tr adresine 24 saat geçerli bir", "bağlantı gönderilir. Mevcut parolası, bağlantı",
                           "kullanılana kadar çalışır. İki aşamalı", "doğrulaması değişmez."]):
        s.t(406, 546 + i * 19, l, 13, 400, MUTED)
    s.btn(406, 640, 358, 48, "Bağlantıyı gönder")
    s.btn(406, 698, 358, 48, "Vazgeç", "sec")
    s.note(406, 776, "Alt sayfa (pattern 4, springs.sheet). Yönetici bağlantıyı görmez.")
    # 3 policy
    s.r(780, 0, 390, 844, BG, 0, LINE)
    s.t(800, 30, "9:41", 14, 600)
    s.t(796, 84, "Giriş güvenliği", 26, 700)
    s.r(796, 108, 358, 44, "#E2E8F0", 22)
    for i, l in enumerate(["Kapalı", "İsteğe bağlı", "Zorunlu"]):
        if i == 2:
            s.r(796 + 2 + i * 119, 110, 117, 40, "#FFFFFF", 20)
        s.t(796 + 60 + i * 119, 135, l, 13, 600 if i == 2 else 500, FG, "middle")
    s.t(796, 184, "Hangi roller için?", 13, 700)
    cx, cy = 796, 196
    for l, sel in [("Yönetici", True), ("Planlamacı", True), ("Onaylayıcı", False), ("Öğretim elemanı", False), ("Tüm roller", False)]:
        w = max(44, int(len(l) * 12 * 0.58) + 28)
        if cx + w > 1154:
            cx, cy = 796, cy + 44
        s.chip(cx, cy, l, sel=sel, h=36, size=12)
        cx += w + 6
    s.t(796, 316, "Kurulum için süre", 13, 700)
    cx = 796
    for l, sel in [("7 gün", False), ("14 gün", True), ("30 gün", False)]:
        cx += s.chip(cx, 328, l, sel=sel, h=44, size=13) + 6
    s.r(796, 392, 358, 60, TINT, 10)
    s.t(808, 416, "Bu ayarla 12 kişi 1 Kasım'a kadar kurmalı;", 12, 600, PRI)
    s.t(808, 436, "3 kişi zaten kurdu.", 12, 600, PRI)
    s.t(796, 488, "Geçiş anahtarları", 14, 700)
    s.r(1102, 470, 52, 30, OK, 15).c(1139, 485, 11, "#FFFFFF")
    checkbox(s, 796, 514, "Parolasız girişe de izin ver", True)
    s.t(796, 574, "Gelişmiş  ⌄", 14, 600, PRI)
    s.r(780, 700, 390, 60, "#FFFFFF", 0, LINE)
    s.btn(796, 708, 358, 44, "Kaydet")
    s.note(796, 790, "Kaydet çubuğu sekme çubuğunun üstünde yapışkan (M-05).")
    s.save(f"{OUT}/auth-admin-390.svg")


# --- 5. Input system -----------------------------------------------------------------------------------------
def inputs():
    s = S(1440, 860, "Girdi kutusu sistemi: durumlar, OTP slotları, otomatik doldurma, klavyeler")
    s.t(40, 56, "Girdi kutusu sistemi (auth.md §10)", 26, 700)
    states = [("Varsayılan", "default", "", None), ("Odak", "focus", "ayse.yil", None),
              ("Otomatik dolduruldu", "auto", "ayse.yilmaz", "%7 tint, sarı/mavi yok"),
              ("Hata", "error", "ayse", "⚠ Kullanıcı adı, e-posta veya parola yanlış."),
              ("Başarılı (yalnız doğrulama)", "ok", "7K3M-Q9PX-2DTA-8WRB", "✓ Doğrulandı"),
              ("Salt okunur", "ro", "ayse.yilmaz", None)]
    for i, (lab, st, val, msg) in enumerate(states):
        x, y = 40 + (i % 3) * 460, 120 + (i // 3) * 150
        s.t(x, y - 34, lab, 12, 700, "#7C3AED")
        field(s, x, y, 400, "Kullanıcı adı veya e-posta" if st not in ("ok",) else "Kurtarma kodu", val, 44, st,
              msg=msg if st in ("error", "ok") else None, hint=msg if st == "auto" else None, mono=(st == "ok"))
    y = 440
    s.t(40, y, "OTP slotları (tek gerçek input; 3 + 3)", 14, 700)
    labels = [("Boş, odakta", "", "default", 0), ("Yazılıyor", "482", "default", 3), ("Hata", "", "error", 0), ("Doğrulandı", "482913", "ok", None)]
    for i, (lab, d, st, act) in enumerate(labels):
        x = 40 + i * 340
        s.t(x, y + 30, lab, 12, 600, "#7C3AED")
        slots(s, x, y + 44, d, False, st, act)
    s.note(40, y + 124, "İnce imleç 44×52, kaba 48×56; aralık 8, orta 16; 24/600 tablo rakamları; imleç 1 s adım (azaltılmış: sabit).")
    y = 600
    s.t(40, y, "Klavye ve otomatik doldurma öznitelikleri", 14, 700)
    rows = [("Alan", "type", "inputmode", "autocomplete", "enterkeyhint"),
            ("Kimlik", "text", "email", "username webauthn", "next"),
            ("Parola", "password", "—", "current-password", "go"),
            ("Yeni parola", "password", "—", "new-password", "go"),
            ("Doğrulama kodu", "text", "numeric", "one-time-code", "done"),
            ("Kurtarma kodu", "text", "text", "off", "go")]
    for i, r in enumerate(rows):
        for j, c in enumerate(r):
            s.t(40 + j * 230, y + 30 + i * 26, c, 13, 700 if i == 0 else 400, SOFT if i == 0 else FG)
    s.note(40, y + 200, "Telefonda her alan ≥ 16 px (iOS yakınlaştırmaz); giriş alanları kaba imleçte 48 px.")
    s.save(f"{OUT}/auth-inputs.svg")


signin_1440(); signin_390(); mfa_1440(); mfa_390(); security_1440(); security_390(); admin_1440(); admin_390(); inputs()
