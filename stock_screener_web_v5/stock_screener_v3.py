#!/usr/bin/env python3
"""
Stock Fundamental Screener V3
- Sector-aware scoring
- N/A-safe scoring
- Outlier validation
- Data-quality score
- Risk flags
- Bank metrics when Yahoo Finance exposes them
- Multi-ticker peer comparison
- JSON/CSV/text output
- Local cache + retry
"""
import argparse, csv, json, logging, math, sys, time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yfinance as yf
except ImportError:
    print("yfinance belum terpasang. Jalankan: python -m pip install yfinance", file=sys.stderr)
    raise SystemExit(1)

DEFAULT = {
    "weights": {
        "pbv": 1.0, "per": 1.0, "roe": 1.5, "roa": 1.0, "der": 1.5,
        "net_margin": 1.0, "revenue_growth": 1.0, "earnings_growth": 1.0,
        "dividend_yield": 0.5,
        "nim": 1.2, "npl": 1.2, "ldr": 0.8, "casa": 0.8,
    },
    "thresholds": {
        "pbv": [1.0, 2.0, 3.5], "per": [10.0, 15.0, 25.0],
        "roe": [0.20, 0.15, 0.08], "roa": [0.10, 0.06, 0.03],
        "der": [0.5, 1.0, 2.0], "net_margin": [0.15, 0.08, 0.03],
        "revenue_growth": [0.15, 0.08, 0.0], "earnings_growth": [0.15, 0.08, 0.0],
        "dividend_yield": [0.05, 0.02, 0.0],
        "nim": [0.06, 0.04, 0.02], "npl": [0.02, 0.04, 0.06],
        "ldr": [0.70, 0.85, 1.00], "casa": [0.60, 0.50, 0.40],
    },
    "data_quality": {"minimum": 0.50, "good": 0.80},
    "limits": {"pbv": 1000, "per": 1000, "der": 100, "dividend_yield": 1.0},
    "retry": {"attempts": 3, "backoff": 2.0},
    "cache": {"enabled": True, "ttl": 900, "dir": ".stock_cache"},
}

PERCENT = {"roe","roa","net_margin","revenue_growth","earnings_growth",
           "dividend_yield","nim","npl","casa"}
LABEL = {2:"Sangat Baik",1:"Baik",0:"Cukup",-1:"Kurang",None:"N/A"}
FINANCIAL_WORDS = ("financial", "bank", "insurance", "capital markets",
                   "credit services", "mortgage finance", "financial services")
BANK_WORDS = ("bank", "perbankan")

@dataclass
class Metric:
    key: str
    name: str
    value: Optional[float]
    score: Optional[int]
    weight: float
    note: str = ""
    source: str = "Yahoo Finance"

@dataclass
class Report:
    ticker: str
    resolved_ticker: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    currency: Optional[str] = None
    price: Optional[float] = None
    market_cap: Optional[float] = None
    profile: str = "NON_FINANCIAL"
    metrics: List[Metric] = field(default_factory=list)
    score: Optional[float] = None
    data_quality: float = 0.0
    verdict: str = "TIDAK DIKETAHUI"
    risk_flags: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    fetched_at_utc: str = ""

    def to_dict(self):
        return asdict(self)

def merge(a, b):
    for k,v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict): merge(a[k], v)
        else: a[k] = v
    return a

