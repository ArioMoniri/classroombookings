"""Tiny SVG wireframe kit for docs/design/v3/wireframes (W3-DES). Usage: python3 -I wf.py <outdir>"""
from xml.sax.saxutils import escape
FG="#0F172A"; MUTED="#475569"; SOFT="#64748B"; LINE="#E2E8F0"; CARD="#FFFFFF"; BG="#F4F6F9"
PRI="#2563EB"; TINT="#EFF6FF"; OK="#15803D"; OKBG="#DCFCE7"; WARN="#B45309"; WARNBG="#FEF3C7"
BAD="#B91C1C"; BADBG="#FEE2E2"; LOCK="#4338CA"; LOCKBG="#E0E7FF"; CAT=["#2a78d6","#eb6834","#1baf7a","#eda100","#e87ba4"]
FONT="-apple-system,BlinkMacSystemFont,Inter,Segoe UI,sans-serif"

class S:
    def __init__(s,w,h,title,bg=BG):
        s.w,s.h,s.title=w,h,title; s.o=[f"<rect width='{w}' height='{h}' fill='{bg}'/>"]
    def r(s,x,y,w,h,fill=CARD,rx=12,stroke=None,sw=1,op=1,dash=None):
        st=f" stroke='{stroke}' stroke-width='{sw}'" if stroke else ""
        if dash: st+=f" stroke-dasharray='{dash}'"
        s.o.append(f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' fill='{fill}' fill-opacity='{op}'{st}/>"); return s
    def t(s,x,y,txt,size=14,w=400,fill=FG,anchor="start"):
        s.o.append(f"<text x='{x}' y='{y}' font-size='{size}' font-weight='{w}' fill='{fill}' text-anchor='{anchor}'>{escape(str(txt))}</text>"); return s
    def line(s,x1,y1,x2,y2,stroke=LINE,sw=1,dash=None):
        d=f" stroke-dasharray='{dash}'" if dash else ""
        s.o.append(f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{stroke}' stroke-width='{sw}'{d}/>"); return s
    def poly(s,pts,stroke=PRI,sw=2,fill="none"):
        s.o.append(f"<polyline points='{' '.join(f'{a},{b}' for a,b in pts)}' fill='{fill}' stroke='{stroke}' stroke-width='{sw}' stroke-linejoin='round'/>"); return s
    def c(s,x,y,r,fill=PRI,stroke=None):
        st=f" stroke='{stroke}' stroke-width='2'" if stroke else ""
        s.o.append(f"<circle cx='{x}' cy='{y}' r='{r}' fill='{fill}'{st}/>"); return s
    def chip(s,x,y,label,sel=False,dis=False,h=36,w=None,size=13):
        w=w or max(44,int(len(label)*size*0.58)+28)
        if sel: s.r(x,y,w,h,TINT,h/2,PRI,2); col=PRI; wt=600
        elif dis: s.r(x,y,w,h,"#F1F5F9",h/2,LINE); col="#94A3B8"; wt=400
        else: s.r(x,y,w,h,CARD,h/2,"#94A3B8"); col=FG; wt=500
        s.t(x+w/2,y+h/2+size*0.36,label,size,wt,col,"middle"); return w
    def btn(s,x,y,w,h,label,kind="pri",size=15):
        if kind=="pri": s.r(x,y,w,h,PRI,h/2); col="#FFFFFF"
        elif kind=="dis": s.r(x,y,w,h,"#CBD5E1",h/2); col="#FFFFFF"
        elif kind=="sec": s.r(x,y,w,h,CARD,h/2,"#94A3B8"); col=FG
        else: col=PRI
        s.t(x+w/2,y+h/2+size*0.36,label,size,600,col,"middle"); return s
    def badge(s,x,y,label,fg=WARN,bg=WARNBG,size=11):
        w=int(len(label)*size*0.6)+16; s.r(x,y,w,20,bg,10); s.t(x+w/2,y+14,label,size,600,fg,"middle"); return w
    def note(s,x,y,txt,size=11):
        s.t(x,y,txt,size,500,"#7C3AED"); return s
    def phone_shell(s,title,tab=1,tabs=("Panel","Takvim","Rezerve et","Talepler","Daha")):
        s.t(20,30,"9:41",14,600); s.t(370,30,"100%",12,500,FG,"end")
        s.t(20,92,title,30,700)
        y=s.h-83; s.r(0,y,s.w,83,"#FFFFFF",0,op=.94); s.line(0,y,s.w,y)
        n=len(tabs)
        for i,lab in enumerate(tabs):
            cx=s.w/n*(i+.5); col=PRI if i==tab else SOFT
            s.r(cx-11,y+10,22,22,col if i==tab else "none",6,col,1.5); s.t(cx,y+48,lab,10,600 if i==tab else 500,col,"middle")
        s.r(s.w/2-67,s.h-9,134,5,FG,3); return s
    def desk_shell(s,title,active=0,items=()):
        s.r(12,12,232,s.h-24,"#FFFFFF",18,op=.86).r(12,12,232,s.h-24,"none",18,LINE)
        s.t(32,48,"SmartSched",16,700)
        for i,it in enumerate(items):
            y=80+i*36
            if it.startswith("§"): s.t(32,y+22,it[1:],11,600,SOFT); continue
            if i==active: s.r(24,y,208,32,TINT,8)
            s.t(40,y+21,it,13,600 if i==active else 400,PRI if i==active else FG)
        s.t(276,56,title,28,700); return s
    def save(s,path):
        body="\n".join(s.o)
        open(path,"w").write(f"<svg xmlns='http://www.w3.org/2000/svg' width='{s.w}' height='{s.h}' viewBox='0 0 {s.w} {s.h}' font-family='{FONT}' role='img' aria-label='{escape(s.title)}'>\n<title>{escape(s.title)}</title>\n{body}\n</svg>\n")
