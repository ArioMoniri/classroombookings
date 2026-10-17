import sys; sys.path.insert(0,".")
from wf import *
OUT=sys.argv[1]
ROOMS=[("A 101","Amfi","A Blok · 40 kişi","PC",None,True),("B 204","Derslik","B Blok · 36 kişi","Projeksiyon",None,False),
       ("C 112","Seminer","C Blok · 24 kişi","",("Talep",WARN,WARNBG),False),("A 205","Derslik","A Blok · 48 kişi","",None,False),
       ("D 010","Toplantı","D Blok · 12 kişi","",None,False),("B 107","Derslik","B Blok · 60 kişi","Projeksiyon",None,False)]
def phone_steps(s,sel_room=0,top=110):
    s.t(20,top+22,"1. Ne zaman?",13,600,SOFT)
    x=20
    for i,d in enumerate(["Bugün","Yarın","Pzt 20","Sal 21","Çar 22"]): x+=s.chip(x,top+32,d,sel=i==0,h=44)+8
    s.t(20,top+104,"Ders saati",11,500,SOFT); x=20
    for i,d in enumerate(["2. ders · 09:20","3. ders · 10:10","4. ders · 11:00"]):
        x+=s.chip(x,top+112,d if i else "2. ders · Dolu",sel=i==1,dis=i==0,h=44,size=12)+8
    s.note(20,top+172,"scrolls inside its own row → started slots hidden; ‘Dolu’ = no free room")
    y=top+196; s.t(20,y+16,"2. Nerede?",13,600,SOFT); s.t(20,y+40,"12 boş derslik",15,600)
    s.chip(262,y+20,"Filtreler · 1",h=36,w=108)
    y+=60
    for i,(code,name,meta,tag,b,recent) in enumerate(ROOMS[:5]):
        sel=i==sel_room
        s.r(20,y,350,60,TINT if sel else CARD,12,PRI if sel else LINE,2 if sel else 1)
        s.c(46,y+30,12,PRI if sel else "#FFFFFF",None if sel else "#94A3B8")
        if sel: s.poly([(40,y+30),(45,y+35),(53,y+25)],"#FFFFFF",2.4)
        s.t(68,y+25,f"{code} · {name}",15,600); s.t(68,y+45,meta+(f" · {tag}" if tag else ""),12,400,MUTED)
        if b: s.badge(300,y+20,"⌛ "+b[0],b[1],b[2])
        if recent: s.t(362,y+45,"Son kullandığınız",10,500,SOFT,"end")
        y+=68
    return y
def qr390():
    s=S(390,844,"Quick reserve, phone 390, room selected"); s.phone_shell("Hızlı rezervasyon",2)
    phone_steps(s)
    fy=844-83-150; s.r(8,fy,374,142,"#FFFFFF",24,LINE,op=.96)
    s.t(24,fy+28,"3. Onayla",12,600,SOFT); s.t(24,fy+52,"A 101 · Bugün 3. ders (10:10–10:50)",15,600)
    s.t(366,fy+28,"Not ekle",13,600,PRI,"end")
    s.btn(24,fy+66,342,48,"Rezerve et"); s.t(195,fy+132,"Bu hafta 2 rezervasyon hakkınız kaldı",11,400,MUTED,"middle")
    s.save(f"{OUT}/quick-reserve-390.svg")
