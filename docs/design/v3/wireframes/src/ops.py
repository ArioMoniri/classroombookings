import sys, random, math; sys.path.insert(0,".")
from wf import *
OUT=sys.argv[1]
NAV=["Panel","Takvim","Rezerve et","§YÖNETİM","Kullanıcılar","Yapay zekâ","Operasyon","Ayarlar"]
def tabs(s,x,y,sel,labels=("Durum","Hatalar","Günlükler","Panolar")):
    s.r(x,y,440,36,"#E8ECF2",18); w=440/len(labels)
    for i,l in enumerate(labels):
        if i==sel: s.r(x+i*w+3,y+3,w-6,30,CARD,15,LINE)
        s.t(x+i*w+w/2,y+23,l,13,600 if i==sel else 400,FG,"middle")
STC={"ok":("#16A34A","Çalışıyor",OK),"warn":("#F59E0B","Dikkat",WARN),"down":("#DC2626","Çalışmıyor",BAD),"unk":("#94A3B8","Bilinmiyor",SOFT)}
def card(s,x,y,w,name,st,l1,l2,link=None,h=104):
    s.r(x,y,w,h,CARD,14,LINE); s.t(x+16,y+26,name,14,700)
    dc,word,col=STC[st]; s.c(x+w-90,y+21,4,dc); s.t(x+w-80,y+25,word,12,600,col)
    s.t(x+16,y+54,l1,15,600); s.t(x+16,y+76,l2,12,400,MUTED if st=="ok" else col)
    if link: s.t(x+16,y+96,link,11,600,PRI)
def spark(s,x,y,w,h,seed,col=PRI,spike=None,flat=False):
    random.seed(seed); pts=[]
    for i in range(60):
        v=0 if flat else 0.45+0.25*math.sin(i/7)+random.random()*0.2
        if spike and spike[0]<=i<=spike[1]: v=0.9
        if flat and spike and spike[0]<=i<=spike[1]: v=0.6
        pts.append((x+i*w/59,y+h-v*h))
    s.line(x,y+h,x+w,y+h,"#CBD5E1"); s.poly(pts,col,2)
