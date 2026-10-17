import sys; sys.path.insert(0,".")
from wf import *
OUT=sys.argv[1]
P=[("08:30","09:10"),("09:20","10:00"),("10:10","10:50"),("11:00","11:40"),("11:50","12:30"),("12:40","13:20"),("13:30","14:10"),("14:20","15:00"),("15:10","15:50"),("16:00","16:40"),("16:50","17:30"),("17:30","18:00")]
def mins(a): h,m=a.split(":"); return int(h)*60+int(m)
STAT=["free","booked","class","free","free","closed","booked","free","class","free","free","free"]
def cellfill(st): return {"free":(CARD,LINE,"Boş"),"booked":(LOCKBG,"#A5B4FC","Rezerve"),"class":("#F4F4F5","#D4D4D8","Ders"),"closed":(BADBG,"#FCA5A5","Kapalı")}[st]
def grid(s,x,y,w,layout="periods",label="both",rowh=32,n=12,rooms=("A 101","B 204","C 112")):
    gx=x+92; cw=(w-92)/len(rooms)
    for j,r in enumerate(rooms): s.t(gx+cw*j+cw/2,y+14,r,12,600,FG,"middle")
    yy=y+24; t0=mins(P[0][0])
    for i,(a,b) in enumerate(P[:n]):
        if layout=="timeline":
            top=y+24+(mins(a)-t0)*1.1*(rowh/44); h=(mins(b)-mins(a))*1.1*(rowh/44)-0
        else:
            top=yy; h=rowh-4; yy+=rowh
        lab={"both":(f"{i+1}. ders",a),"period":(f"{i+1}. ders",""),"time":(f"{a}–{b}","")}[label]
        s.t(x,top+(h/2 if not lab[1] else h/2-2)+4,lab[0],12,600)
        if lab[1] and h>=24: s.t(x,top+h/2+14,lab[1],10,400,MUTED)
        for j in range(len(rooms)):
            st=STAT[(i+j*3)%len(STAT)]; f,stc,word=cellfill(st)
            s.r(gx+cw*j+2,top,cw-4,h,f,6,stc)
            if h>=18: s.t(gx+cw*j+cw/2,top+h/2+4,word,10,500,MUTED,"middle")
    return s
def d1440():
    s=S(1440,900,"Slot display settings with live preview, desktop 1440")
    s.desk_shell("Ayarlar",6,["Panel","Takvim","Rezerve et","Rezervasyonlarım","Derslik bul","§YÖNETİM","Ayarlar","Kullanıcılar"])
    x=276; tx=x
    for i,tb in enumerate(["Genel","Görünüm","Yapay zekâ","Çözücü","Rezervasyon kuralları","Ders saatleri","Entegrasyonlar"]):
        w=s.chip(tx,76,tb,sel=i==5,h=32,size=12); tx+=w+6
    s.r(x,124,560,720,CARD,14,LINE)
    s.t(x+20,156,"Ders saati görünümü",18,700); s.t(x+20,178,"Rezervasyon ekranlarında ders saatlerinin nasıl görüneceğini seçin.",12,400,MUTED)
    s.t(x+20,212,"Düzen",13,700)
    for k,(t1,t2) in enumerate([("Ders satırları","Her ders saati eşit yükseklikte"),("Zaman blokları","Yükseklik süreyle orantılı")]):
        bx=x+20+k*262; sel=k==0; s.r(bx,222,252,80,TINT if sel else CARD,12,PRI if sel else "#94A3B8",2 if sel else 1)
        for q in range(4):
            hh=12 if k==0 else [10,14,8,16][q]; yy=232+(q*15 if k==0 else [0,12,28,38][q])
            s.r(bx+12,yy,36,hh,"#CBD5E1",3)
        s.t(bx+60,254,t1,13,600); s.t(bx+60,274,t2,11,400,MUTED)
    def seg(y,label,opts,sel):
        s.t(x+20,y,label,13,700); bx=x+150; s.r(bx,y-20,390,32,"#EEF2F6",16)
        ww=390/len(opts)
        for i,o in enumerate(opts):
            if i==sel: s.r(bx+i*ww+3,y-17,ww-6,26,CARD,13,LINE)
            s.t(bx+i*ww+ww/2,y,o,12,600 if i==sel else 400,FG,"middle")
    seg(336,"Etiket",["Ders","Saat","İkisi"],2)
    seg(376,"Ders adı",["Sıra (3. ders)","Çizelgedeki ad"],0)
    seg(416,"Saat",["Başlangıç (10:10)","Aralık (10:10–10:50)"],0)
    seg(468,"Yoğunluk",["Sıkı","Standart","Geniş"],1); s.t(x+150,490,"Telefonda satırlar en az 44 px kalır.",11,400,MUTED)
    s.t(x+20,530,"Görünen saatler",13,700)
    s.r(x+150,512,180,32,CARD,10,"#7A808C"); s.t(x+162,533,"İlk: 1. ders · 08:30 ▾",12,400)
    s.r(x+340,512,200,32,CARD,10,"#7A808C"); s.t(x+352,533,"Son: 11. ders · 16:50 ▾",12,400)
    s.r(x+150,556,36,20,PRI,10); s.c(x+176,566,8,"#FFFFFF"); s.t(x+196,571,"Kısa geçiş saatlerini gizle (17:30–18:00)",12,400)
    s.t(x+150,598,"11 / 18 ders saati görünür",12,600,MUTED)
    s.t(x+20,640,"Varsayılan görünüm",13,700)
    s.r(x+150,622,180,32,CARD,10,"#7A808C"); s.t(x+162,643,"Masaüstü: Günlük tablo ▾",12,400)
    s.r(x+340,622,200,32,CARD,10,"#7A808C"); s.t(x+352,643,"Telefon: Boş saatler ▾",12,400)
    seg(704,"Hızlı rezervasyon",["En fazla 1","2","3 ders"],0)
    s.r(x+20,738,36,20,PRI,10); s.c(x+46,748,8,"#FFFFFF"); s.t(x+66,753,"Kullanıcılar yoğunluğu ve varsayılan görünümü kendileri değiştirebilir",12,400)
    s.t(x+20,800,"Ders saatlerini değiştirmek için: Zaman çizelgeleri →",12,600,PRI)
    # preview
    px=x+576; s.r(px,124,520,560,CARD,14,LINE); s.t(px+20,156,"Önizleme",16,700); s.t(px+20,176,"Bugünün ders saatleri · örnek doluluk",11,400,MUTED)
    bx=px+20; s.r(bx,190,230,30,"#EEF2F6",15); s.r(bx+3,193,74,24,CARD,12,LINE)
    for i,o in enumerate(["Tablo","Liste","Hızlı"]): s.t(bx+38+i*77,210,o,12,600 if i==0 else 400,FG,"middle")
    bx=px+300; s.r(bx,190,200,30,"#EEF2F6",15); s.r(bx+3,193,94,24,CARD,12,LINE)
    for i,o in enumerate(["Masaüstü","Telefon"]): s.t(bx+50+i*100,210,o,12,600 if i==0 else 400,FG,"middle")
    grid(s,px+20,236,480,"periods","both",36,11)
    s.t(px+20,670,"+1 gizli saat",11,600,PRI)
    # save bar
    s.r(x+700,820,396,56,"#FFFFFF",28,LINE,op=.95); s.t(x+724,853,"Kaydedilmemiş değişiklikler",12,500,MUTED)
    s.btn(x+890,830,90,36,"Varsayılan","sec",12); s.btn(x+988,830,96,36,"Kaydet","pri",13)
    s.save(f"{OUT}/slot-display-1440.svg")
