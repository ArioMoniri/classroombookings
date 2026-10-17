"""E-mail mock-ups for docs/design/v3/emails.md (lane W3-DES2).

Usage (from this folder): python3 -I em.py ..   -> writes email-<id>-{desktop,phone}.svg into the wireframes folder.
Each file shows the same message twice, light and dark, side by side. Colours are the e-mail tokens of emails.md §3
(not the slate wireframe palette of wf.py); the copy is the Turkish copy of emails.md §8. Purple = annotation.
"""
import sys
sys.path.insert(0, ".")
from wf import S, FONT

LIGHT = dict(canvas="#EEF0F4", card="#FFFFFF", t1="#1D1D1F", t2="#4B4B51", t3="#5F5F66", line="#D9DCE3",
             btn="#0A63D1", btnfg="#FFFFFF", link="#0957BB", detail="#F5F7FA", code="#F1F3F6",
             ok=("#0F6430", "#E6F5EA"), bad=("#A3211A", "#FCEBEA"), warn=("#7C4800", "#FFF2D9"),
             info=("#0957BB", "#E8F1FC"), inbox="#FFFFFF", name="Açık tema")
DARK = dict(canvas="#0D0E12", card="#1B1C21", t1="#F5F5F7", t2="#B6B6BD", t3="#A9A9B1", line="#33343B",
            btn="#4DA0FF", btnfg="#06101F", link="#6CB0FF", detail="#24252B", code="#24252B",
            ok=("#63E08B", "#11291A"), bad=("#FF9D95", "#351614"), warn=("#FFCC66", "#33270C"),
            info=("#6CB0FF", "#122238"), inbox="#16171B", name="Koyu tema (prefers-color-scheme: dark)")
TILE = "../../../images/brand/smartsched-tile-small.svg"
ORG = "Örnek Üniversitesi"


def wrap(text, width, size, factor=0.5):
    """Greedy word wrap with an average glyph width (system UI fonts, Turkish text)."""
    per = max(8, int(width / (size * factor)))
    out, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + (1 if cur else 0) > per:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