def load_config(path):
    cfg = json.loads(json.dumps(DEFAULT))
    if path:
        try:
            merge(cfg, json.loads(Path(path).read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[WARN] Config gagal dibaca: {e}; memakai default.", file=sys.stderr)
    return cfg

def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def get(info, *keys):
    for k in keys:
        x = num(info.get(k))
        if x is not None: return x
    return None

def text(info, *keys):
    for k in keys:
        if info.get(k) not in (None, ""): return str(info[k])
    return None

def ticker_name(s):
    s = s.strip().upper()
    return s if "." in s else (s + ".JK" if len(s)==4 and s.isalpha() else s)

def setup_log(debug, verbose, path):
    log = logging.getLogger("screener")
    log.handlers.clear(); log.setLevel(logging.DEBUG)
    h = logging.StreamHandler(sys.stdout)
    h.setLevel(logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING))
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(h)
    if path:
        f = logging.FileHandler(path, encoding="utf-8"); f.setLevel(logging.DEBUG); f.setFormatter(h.formatter); log.addHandler(f)
    return log

def cache_file(t, cfg):
    p = Path(cfg["cache"]["dir"]); p.mkdir(exist_ok=True)
    return p / (t.replace("/","_") + ".json")

def fetch(t, cfg, log):
    cp = cache_file(t, cfg)
    if cfg["cache"]["enabled"] and cp.exists():
        try:
            x=json.loads(cp.read_text(encoding="utf-8"))
            if time.time()-x["time"] <= cfg["cache"]["ttl"]:
                log.debug("Cache dipakai: %s", t); return x["info"]
        except Exception: pass
    last=None
    for i in range(cfg["retry"]["attempts"]):
        try:
            info=yf.Ticker(t).info
            if not isinstance(info,dict): raise RuntimeError("data Yahoo bukan dict")
            if cfg["cache"]["enabled"]:
                try: cp.write_text(json.dumps({"time":time.time(),"info":info},ensure_ascii=False),encoding="utf-8")
                except Exception: pass
            return info
        except Exception as e:
            last=e; log.warning("Fetch %s gagal %d/%d: %s",t,i+1,cfg["retry"]["attempts"],e)
            if i+1<cfg["retry"]["attempts"]: time.sleep(cfg["retry"]["backoff"]*(2**i))
    raise RuntimeError(str(last))

def profile(info):
    s=f"{info.get('sector','')} {info.get('industry','')} {info.get('longName','')}".lower()
    if any(x in s for x in BANK_WORDS): return "BANK"
    if any(x in s for x in FINANCIAL_WORDS): return "FINANCIAL"
    return "NON_FINANCIAL"

def score(v, bands, low):
    if v is None: return None
    a,b,c=bands
    if low: return 2 if v<=a else 1 if v<=b else 0 if v<=c else -1
    return 2 if v>=a else 1 if v>=b else 0 if v>=c else -1

def ldr_score(v,b):
    if v is None:return None
    lo,ideal,hi=b
    return 2 if lo<=v<=ideal else 1 if ideal<v<=hi else 0 if v<lo else -1

def add(r,key,name,v,w,b,low,note=""):
    r.metrics.append(Metric(key,name,v,score(v,b,low),w,note))

def dividend(info,price,cfg):
    rate=get(info,"dividendRate")
    if rate is not None and price:
        v=rate/price
        if 0<=v<=cfg["limits"]["dividend_yield"]: return v,"Dihitung dari dividendRate / harga"
    y=get(info,"dividendYield")
    if y is not None:
        y=y/100 if y>1 else y
        if 0<=y<=cfg["limits"]["dividend_yield"]: return y,"Menggunakan dividendYield Yahoo"
    return None,"Dividend yield N/A/tidak valid"

def der(info,prof,cfg):
    if prof!="NON_FINANCIAL": return None,"DER konvensional dikeluarkan untuk sektor keuangan"
    x=get(info,"debtToEquity")
    if x is not None:
        x=x/100 if x>5 else x
        if 0<=x<=cfg["limits"]["der"]: return x,"Dari debtToEquity"
    debt=get(info,"totalDebt"); eq=get(info,"totalStockholderEquity")
    if debt is not None and eq not in (None,0):
        x=debt/eq
        if 0<=x<=cfg["limits"]["der"]: return x,"Dihitung totalDebt / totalStockholderEquity"
    return None,"DER N/A/tidak valid"

def bank_value(info,keys,maxv):
    v=get(info,*keys)
    return (v,None) if v is not None and 0<=v<=maxv else (None,"Data tidak tersedia")

def analyze(raw,cfg,log):
    t=ticker_name(raw); r=Report(raw,t,fetched_at_utc=datetime.now(timezone.utc).isoformat())
    try: info=fetch(t,cfg,log)
    except Exception as e: r.verdict="GAGAL AMBIL DATA"; r.errors.append(str(e)); return r
    r.company_name=text(info,"longName","shortName"); r.sector=text(info,"sector")
    r.industry=text(info,"industry"); r.currency=text(info,"currency")
    r.price=get(info,"currentPrice","regularMarketPrice"); r.market_cap=get(info,"marketCap")
    r.profile=profile(info); th=cfg["thresholds"]; w=cfg["weights"]; lim=cfg["limits"]

    pbv=get(info,"priceToBook"); 
    if pbv is not None and (pbv<0 or pbv>lim["pbv"]): pbv=None; r.risk_flags.append("PBV di luar batas validasi.")
    per=get(info,"trailingPE","forwardPE")
    if per is not None and (per<=0 or per>lim["per"]): per=None; r.risk_flags.append("PER negatif/ekstrem tidak digunakan.")
    roe=get(info,"returnOnEquity"); roa=get(info,"returnOnAssets")
    nm=get(info,"profitMargins"); rg=get(info,"revenueGrowth")
    eg=get(info,"earningsGrowth","earningsQuarterlyGrowth")
    dy,dyn=dividend(info,r.price,cfg); de,den=der(info,r.profile,cfg)

    add(r,"pbv","PBV",pbv,w["pbv"],th["pbv"],True,"Makin rendah relatif lebih murah; tetap bandingkan peer.")
    add(r,"per","PER",per,w["per"],th["per"],True)
    add(r,"roe","ROE",roe,w["roe"],th["roe"],False)
    add(r,"roa","ROA",roa,w["roa"],th["roa"],False)
    add(r,"net_margin","Net Profit Margin",nm,w["net_margin"],th["net_margin"],False)
    add(r,"revenue_growth","Revenue Growth",rg,w["revenue_growth"],th["revenue_growth"],False)
    add(r,"earnings_growth","Earnings Growth",eg,w["earnings_growth"],th["earnings_growth"],False)
    add(r,"der","DER",de,w["der"],th["der"],True,den)
    add(r,"dividend_yield","Dividend Yield",dy,w["dividend_yield"],th["dividend_yield"],False,dyn)

    if r.profile=="BANK":
        nim,nn=bank_value(info,("netInterestMargin","netInterestMarginTTM","nim"),1)
        npl, npn=bank_value(info,("nonPerformingLoanRatio","nplRatio","npl"),1)
        ldr, ldn=bank_value(info,("loanToDepositRatio","ldr"),10)
        casa,cn=bank_value(info,("casaRatio","casa"),1)
        add(r,"nim","NIM",nim,w["nim"],th["nim"],False,nn or "")
        add(r,"npl","NPL",npl,w["npl"],th["npl"],True,npn or "")
        r.metrics.append(Metric("ldr","LDR",ldr,ldr_score(ldr,th["ldr"]),w["ldr"],ldn or ""))
        add(r,"casa","CASA",casa,w["casa"],th["casa"],False,cn or "")
        r.notes += ["Profil BANK: DER konvensional tidak dinilai.",
                    "NIM/NPL/LDR/CASA hanya dipakai jika Yahoo menyediakan data valid; tidak ada angka yang ditebak."]
    elif r.profile=="FINANCIAL":
        r.notes.append("Profil FINANCIAL: DER konvensional tidak dinilai agar tidak salah interpretasi.")

    valid=[m for m in r.metrics if m.score is not None]
    r.data_quality=len(valid)/len(r.metrics) if r.metrics else 0
    if valid:
        total=sum(m.weight*3 for m in valid)
        got=sum((m.score+1)*m.weight for m in valid)
        r.score=round(got/total*100,2)
    if r.data_quality<cfg["data_quality"]["minimum"]: r.verdict="DATA TERBATAS / PERLU VERIFIKASI"
    elif r.score is None: r.verdict="DATA TIDAK CUKUP"
    elif r.score>=70: r.verdict="FUNDAMENTAL RELATIF KUAT"
    elif r.score>=50: r.verdict="FUNDAMENTAL CUKUP"
    elif r.score>=35: r.verdict="FUNDAMENTAL PERLU PERHATIAN"
    else: r.verdict="FUNDAMENTAL LEMAH"

    if rg is not None and rg<0:r.risk_flags.append("Revenue growth negatif.")
    if eg is not None and eg<0:r.risk_flags.append("Earnings growth negatif.")
    if nm is not None and nm<0:r.risk_flags.append("Net margin negatif.")
    if roe is not None and roe<0:r.risk_flags.append("ROE negatif.")
    if r.profile=="NON_FINANCIAL" and de is not None and de>th["der"][2]:r.risk_flags.append("DER melewati threshold tertinggi.")
    if r.profile=="BANK" and npl is not None and npl>th["npl"][2]:r.risk_flags.append("NPL melewati threshold tertinggi.")
    r.notes.append("Verifikasi angka penting dengan laporan resmi emiten/BEI sebelum mengambil keputusan.")
    return r

def fmt(m):
    if m.value is None:return "N/A"
    return f"{m.value*100:.2f}%" if m.key in PERCENT else f"{m.value:.4f}"

def print_report(r):
    print("="*76); print(f"{r.company_name or r.resolved_ticker} ({r.resolved_ticker})"); print("="*76)
    print(f"Sektor   : {r.sector or 'N/A'}"); print(f"Industri : {r.industry or 'N/A'}"); print(f"Profil   : {r.profile}")
    if r.price is not None: print(f"Harga    : {r.price:,.2f} {r.currency or ''}")
    if r.market_cap is not None: print(f"MarketCap: {r.market_cap:,.0f} {r.currency or ''}")
    print("-"*76); print(f"{'METRIK':<24}{'NILAI':>14}{'SKOR':>15}{'BOBOT':>10}"); print("-"*76)
    for m in r.metrics:
        print(f"{m.name:<24}{fmt(m):>14}{LABEL[m.score]:>15}{m.weight:>10.2f}")
        if m.note: print(f"    -> {m.note}")
    print("-"*76); print(f"Data quality : {r.data_quality*100:.2f}%")
    print(f"Skor         : {r.score if r.score is not None else 'N/A'} / 100")
    print(f"VERDICT      : {r.verdict}")
    if r.risk_flags:
        print("\nRISK / WARNING:"); [print("  -",x) for x in r.risk_flags]
    if r.notes:
        print("\nNOTES:"); [print("  -",x) for x in r.notes]
    if r.errors:
        print("\nERROR:"); [print("  -",x) for x in r.errors]
    print()

def output_json(rs,path):
    payload={"tool":"stock_screener_v3","generated_at_utc":datetime.now(timezone.utc).isoformat(),
             "reports":[r.to_dict() for r in rs]}
    s=json.dumps(payload,indent=2,ensure_ascii=False)
    Path(path).write_text(s,encoding="utf-8") if path else print(s)

def output_csv(rs,path):
    rows=[]
    for r in rs:
        row={"ticker":r.resolved_ticker,"company_name":r.company_name,"sector":r.sector,
             "industry":r.industry,"profile":r.profile,"price":r.price,"market_cap":r.market_cap,
             "score":r.score,"data_quality":r.data_quality,"verdict":r.verdict,
             "risk_flags":" | ".join(r.risk_flags)}
        for m in r.metrics: row[m.key]=m.value; row[m.key+"_score"]=m.score
        rows.append(row)
    if not rows:return
    f=open(path,"w",newline="",encoding="utf-8-sig") if path else sys.stdout
    try:
        wri=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction="ignore"); wri.writeheader(); wri.writerows(rows)
    finally:
        if path:f.close()

