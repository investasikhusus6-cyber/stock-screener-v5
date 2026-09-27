const $=s=>document.querySelector(s);
const fmt=(v,d=2)=>v==null?"—":Number(v).toLocaleString("id-ID",{maximumFractionDigits:d});
const pct=v=>v==null?"—":(Number(v)*100).toFixed(2)+"%";
const money=v=>v==null?"—":Number(v).toLocaleString("id-ID",{maximumFractionDigits:0});
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));

function renderMetricCards(r){
  const m={}; (r.metrics||[]).forEach(x=>m[x.key]=x);
  const get=k=>m[k]?.value;
  return `<div class="grid">
    <div class="metric card"><div class="k">Harga</div><div class="v">${fmt(r.price)}</div></div>
    <div class="metric card"><div class="k">Market Cap</div><div class="v">${money(r.market_cap)}</div></div>
    <div class="metric card"><div class="k">PBV</div><div class="v">${fmt(get("pbv"),2)}</div></div>
    <div class="metric card"><div class="k">PER</div><div class="v">${fmt(get("per"),2)}</div></div>
    <div class="metric card"><div class="k">ROE</div><div class="v">${pct(get("roe"))}</div></div>
    <div class="metric card"><div class="k">ROA</div><div class="v">${pct(get("roa"))}</div></div>
    <div class="metric card"><div class="k">Net Margin</div><div class="v">${pct(get("net_margin"))}</div></div>
    <div class="metric card"><div class="k">Dividend Yield</div><div class="v">${pct(get("dividend_yield"))}</div></div>
  </div>`;
}

function renderFiveYearSummary(r){
  const s=r.five_year_summary||{};
  const val=k=>s[k]?.value;
  const count=k=>s[k]?.count||0;
  const avgPct=k=>val(k)==null?"—":pct(val(k));
  const avgNum=k=>val(k)==null?"—":fmt(val(k),2);
  const perf=s.performance_score_5y==null?"—":fmt(s.performance_score_5y,2)+" / 100";
  const periods=s.periods||0;
  return `<section class="section card fiveyear">
    <div class="sectionhead"><div><h3>Rata-rata Fundamental ${periods ? periods+' Periode' : '5 Tahun'}</h3>
    <p class="muted">Dihitung dari data laporan yang benar-benar tersedia. Tidak ada data kosong yang diganti dengan asumsi.</p></div>
    <div class="avgscore"><span>Score Performa Historis</span><b>${perf}</b></div></div>
    <div class="avggrid">
      <div class="avgitem"><span>ROE rata-rata</span><b>${avgPct('roe')}</b><small>${count('roe')} data</small></div>
      <div class="avgitem"><span>ROA rata-rata</span><b>${avgPct('roa')}</b><small>${count('roa')} data</small></div>
      <div class="avgitem"><span>Net Margin rata-rata</span><b>${avgPct('npm')}</b><small>${count('npm')} data</small></div>
      <div class="avgitem"><span>Revenue Growth rata-rata</span><b>${avgPct('revenue_growth')}</b><small>${count('revenue_growth')} data</small></div>
      <div class="avgitem"><span>Earnings Growth rata-rata</span><b>${avgPct('earnings_growth')}</b><small>${count('earnings_growth')} data</small></div>
      <div class="avgitem"><span>Debt/Equity rata-rata</span><b>${avgNum('de')}</b><small>${count('de')} data</small></div>
      <div class="avgitem"><span>PER historis rata-rata</span><b>${avgNum('per')}</b><small>${count('per')} data</small></div>
      <div class="avgitem"><span>PBV historis rata-rata</span><b>${avgNum('pbv')}</b><small>${count('pbv')} data</small></div>
    </div>
    <div class="comparebox">
      <div><span>PER sekarang</span><b>${fmt((r.metrics||[]).find(x=>x.key==='per')?.value,2)}</b></div>
      <div><span>PBV sekarang</span><b>${fmt((r.metrics||[]).find(x=>x.key==='pbv')?.value,2)}</b></div>
      <div><span>Score snapshot sekarang</span><b>${r.score==null?'—':fmt(r.score,2)}</b></div>
    </div>
    <p class="disclaimer">PER/PBV rata-rata hanya ditampilkan jika data valuasi historis tersedia dari Yahoo Finance. Untuk bank/financial, Debt/Equity konvensional dapat tetap N/A karena tidak cocok dibandingkan seperti perusahaan non-keuangan.</p>
  </section>`;
}