class Mail:
    """Draws one e-mail into an S canvas at (x0, y0) with content width w (600 desktop, 390 phone)."""

    def __init__(s, svg, P, x0, y0, w, phone):
        s.s, s.P, s.x0, s.y, s.w, s.phone = svg, P, x0, y0, w, phone
        s.pad = 20 if phone else 40
        s.inner = w - 2 * s.pad

    def text(s, txt, size=16, weight=400, color="t1", lh=None, indent=0, width=None):
        lh = lh or round(size * 1.5)
        for ln in wrap(txt, (width or s.inner) - indent, size):
            s.y += lh
            s.s.t(s.x0 + s.pad + indent, s.y - (lh - size) / 2 - 2, ln, size, weight, s.P[color])
        return s

    def gap(s, h):
        s.y += h
        return s

    def header(s):
        s.s.o.append(f"<image href='{TILE}' x='{s.x0 + s.pad}' y='{s.y + 20}' width='28' height='28'/>")
        s.s.t(s.x0 + s.pad + 38, s.y + 40, "SmartSched", 16, 600, s.P["t1"])
        s.s.t(s.x0 + s.w - s.pad, s.y + 40, ORG, 13, 500, s.P["t3"], "end")
        s.y += 68
        s.s.line(s.x0, s.y, s.x0 + s.w, s.y, s.P["line"])
        return s

    def status(s, word, tone):
        fg, bg = s.P[tone]
        wpx = int(len(word) * 13 * 0.6) + 24
        s.y += 24
        s.s.r(s.x0 + s.pad, s.y, wpx, 26, bg, 13)
        s.s.t(s.x0 + s.pad + wpx / 2, s.y + 17.5, word, 13, 600, fg, "middle")
        s.y += 26
        return s

    def title(s, txt):
        s.gap(18)
        return s.text(txt, 22 if s.phone else 24, 600, "t1", 30 if s.phone else 32)

    def details(s, rows, tone=None, heading=None):
        """Details card: label above value on phones, two columns on desktop. A 4 px left bar carries the tone."""
        s.y += 20
        top = s.y
        start = len(s.s.o)
        x, w = s.x0 + s.pad, s.inner
        s.y += 14
        if heading:
            s.text(heading, 13, 600, "t3", 18, indent=16)
            s.y += 4
        for label, value in rows:
            if s.phone:
                s.text(label, 13, 500, "t3", 18, indent=16, width=w - 16)
                s.text(value, 16, 600, "t1", 22, indent=16, width=w - 16)
                s.y += 6
            else:
                y0 = s.y
                s.text(label, 14, 500, "t3", 24, indent=16, width=170)
                s.y = y0
                s.text(value, 16, 600, "t1", 24, indent=170, width=w - 16)
                s.y += 4
        s.y += 10
        rects = f"<rect x='{x}' y='{top}' width='{w}' height='{s.y - top}' rx='12' fill='{s.P['detail']}' stroke='{s.P['line']}'/>"
        if tone:
            rects += f"<rect x='{x}' y='{top}' width='4' height='{s.y - top}' rx='2' fill='{s.P[tone][0]}'/>"
        s.s.o.insert(start, rects)
        return s

    def mark(s):
        s._mark = len(s.s.o)
        return s

    def callout(s, label, body, tone):
        fg, bg = s.P[tone]
        s.y += 18
        top = s.y
        s.mark()
        s.y += 10
        s.text(label, 14, 600, "t1", 20, indent=16)
        s.text(body, 15, 400, "t1", 22, indent=16)
        s.y += 12
        s.s.o.insert(s._mark, f"<rect x='{s.x0 + s.pad}' y='{top}' width='{s.inner}' height='{s.y - top}' rx='12' fill='{bg}'/>"
                     f"<rect x='{s.x0 + s.pad}' y='{top}' width='4' height='{s.y - top}' rx='2' fill='{fg}'/>")
        return s

    def code(s, label, code):
        s.y += 20
        s.text(label, 13, 600, "t3", 18)
        s.y += 6
        s.s.r(s.x0 + s.pad, s.y, s.inner, 56, s.P["code"], 12, s.P["line"])
        s.s.o.append(f"<text x='{s.x0 + s.w / 2}' y='{s.y + 37}' font-size='26' font-weight='600' "
                     f"font-family='ui-monospace,SFMono-Regular,Menlo,Consolas,monospace' letter-spacing='3' "
                     f"fill='{s.P['t1']}' text-anchor='middle'>{code}</text>")
        s.y += 56
        return s

    def button(s, label):
        s.y += 24
        bw = s.inner if s.phone else max(220, int(len(label) * 16 * 0.6) + 64)
        s.s.r(s.x0 + s.pad, s.y, bw, 48, s.P["btn"], 12)
        s.s.t(s.x0 + s.pad + bw / 2, s.y + 30, label, 16, 600, s.P["btnfg"], "middle")
        s.y += 48
        return s

    def link(s, txt):
        s.y += 8
        return s.text(txt, 15, 600, "link", 24)

    def suggestions(s, heading, items):
        s.y += 18
        s.text(heading, 15, 600, "t1", 22)
        for room, meta, cta in items:
            s.y += 8
            top = s.y
            s.s.r(s.x0 + s.pad, top, s.inner, 64 if not s.phone else 76, s.P["card"], 12, s.P["line"])
            s.s.t(s.x0 + s.pad + 16, top + 26, room, 16, 600, s.P["t1"])
            s.s.t(s.x0 + s.pad + 16, top + 48, meta, 14, 400, s.P["t2"])
            if s.phone:
                s.s.t(s.x0 + s.pad + 16, top + 68, cta, 14, 600, s.P["link"])
                s.y += 76
            else:
                s.s.t(s.x0 + s.w - s.pad - 16, top + 38, cta, 15, 600, s.P["link"], "end")
                s.y += 64
        return s

    def footer(s, why):
        s.y += 32
        s.s.line(s.x0 + s.pad, s.y, s.x0 + s.w - s.pad, s.y, s.P["line"])
        s.y += 8
        s.text(f"{ORG} · SmartSched", 13, 600, "t2", 20)
        s.text(why, 13, 400, "t3", 20)
        s.y += 4
        s.text("Bildirim tercihleri · KVKK Aydınlatma Metni", 13, 600, "link", 20)
        s.y += 28
        return s


def inbox_row(svg, P, x, y, w, sender, subject, pre):
    svg.r(x, y, w, 76, P["inbox"], 12, P["line"])
    svg.c(x + 28, y + 38, 16, P["btn"])
    svg.t(x + 28, y + 43, sender[:1], 14, 700, P["btnfg"], "middle")
    svg.t(x + 54, y + 26, sender, 14, 700, P["t1"])
    svg.t(x + w - 14, y + 26, "20:14", 12, 500, P["t3"], "end")
    svg.t(x + 54, y + 46, subject[: int((w - 70) / 7.6)], 14, 600, P["t1"])
    svg.t(x + 54, y + 64, (pre[: int((w - 70) / 7.0) - 1] + "…") if len(pre) > (w - 70) / 7.0 else pre, 13, 400, P["t2"])
    return y + 76


