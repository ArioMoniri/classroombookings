"""Wireframe for docs/design/v3/messages.md (W3-DES2): bell, toasts, banner, empty state. python3 -I ms.py .."""
import sys
sys.path.insert(0, ".")
from wf import *  # noqa: F401,F403

OUT = sys.argv[1] if len(sys.argv) > 1 else ".."
s = S(1440, 900, "Uygulama içi iletiler: zil, bildirim (toast), uyarı bandı, boş durum")
# desktop bell panel
s.t(40, 50, "Masaüstü · zil paneli", 18, 700)
s.r(40, 70, 420, 560, CARD, 16, LINE)
s.t(60, 104, "Bildirimler", 17, 700).t(440, 104, "Tümünü okundu say", 13, 600, PRI, "end")
x = 60
for i, l in enumerate(["Tümü", "Okunmamış 2", "Onaylar"]):
    x += s.chip(x, 120, l, sel=i == 0, h=32, size=12) + 8
items = [(OK, "Oda talebiniz onaylandı: B-204 · 21 Eki · 3. ders", "Mehmet Kaya onayladı.", "5 dk önce", True),
         (BAD, "Oda talebiniz reddedildi: C-105 · 22 Eki · 5. ders", "Gerekçe: Kapasite yetersiz. Aynı saatte boş 2 derslik var.", "1 sa önce", True),
         (WARN, "Onay bekleyen oda talebi: B-204 · 23 Eki · 2. ders", "Ayşe Yılmaz onay istiyor · 8 hafta · çakışma yok", "dün", False),
         (MUTED, "Oda talebi geri çekildi: A-12 · 24 Eki · 1. ders", "Can Demir geri çekti; bir şey yapmanız gerekmez.", "2 gün önce", False)]
y = 168
for col, title, body, when, unread in items:
    s.c(76, y + 18, 9, col)
    s.t(96, y + 22, title[:52], 13, 700 if unread else 500, FG)
    s.t(96, y + 42, body[:58], 12, 400, MUTED)
    s.t(96, y + 60, when, 11, 400, SOFT)
    if unread:
        s.c(444, y + 18, 5, PRI)
    s.line(60, y + 76, 440, y + 76)
    y += 88
s.t(60, 610, "Bildirim tercihleri", 13, 600, PRI)
s.note(40, 650, "Başlık = e-posta konusu; gövde = ön başlık. Okunmamış: kalın başlık + mavi nokta.")
s.note(40, 668, "Rozet: sayı artınca bir kez 'pop' (bouncySubtle); sayfa açılışında ve azalınca yok.")
# bell badge
s.r(392, 20, 44, 36, CARD, 18, LINE).t(414, 43, "Zil", 12, 600, FG, "middle")
s.r(424, 14, 22, 18, BAD, 9).t(435, 27, "2", 11, 700, "#FFFFFF", "middle")
# toasts
s.t(520, 50, "Bildirim (toast) yığını", 18, 700)
s.r(536, 92, 380, 52, "#1E293B", 14, op=.55)
s.r(528, 100, 396, 56, "#1E293B", 14, op=.75)
s.r(520, 112, 412, 60, "#0F172A", 14)
s.t(540, 147, "B-204 rezerve edildi", 14, 600, "#FFFFFF").t(912, 147, "Geri al", 14, 700, "#93C5FD", "end")
s.note(520, 196, "En fazla 3; eskiler geride (ölçek .05, opaklık .85/.7); üzerine gelince açılır.")
s.note(520, 214, "Giriş 240 ms y16→0 (bulanıklık yok: cam), çıkış 160 ms; 8 sn (eylemli), üzerindeyken durur.")
# banner
s.t(520, 270, "Uyarı bandı (koşul sürüyor)", 18, 700)
s.r(520, 290, 860, 56, BADBG, 12).t(540, 324, "E-posta gönderilemiyor: 535 kimlik doğrulama. 12 bildirim bekliyor.", 14, 600, BAD)
s.t(1360, 324, "Sorunu gider", 14, 700, PRI, "end")
s.r(520, 356, 860, 56, WARNBG, 12).t(540, 390, "Microsoft 365 gizli anahtarının süresi 2 Kasım 2026 tarihinde doluyor.", 14, 600, WARN)
s.t(1360, 390, "Anahtarı değiştir", 14, 700, PRI, "end")
s.note(520, 432, "Akışta tam genişlik bloklar (üst üste binmez); en yeni üstte, en fazla 3 + '+n uyarı'.")
# empty state
s.t(520, 490, "Boş durum", 18, 700)
s.r(520, 510, 420, 200, CARD, 16, LINE)
s.t(540, 560, "Henüz bildirim yok.", 16, 700)
s.t(540, 586, "Talepleriniz ve rezervasyonlarınızla ilgili", 14, 400, MUTED)
s.t(540, 606, "gelişmeler burada görünür.", 14, 400, MUTED)
s.btn(540, 630, 190, 40, "Bildirim tercihleri", "sec", 14)
# phone
s.t(1000, 490, "Telefon · toast", 18, 700)
s.r(1000, 510, 390, 360, "#F4F6F9", 24, LINE)
s.r(1016, 720, 358, 52, "#0F172A", 14).t(1034, 752, "Talebiniz gönderildi: B-204", 14, 600, "#FFFFFF").t(1358, 752, "Görüntüle", 14, 700, "#93C5FD", "end")
s.r(1000, 790, 390, 80, "#FFFFFF", 0).line(1000, 790, 1390, 790)
for i, lab in enumerate(["Panel", "Takvim", "Rezerve et", "Talepler", "Daha"]):
    s.t(1000 + 390 / 5 * (i + .5), 840, lab, 10, 500, SOFT, "middle")
s.note(1000, 704, "Sekme çubuğunun ve güvenli alanın 8 px üstünde; en fazla 2.")
s.save(f"{OUT}/messages-surfaces.svg")
print("ok 1")
