"""Wireframes for docs/design/v3/integrations.md (lane W3-DES2). Usage (from this folder): python3 -I ig.py .."""
import sys
sys.path.insert(0, ".")
from wf import *  # noqa: F401,F403

OUT = sys.argv[1] if len(sys.argv) > 1 else ".."
NAV = ["Panel", "Takvim", "Rezerve et", "§YÖNETİM", "Kullanıcılar", "Entegrasyonlar", "Yapay zekâ", "Operasyon", "Ayarlar"]
GREY = "#94A3B8"

STATUS = {"ok": ("Bağlı", OK, OKBG), "off": ("Yapılandırılmadı", MUTED, "#F1F5F9"), "bad": ("Hata", BAD, BADBG),
          "dis": ("Kapalı", MUTED, "#F1F5F9"), "warn": ("Dikkat", WARN, WARNBG)}


def status(s, x, y, kind):
    word, fg, bg = STATUS[kind]
    s.c(x + 5, y - 4, 5, fg if kind != "off" else "none", fg if kind == "off" else None)
    s.t(x + 16, y, word, 13, 600, fg)


def toggle(s, x, y, on=True):
    s.r(x, y, 44, 26, PRI if on else "#CBD5E1", 13)
    s.c(x + (31 if on else 13), y + 13, 10, "#FFFFFF")


def monogram(s, x, y, txt, size=40):
    s.r(x, y, size, size, "#F1F5F9", 10, LINE)
    s.t(x + size / 2, y + size / 2 + 5, txt, 13 if len(txt) < 3 else 11, 700, FG, "middle")


def card(s, x, y, w, h, mono, name, summary, st, check, changed, action, on=None):
    s.r(x, y, w, h, CARD, 14, BAD if st == "bad" else LINE, 2 if st == "bad" else 1)
    monogram(s, x + 16, y + 16, mono)
    s.t(x + 66, y + 32, name, 15, 600)
    s.t(x + 66, y + 50, summary, 12, 400, MUTED)
    status(s, x + 16, y + 86, st)
    s.t(x + 16, y + 108, check, 12, 400, SOFT)
    s.t(x + 16, y + 126, changed, 12, 400, SOFT)
    s.line(x, y + h - 52, x + w, y + h - 52)
    s.btn(x + 16, y + h - 42, 96 if action == "Yönet" else 120, 32, action, "sec" if action == "Yönet" else "pri", 13)
    if on is not None:
        toggle(s, x + w - 60, y + h - 39, on)