def render(msg, phone, out):
    W = 390 if phone else 680
    width = W * 2 + (40 if phone else 60) + 40
    svg = S(width, 2400, f"E-posta: {msg['name']} ({'telefon 390' if phone else 'masaüstü 600'}, açık ve koyu)", "#FFFFFF")
    ends = []
    for i, P in enumerate((LIGHT, DARK)):
        x = 20 + i * (W + (40 if phone else 60))
        svg.note(x, 28, f"{P['name']} · {'390 px telefon' if phone else '600 px gövde'}", 12)
        svg.r(x, 40, W, 2340, P["canvas"], 16)
        y = inbox_row(svg, P, x + 12, 52, W - 24, msg["sender"], msg["subject"], msg["preheader"]) + 8
        svg.note(x + 12, y + 8, "gelen kutusu: gönderen · konu · ön başlık (preheader)", 11)
        y += 24
        cx = x if phone else x + 40
        cw = W if phone else 600
        m = Mail(svg, P, cx, y, cw, phone)
        card_idx = len(svg.o)
        m.header()
        msg["draw"](m)
        m.footer(msg["why"])
        svg.o.insert(card_idx, f"<rect x='{cx}' y='{y}' width='{cw}' height='{m.y - y}' rx='{0 if phone else 16}' fill='{P['card']}'/>")
        ends.append(m.y)
    h = int(max(ends) + 40)
    svg.h = h
    svg.o[0] = f"<rect width='{width}' height='{h}' fill='#FFFFFF'/>"
    svg.o = [o.replace("height='2340'", f"height='{h - 60}'") for o in svg.o]
    svg.save(out)


def d_reset(m):
    m.title("Parolanızı sıfırlayın")
    m.gap(4).text("Merhaba Ayşe Yılmaz,", 16, 400, "t1", 24)
    m.text("Örnek Üniversitesi SmartSched hesabınız (ayse.yilmaz) için parola sıfırlama istendi.", 16, 400, "t1", 24)
    m.code("Sıfırlama kodu", "K7Q4-M2X9")
    m.button("Parolayı sıfırla")
    m.gap(10).text("Kod 24 saat geçerlidir ve bir kez kullanılabilir. Düğme açılmazsa giriş sayfasında Parolamı unuttum adımına bu kodu yazın.", 14, 400, "t2", 21)
    m.callout("Bu isteği siz yapmadınız mı?", "Bir şey yapmanız gerekmez; parolanız değişmez. İstek: 17 Ekim 2026 20:14 · Chrome, Windows.", "info")


def d_invite(m):
    m.title("SmartSched'e davet edildiniz")
    m.gap(4).text("Mehmet Kaya, sizi Örnek Üniversitesi ders programı ve derslik rezervasyonu sistemine davet etti.", 16, 400, "t1", 24)
    m.details([("Rol", "Öğretim elemanı"), ("Davet edilen adres", "a•••@ornek.edu.tr"),
                      ("Giriş yöntemi", "Microsoft (iş veya okul hesabı)"), ("Son geçerlilik", "16 Kasım 2026")])
    m.button("Daveti kabul et")
    m.gap(10).text("Açılan sayfada Microsoft ile giriş yap düğmesine basın ve bu adresle giriş yapın. Hesabınız ilk girişte bağlanır.", 14, 400, "t2", 21)
    m.gap(6).text("Bu daveti beklemiyorsanız e-postayı yok sayabilirsiniz; siz giriş yapmadan hesap etkinleşmez.", 14, 400, "t2", 21)


def d_approved(m):
    m.status("Onaylandı", "ok")
    m.title("Oda talebiniz onaylandı")
    m.gap(4).text("Mehmet Kaya talebinizi onayladı. Derslik bu saatlerde sizin adınıza ayrıldı.", 16, 400, "t1", 24)
    m.details([("Derslik", "B-204 · 40 kişi"), ("Tarih", "21 Ekim 2026 Çarşamba"),
                      ("Ders saati", "3. ders · 10:30–11:20"), ("Talep no", "#128")], tone="ok")
    m.button("Rezervasyonu görüntüle")
    m.link("Takvime ekle (.ics)")