def qr390r():
    s=S(390,844,"Quick reserve, phone 390, receipt with undo"); s.phone_shell("Hızlı rezervasyon",2)
    phone_steps(s)
    s.r(0,300,390,844-83-300,"#F4F6F9",0,op=.85)
    fy=380; s.r(8,fy,374,844-83-fy-8,"#FFFFFF",24,LINE)
    s.c(195,fy+48,22,OKBG); s.poly([(184,fy+48),(192,fy+56),(206,fy+40)],OK,3)
    s.t(195,fy+100,"Rezerve edildi",22,700,FG,"middle")
    s.t(195,fy+126,"A 101 · Amfi",15,600,FG,"middle"); s.t(195,fy+148,"Bugün, 17 Ekim · 3. ders · 10:10–10:50",13,400,MUTED,"middle")
    s.btn(24,fy+172,164,44,"Geri al","sec"); s.btn(202,fy+172,164,44,"Takvime ekle","sec")
    s.btn(24,fy+228,342,48,"Rezervasyonlarım")
    s.btn(24,fy+284,342,40,"Yeni rezervasyon","ghost")
    ty=844-83-8-56-0
    s.r(16,fy-72,358,56,FG,14); s.t(32,fy-38,"A 101 rezerve edildi",14,500,"#FFFFFF"); s.t(358,fy-38,"Geri al",14,700,"#93C5FD","end")
    s.note(20,fy-90,"toast 10 s (pauses on hover/focus); the receipt keeps Geri al")
    s.save(f"{OUT}/quick-reserve-390-receipt.svg")
def qr1440():
    s=S(1440,900,"Quick reserve, desktop 1440")
    s.desk_shell("Hızlı rezervasyon",2,["Panel","Takvim","Rezerve et","Rezervasyonlarım","Derslik bul","Talepler","§YÖNETİM","Ayarlar"])
    x0=276; s.t(x0,84,"Ne zaman, nerede: üç adımda bir ders saati ayırın.",14,400,MUTED)
    # col1
    s.r(x0,108,280,760,CARD,14,LINE); s.t(x0+20,140,"1. Ne zaman?",15,700)
    s.t(x0+20,168,"Gün",11,600,SOFT)
    for i,d in enumerate(["Bugün · Cum 17 Ekim","Pzt 20 Ekim","Sal 21 Ekim","Çar 22 Ekim","Per 23 Ekim","Cum 24 Ekim","Tarih seç…"]):
        y=178+i*36; sel=i==0; dis=False
        if sel: s.r(x0+12,y,256,32,TINT,8,PRI,2)
        s.t(x0+24,y+21,d,13,600 if sel else 400,PRI if sel else FG)
    s.t(x0+20,446,"Ders saati",11,600,SOFT)
    for i,(p,tm,st) in enumerate([("2. ders","09:20–10:00","Dolu"),("3. ders","10:10–10:50",""),("4. ders","11:00–11:40",""),("5. ders","11:50–12:30",""),("6. ders","12:40–13:20","Dolu"),("7. ders","13:30–14:10",""),("8. ders","14:20–15:00",""),("9. ders","15:10–15:50","")]):
        y=456+i*36; sel=i==1; dis=bool(st)
        if sel: s.r(x0+12,y,256,32,TINT,8,PRI,2)
        col=PRI if sel else ("#94A3B8" if dis else FG)
        s.t(x0+24,y+21,p,13,600 if sel else 500,col); s.t(x0+96,y+21,tm,13,400,col)
        if st: s.t(x0+258,y+21,st,12,500,"#94A3B8","end")
    s.note(x0+20,768,"radiogroups, roving tabindex, ↑/↓;");s.note(x0+20,784,"Dolu rows focusable + reason")
    # col2
    x1=x0+296; x2=1440-24-340; w1=x2-16-x1
    s.r(x1,108,w1,760,CARD,14,LINE); s.t(x1+20,140,"2. Nerede?",15,700); s.t(x1+20,166,"12 boş derslik",13,500,MUTED)
    cx=x1+20
    for i,c in enumerate(["Kişi: Hepsi ▾","Bina ▾","Özellik ▾"]): cx+=s.chip(cx,180,c,h=32,size=12)+6
    s.line(x1,226,x1+w1,226)
    for j,h in enumerate(["Derslik","Bina","Kişi","Özellik",""]): s.t([x1+52,x1+250,x1+330,x1+380,x1+w1-20][j],248,h,11,600,SOFT,"end" if j==4 else "start")
    for i,(code,name,meta,tag,b,recent) in enumerate(ROOMS):
        y=260+i*52; sel=i==0
        s.r(x1+8,y,w1-16,46,TINT if sel else CARD,8,PRI if sel else None,2)
        s.c(x1+32,y+23,9,PRI if sel else "#FFFFFF",None if sel else "#94A3B8")
        s.t(x1+52,y+20 if (recent or b) else y+28,f"{code} · {name}",14,600); 
        if recent: s.t(x1+52,y+37,"Son kullandığınız",11,400,SOFT)
        s.t(x1+250,y+28,meta.split(" · ")[0],13,400,MUTED); s.t(x1+330,y+28,meta.split(" · ")[1].split()[0],13,400,MUTED); s.t(x1+380,y+28,tag or "—",13,400,MUTED)
        if b: s.badge(x1+52,y+25,"⌛ Talep",WARN,WARNBG)
    s.t(x1+20,600,"Neden bazı derslikler yok? ▸",13,500,PRI)
    # col3
    s.r(x2,108,340,420,CARD,14,LINE)
    s.t(x2+20,140,"3. Onayla",15,700)
    s.t(x2+20,176,"A 101 · Amfi",20,700); s.t(x2+20,200,"Bugün, 17 Ekim · 3. ders",14,400,MUTED); s.t(x2+20,220,"10:10–10:50 · A Blok · 40 kişi",14,400,MUTED)
    s.t(x2+20,256,"Not (isteğe bağlı)",12,600,SOFT); s.r(x2+20,264,300,72,CARD,12,"#7A808C"); s.t(x2+32,288,"Örn. telafi dersi",13,400,"#94A3B8")
    s.btn(x2+20,356,300,44,"Rezerve et  ⌘↵"); s.t(x2+170,420,"Bu hafta 2 rezervasyon hakkınız kaldı",12,400,MUTED,"middle")
    s.t(x2+170,452,"Daha fazla seçenek →",13,600,PRI,"middle")
    s.note(x2,548,"sticky; the Talep et variant adds an info Alert");s.note(x2,564,"(approver, lead time), see the state board")
    s.save(f"{OUT}/quick-reserve-1440.svg")