def gallery_1440():
    s = S(1440, 1000, "Entegrasyonlar galerisi, 1440")
    s.desk_shell("Entegrasyonlar", 5, NAV)
    s.t(276, 84, "Kurum genelindeki bağlantılar. Her yönetici aynı ayarları görür; değişiklikler denetim kaydına yazılır.", 14, 400, MUTED)
    s.r(276, 104, 360, 40, CARD, 20, GREY).t(300, 129, "Entegrasyon ara", 14, 400, SOFT)
    x = 652
    for i, lab in enumerate(["Tümü", "Kimlik 4", "E-posta 1", "Takvim 2", "Kanallar 5", "Webhook ve otomasyon 2", "Yapay zekâ 3"]):
        x += s.chip(x, 106, lab, sel=i == 0) + 8
    s.t(276, 176, "6 bağlı · 1 hata · 9 yapılandırılmadı", 13, 600, FG)
    # attention row
    s.r(276, 192, 1140, 52, BADBG, 12).t(296, 224, "Dikkat isteyen: E-posta (SMTP) · 535 kimlik doğrulama başarısız · 12 bildirim bekliyor", 14, 600, BAD)
    s.btn(1250, 202, 150, 32, "Sorunu gider", "pri", 13)
    s.t(276, 280, "Kimlik", 18, 700).t(352, 280, "giriş ve davet yöntemleri", 13, 400, MUTED)
    W, H, G = 272, 196, 18
    cards = [("MS", "Microsoft 365", "Entra ID · tek kiracı", "ok", "Son kontrol: 4 dk önce · başarılı", "Son değişiklik: Mehmet Kaya, 17 Eki 19:40", "Yönet", True),
             ("G", "Google Workspace", "uni.edu.tr alanı", "off", "Henüz kurulmadı", "—", "Kur", None),
             ("OIDC", "Okta", "OpenID Connect · ön ayar", "dis", "Son kontrol: dün · başarılı", "Son değişiklik: Ayşe Yılmaz, 12 Eki", "Yönet", False),
             ("SAML", "Kurum girişi (SAML)", "Shibboleth · YETKİM", "off", "Henüz kurulmadı", "—", "Kur", None)]
    for i, c in enumerate(cards):
        card(s, 276 + i * (W + G), 300, W, H, *c)
    s.t(276, 540, "E-posta", 18, 700).t(362, 540, "bildirimlerin gönderildiği sunucu", 13, 400, MUTED)
    card(s, 276, 560, W, H, "SMTP", "E-posta (SMTP)", "Microsoft 365 ön ayarı", "bad", "Son kontrol: 2 dk önce · 535 5.7.3", "Son değişiklik: Mehmet Kaya, 17 Eki", "Yönet", True)
    s.t(276 + W + G, 540, "Takvim", 18, 700)
    card(s, 276 + W + G, 560, W, H, "ICS", "Takvim akışları", "Kişisel abonelik adresleri", "ok", "KVKK onayı: 2 Eki", "Son değişiklik: Mehmet Kaya", "Yönet", True)
    card(s, 276 + 2 * (W + G), 560, W, H, "MS", "Microsoft 365 takvim", "Rezervasyon aktarımı", "off", "Henüz kurulmadı", "—", "Kur", None)
    card(s, 276 + 3 * (W + G), 560, W, H, "AI", "Anthropic", "Yapay zekâ sağlayıcısı", "ok", "Son kontrol: 1 sa önce", "Yapay zekâ ekranında yönetilir ↗", "Yönet", True)
    s.note(276, 800, "Kart: monogram (logo yok) · ad · tek satır özet · durum noktası + kelime · son kontrol · Son değişiklik: <ad>, <zaman> · Kur/Yönet + açma anahtarı.")
    s.note(276, 820, "Hata kartı 2 px kırmızı kenar + kelime; 'Dikkat isteyen' satırı en üstte. Başka ekranın kartları (Yapay zekâ, Kanallar) oraya bağlanır (↗).")
    s.note(276, 840, "Alan sekmeleri sayılarla; arama ad ve sağlayıcı adlarında çalışır. Sıra sabittir: durum değişince kartlar yer değiştirmez.")
    s.save(f"{OUT}/integrations-gallery-1440.svg")


def gallery_390():
    s = S(390, 844, "Entegrasyonlar galerisi, 390")
    s.phone_shell("Entegrasyonlar", 4)
    s.r(16, 112, 358, 44, CARD, 22, GREY).t(40, 140, "Entegrasyon ara", 15, 400, SOFT)
    x = 16
    for i, lab in enumerate(["Tümü", "Kimlik", "E-posta", "Takvim"]):
        x += s.chip(x, 168, lab, sel=i == 0, h=36) + 8
    s.r(16, 216, 358, 64, BADBG, 12).t(32, 242, "E-posta (SMTP): Hata", 14, 700, BAD).t(32, 264, "535 kimlik doğrulama · Sorunu gider ›", 13, 500, BAD)
    s.t(16, 312, "Kimlik", 17, 700)
    rows = [("MS", "Microsoft 365", "ok"), ("G", "Google Workspace", "off"), ("OIDC", "Okta", "dis"), ("SAML", "Kurum girişi (SAML)", "off")]
    y = 324
    for mono, name, st in rows:
        s.r(16, y, 358, 64, CARD, 12, LINE)
        monogram(s, 28, y + 12, mono)
        s.t(80, y + 28, name, 15, 600)
        status(s, 80, y + 50, st)
        s.t(354, y + 38, "›", 22, 400, SOFT, "end")
        y += 72
    s.t(16, y + 24, "E-posta", 17, 700)
    s.r(16, y + 36, 358, 64, CARD, 12, BAD, 2)
    monogram(s, 28, y + 48, "SMTP")
    s.t(80, y + 64, "E-posta (SMTP)", 15, 600)
    status(s, 80, y + 86, "bad")
    s.note(16, 744, "Telefonda kart = 64 px satır; açma anahtarı kurulum sayfasında.")
    s.save(f"{OUT}/integrations-gallery-390.svg")