def d_rejected(m):
    m.status("Reddedildi", "bad")
    m.title("Oda talebiniz reddedildi")
    m.gap(4).text("Mehmet Kaya talebinizi reddetti. Gerekçe ve aynı saatte boş olan derslikler aşağıda.", 16, 400, "t1", 24)
    m.callout("Gerekçe: Kapasite yetersiz", "Derse 52 öğrenci kayıtlı; B-204 40 kişilik.", "bad")
    m.details([("Derslik", "B-204 · 40 kişi"), ("Tarih", "21 Ekim 2026 Çarşamba"),
                      ("Ders saati", "3. ders · 10:30–11:20"), ("Talep no", "#128")])
    m.suggestions("Aynı saatte boş derslikler", [("B-301", "60 kişi · Projeksiyon · aynı kat", "Bu dersliği iste"),
                                                  ("C-105", "56 kişi · Projeksiyon", "Bu dersliği iste")])
    m.button("Başka bir derslik bul")


def d_approver(m):
    m.status("Onay bekliyor", "warn")
    m.title("Onayınızı bekleyen bir talep var")
    m.gap(4).text("Ayşe Yılmaz aşağıdaki derslik için onay istiyor.", 16, 400, "t1", 24)
    m.details([("Talep eden", "Ayşe Yılmaz · Bilgisayar Mühendisliği"), ("Derslik", "B-204 · 40 kişi"),
                      ("Tarih", "21 Ekim 2026 Çarşamba"), ("Ders saati", "3. ders · 10:30–11:20"),
                      ("Tekrar", "Her çarşamba · 8 hafta (seri #44)"), ("Not", "Proje sunumları"),
                      ("Çakışma", "Yok")], tone="warn")
    m.button("Talebi incele")
    m.link("Onay kuyruğu: 3 talep bekliyor")
    m.gap(8).text("Karar uygulamada verilir; bu e-postadaki bağlantılar tek başına onaylamaz veya reddetmez.", 14, 400, "t2", 21)


MESSAGES = {
    "reset": dict(name="parola sıfırlama", sender="Örnek Üniversitesi SmartSched", subject="Parola sıfırlama kodunuz",
                  preheader="Kod 24 saat geçerli. Bu isteği siz yapmadıysanız bu e-postayı yok sayın.",
                  why="Bu bir güvenlik e-postasıdır; bildirim tercihlerinden kapatılamaz.", draw=d_reset),
    "invite": dict(name="davet (Microsoft)", sender="Örnek Üniversitesi SmartSched",
                   subject="Mehmet Kaya sizi SmartSched'e davet etti",
                   preheader="Microsoft iş veya okul hesabınızla katılın. Davet 16 Kasım 2026'ya kadar geçerli.",
                   why="Bu e-postayı, bir yönetici bu adresi davet ettiği için aldınız.", draw=d_invite),
    "approved": dict(name="talep onaylandı", sender="Örnek Üniversitesi SmartSched",
                     subject="Oda talebiniz onaylandı: B-204 · 21 Eki · 3. ders",
                     preheader="B-204, 21 Ekim 10:30–11:20 sizin. Takviminize ekleyebilirsiniz.",
                     why="Bu e-postayı, Talebim onaylandı bildirimi açık olduğu için aldınız.", draw=d_approved),
    "rejected": dict(name="talep reddedildi", sender="Örnek Üniversitesi SmartSched",
                     subject="Oda talebiniz reddedildi: B-204 · 21 Eki · 3. ders",
                     preheader="Gerekçe: Kapasite yetersiz. Aynı saatte boş 2 derslik var.",
                     why="Bu e-postayı, Talebim reddedildi bildirimi açık olduğu için aldınız.", draw=d_rejected),
    "approver-request": dict(name="onaycıya yeni talep", sender="Örnek Üniversitesi SmartSched",
                             subject="Onay bekleyen oda talebi: B-204 · 21 Eki · 3. ders",
                             preheader="Ayşe Yılmaz B-204 için onay istiyor · 8 hafta · çakışma yok.",
                             why="Bu e-postayı, B-204 için onaycı olduğunuz için aldınız.", draw=d_approver),
}

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else ".."
    for key, msg in MESSAGES.items():
        for phone in (False, True):
            render(msg, phone, f"{out}/email-{key}-{'phone' if phone else 'desktop'}.svg")
    print("ok", len(MESSAGES) * 2)