function renderTable(r){
  const rows=r.history_5y||[];
  if(!rows.length)return `<section class="section card"><h3>Riwayat Fundamental</h3><p class="muted">Data laporan tahunan tidak tersedia dari sumber.</p></section>`;
  const body=rows.map(x=>`<tr>
    <td><b>${esc(x.year)}</b><br><span class="muted">${esc(x.period)}</span></td>
    <td>${money(x.revenue)}</td><td>${money(x.net_income)}</td>
    <td>${pct(x.roe)}</td><td>${pct(x.roa)}</td><td>${pct(x.npm)}</td>
    <td>${pct(x.revenue_growth)}</td><td>${pct(x.earnings_growth)}</td>
    <td>${fmt(x.de,2)}</td><td>${fmt(x.historical_per,2)}</td><td>${fmt(x.historical_pbv,2)}</td><td>${money(x.year_end_price)}</td>
  </tr>`).join("");
  return `<section class="section card"><h3>Riwayat Fundamental</h3>
  <div class="tablewrap"><table class="table"><thead><tr>
  <th>Periode</th><th>Revenue</th><th>Net Income</th><th>ROE</th><th>ROA</th><th>NPM</th>
  <th>Revenue Growth</th><th>Earnings Growth</th><th>Debt/Equity</th><th>PER</th><th>PBV</th><th>Harga</th>
  </tr></thead><tbody>${body}</tbody></table></div>
  <p class="disclaimer">FY = laporan fiskal tahunan. TTM = trailing twelve months/data terbaru yang tersedia, bukan otomatis laporan FY penuh. Harga tahun berjalan adalah harga referensi terbaru yang tersedia, bukan selalu harga penutupan 31 Desember.</p>
  </section>`;
}

function renderChart(r){
  const rows=r.history_5y||[];
  const id="chart_"+Math.random().toString(36).slice(2);
  setTimeout(()=>{
    const el=document.getElementById(id); if(!el)return;
    new Chart(el,{type:"line",data:{labels:rows.map(x=>x.year),datasets:[
      {label:"Revenue",data:rows.map(x=>x.revenue),tension:.25},
      {label:"Net Income",data:rows.map(x=>x.net_income),tension:.25}
    ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom"}},scales:{y:{ticks:{callback:v=>Number(v).toLocaleString("id-ID")}}}}});
  },30);
  return `<section class="section card"><h3>Grafik Tren 5 Tahun</h3><div class="chartbox"><canvas id="${id}"></canvas></div></section>`;
}

function renderConclusion(r){
  const c=r.conclusion||{};
  const reasons=(c.reasons||[]).map(x=>`<div class="reason">• ${esc(x)}</div>`).join("");
  const risks=(c.risk_flags||[]).map(x=>`<div class="reason warn">⚠ ${esc(x)}</div>`).join("");
  return `<section class="section card conclusion">
    <h3>Kesimpulan Screening</h3>
    <div class="badge">${esc(c.label||r.verdict||"TIDAK DIKETAHUI")}</div>
    <p><b>Score snapshot:</b> ${c.score==null?"—":fmt(c.score,2)} / 100 &nbsp; • &nbsp; <b>Kualitas data:</b> ${fmt(c.data_quality,2)}%</p>
    ${reasons}${risks}
    <p class="disclaimer">Ini adalah hasil penyaringan rasio dan tren data, bukan instruksi beli/jual. Keputusan akhir perlu mempertimbangkan laporan resmi, valuasi, kondisi bisnis, risiko, dan tujuan Anda.</p>
  </section>`;
}

function render(r){
  if(r.errors?.length)return `<div class="error">${esc(r.errors.join(" • "))}</div>`;
  return `<article class="stock">
    <section class="hero card">
      <div class="identity"><div class="eyebrow">${esc(r.profile||"STOCK")}</div>
      <h2>${esc(r.company_name||r.resolved_ticker)}</h2>
      <div class="muted">${esc(r.resolved_ticker)} • ${esc(r.sector||"N/A")} • ${esc(r.industry||"N/A")}</div>
      <p class="muted">Data diambil: ${esc(r.fetched_at_utc||"—")}<br>${esc(r.period_note||"")}</p></div>
      <div class="score">${r.score==null?"—":fmt(r.score,2)}<div class="badge">${esc(r.verdict||"TIDAK DIKETAHUI")}</div></div>
    </section>
    ${renderMetricCards(r)}
    ${renderFiveYearSummary(r)}
    ${renderTable(r)}
    ${renderChart(r)}
    <div class="twocol">
      <section class="section card"><h3>Risk / Warning</h3>${(r.risk_flags||[]).length?(r.risk_flags.map(x=>`<div class="reason warn">⚠ ${esc(x)}</div>`).join("")):"<div class='reason'>Tidak ada flag dari mesin screening.</div>"}</section>
      <section class="section card"><h3>Catatan</h3>${(r.notes||[]).map(x=>`<div class="reason">• ${esc(x)}</div>`).join("")}</section>
    </div>
    ${renderConclusion(r)}
  </article>`;
}

async function analyze(){
  const t=$("#ticker").value.trim();
  if(!t)return;
  $("#status").innerHTML='<div class="loading">Mengambil laporan 5 tahun dan data terbaru…</div>';
  $("#results").innerHTML="";
  try{
    const res=await fetch("/api/analyze?ticker="+encodeURIComponent(t));
    const data=await res.json();
    if(!res.ok)throw new Error(data.error||"Gagal mengambil data");
    $("#status").innerHTML="";
    $("#results").innerHTML=(data.reports||[]).map(render).join("");
  }catch(e){$("#status").innerHTML=`<div class="error">${esc(e.message)}</div>`}
}
$("#analyzeBtn").onclick=analyze;
$("#ticker").addEventListener("keydown",e=>{if(e.key==="Enter")analyze()});
document.querySelectorAll("[data-ticker]").forEach(b=>b.onclick=()=>{$("#ticker").value=b.dataset.ticker;analyze()});
$("#themeBtn").onclick=()=>document.body.classList.toggle("light");
analyze();