def main():
    p=argparse.ArgumentParser(description="Stock Fundamental Screener V3")
    p.add_argument("-t","--ticker",required=True,help="BBCA atau BBCA,BBRI,TLKM,ASII")
    p.add_argument("-c","--config"); p.add_argument("-o","--output",choices=["text","json","csv"],default="text")
    p.add_argument("-f","--output-file"); p.add_argument("--no-cache",action="store_true")
    p.add_argument("--cache-ttl",type=int); p.add_argument("--clear-cache",action="store_true")
    p.add_argument("-v","--verbose",action="store_true"); p.add_argument("--debug",action="store_true"); p.add_argument("--log-file")
    a=p.parse_args(); log=setup_log(a.debug,a.verbose,a.log_file); cfg=load_config(a.config)
    if a.no_cache:cfg["cache"]["enabled"]=False
    if a.cache_ttl is not None:cfg["cache"]["ttl"]=max(0,a.cache_ttl)
    ts=[x.strip() for x in a.ticker.split(",") if x.strip()]
    if a.clear_cache:
        for x in ts:
            try:cache_file(ticker_name(x),cfg).unlink(missing_ok=True)
            except Exception:pass
    rs=[]
    for x in ts:
        try:rs.append(analyze(x,cfg,log))
        except Exception as e:
            z=Report(x,ticker_name(x),verdict="ERROR");z.errors.append(str(e));rs.append(z)
    if a.output=="text":
        for r in rs:print_report(r)
        usable=sorted([r for r in rs if r.score is not None],key=lambda x:x.score,reverse=True)
        if len(usable)>1:
            print("="*76);print("PEER COMPARISON — urutan matematis screener");print("="*76)
            for i,r in enumerate(usable,1):print(f"{i:>2}. {r.resolved_ticker:<12}{r.score:>7.2f}  quality={r.data_quality*100:>5.1f}%  {r.verdict}")
        print("\nDisclaimer: ini alat screening, bukan rekomendasi/nasihat investasi.")
    elif a.output=="json":output_json(rs,a.output_file)
    else:output_csv(rs,a.output_file)

if __name__=="__main__":main()
