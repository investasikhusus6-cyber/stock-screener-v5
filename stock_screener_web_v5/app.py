from flask import Flask, jsonify, render_template, request
from datetime import datetime, timezone
from pathlib import Path
import logging, math, time

import yfinance as yf

from stock_screener_v3 import analyze, load_config, setup_log, ticker_name

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "stock_screener_v3_config.json"

app = Flask(__name__)
CFG = load_config(str(CONFIG) if CONFIG.exists() else None)
LOG = setup_log(False, False, None)

METRIC_ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue", "TotalRevenue"],
    "net_income": ["Net Income", "Net Income Common Stockholders", "NetIncome"],
    "assets": ["Total Assets", "TotalAssets"],
    "equity": ["Stockholders Equity", "Total Stockholder Equity", "Total Equity Gross Minority Interest",
               "Common Stock Equity", "Stockholders' Equity"],
    "debt": ["Total Debt", "TotalDebt"],
    "operating_income": ["Operating Income", "OperatingIncome"],
    "gross_profit": ["Gross Profit", "GrossProfit"],
}

def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def _row_value(df, names, col):
    if df is None or df.empty:
        return None
    for name in names:
        if name in df.index:
            try:
                return _num(df.loc[name, col])
            except Exception:
                pass
    # relaxed case-insensitive match
    wanted = {n.lower().replace(" ", "") for n in names}
    for idx in df.index:
        key = str(idx).lower().replace(" ", "")
        if key in wanted:
            try:
                return _num(df.loc[idx, col])
            except Exception:
                pass
    return None

def _period_label(ts):
    try:
        return str(ts.year)
    except Exception:
        return str(ts)[:4]