def states():
    s=S(1440,900,"Quick reserve, state board")
    s.t(32,48,"Quick reserve: states (desktop card / phone footer share the content)",22,700)
    boxes=[(32,80,"Loading"),(380,80,"None free (slot)"),(728,80,"Approval-first: Talep et"),(1076,80,"Conflict (409)"),
           (32,500,"Receipt: requested"),(380,500,"Closed day"),(728,500,"Policy refusal"),(1076,500,"Quota reached")]
    for x,y,lab in boxes:
        s.r(x,y,332,392,CARD,14,LINE); s.t(x+16,y+28,lab,14,700)
    # loading
    x,y=32,80
    for i in range(4): s.r(x+16,y+56+i*56,300,44,"#EEF2F6",10)
    s.btn(x+16,y+340,300,40,"Rezerve et","dis"); s.note(x+16,y+330,"static placeholders, aria-busy; day chips already live")
    # none free
    x,y=380,80
    s.r(x+146,y+60,40,40,"#F1F5F9",10); s.t(x+166,y+86,"🚪",18,400,FG,"middle")
    s.t(x+166,y+130,"Bu saatte boş derslik yok",15,700,FG,"middle"); s.t(x+16,y+168,"En yakın boş saatler",12,600,SOFT)
    for i,c in enumerate(["4. ders · 11:00 · 6 derslik","5. ders · 11:50 · 9 derslik","7. ders · 13:30 · 14 derslik"]): s.chip(x+16,y+180+i*44,c,h=36,w=300,size=12)
    s.btn(x+16,y+320,300,40,"Başka gün seç","sec"); s.t(x+166,y+378,"Gelişmiş arama →",13,600,PRI,"middle")
    # approval
    x,y=728,80
    s.t(x+16,y+64,"C 112 · Seminer",18,700); s.badge(x+250,y+50,"⌛ Talep")
    s.t(x+16,y+88,"Bugün · 3. ders · 10:10–10:50",13,400,MUTED)
    s.r(x+16,y+108,300,92,TINT,12); s.t(x+30,y+132,"ⓘ Bu derslik onay gerektirir.",13,600,PRI)
    s.t(x+30,y+154,"Talebiniz onaylanınca rezervasyon",12,400,FG); s.t(x+30,y+172,"kesinleşir.",12,400,FG)
    s.t(x+16,y+226,"Onaycı: Yapı İşleri · en geç 2 gün önce",12,400,MUTED)
    s.btn(x+16,y+250,300,44,"Talep et"); s.note(x+16,y+316,"verb known before the tap (approvals check prefetched)")
    # conflict
    x,y=1076,80
    s.r(x+16,y+48,300,84,BADBG,12,BAD); s.t(x+30,y+74,"⨯ Bu saat az önce doldu.",14,700,BAD)
    s.t(x+30,y+96,"Aynı saatte başka bir derslik ya da",12,400,FG); s.t(x+30,y+114,"yakın bir saat seçin.",12,400,FG)
    for i,c in enumerate(["B 204 · aynı saat · 36 kişi","A 205 · aynı saat · 48 kişi","A 101 · 4. ders · 11:00"]):
        s.r(x+16,y+146+i*50,300,42,CARD,10,"#94A3B8"); s.t(x+30,y+172+i*50,c,13,500)
    s.t(x+166,y+318,"Listeyi yenile",13,600,PRI,"middle"); s.note(x+16,y+350,"one 3 px shake (none under reduced motion); role=alert")
    # receipt requested
    x,y=32,500
    s.c(x+166,y+78,22,WARNBG); s.t(x+166,y+86,"⌛",18,400,WARN,"middle")
    s.t(x+166,y+130,"Talebiniz gönderildi",18,700,FG,"middle"); s.t(x+166,y+154,"C 112 · Bugün 3. ders",13,400,MUTED,"middle")
    s.t(x+166,y+176,"Onaycı karar verince size bildirilecek.",12,400,MUTED,"middle")
    s.btn(x+16,y+200,300,42,"Talebi geri çek","sec"); s.btn(x+16,y+252,300,42,"Taleplerim")
    # closed day
    x,y=380,500
    xx=x+16
    for i,d in enumerate(["Bugün","Yarın","Sal 28","Çar 29"]): xx+=s.chip(xx,y+52,d,sel=i==1,dis=i==2,h=40)+6
    s.r(x+16,y+108,300,64,"#F8FAFC",10,LINE); s.t(x+30,y+134,"Sal 28 Ekim — Tatil:",13,600); s.t(x+30,y+154,"Cumhuriyet Bayramı",13,400,MUTED)
    s.note(x+16,y+196,"disabled chip stays focusable; reason in its name")
    s.r(x+16,y+220,300,52,"#F1F5F9",10); s.t(x+30,y+251,"Bugün dolu; Yarın 2. ders seçildi",13,500)
    # policy
    x,y=728,500
    s.r(x+16,y+48,300,96,WARNBG,12,WARN); s.t(x+30,y+74,"⚠ Bu derslik için en az 2 gün",13,700,WARN); s.t(x+30,y+94,"önceden rezervasyon gerekir.",13,700,WARN)
    s.t(x+30,y+124,"Neden? →",12,600,PRI); s.btn(x+16,y+168,300,44,"Rezerve et","dis")
    # quota
    x,y=1076,500
    s.r(x+16,y+48,300,84,"#F8FAFC",12,LINE); s.t(x+30,y+76,"Bu dönem için rezervasyon",13,600); s.t(x+30,y+96,"hakkınız doldu.",13,600)
    s.t(x+30,y+120,"Rezervasyonlarım →",12,600,PRI); s.btn(x+16,y+152,300,44,"Rezerve et","dis")
    s.save(f"{OUT}/quick-reserve-states.svg")
qr390(); qr390r(); qr1440(); states(); print("ok")