def copyfield(s, x, y, w, label, value):
    s.t(x, y, label, 13, 600, MUTED)
    s.r(x, y + 8, w, 44, "#F8FAFC", 10, LINE)
    s.t(x + 12, y + 35, value, 13, 500, FG)
    s.btn(x + w - 104, y + 14, 96, 32, "Kopyala", "sec", 13)


def stepper(s, x, y, steps, cur, vertical=True):
    for i, lab in enumerate(steps):
        yy = y + i * 34
        done = i < cur
        s.c(x + 11, yy + 11, 11, OK if done else (PRI if i == cur else CARD), None if (done or i == cur) else GREY)
        s.t(x + 11, yy + 16, "✓" if done else str(i + 1), 12, 700, "#FFFFFF" if (done or i == cur) else MUTED, "middle")
        s.t(x + 30, yy + 16, lab, 14, 600 if i == cur else 400, FG if i <= cur else MUTED)


STEPS = ["Ön ayar", "Sağlayıcıda kaydet", "Değerleri yapıştır", "Bağlantıyı dene", "Etkinleştir"]


def setup_1440():
    s = S(1440, 1000, "Kurulum sayfası (Microsoft 365), 1440")
    s.desk_shell("Entegrasyonlar", 5, NAV)
    s.r(244, 0, 1196, 1000, "#0F172A", 0, op=.28)
    X = 820
    s.r(X, 12, 608, 976, CARD, 18, LINE)
    monogram(s, X + 24, 32, "MS", 44)
    s.t(X + 80, 52, "Microsoft 365 ile giriş", 20, 700).t(X + 80, 72, "Son değişiklik: Mehmet Kaya, 17 Eki 19:40 · Taslak paylaşılır", 12, 400, SOFT)
    s.btn(X + 556, 36, 36, 36, "✕", "sec", 14)
    stepper(s, X + 24, 104, STEPS, 1)
    Y = 290
    s.line(X, Y - 14, X + 608, Y - 14)
    s.t(X + 24, Y + 8, "2. Microsoft Entra'da uygulamayı kaydedin", 17, 700)
    lines = ["1  Entra yönetim merkezi › Uygulama kayıtları › Yeni kayıt: 'Yalnızca bu kuruluş dizini'.",
             "2  Yeniden yönlendirme URI'si (Web) olarak aşağıdaki adresi yapıştırın.",
             "3  Sertifikalar ve gizli diziler › Yeni istemci gizli anahtarı; değeri hemen kopyalayın."]
    for i, l in enumerate(lines):
        s.t(X + 24, Y + 40 + i * 24, l, 13, 400, FG)
    s.t(X + 24, Y + 122, "Entra yönetim merkezini aç ↗", 13, 600, PRI)
    copyfield(s, X + 24, Y + 156, 560, "Yeniden yönlendirme URI'si (Web)", "https://plan.uni.edu.tr/api/v1/auth/sso/entra/callback")
    copyfield(s, X + 24, Y + 230, 560, "Ön kanal oturum kapatma URL'si", "https://plan.uni.edu.tr/api/v1/auth/sso/entra/logout")
    copyfield(s, X + 24, Y + 304, 560, "API izinleri (Microsoft Graph, temsilci)", "openid · profile · email · User.Read")
    s.r(X + 24 + 456, Y + 170, 96, 32, OKBG, 16, OK).t(X + 24 + 504, Y + 191, "✓ Kopyalandı", 12, 600, OK, "middle")
    s.note(X + 24, Y + 380, "'Kopyala' → aynı yerde '✓ Kopyalandı' (1,5 sn), aria-live: 'Yönlendirme adresi kopyalandı'.")
    s.r(X + 24, Y + 396, 560, 72, TINT, 12).t(X + 40, Y + 422, "Değerler kurumunuzun genel adresinden üretilir:", 13, 600, PRI)
    s.t(X + 40, Y + 446, "https://plan.uni.edu.tr · Ayarlar › Genel'de değiştirilir", 13, 400, PRI)
    s.line(X, 900, X + 608, 900)
    s.btn(X + 24, 920, 100, 44, "Geri", "sec", 15).btn(X + 444, 920, 140, 44, "İleri", "pri", 15)
    s.t(X + 140, 948, "Taslak kaydedildi · 19:42", 12, 400, SOFT)
    # second panel: test results (inset illustration)
    s.r(276, 120, 520, 400, CARD, 16, LINE)
    s.t(296, 152, "4. Bağlantıyı dene (aynı sayfa, sonraki adım)", 15, 700)
    checks = [("ok", "Keşif belgesi alındı (login.microsoftonline.com)"), ("ok", "Kiracı kimliği doğru: Örnek Üniversitesi"),
              ("ok", "İstemci kimliği ve gizli anahtar kabul edildi"), ("bad", "Deneme girişi: AADSTS50011"),
              ]
    for i, (k, t) in enumerate(checks):
        yy = 186 + i * 34
        s.c(306, yy - 4, 8, OK if k == "ok" else BAD)
        s.t(306, yy, "✓" if k == "ok" else "✕", 10, 700, "#FFFFFF", "middle")
        s.t(322, yy, t, 13, 500 if k == "ok" else 600, FG if k == "ok" else BAD)
    s.r(296, 330, 480, 112, BADBG, 12)
    s.t(312, 356, "Yönlendirme adresi Entra'daki kayıtla eşleşmiyor.", 14, 700, BAD)
    s.t(312, 380, "2. adımdaki adresi Yeniden yönlendirme URI'si (Web)", 13, 400, FG)
    s.t(312, 400, "olarak ekleyin, sonra yeniden deneyin.", 13, 400, FG)
    s.t(312, 426, "2. adıma dön · Ayrıntı: AADSTS50011", 13, 600, PRI)
    s.btn(296, 456, 170, 40, "Yeniden dene", "pri", 14).btn(478, 456, 220, 40, "Kendi hesabımla dene", "sec", 14)
    s.note(276, 540, "Sonuçlar tek tek gelir (sunucu adımları); her satır kelime + simge; hata = neden + düzeltme + hangi adım.")
    s.note(276, 560, "'Kendi hesabımla dene' açılır pencerede gerçek giriş yapar; başarı = 5. adım açılır.")
    s.save(f"{OUT}/integrations-setup-1440.svg")