def _annual_history(ticker):
    """
    Returns up to 5 fiscal-year observations from Yahoo annual statements.
    Current year is represented separately by TTM when Yahoo exposes it.
    """
    t = yf.Ticker(ticker)
    try:
        inc = t.get_income_stmt(freq="yearly")
    except Exception:
        inc = getattr(t, "income_stmt", None)

    try:
        bs = t.get_balance_sheet(freq="yearly")
    except Exception:
        bs = getattr(t, "balance_sheet", None)

    if inc is None or inc.empty:
        inc = getattr(t, "income_stmt", None)
    if bs is None or bs.empty:
        bs = getattr(t, "balance_sheet", None)

    cols = []
    if inc is not None and not inc.empty:
        cols = list(inc.columns)
    if bs is not None and not bs.empty:
        for c in bs.columns:
            if c not in cols:
                cols.append(c)

    # Yahoo/yfinance may return pandas Timestamp, datetime, date, or strings.
    # Never compare bound methods such as Timestamp.timestamp; normalize safely.
    def _col_sort_key(x):
        try:
            if hasattr(x, "to_pydatetime"):
                return x.to_pydatetime().timestamp()
            if hasattr(x, "year") and hasattr(x, "month") and hasattr(x, "day"):
                import datetime as _dt
                return _dt.datetime(int(x.year), int(x.month), int(x.day)).timestamp()
            import pandas as _pd
            return _pd.to_datetime(str(x), errors="coerce").timestamp()
        except Exception:
            return 0.0

    cols = sorted(cols, key=_col_sort_key, reverse=True)[:5]
    rows = []
    for c in reversed(cols):
        revenue = _row_value(inc, METRIC_ROWS["revenue"], c)
        net_income = _row_value(inc, METRIC_ROWS["net_income"], c)
        assets = _row_value(bs, METRIC_ROWS["assets"], c)
        equity = _row_value(bs, METRIC_ROWS["equity"], c)
        debt = _row_value(bs, METRIC_ROWS["debt"], c)

        roe = net_income / equity if net_income is not None and equity not in (None, 0) else None
        roa = net_income / assets if net_income is not None and assets not in (None, 0) else None
        npm = net_income / revenue if net_income is not None and revenue not in (None, 0) else None
        de = debt / equity if debt is not None and equity not in (None, 0) else None

        rows.append({
            "year": _period_label(c),
            "period": "FY",
            "revenue": revenue,
            "net_income": net_income,
            "assets": assets,
            "equity": equity,
            "debt": debt,
            "roe": roe,
            "roa": roa,
            "npm": npm,
            "de": de,
        })

    # Add growth rates after chronological sorting.
    for i, row in enumerate(rows):
        prev = rows[i - 1] if i else None
        row["revenue_growth"] = (
            row["revenue"] / prev["revenue"] - 1
            if prev and row["revenue"] is not None and prev["revenue"] not in (None, 0)
            else None
        )
        row["earnings_growth"] = (
            row["net_income"] / prev["net_income"] - 1
            if prev and row["net_income"] is not None and prev["net_income"] not in (None, 0)
            else None
        )

    # TTM is used as the current-year view when available.
    try:
        ttm_inc = getattr(t, "ttm_income_stmt", None)
        if ttm_inc is not None and not ttm_inc.empty:
            col = ttm_inc.columns[0]
            revenue = _row_value(ttm_inc, METRIC_ROWS["revenue"], col)
            net_income = _row_value(ttm_inc, METRIC_ROWS["net_income"], col)
            # For balance-sheet values use latest annual balance sheet.
            assets = rows[-1]["assets"] if rows else None
            equity = rows[-1]["equity"] if rows else None
            debt = rows[-1]["debt"] if rows else None
            if revenue is not None or net_income is not None:
                current_year = datetime.now().year
                last_year = rows[-1]["year"] if rows else ""
                if str(current_year) != str(last_year):
                    roe = net_income / equity if net_income is not None and equity not in (None, 0) else None
                    roa = net_income / assets if net_income is not None and assets not in (None, 0) else None
                    npm = net_income / revenue if net_income is not None and revenue not in (None, 0) else None
                    de = debt / equity if debt is not None and equity not in (None, 0) else None
                    prev = rows[-1] if rows else None
                    rows.append({
                        "year": str(current_year),
                        "period": "TTM",
                        "revenue": revenue,
                        "net_income": net_income,
                        "assets": assets,
                        "equity": equity,
                        "debt": debt,
                        "roe": roe,
                        "roa": roa,
                        "npm": npm,
                        "de": de,
                        "revenue_growth": revenue / prev["revenue"] - 1 if prev and revenue is not None and prev["revenue"] not in (None, 0) else None,
                        "earnings_growth": net_income / prev["net_income"] - 1 if prev and net_income is not None and prev["net_income"] not in (None, 0) else None,
                    })
    except Exception:
        pass

    # Keep up to five annual periods plus the current TTM period when available.
    # Yahoo commonly exposes fewer than five annual statement columns; never invent data.
    has_ttm = bool(rows and rows[-1].get("period") == "TTM")
    annual_rows = [x for x in rows if x.get("period") == "FY"][-5:]
    return annual_rows + ([rows[-1]] if has_ttm else [])

