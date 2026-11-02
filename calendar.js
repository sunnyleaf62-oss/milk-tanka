/*
 * お得な日カレンダー（ミルク単価くらべ・おむつ単価くらべ共通）
 * 使い方：<section id="okcal" data-src="calendar.json" data-amazon-tag="xxx-22" data-rakuten-rt="_RTLinkXXXX"></section>
 *        <script src="calendar.js" defer></script>
 * 日付はすべて日本時間で計算する。
 */
(function () {
  const root = document.getElementById("okcal");
  if (!root) return;

  const RAKUTEN_AFF = "589314bc.bddfa8b8.589314bd.ed2be359";   // 楽天アフィリエイトID（リンクに出る公開の値）
  const VC = { sid: "3784952", pid: "892737497" };            // バリューコマース（公開の値）
  const MALLS = {
    "楽天":   { cls: "rk", mark: "楽", top: "https://www.rakuten.co.jp/" },
    "Yahoo!": { cls: "yh", mark: "Y",  top: "https://shopping.yahoo.co.jp/" },
    "Amazon": { cls: "az", mark: "A",  top: "https://www.amazon.co.jp/" },
  };
  const WD = ["日", "月", "火", "水", "木", "金", "土"];
  const JST = 9 * 3600e3;

  const css = `
  #okcal{--tag-ink:#FFFFFF;--rk:#B8232F;--yh:#7A3FB8;--az:#B4600A;--rk-soft:#FBE7E8;--yh-soft:#F1E8FA;--az-soft:#FBEEDD;
    background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px;display:flex;flex-direction:column;gap:10px}
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]) #okcal{--tag-ink:#1A1215;--rk:#FF8A92;--yh:#C9A2F2;--az:#F2B866;--rk-soft:#3A1C20;--yh-soft:#2B2140;--az-soft:#3A2A14}}
  :root[data-theme="dark"] #okcal{--tag-ink:#1A1215;--rk:#FF8A92;--yh:#C9A2F2;--az:#F2B866;--rk-soft:#3A1C20;--yh-soft:#2B2140;--az-soft:#3A2A14}
  #okcal h2{font-family:var(--f-display);font-size:18px;margin:0}
  #okcal .oc-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:6px 12px}
  #okcal .oc-today{font-size:13.5px;line-height:1.6}
  #okcal .oc-today b{color:var(--accent)}
  #okcal .oc-bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;justify-content:space-between}
  #okcal .oc-malls,#okcal .oc-months{display:flex;gap:6px;flex-wrap:wrap}
  #okcal button{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:999px;padding:4px 11px;cursor:pointer}
  #okcal button[aria-pressed="true"]{border-color:var(--accent);background:var(--accent-soft);color:var(--accent);font-weight:700}
  #okcal button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  #okcal .oc-tag{display:inline-grid;place-items:center;min-width:18px;height:18px;padding:0 4px;border-radius:5px;font-size:11px;font-weight:700;color:var(--tag-ink);line-height:1}
  #okcal .rk{background:var(--rk)} #okcal .yh{background:var(--yh)} #okcal .az{background:var(--az)}
  #okcal .oc-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}
  #okcal .oc-wd{font-size:11px;text-align:center;color:var(--muted);font-weight:700}
  #okcal .oc-wd:first-child{color:var(--rk)} #okcal .oc-wd:last-child{color:var(--accent)}
  #okcal .oc-day{border:1px solid transparent;border-radius:8px;background:var(--bg);min-height:50px;padding:3px 2px;display:flex;flex-direction:column;align-items:center;gap:2px;cursor:pointer;color:var(--ink);font:inherit}
  #okcal .oc-day.out{visibility:hidden}
  #okcal .oc-day.past{opacity:.45}
  #okcal .oc-day.today{border-color:var(--accent);font-weight:700}
  #okcal .oc-day[aria-selected="true"]{background:var(--accent-soft);border-color:var(--accent)}
  #okcal .oc-num{font-size:12.5px;font-variant-numeric:tabular-nums}
  #okcal .oc-dots{display:flex;flex-wrap:wrap;gap:2px;justify-content:center}
  #okcal .oc-dots .oc-tag{min-width:14px;height:14px;font-size:9.5px;padding:0 2px}
  #okcal .oc-dots .guess{opacity:.55}
  #okcal .oc-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
  #okcal .oc-item{display:grid;grid-template-columns:auto 1fr;gap:4px 8px;align-items:start;padding:8px 10px;border-radius:10px}
  #okcal .oc-item.rk{background:var(--rk-soft)} #okcal .oc-item.yh{background:var(--yh-soft)} #okcal .oc-item.az{background:var(--az-soft)}
  #okcal .oc-item .oc-tag{margin-top:2px}
  #okcal .oc-name{font-weight:700;font-size:14px;display:flex;flex-wrap:wrap;gap:4px 8px;align-items:center}
  #okcal .oc-badge{font-size:11px;font-weight:700;border-radius:5px;padding:0 6px;border:1px dashed var(--muted);color:var(--muted)}
  #okcal .oc-badge.baby{border-style:solid;border-color:var(--accent);color:var(--accent)}
  #okcal .oc-text{grid-column:2;font-size:13px;color:var(--ink);line-height:1.55}
  #okcal .oc-text a{color:var(--accent);font-weight:700}
  #okcal .oc-time{font-size:12px;color:var(--muted)}
  #okcal .oc-none{font-size:13px;color:var(--muted)}
  #okcal .oc-note{font-size:11.5px;color:var(--muted);line-height:1.6}
  @media (max-width:400px){#okcal .oc-day{min-height:44px}}
  `;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  // ---------- 日本時間の日付 ----------
  const jstNow = () => new Date(Date.now() + JST);                 // UTCの値で日本時間を表す
  const ymd = d => d.toISOString().slice(0, 10);
  const fromYmd = s => new Date(s + "T00:00:00Z");
  const parseJst = s => new Date(new Date(s.length <= 10 ? s + "T00:00:00+09:00" : s + "+09:00").getTime() + JST);
  const md = s => { const d = fromYmd(s); return `${d.getUTCMonth() + 1}/${d.getUTCDate()}（${WD[d.getUTCDay()]}）`; };
  const hm = d => `${d.getUTCHours()}:${String(d.getUTCMinutes()).padStart(2, "0")}`;

  // ---------- リンク（各サイトのアフィリエイトIDを付ける） ----------
  const amazonTag = root.dataset.amazonTag || "";
  const rtLink = root.dataset.rakutenRt || "";
  function link(mall, url) {
    url = url || MALLS[mall].top;
    if (mall === "楽天") {
      const e = encodeURIComponent(url);
      return `https://hb.afl.rakuten.co.jp/hgc/${RAKUTEN_AFF}/${rtLink}?pc=${e}&m=${e}`;
    }
    if (mall === "Yahoo!") {
      return `https://ck.jp.ap.valuecommerce.com/servlet/referral?sid=${VC.sid}&pid=${VC.pid}&vc_url=${encodeURIComponent(url)}`;
    }
    if (mall === "Amazon" && amazonTag) {
      return url + (url.includes("?") ? "&" : "?") + "tag=" + encodeURIComponent(amazonTag);
    }
    return url;
  }

  // ---------- 1日ごとの「お得」の一覧を作る ----------
  function build(data, first, last) {
    const map = {};
    const add = (day, item) => { if (day >= first && day <= last) (map[day] = map[day] || []).push(item); };
    for (let d = fromYmd(first); ymd(d) <= last; d.setUTCDate(d.getUTCDate() + 1)) {
      const key = ymd(d);
      for (const r of data.rules || []) {
        if (r.days.includes(d.getUTCDate()) && !(r.skip || []).includes(key) &&
            (!r.until || key <= r.until) && (!r.from || key >= r.from)) {
          add(key, { ...r, status: "定例" });
        }
      }
    }
    for (const e of data.events || []) {
      if (e.dates) { e.dates.forEach(k => add(k, e)); continue; }
      const s = parseJst(e.start), en = parseJst(e.end);
      // 「〜1:59まで」のように深夜に終わるものは、その前の日までとして表示する
      const lastDay = new Date(en.getTime() - (en.getUTCHours() < 4 ? 864e5 : 0));
      const time = `${md(ymd(s))}${s.getUTCHours() ? " " + hm(s) : ""}〜${md(ymd(en))} ${hm(en)}`;
      for (let d = fromYmd(ymd(s)); ymd(d) <= ymd(lastDay); d.setUTCDate(d.getUTCDate() + 1)) {
        add(ymd(d), { ...e, time: e.time || time });
      }
    }
    const order = { "楽天": 0, "Yahoo!": 1, "Amazon": 2 };
    Object.values(map).forEach(l => l.sort((a, b) => (b.baby ? 1 : 0) - (a.baby ? 1 : 0) || order[a.mall] - order[b.mall]));
    return map;
  }

  // ---------- 表示 ----------
  const KEY = "okcal-malls";
  let shown;
  try { shown = JSON.parse(localStorage.getItem(KEY)) } catch (e) {}
  if (!Array.isArray(shown) || !shown.length) shown = Object.keys(MALLS);
  let offset = 0, selected = null, DATA = null;

  function itemHtml(it) {
    const m = MALLS[it.mall];
    const badge = it.status === "予想" ? `<span class="oc-badge">予想・未発表</span>` : "";
    const baby = it.baby ? `<span class="oc-badge baby">ベビー用品</span>` : "";
    const time = it.time ? `<div class="oc-time">${it.time}</div>` : "";
    return `<li class="oc-item ${m.cls}"><span class="oc-tag ${m.cls}" aria-label="${it.mall}">${m.mark}</span>
      <div class="oc-name">${it.mall} ${it.name}${badge}${baby}</div>
      <div class="oc-text">${time}${it.text || ""} <a href="${link(it.mall, it.url)}" target="_blank" rel="noopener sponsored">${it.url ? "くわしく" : it.mall + "を開く"} →</a></div></li>`;
  }

  function render() {
    const now = jstNow();
    const today = ymd(now);
    const y = now.getUTCFullYear(), mo = now.getUTCMonth() + offset;
    const first = new Date(Date.UTC(y, mo, 1)), last = new Date(Date.UTC(y, mo + 1, 0));
    const lookFrom = ymd(new Date(Date.UTC(y, now.getUTCMonth(), 1)));
    const lookTo = ymd(new Date(Date.UTC(y, now.getUTCMonth() + 2, 0)));
    const map = build(DATA, lookFrom, lookTo);
    const vis = l => (l || []).filter(it => shown.includes(it.mall));
    if (!selected || selected < ymd(first) || selected > ymd(last)) selected = offset ? ymd(first) : today;

    // 今日と、次のお得な日
    const todays = vis(map[today]);
    let next = null;
    for (let d = new Date(now); ymd(d) <= lookTo; d.setUTCDate(d.getUTCDate() + 1)) {
      const k = ymd(d);
      if (k > today && vis(map[k]).length) { next = k; break; }
    }
    const names = l => l.map(it => `${it.mall}「${it.name}」`).join("、");
    const todayLine = todays.length ? `今日は <b>${names(todays)}</b>` : "今日は対象のお得な日はありません";
    const nextLine = next ? `次は ${md(next)}：${names(vis(map[next]))}` : "";

    const cells = [];
    for (let i = 0; i < first.getUTCDay(); i++) cells.push(`<div class="oc-day out" aria-hidden="true"></div>`);
    for (let d = new Date(first); d <= last; d.setUTCDate(d.getUTCDate() + 1)) {
      const k = ymd(d), l = vis(map[k]);
      const seen = new Set(), dots = [];
      l.forEach(it => {
        if (seen.has(it.mall)) return; seen.add(it.mall);
        dots.push(`<span class="oc-tag ${MALLS[it.mall].cls}${it.status === "予想" ? " guess" : ""}">${MALLS[it.mall].mark}</span>`);
      });
      const label = `${md(k)}${l.length ? "：" + l.map(it => it.mall + it.name).join("、") : ""}`;
      cells.push(`<button type="button" class="oc-day${k === today ? " today" : ""}${k < today ? " past" : ""}" data-day="${k}" aria-selected="${k === selected}" aria-label="${label}">
        <span class="oc-num">${d.getUTCDate()}</span><span class="oc-dots">${dots.join("")}</span></button>`);
    }
    const sel = vis(map[selected]);

    root.innerHTML = `
      <div class="oc-head"><h2>お得な日カレンダー</h2><span class="oc-note">日本時間・${DATA.updated ? DATA.updated.replace(/-/g, "/") + " 更新" : ""}</span></div>
      <div class="oc-today">${todayLine}${nextLine ? "<br>" + nextLine : ""}</div>
      <div class="oc-bar">
        <div class="oc-malls" role="group" aria-label="表示するモール">${Object.keys(MALLS).map(m =>
          `<button type="button" data-mall="${m}" aria-pressed="${shown.includes(m)}"><span class="oc-tag ${MALLS[m].cls}">${MALLS[m].mark}</span> ${m}</button>`).join("")}</div>
        <div class="oc-months" role="group" aria-label="月">
          <button type="button" data-off="0" aria-pressed="${offset === 0}">${now.getUTCMonth() + 1}月</button>
          <button type="button" data-off="1" aria-pressed="${offset === 1}">${new Date(Date.UTC(y, now.getUTCMonth() + 1, 1)).getUTCMonth() + 1}月</button>
        </div>
      </div>
      <div class="oc-grid">${WD.map(w => `<div class="oc-wd">${w}</div>`).join("")}${cells.join("")}</div>
      <div>
        <div class="oc-time" style="margin-bottom:6px">${md(selected)} のお得</div>
        ${sel.length ? `<ul class="oc-list">${sel.map(itemHtml).join("")}</ul>` : `<div class="oc-none">この日は対象のお得な日はありません。</div>`}
      </div>
      <div class="oc-note">ほとんどのポイントアップは、買い物の前にエントリーが必要です。「予想・未発表」はまだ公式に発表されていない例年の日程で、変わることがあります。倍率や条件は各モールのキャンペーンページでご確認ください。</div>`;

    root.querySelectorAll("[data-day]").forEach(b => b.onclick = () => { selected = b.dataset.day; render(); });
    root.querySelectorAll("[data-off]").forEach(b => b.onclick = () => { offset = +b.dataset.off; selected = null; render(); });
    root.querySelectorAll("[data-mall]").forEach(b => b.onclick = () => {
      const m = b.dataset.mall;
      shown = shown.includes(m) ? shown.filter(x => x !== m) : [...shown, m];
      if (!shown.length) shown = [m];
      try { localStorage.setItem(KEY, JSON.stringify(shown)) } catch (e) {}
      render();
    });
  }

  root.innerHTML = `<div class="oc-note">お得な日カレンダーを読み込み中…</div>`;
  fetch(root.dataset.src || "calendar.json", { cache: "no-cache" })
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(d => { DATA = d; render(); })
    .catch(() => { root.hidden = true; });
})();