def setup_390():
    s = S(390, 844, "Kurulum sayfası, 390")
    s.t(20, 30, "9:41", 14, 600)
    s.btn(16, 48, 44, 44, "‹", "sec", 20)
    s.t(72, 76, "Microsoft 365 ile giriş", 18, 700)
    s.t(16, 120, "Adım 2 / 5 · Sağlayıcıda kaydet", 13, 600, PRI)
    s.r(16, 130, 358, 6, "#E2E8F0", 3).r(16, 130, 143, 6, PRI, 3)
    s.t(16, 172, "Microsoft Entra'da uygulamayı kaydedin", 17, 700)
    for i, l in enumerate(["1  Uygulama kayıtları › Yeni kayıt", "2  Yönlendirme URI'si (Web): aşağıdaki adres", "3  Yeni istemci gizli anahtarı"]):
        s.t(16, 204 + i * 24, l, 14, 400)
    s.t(16, 290, "Yeniden yönlendirme URI'si (Web)", 13, 600, MUTED)
    s.r(16, 300, 358, 72, "#F8FAFC", 10, LINE)
    s.t(28, 324, "https://plan.uni.edu.tr/api/v1/", 13, 500).t(28, 344, "auth/sso/entra/callback", 13, 500)
    s.btn(16, 380, 358, 44, "Kopyala", "sec", 15)
    s.t(16, 456, "API izinleri", 13, 600, MUTED)
    s.r(16, 466, 358, 48, "#F8FAFC", 10, LINE).t(28, 495, "openid · profile · email · User.Read", 13, 500)
    s.btn(16, 522, 358, 44, "Kopyala", "sec", 15)
    s.t(16, 600, "Entra yönetim merkezini aç ↗", 15, 600, PRI)
    s.r(0, 740, 390, 104, CARD, 0).line(0, 740, 390, 740)
    s.btn(16, 756, 110, 48, "Geri", "sec", 16).btn(138, 756, 236, 48, "İleri", "pri", 16)
    s.note(16, 700, "Değer tam görünür (kırpılmaz); Kopyala 44 px tam genişlik.")
    s.save(f"{OUT}/integrations-setup-390.svg")


