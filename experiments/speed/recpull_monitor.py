import subprocess, time, json, sys, os, urllib.request, re
ADB=r"C:/Users/jjh7757/dev/android-sdk/platform-tools/adb.exe"
H="192.168.50.56:46057"; T="192.168.50.17:43405"
HEADDIR="/sdcard/Android/data/dev.jjh.mahjong_calc.ondevice/files/rec/rec_20261112_130244"
TABDIR="/sdcard/Android/data/dev.jjh.mahjong_calc.ondevice/files/rec_pull/rec_20261112_130244"
TOK=open(sys.argv[1]).read().strip(); OUT=sys.argv[2]; PHASE=sys.argv[3]; DUR=float(sys.argv[4])
env=dict(os.environ, MSYS_NO_PATHCONV="1")
def sh(dev,cmd):
    try: return subprocess.run([ADB,"-s",dev,"shell",cmd],capture_output=True,text=True,timeout=30,env=env).stdout
    except Exception as e: return ""
def frames(dev,d):
    out=sh(dev,f"ls {d} 2>/dev/null")
    ms=[int(m) for m in re.findall(r"f_(\d+)\.jpg\b",out)]
    return len(ms),(max(ms) if ms else None)
def therm(dev):
    o=sh(dev,"dumpsys thermalservice"); b=sh(dev,"dumpsys battery")
    st=re.search(r"Thermal Status: (\d+)",o); temps={}
    for name in ("AP","SKIN","BAT","battery","skin"):
        m=re.search(r"mName="+name+r"[^}]*?mValue=([\d.]+)|mValue=([\d.]+)[^}]*?mName="+name+r"\b",o)
        if m: temps[name]=float(m.group(1) or m.group(2))
    lv=re.search(r"level: (\d+)",b); cc=re.search(r"Charge counter: (\d+)",b)
    return dict(status=int(st.group(1)) if st else None,temps=temps,level=int(lv.group(1)) if lv else None,cc=int(cc.group(1)) if cc else None)
def cap():
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://192.168.50.56:8765/capture",headers={"X-Head-Token":TOK}),timeout=20); n=len(r.read())
        return round(time.time()-t,3),n
    except Exception as e: return None,str(e)
end=time.time()+DUR; i=0
with open(OUT,"a",encoding="utf-8") as f:
    while time.time()<end:
        t0=time.time()
        hn,hl=frames(H,HEADDIR); tn,tl=frames(T,TABDIR)
        rec=dict(t=round(t0,1),phase=PHASE,head_n=hn,head_last=hl,tab_n=tn,tab_last=tl,head=therm(H))
        if i%4==0: rec["capture"]=[cap() for _ in range(2)]
        f.write(json.dumps(rec,ensure_ascii=False)+"\n"); f.flush(); i+=1
        time.sleep(max(0,15-(time.time()-t0)))