def status1440():
    s=S(1440,900,"Operations panel, status tab, desktop 1440"); s.desk_shell("Operasyon",6,NAV)
    x=276; tabs(s,x,76,0); s.t(x+1140,98,"Son yenileme 19:42:10 · Otomatik yenile ●",12,400,MUTED,"end")
    s.c(x+8,146,6,"#F59E0B"); s.t(x+24,152,"2 servis dikkat istiyor",22,650)
    s.t(x,178,"Sürüm 3.4.1 · a1b2c3d · 17 Eki 16:05'te yayına alındı · üretim",12,400,MUTED)
    s.r(x,194,1140,40,WARNBG,12,"#FCD34D"); s.t(x+16,219,"⚠ E-posta kuyruğu 30 dakikadan uzun süredir bekliyor · 19:05 itibarıyla",13,600,WARN); s.t(x+1124,219,"Grafana'da gör ↗",13,600,PRI,"end")
    cw=372; g=12
    cards=[("E-posta","warn","42 bekliyor","En eski 37 dk · 0 başarısız","Ayarlar › Kanallar"),("İzleme","warn","Grafana ✓ · Prometheus ✓ · Loki ✕","Loki çalışmıyor: günlükler gösterilemez","Panolar"),
           ("API","ok","Çalışma süresi 3 g 4 sa","2 işçi süreç","Panolar › API"),("Veritabanı","ok","Gecikme 4 ms","Şema güncel",None),
           ("İş kuyrukları","ok","0 sırada · 1 çalışıyor","Son 24 sa 0 başarısız","Çalıştırmalar"),("Teslimatlar","ok","0 başarısız","Bildirim 0 · Webhook 0 · Takvim 0",None),
           ("Disk","ok","%61 dolu · 38 GB boş","",None),("Hatalar","ok","2 açık hata grubu","Son 24 sa 9 olay","Hatalar"),("Pod CI","ok","Son çalıştırma: Geçti","main · a1b2c3d · 15:58",None)]
    for i,(n,st,l1,l2,lk) in enumerate(cards):
        cx=x+(i%3)*(cw+g); cy=248+(i//3)*(104+g); card(s,cx,cy,cw,n,st,l1,l2,lk)
        if n=="Disk":
            s.r(cx+16,cy+70,cw-32,8,"#DBEAFE",4); s.r(cx+16,cy+70,(cw-32)*.61,8,PRI,4)
    y=600; s.r(x,y,1140,280,CARD,14,LINE); s.t(x+16,y+28,"İstekler",15,700); s.t(x+16,y+48,"Son 1 saatte dakikada ortalama 42 istek; 19:21'de kısa bir 5xx artışı; p95 180 ms.",12,400,MUTED)
    bx=x+800
    for i,o in enumerate(["Son 1 sa","Son 6 sa","Son 24 sa"]): bx+=s.chip(bx,y+14,o,sel=i==0,h=30,size=12)+4
    for k,(t,col,sp,flat) in enumerate([("İstek/dk",PRI,None,False),("⨯ 5xx/dk",BAD,(20,24),True),("p95 gecikme (ms)",PRI,(20,24),False)]):
        cx=x+16+k*372; s.t(cx,y+84,t,12,600,FG); spark(s,cx,y+100,348,130,k+3,col,sp,flat)
        s.t(cx,y+250,"18:42",10,400,SOFT); s.t(cx+348,y+250,"19:42",10,400,SOFT,"end")
    s.line(x+16+20*348/59+0,y+96,x+16+20*348/59,y+232,FG,1,"3 3"); s.r(x+16+20*348/59+6,y+100,150,48,FG,8); s.t(x+16+20*348/59+14,y+120,"19:02 · 61 istek/dk",11,600,"#FFFFFF"); s.t(x+16+20*348/59+14,y+138,"5xx 4 · p95 410 ms",11,400,"#E2E8F0")
    s.note(x+380,y+272,"three small multiples, one axis each, shared crosshair; Kaynak: Prometheus; Tablo toggle")
    s.save(f"{OUT}/ops-status-1440.svg")
def el1440():
    s=S(1440,900,"Operations panel, errors with detail sheet and logs, desktop 1440"); s.desk_shell("Operasyon",6,NAV)
    x=276; tabs(s,x,76,1)
    cx=x
    for i,o in enumerate(["Açık","Çözüldü","Yok sayıldı","Tümü"]): cx+=s.chip(cx,128,o,sel=i==0,h=32,size=12)+4
    s.chip(cx+12,128,"Kaynak: Tümü ▾",h=32,size=12); s.r(x+450,128,240,32,CARD,10,"#7A808C"); s.t(x+462,149,"Ara: tür, mesaj, rota",12,400,"#94A3B8")
    s.r(x,176,690,420,CARD,14,LINE)
    for c,cxx in [("Durum",16),("Hata",120),("Kaynak",400),("Olay",480),("Son görülme",560)]: s.t(x+cxx,202,c,11,600,SOFT)
    rows=[("Yeni","IntegrityError","duplicate key value violates unique…","Sunucu","37","2 dk önce",BAD,True),("İnceleniyor","TimeoutError","mail send timed out after 30 s","Arka plan işi","12","9 dk önce",WARN,False),("Yeni","TypeError","Cannot read properties of undefined…","Tarayıcı","5","1 sa önce",BAD,False),("Yeni ×1","HTTPStatusError","Loki 502 Bad Gateway","Sunucu","3","2 sa önce",BAD,False)]
    for i,(st,k,m,src,n,last,col,sel) in enumerate(rows):
        yy=214+i*58; 
        if sel: s.r(x+6,yy,678,54,TINT,8,PRI,2)
        else: s.line(x+8,yy,x+682,yy)
        s.badge(x+16,yy+18,st,col,BADBG if col==BAD else WARNBG)
        s.t(x+120,yy+24,k,13,700); s.t(x+120,yy+42,m,11,400,MUTED); s.t(x+400,yy+30,src,12,400); s.t(x+480,yy+30,n,13,600); s.t(x+560,yy+30,last,12,400,MUTED)
    s.t(x+16,560,"Yeni ×1 = yeniden açıldı (çözüldü olarak işaretlenmişti)",11,500,"#7C3AED")
    # sheet
    sx=x+706; s.r(sx,124,434,756,CARD,18,LINE)
    s.t(sx+20,156,"IntegrityError",18,700); s.badge(sx+340,142,"Yeni",BAD,BADBG)
    s.t(sx+20,180,"37 olay · ilk 18:12 · son 19:40 · sürüm 3.4.1",12,400,MUTED)
    s.t(sx+20,210,"duplicate key value violates unique constraint",13,400); s.t(sx+20,228,"\"uq_booking_slot\"",13,400)
    s.t(sx+20,256,"POST /api/v1/bookings · 500 · rol: öğretim elemanı",12,400,MUTED)
    s.t(sx+20,288,"Yığın izi",13,700); s.t(sx+414,288,"Kopyala",12,600,PRI,"end")
    s.r(sx+20,298,394,180,"#0F172A",10)
    for i,l in enumerate(["Traceback (most recent call last):",'  File "app/services/bookings.py", line 812','    await session.flush()','  File "sqlalchemy/orm/session.py", line 4331','sqlalchemy.exc.IntegrityError: (psycopg)','  duplicate key value violates unique','  constraint "uq_booking_slot"','  request_id=7f3c…a9']):
        s.t(sx+32,320+i*20,l,11,400,"#E2E8F0")
    s.btn(sx+20,494,190,40,"Günlüklerde aç","sec",13); s.btn(sx+224,494,190,40,"Grafana'da aç ↗","sec",13)
    s.line(sx,820,sx+434,820)
    s.btn(sx+20,832,120,36,"İncelemeye al","sec",12); s.btn(sx+148,832,140,36,"Çözüldü olarak işaretle","pri",11); s.btn(sx+296,832,118,36,"Yok say","sec",12)
    # log preview under table
    s.r(x,612,690,268,CARD,14,LINE); s.t(x+16,636,"Günlükler (önizleme: Günlüklerde aç sonrası)",13,700)
    cx=x+16
    for o in ["Sunucu ▾","1 sa","Hata ✓","7f3c…a9 ✕"]: cx+=s.chip(cx,646,o,h=28,size=11)+4
    s.r(x+580,648,32,18,PRI,9); s.c(x+603,657,6,"#FFFFFF"); s.t(x+620,661,"Canlı",11,600)
    lines=[("19:40:02.114","Bilgi","POST /api/v1/bookings 201 18ms req=51ab…"),("19:40:02.871","Hata","IntegrityError uq_booking_slot req=7f3c…a9"),("19:40:02.872","Hata","500 POST /api/v1/bookings 41ms req=7f3c…a9"),("19:40:03.010","Uyarı","retry booking flush skipped (conflict)")]
    for i,(t,lv,m) in enumerate(lines):
        yy=696+i*26; col={"Bilgi":MUTED,"Hata":BAD,"Uyarı":WARN}[lv]
        s.t(x+16,yy,t,11,400,MUTED); s.t(x+112,yy,lv,11,600,col); s.t(x+164,yy,m,11,400,FG)
    s.r(x+262,820,166,30,FG,15); s.t(x+345,840,"3 yeni satır ↓",12,600,"#FFFFFF","middle")
    s.t(x+16,870,"Parolalar, belirteçler ve çerezler gizlenir. Saklama: 14 gün.",10,400,SOFT)
    s.save(f"{OUT}/ops-errors-logs-1440.svg")
def o390():
    s=S(390,844,"Operations panel, phone 390"); s.phone_shell("Operasyon",4)
    tx=20
    for i,t in enumerate(["Durum","Hatalar","Günlükler","Panolar"]): tx+=s.chip(tx,108,t,sel=i==0,h=44,size=12)+6
    s.c(26,184,6,"#F59E0B"); s.t(40,190,"2 servis dikkat istiyor",18,650); s.t(20,212,"Sürüm 3.4.1 · a1b2c3d · 17 Eki 16:05",11,400,MUTED)
    s.r(20,224,350,52,WARNBG,12,"#FCD34D"); s.t(32,246,"⚠ E-posta kuyruğu 30 dk'dan uzun",12,600,WARN); s.t(32,264,"süredir bekliyor · 19:05",12,400,WARN)
    rows=[("E-posta","warn","42 bekliyor · en eski 37 dk"),("İzleme","warn","Loki çalışmıyor"),("API","ok","3 g 4 sa · 2 işçi"),("Veritabanı","ok","4 ms · şema güncel"),("İş kuyrukları","ok","0 sırada · 1 çalışıyor"),("Hatalar","ok","2 açık grup")]
    s.r(20,288,350,6*58,CARD,14,LINE)
    for i,(n,st,l) in enumerate(rows):
        yy=288+i*58; dc,word,col=STC[st]
        if i: s.line(32,yy,358,yy)
        s.c(36,yy+29,5,dc); s.t(50,yy+25,n,14,600); s.t(50,yy+44,l,12,400,MUTED); s.t(330,yy+34,word,12,600,col,"end"); s.t(352,yy+34,"›",16,500,SOFT,"end")
    s.r(20,650,350,44,"#EEF2F6",22); 
    for i,o in enumerate(["İstek","5xx","p95"]):
        if i==0: s.r(23,653,111,38,CARD,19,LINE)
        s.t(20+58+i*116,677,o,12,600 if i==0 else 400,FG,"middle")
    s.save(f"{OUT}/ops-390.svg")
status1440(); el1440(); o390(); print("ok")