def ms_button(s, x, y, w, h=44, label="Microsoft ile giriş yap"):
    s.r(x, y, w, h, "#FFFFFF", 12, "#8C8C8C")
    bx = x + w / 2 - (len(label) * 15 * 0.55) / 2 - 16
    for dx, dy, col in ((0, 0, "#F25022"), (10, 0, "#7FBA00"), (0, 10, "#00A4EF"), (10, 10, "#FFB900")):
        s.r(bx + dx, y + h / 2 - 10 + dy, 9, 9, col, 0)
    s.t(bx + 30, y + h / 2 + 5, label, 15, 600, "#5E5E5E")


def g_button(s, x, y, w, h=44, label="Google ile oturum açın"):
    s.r(x, y, w, h, "#FFFFFF", 12, "#747775")
    bx = x + w / 2 - (len(label) * 14 * 0.55) / 2 - 16
    s.c(bx + 9, y + h / 2, 9, "none", "#4285F4")
    s.t(bx + 9, y + h / 2 + 4, "G", 11, 700, "#4285F4", "middle")
    s.t(bx + 30, y + h / 2 + 5, label, 14, 500, "#1F1F1F")


def gen_button(s, x, y, w, mono, label, h=44):
    s.r(x, y, w, h, CARD, 12, GREY)
    bx = x + w / 2 - (len(label) * 15 * 0.55) / 2 - 16
    s.r(bx, y + h / 2 - 10, 20, 20, "#F1F5F9", 5, LINE).t(bx + 10, y + h / 2 + 4, mono, 9, 700, FG, "middle")
    s.t(bx + 30, y + h / 2 + 5, label, 15, 600, FG)


def signin(phone):
    if phone:
        s = S(390, 844, "Giriş sayfası, birden çok sağlayıcı, 390")
        x, w, y = 16, 358, 70
        s.t(20, 30, "9:41", 14, 600)
    else:
        s = S(1440, 900, "Giriş sayfası, birden çok sağlayıcı, 1440")
        s.r(12, 12, 480, 876, "#FFFFFF", 22, LINE)
        x, w, y = 52, 400, 80
        s.r(504, 12, 924, 876, "#E8EEF6", 22)
        s.note(540, 60, "Sağ taraf: kurum sahnesi (değişmedi, sign-in.md §5.1)")
    s.r(x, y, 40, 40, PRI, 10).t(x + 20, y + 27, "S", 18, 700, "#FFFFFF", "middle")
    s.t(x + 52, y + 26, "SmartSched", 17, 700)
    s.r(x + w - 120, y + 4, 120, 32, "#F1F5F9", 8).t(x + w - 60, y + 25, "Üniversite logosu", 11, 500, MUTED, "middle")
    s.t(x, y + 92, "Giriş yap", 28, 700)
    s.t(x, y + 120, "Örnek Üniversitesi · ders programı ve rezervasyon", 14, 400, MUTED)
    by = y + 148
    s.r(x, by, 150, 24, TINT, 12).t(x + 75, by + 16, "Son girişiniz bu yöntemle", 11, 600, PRI, "middle")
    by += 32
    ms_button(s, x, by, w)
    g_button(s, x, by + 56, w)
    gen_button(s, x, by + 112, w, "OK", "Okta ile giriş yap")
    s.t(x, by + 188, "Diğer giriş yolları (1)  ▾", 14, 600, PRI)
    s.t(x, by + 222, "Kurum hesabınızla ilk girişte hesabınız standart kullanıcı", 13, 400, MUTED)
    s.t(x, by + 240, "olarak açılır. Rolünüzü yalnızca bir yönetici değiştirebilir.", 13, 400, MUTED)
    s.line(x, by + 268, x + w, by + 268)
    s.t(x, by + 300, "Kullanıcı adı ve parolayla giriş yap  ▸", 14, 600, FG)
    for i, n in enumerate(["Sağlayıcı düğmeleri aynı boy ve ağırlıkta", "(Google: eşit belirginlik). Sıra yöneticinin;",
                           "en fazla 3 görünür, fazlası 'Diğer giriş yolları'.", "Microsoft ve Google kendi marka kurallarıyla,",
                           "diğerleri nötr. Davet bağlantısında yalnız", "davetteki yöntem gösterilir."]):
        s.note(x, by + 340 + i * 18, n)
    s.save(f"{OUT}/signin-providers-{'390' if phone else '1440'}.svg")