def d390():
    s=S(390,844,"Slot display settings, phone 390"); s.phone_shell("Ayarlar",4)
    tx=20
    for i,tb in enumerate(["Rezervasyon kuralları","Ders saatleri","Entegr"]): tx+=s.chip(tx,108,tb,sel=i==1,h=44,size=12)+6
    s.t(20,186,"Ders saati görünümü",18,700)
    s.t(20,214,"Düzen",13,700)
    for k,t1 in enumerate(["Ders satırları","Zaman blokları"]):
        sel=k==0; s.r(20+k*179,224,171,56,TINT if sel else CARD,12,PRI if sel else "#94A3B8",2 if sel else 1); s.t(20+k*179+86,257,t1,13,600,FG,"middle")
    def seg(y,label,opts,sel):
        s.t(20,y,label,13,700); s.r(20,y+8,350,44,"#EEF2F6",22); ww=350/len(opts)
        for i,o in enumerate(opts):
            if i==sel: s.r(20+i*ww+3,y+11,ww-6,38,CARD,19,LINE)
            s.t(20+i*ww+ww/2,y+35,o,12,600 if i==sel else 400,FG,"middle")
    seg(306,"Etiket",["Ders","Saat","İkisi"],2)
    s.r(20,370,350,132,CARD,12,LINE); s.t(32,390,"Önizleme · Liste",11,600,SOFT)
    for i,(p,a,b,w) in enumerate([("2. ders","09:20","10:00","Rezerve"),("3. ders","10:10","10:50","Boş"),("4. ders","11:00","11:40","Boş")]):
        y=398+i*34; s.line(32,y,358,y); s.t(32,y+22,f"{p} · {a}",13,600); s.t(358,y+22,w,12,500,MUTED,"end")
    seg(530,"Yoğunluk",["Sıkı","Standart","Geniş"],1); s.t(20,602,"Telefonda satırlar en az 44 px kalır.",11,400,MUTED)
    s.t(20,636,"Görünen saatler",13,700); s.t(20,656,"1. ders – 11. ders · 11 / 18 görünür",12,400,MUTED)
    fy=844-83-76; s.r(8,fy,374,68,"#FFFFFF",24,LINE,op=.96)
    s.btn(20,fy+12,140,44,"Önizle","sec"); s.btn(170,fy+12,200,44,"Kaydet")
    s.save(f"{OUT}/slot-display-390.svg")
def matrix():
    s=S(1440,900,"Slot display matrix: period rows vs time blocks, label variants")
    s.t(32,48,"Düzen × etiket: how the /bookings day grid renders each choice (desktop, standard density)",20,700)
    cols=[("Ders satırları · İkisi","periods","both"),("Ders satırları · Saat","periods","time"),("Zaman blokları · İkisi","timeline","both"),("Zaman blokları · Ders","timeline","period")]
    for k,(t1,lay,lab) in enumerate(cols):
        x=32+k*352; s.r(x,72,336,740,CARD,14,LINE); s.t(x+16,100,t1,14,700)
        grid(s,x+16,116,304,lay,lab,44 if lay=="periods" else 44,12,("A 101","B 204"))
    s.note(32,840,"Timeline: height = minutes × 1.1 px (standard), 10-min breaks become gaps, the 30-min 17:30 slot is visibly shorter. Lists and chips ignore Düzen; phones keep ≥ 44 px rows.")
    s.note(32,860,"Every cell and row keeps a full accessible name (‘3. ders, 10:10–10:50’) whatever the visible label.")
    s.save(f"{OUT}/slot-display-matrix.svg")
d1440(); d390(); matrix(); print("ok")