def _historical_prices(ticker, years):
    out = {}
    try:
        hist = yf.Ticker(ticker).history(period="5y", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return out
        for y in years:
            try:
                part = hist[hist.index.year == int(y)]
                if not part.empty:
                    out[str(y)] = _num(part["Close"].dropna().iloc[-1])
            except Exception:
                pass
    except Exception:
        pass
    return out

def _historical_valuation(ticker):
    """Best-effort yearly historical valuation from yfinance valuation measures."""
    out = {}
    try:
        t = yf.Ticker(ticker)
        if not hasattr(t, "get_valuation_measures"):
            return out
        df = t.get_valuation_measures(freq="yearly", periods=5)
        if df is None or df.empty:
            return out
        # Row names vary slightly across yfinance versions.
        aliases = {
            "per": ["P/E Ratio", "Pe Ratio", "Trailing P/E", "Trailing PE"],
            "pbv": ["Price/Book", "Price to Book", "P/B Ratio", "Price/Book Value"],
        }
        def find_row(names):
            exact = {str(x).strip().lower() for x in names}
            for idx in df.index:
                if str(idx).strip().lower() in exact:
                    return idx
            for idx in df.index:
                low = str(idx).strip().lower()
                if any(n.lower() in low for n in names):
                    return idx
            return None
        rows = {k: find_row(v) for k, v in aliases.items()}
        for col in df.columns:
            try:
                label = str(col)
                if label.lower() == "current":
                    continue
                dt = __import__("pandas").to_datetime(col, errors="coerce")
                if __import__("pandas").isna(dt):
                    continue
                year = str(dt.year)
                out[year] = {
                    "per": _num(df.loc[rows["per"], col]) if rows["per"] is not None else None,
                    "pbv": _num(df.loc[rows["pbv"], col]) if rows["pbv"] is not None else None,
                }
            except Exception:
                continue
    except Exception:
        pass
    return out

def _average(values):
    vals = [_num(x) for x in values]
    vals = [x for x in vals if x is not None]
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

def _five_year_summary(report, history, valuation):
    """Calculate transparent averages from the historical periods actually available."""
    def avg(key):
        return _average([row.get(key) for row in history])

    summary = {}
    for key in ["revenue", "net_income", "roe", "roa", "npm", "revenue_growth", "earnings_growth", "de"]:
        value, count = avg(key)
        summary[key] = {"value": value, "count": count}

    per_val, per_count = _average([x.get("per") for x in valuation.values()])
    pbv_val, pbv_count = _average([x.get("pbv") for x in valuation.values()])
    summary["per"] = {"value": per_val, "count": per_count}
    summary["pbv"] = {"value": pbv_val, "count": pbv_count}

    # A separate historical quality count is useful because Yahoo may expose fewer
    # than five annual statement columns. Do not manufacture missing years.
    periods = len(history)
    summary["periods"] = periods
    summary["valuation_periods"] = max(per_count, pbv_count)

    # Trend from first to last available period.
    usable_profit = [x for x in history if x.get("net_income") is not None]
    usable_revenue = [x for x in history if x.get("revenue") is not None]
    summary["net_income_trend"] = None
    summary["revenue_trend"] = None
    if len(usable_profit) >= 2 and usable_profit[0]["net_income"] not in (None, 0):
        summary["net_income_trend"] = usable_profit[-1]["net_income"] / usable_profit[0]["net_income"] - 1
    if len(usable_revenue) >= 2 and usable_revenue[0]["revenue"] not in (None, 0):
        summary["revenue_trend"] = usable_revenue[-1]["revenue"] / usable_revenue[0]["revenue"] - 1

    # 5Y performance score: only historical operating/profitability metrics,
    # with valuation shown separately. This prevents today's PER/PBV from being
    # mistaken for a five-year average.
    components = []
    thresholds = CFG.get("thresholds", {})
    weights = CFG.get("weights", {})
    rules = [
        ("roe", "roe", False), ("roa", "roa", False),
        ("npm", "net_margin", False), ("revenue_growth", "revenue_growth", False),
        ("earnings_growth", "earnings_growth", False),
    ]
    # Score using the same 0/1/2/-1 concept as V3, normalized to 0-100.
    for hist_key, cfg_key, low in rules:
        val = summary[hist_key]["value"]
        band = thresholds.get(cfg_key)
        weight = weights.get(cfg_key, 0)
        if val is None or not band or not weight:
            continue
        a, b, c = band
        raw_score = 2 if val >= a else 1 if val >= b else 0 if val >= c else -1
        components.append(((raw_score + 1) * weight, 3 * weight))
    if components:
        summary["performance_score_5y"] = round(sum(x[0] for x in components) / sum(x[1] for x in components) * 100, 2)
    else:
        summary["performance_score_5y"] = None
    summary["performance_components"] = len(components)
    return summary

def _snapshot_to_dict(r):
    return r.to_dict()

def _conclusion(report, history, summary):
    score = report.get("score")
    quality = report.get("data_quality", 0) * 100
    flags = report.get("risk_flags", [])
    perf_score = summary.get("performance_score_5y")
    notes = []

    if score is None and perf_score is None:
        label = "DATA TIDAK CUKUP"
    elif quality < 50:
        label = "DATA TERBATAS — PERLU VERIFIKASI"
    elif perf_score is not None and perf_score >= 70 and score is not None and score >= 70:
        label = "FUNDAMENTAL TERKONFIRMASI RELATIF KUAT"
    elif perf_score is not None and perf_score >= 50 and score is not None and score >= 50:
        label = "FUNDAMENTAL CUKUP — PERLU RISET LANJUT"
    elif perf_score is not None and perf_score < 50:
        label = "TREN FUNDAMENTAL 5 TAHUN PERLU PERHATIAN"
    else:
        label = "PERLU RISET LANJUT"

    periods = summary.get("periods", 0)
    if periods:
        notes.append(f"Rata-rata fundamental dihitung dari {periods} periode laporan yang benar-benar tersedia; data kosong tidak diisi dengan asumsi.")
    if summary.get("net_income_trend") is not None:
        direction = "naik" if summary["net_income_trend"] > 0 else "turun" if summary["net_income_trend"] < 0 else "relatif datar"
        notes.append(f"Laba bersih dari periode awal ke periode terakhir tersedia {direction} ({summary['net_income_trend']*100:.2f}%).")
    if summary.get("revenue_trend") is not None:
        direction = "naik" if summary["revenue_trend"] > 0 else "turun" if summary["revenue_trend"] < 0 else "relatif datar"
        notes.append(f"Revenue dari periode awal ke periode terakhir tersedia {direction} ({summary['revenue_trend']*100:.2f}%).")
    if perf_score is not None:
        notes.append(f"Score performa historis: {perf_score:.2f}/100 dari {summary.get('performance_components', 0)} komponen yang tersedia.")
    if flags:
        notes.append(f"Ada {len(flags)} risk/warning pada snapshot fundamental terbaru.")
    if quality >= 80:
        notes.append("Kelengkapan data snapshot termasuk kategori baik.")
    else:
        notes.append("Sebagian metrik snapshot tidak tersedia/valid dan tidak boleh diasumsikan.")

    return {"label": label, "score": score, "performance_score_5y": perf_score,
            "data_quality": quality, "reasons": notes, "risk_flags": flags}

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok", "version": "V5.1", "time_utc": datetime.now(timezone.utc).isoformat()})

@app.get("/api/analyze")
def api_analyze():
    raw = request.args.get("ticker", "").strip()
    if not raw:
        return jsonify({"error": "Masukkan ticker, contoh BBCA"}), 400

    tickers = [x.strip() for x in raw.split(",") if x.strip()][:10]
    reports = []
    for raw_ticker in tickers:
        try:
            resolved = ticker_name(raw_ticker)
            r = analyze(resolved, CFG, LOG)
            snap = _snapshot_to_dict(r)
            history = _annual_history(resolved)
            prices = _historical_prices(resolved, [x["year"] for x in history])
            valuation = _historical_valuation(resolved)
            for row in history:
                row["year_end_price"] = prices.get(row["year"])
                row["historical_per"] = valuation.get(row["year"], {}).get("per")
                row["historical_pbv"] = valuation.get(row["year"], {}).get("pbv")
            summary = _five_year_summary(snap, history, valuation)
            # A current-year TTM row is clearly labeled so it is not confused with FY.
            snap["history_5y"] = history
            snap["five_year_summary"] = summary
            snap["conclusion"] = _conclusion(snap, history, summary)
            snap["period_note"] = "FY = fiscal year; TTM = trailing twelve months/data terbaru yang tersedia."
            snap["history_source"] = "Yahoo Finance via yfinance"
            reports.append(snap)
        except Exception as e:
            reports.append({"ticker": raw_ticker, "resolved_ticker": ticker_name(raw_ticker),
                            "verdict": "ERROR", "errors": [str(e)]})
    return jsonify({"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "reports": reports})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