PRESETS = [("M365", "Microsoft 365", "smtp.office365.com · 587"), ("G", "Google Workspace", "smtp-relay.gmail.com · 587"),
           ("Y", "Yandex 360", "smtp.yandex.com · 465"), ("KUR", "Kurum SMTP sunucusu", "kendi sunucunuz"),
           ("SES", "Amazon SES", "e-posta hizmeti · yurt dışı"), ("PM", "Postmark", "e-posta hizmeti · yurt dışı"),
           ("RS", "Resend", "e-posta hizmeti · yurt dışı"), ("BR", "Brevo", "e-posta hizmeti · yurt dışı"), ("…", "Özel", "elle girin")]


def smtp_1440():
    s = S(1440, 1000, "SMTP ön ayar sihirbazı, 1440")
    s.desk_shell("Entegrasyonlar", 5, NAV)
    s.r(244, 0, 1196, 1000, "#0F172A", 0, op=.28)
    X = 700
    s.r(X, 12, 728, 976, CARD, 18, LINE)
    monogram(s, X + 24, 32, "SMTP", 44)
    s.t(X + 80, 52, "E-posta (SMTP)", 20, 700).t(X + 80, 72, "Son değişiklik: —  · Yapılandırılmadı", 12, 400, SOFT)
    labels = ["Sağlayıcı", "Bağlantı", "Gönderen", "Alan adı", "Deneme", "Etkinleştir"]
    for i, l in enumerate(labels):
        xx = X + 24 + i * 112
        s.r(xx, 100, 104, 4, PRI if i <= 0 else "#E2E8F0", 2)
        s.t(xx, 124, f"{i + 1}. {l}", 12, 600 if i == 0 else 400, PRI if i == 0 else MUTED)
    s.t(X + 24, 164, "1. E-postayı hangi hizmet gönderecek?", 17, 700)
    for i, (m, n, d) in enumerate(PRESETS):
        cx, cy = X + 24 + (i % 3) * 228, 184 + (i // 3) * 92
        sel = i == 0
        s.r(cx, cy, 216, 80, TINT if sel else CARD, 12, PRI if sel else LINE, 2 if sel else 1)
        monogram(s, cx + 12, cy + 20, m)
        s.t(cx + 62, cy + 36, n, 14, 600)
        s.t(cx + 62, cy + 56, d, 12, 400, MUTED)
    s.r(X + 24, 470, 680, 116, WARNBG, 12)
    s.t(X + 40, 496, "Microsoft 365: kimlik doğrulama yöntemi", 14, 700, WARN)
    s.t(X + 40, 520, "Önerilen: OAuth 2.0 (Microsoft ile bağlan). Parola (temel kimlik doğrulama) Exchange Online'da", 13, 400, FG)
    s.t(X + 40, 540, "Aralık 2026'dan itibaren varsayılan olarak kapalıdır; yalnızca yöneticiniz açık tuttuysa çalışır.", 13, 400, FG)
    s.t(X + 40, 566, "Kaynak: Microsoft ileti merkezi MC786329 ↗", 13, 600, PRI)
    s.t(X + 24, 622, "Doğrulama", 14, 600, MUTED)
    s.chip(X + 24, 632, "OAuth 2.0 (önerilen)", sel=True)
    s.chip(X + 220, 632, "Kullanıcı adı ve parola")
    s.note(X + 24, 700, "Yurt dışı hizmet seçilince 3. adımda KVKK md. 9 onay kutusu çıkar (takvim eşitlemeyle aynı kalıp).")
    s.note(X + 24, 718, "Ön ayar host/port/güvenliği doldurur ve kilitler ('Değiştir' ile açılır).")
    s.line(X, 900, X + 728, 900)
    s.btn(X + 24, 920, 100, 44, "Vazgeç", "sec", 15).btn(X + 564, 920, 140, 44, "İleri", "pri", 15)
    # inset: test step
    s.r(276, 120, 400, 520, CARD, 16, LINE)
    s.t(296, 152, "5. Deneme (sonraki adımlardan)", 15, 700)
    rows = [("ok", "smtp.office365.com:587 bağlantı"), ("ok", "STARTTLS · TLS 1.3 · sertifika geçerli"),
            ("ok", "OAuth belirteci alındı (SMTP.Send)"), ("ok", "Gönderen izinli: plan@uni.edu.tr"),
            ("ok", "SPF: uni.edu.tr kaydı Microsoft'u içeriyor"), ("warn", "DMARC kaydı yok (önerilir)"),
            ("ok", "Deneme iletisi gönderildi → siz")]
    for i, (k, t) in enumerate(rows):
        yy = 190 + i * 32
        col = OK if k == "ok" else WARN
        s.c(306, yy - 4, 8, col)
        s.t(306, yy, "✓" if k == "ok" else "!", 10, 700, "#FFFFFF", "middle")
        s.t(322, yy, t, 13, 500, FG)
    s.t(296, 430, "Deneme iletisi gelen kutunuza ulaştı mı?", 14, 600)
    s.btn(296, 446, 110, 40, "Evet, geldi", "pri", 14).btn(416, 446, 220, 40, "Hayır / istenmeyende", "sec", 14)
    s.r(296, 502, 360, 112, "#F8FAFC", 12, LINE)
    s.t(312, 528, "6. Etkinleştir", 14, 700)
    s.t(312, 552, "Gönderilmeyi bekleyen 37 bildirim var.", 13, 400)
    s.chip(312, 566, "Yalnız yenileri", sel=True, h=32, size=12)
    s.chip(452, 566, "Bekleyenleri de gönder", h=32, size=12)
    s.save(f"{OUT}/smtp-wizard-1440.svg")


def smtp_390():
    s = S(390, 844, "SMTP ön ayar sihirbazı, 390")
    s.t(20, 30, "9:41", 14, 600)
    s.btn(16, 48, 44, 44, "‹", "sec", 20)
    s.t(72, 76, "E-posta (SMTP)", 18, 700)
    s.t(16, 120, "Adım 2 / 6 · Bağlantı", 13, 600, PRI)
    s.r(16, 130, 358, 6, "#E2E8F0", 3).r(16, 130, 120, 6, PRI, 3)
    s.r(16, 152, 358, 52, TINT, 12).t(32, 183, "Ön ayar: Google Workspace (SMTP relay)", 14, 600, PRI)
    for i, (lab, val, lock) in enumerate([("Sunucu", "smtp-relay.gmail.com", True), ("Bağlantı noktası", "587", True),
                                          ("Güvenlik", "STARTTLS", True), ("Kullanıcı adı", "plan@uni.edu.tr", False),
                                          ("Uygulama parolası", "••••••••••••••••", False)]):
        y = 230 + i * 84
        s.t(16, y, lab, 13, 600, MUTED)
        s.r(16, y + 8, 358, 48, "#F8FAFC" if lock else CARD, 10, LINE if lock else GREY)
        s.t(28, y + 38, val, 15, 500, MUTED if lock else FG)
        if lock:
            s.t(362, y + 38, "Değiştir", 13, 600, PRI, "end")
    s.t(16, 668, "Uygulama parolası, 2 adımlı doğrulama açık hesapta üretilir ↗", 12, 500, PRI)
    s.r(0, 740, 390, 104, CARD, 0).line(0, 740, 390, 740)
    s.btn(16, 756, 110, 48, "Geri", "sec", 16).btn(138, 756, 236, 48, "İleri", "pri", 16)
    s.save(f"{OUT}/smtp-wizard-390.svg")


gallery_1440(); gallery_390(); setup_1440(); setup_390(); signin(False); signin(True); smtp_1440(); smtp_390()
print("ok 8")
