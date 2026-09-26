"use strict";
const $ = (id) => document.getElementById(id);
const selSub = $("selSub"), selDir = $("selDir"), selCourse = $("selCourse"),
      selGroup = $("selGroup"), search = $("search"), codes = $("codes"),
      out = $("out"), status = $("status");

let INDEX = null, GROUP = null, BELLS = {}, FILTER = "today", MODE = "group";
let SUB = parseInt(localStorage.getItem("kfu_sub") || "0", 10) || 0;

// GitHub Pages — статика без бэкенда: ходим напрямую в API вуза (CORS открыт).
// Локально (web.py) — через свой /api/* прокси. Принудительно: ?api=direct | ?api=local
const CFUV = "https://cfuv.ru/wp-json/cfu/v1/sched/";
const _apiMode = (location.search.match(/[?&]api=(direct|local)/) || [])[1];
const DIRECT = _apiMode ? _apiMode === "direct" : /\.github\.io$/.test(location.hostname);
const api = p => (DIRECT ? CFUV + p.replace(/^api\//, "") : p);
const DAY_NAMES = {1:"Понедельник",2:"Вторник",3:"Среда",4:"Четверг",5:"Пятница",6:"Суббота",7:"Воскресенье"};

// ---------- тема день/ночь ----------
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem("kfu_theme", t);
  $("btnTheme").textContent = t === "night" ? "☀️" : "🌙";
  startStars(); // ночью — герб-созвездие, днём — цельный герб
}
$("btnTheme").onclick = () => setTheme(document.documentElement.dataset.theme === "night" ? "day" : "night");

// ---------- герб КФУ: ночью — созвездие, днём — цельный ----------
let kfuThemeResizer = null;
let kfuSide = "both";
let kfuStarsRunning = false;
let kfuStarsArr = [], kfuCrestObj = { nodes: [], edges: [] };
let kfuPlaces = [], kfuDayDirty = true;
function startStars() {
  const cv = $("stars"), ctx = cv.getContext("2d");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  {
    const m = (location.hash || "").match(/side=(\w+)/);
    if (m && ["center", "left", "right", "both"].includes(m[1])) kfuSide = m[1];
  }
  if (kfuStarsRunning) { build(); return; } // цикл уже крутится — только перестроить
  kfuStarsRunning = true;

  function quadPts(p0, p1, p2, step) {
    const out = [];
    const len = Math.hypot(p2[0] - p0[0], p2[1] - p0[1]);
    const n = Math.max(2, Math.round(len / step));
    for (let i = 0; i <= n; i++) {
      const t = i / n, mt = 1 - t;
      out.push([
        mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
        mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1],
      ]);
    }
    return out;
  }
  function textDots(str, size) {
    // рисуем "КФУ" в офскрин-битмап и превращаем буквы в точки-звёзды
    const off = document.createElement("canvas");
    const sc = 4;
    off.width = Math.ceil(size * 3.1 * sc);
    off.height = Math.ceil(size * 1.2 * sc);
    const oc = off.getContext("2d");
    oc.fillStyle = "#fff"; oc.textAlign = "center"; oc.textBaseline = "middle";
    oc.font = `900 ${Math.round(size * sc)}px system-ui, -apple-system, "Segoe UI", Arial, sans-serif`;
    oc.fillText(str, off.width / 2, off.height / 2);
    const data = oc.getImageData(0, 0, off.width, off.height).data;
    const stp = Math.max(3, Math.round(size / 16));
    const d = [];
    for (let y = 0; y < off.height; y += stp * sc) {
      for (let x = 0; x < off.width; x += stp * sc) {
        if (data[(y * off.width + x) * 4 + 3] > 128) {
          d.push([x / sc - off.width / sc / 2, y / sc - off.height / sc / 2]);
        }
      }
    }
    return d;
  }
  function build() {
    cv.width = innerWidth; cv.height = innerHeight;
    let seed = 42;
    const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
    kfuStarsArr = Array.from({ length: Math.min(220, innerWidth * innerHeight / 9000) }, () => ({
      x: rnd() * cv.width, y: rnd() * cv.height,
      r: .6 + rnd() * 1.8, p: rnd() * Math.PI * 2, s: .5 + rnd() * 1.5,
    }));
    // --- созвездие-герб КФУ: полумесяц + звезда + крылья + надпись ---
    const W = cv.width, H = cv.height;
    const nodes = [], edges = [];
    // unit() рисует герб КФУ: щит + звезда + книга + грифоны + лента
    function unit(cx, cy, L, flip) {
      const N = (x, y, g) => { nodes.push({ x: cx + x * flip, y: cy + y, g }); return nodes.length - 1; };
      const line = (pts, g) => {
        const idx = pts.map(p => N(p[0], p[1], g));
        for (let i = 0; i < idx.length - 1; i++) edges.push([idx[i], idx[i + 1]]);
      };
      const S = L;
      // группы точек: 1=золото, 3=щит (фиолет), 4=книга и лента (синь), 5=надписи (золото)
      // щит (острый снизу, широкий сверху)
      line([
        [-.43*S,-.15*S],[.43*S,-.15*S],[.43*S,.06*S],[.33*S,.28*S],
        [0,.5*S],[-.33*S,.28*S],[-.43*S,.06*S],[-.43*S,-.15*S]
      ], 3);
      // восьмиконечная звезда (над щитом)
      const st = [];
      for (let i = 0; i < 16; i++) {
        const r = (i % 2 ? 5.5 : 13.5) / 88 * L;
        const a = (Math.PI / 8) * i - Math.PI / 2;
        st.push([Math.cos(a) * r, -1.65 * S + Math.sin(a) * r]);
      }
      line(st.concat([st[0]]), 1);
      // книга (между звездой и щитом)
      const bk = -0.42 * S, bh = 0.14 * S;
      line([[0, bk], [0, bk + bh]], 4); // корешок
      line(quadPts([-.48*S,bk+bh], [-.1*S,bk-.04*S], [0,bk], 7), 4); // левая страница
      line(quadPts([.48*S,bk+bh], [.1*S,bk-.04*S], [0,bk], 7), 4);  // правая страница
      // перо (над звездой)
      line([[0, -1.65*S], [0, -1.85*S]], 1);
      N(0, -1.85*S, 1);
      // грифоны (по бокам щита)
      for (const fw of [-1, 1]) {
        const wx = fw * 0.48 * S, wy = -0.5 * S;
        // крылья: 3 дуги вверх-наружу
        line(quadPts([wx,wy], [fw*1.5*S,-S], [fw*1.4*S,-.92*S], 7), 1);
        line(quadPts([wx,wy], [fw*1.05*S,-.5*S], [fw*.85*S,-.4*S], 7), 1);
        line(quadPts([wx,wy], [fw*.6*S,-.38*S], [fw*.42*S,-.35*S], 7), 1);
        // голова + клюв (над крыльями, указывает на щит)
        line(quadPts([fw*.38*S,-.68*S], [fw*.22*S,-.66*S], [fw*.12*S,-.63*S], 7), 1);
        line(quadPts([fw*.12*S,-.63*S], [fw*.22*S,-.58*S], [fw*.38*S,-.5*S], 7), 1);
        N(fw*.38*S,-.6*S, 1);
        // тело (вдоль щита) + хвост (вниз-наружу)
        line(quadPts([fw*.38*S,-.5*S], [fw*.42*S,-.05*S], [fw*.42*S,.35*S], 7), 1);
        line(quadPts([fw*.42*S,.35*S], [fw*.8*S,.38*S], [fw*.9*S,.5*S], 7), 1);
      }
      // лента (внизу)
      line(quadPts([-1.05*S,.58*S], [-.35*S,.52*S], [0,.55*S], 7), 4);
      line(quadPts([0,.55*S], [.35*S,.52*S], [1.05*S,.58*S], 7), 4);
      // надпись КФУ (на щите)
      for (const [dx, dy] of textDots("КФУ", Math.round(.5*S))) N(dx, dy + .05*S, 5);
      // 1918 (внизу щита)
      for (const [dx, dy] of textDots("1918", Math.round(.2*S))) N(dx, dy + .4*S, 5);
    }
    const gutter = (W - Math.min(W, 880)) / 2;
    const S0 = Math.min(W, H * 1.15) * (W < 520 ? .5 : .3) * .32;
    kfuPlaces = [];
    const place = (cx, cy, L, flip) => { kfuPlaces.push({ cx, cy, L, flip }); unit(cx, cy, L, flip); };
    if (kfuSide === "center") {
      place(W / 2, H * .34, S0, 1);
    } else if (kfuSide === "left" || kfuSide === "right") {
      const ox = Math.max(W * .14, gutter * .55);
      const Ls = Math.max(40, Math.min(120, gutter * .5, H * .095));
      place(kfuSide === "left" ? ox : W - ox, H * .42, Ls, kfuSide === "left" ? 1 : -1);
    } else { // both
      if (W >= 1180) {
        const ox = Math.max(W * .13, gutter * .5);
        const Ls = Math.max(44, Math.min(120, gutter * .45, H * .095));
        place(ox, H * .42, Ls, 1);
        place(W - ox, H * .42, Ls, -1);
      } else {
        place(W / 2, H * .34, S0, 1);
      }
    }
    kfuCrestObj = { nodes, edges };
    kfuDayDirty = true;
    console.debug("[kfu] crest:", nodes.length, "nodes,", edges.length, "edges,", kfuSide);
  }
  build();
  if (!kfuThemeResizer) { kfuThemeResizer = build; addEventListener("resize", kfuThemeResizer); }
  // палитра точек ночью (звёздное золото/белый)
  const pal = g => (g === 5 ? "#ffffff" : "#ffe9c0");
  // цельный герб для белой темы: полные цвета, без мерцания и точек
  function drawSolid(cx, cy, S, flip) {
    ctx.save();
    ctx.translate(cx, cy); ctx.scale(flip, 1);
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    // лента
    ctx.strokeStyle = "#1f5fa8"; ctx.lineWidth = Math.max(4, S * .09);
    ctx.beginPath(); ctx.moveTo(-1.05*S, .58*S);
    ctx.quadraticCurveTo(-.35*S, .52*S, 0, .55*S);
    ctx.quadraticCurveTo(.35*S, .52*S, 1.05*S, .58*S); ctx.stroke();
    ctx.fillStyle = "#e8cf8f"; ctx.font = `700 ${Math.max(7, S * .07)}px sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    // надписи не зеркалим: counter-scale возвращает нормальное начертание
    const text = (s, x, y) => { ctx.save(); ctx.scale(flip, 1); ctx.fillText(s, x, y); ctx.restore(); };
    text("NOSCE TE IPSUM", 0, .55*S);
    // крылья и тела грифонов
    ctx.strokeStyle = "#c5a253"; ctx.lineWidth = Math.max(2, S * .035);
    for (const fw of [-1, 1]) {
      const wx = fw * .48 * S, wy = -.5 * S;
      const feather = (x1, y1, x2, y2) => {
        ctx.beginPath(); ctx.moveTo(wx, wy); ctx.quadraticCurveTo(x1, y1, x2, y2); ctx.stroke();
      };
      feather(fw*1.5*S, -S, fw*1.4*S, -.92*S);
      feather(fw*1.05*S, -.5*S, fw*.85*S, -.4*S);
      feather(fw*.6*S, -.38*S, fw*.42*S, -.35*S);
      // голова с клювом
      ctx.beginPath(); ctx.moveTo(fw*.38*S, -.68*S);
      ctx.quadraticCurveTo(fw*.22*S, -.66*S, fw*.12*S, -.63*S);
      ctx.quadraticCurveTo(fw*.22*S, -.58*S, fw*.38*S, -.5*S); ctx.stroke();
      // тело и хвост
      ctx.beginPath(); ctx.moveTo(fw*.38*S, -.5*S);
      ctx.quadraticCurveTo(fw*.42*S, -.05*S, fw*.42*S, .35*S);
      ctx.quadraticCurveTo(fw*.8*S, .38*S, fw*.9*S, .5*S); ctx.stroke();
    }
    // щит
    ctx.fillStyle = "#5e2b97"; ctx.strokeStyle = "#c5a253"; ctx.lineWidth = Math.max(2, S * .03);
    ctx.beginPath();
    ctx.moveTo(-.43*S, -.15*S); ctx.lineTo(.43*S, -.15*S); ctx.lineTo(.43*S, .06*S);
    ctx.quadraticCurveTo(.43*S, .2*S, .33*S, .28*S);
    ctx.quadraticCurveTo(.2*S, .4*S, 0, .5*S);
    ctx.quadraticCurveTo(-.2*S, .4*S, -.33*S, .28*S);
    ctx.quadraticCurveTo(-.43*S, .2*S, -.43*S, .06*S);
    ctx.closePath(); ctx.fill(); ctx.stroke();
    // книга
    const bk = -.42 * S, bh = .14 * S;
    ctx.fillStyle = "#ffffff"; ctx.strokeStyle = "#c5a253"; ctx.lineWidth = Math.max(1.5, S * .018);
    ctx.beginPath();
    ctx.moveTo(-.48*S, bk+bh); ctx.quadraticCurveTo(-.1*S, bk-.04*S, 0, bk);
    ctx.quadraticCurveTo(.1*S, bk-.04*S, .48*S, bk+bh);
    ctx.lineTo(.48*S, bk+bh+S*.05); ctx.quadraticCurveTo(.1*S, bk-.04*S+S*.05, 0, bk+S*.05);
    ctx.quadraticCurveTo(-.1*S, bk-.04*S+S*.05, -.48*S, bk+bh+S*.05);
    ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.strokeStyle = "#1f5fa8"; ctx.lineWidth = Math.max(1.5, S * .02);
    ctx.beginPath(); ctx.moveTo(0, bk); ctx.lineTo(0, bk + bh + S*.05); ctx.stroke();
    // звезда
    ctx.fillStyle = "#c5a253";
    ctx.beginPath();
    for (let i = 0; i < 16; i++) {
      const r = (i % 2 ? 5.5 : 13.5) / 88 * S;
      const a = (Math.PI / 8) * i - Math.PI / 2;
      const x = Math.cos(a) * r, y = -1.65 * S + Math.sin(a) * r;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath(); ctx.fill();
    // надписи
    ctx.fillStyle = "#e8cf8f"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = `800 ${S * .5}px sans-serif`;
    text("КФУ", 0, .05*S);
    ctx.font = `700 ${S * .16}px sans-serif`;
    text("1918", 0, .38*S);
    ctx.restore();
  }
  (function frame() {
    requestAnimationFrame(frame);
    const night = document.documentElement.dataset.theme === "night";
    if (!night) {
      if (!kfuDayDirty) return; // днём статика: рисуем один раз, без эффектов
      kfuDayDirty = false;
      ctx.clearRect(0, 0, cv.width, cv.height);
      ctx.globalAlpha = 1;
      for (const p of kfuPlaces) drawSolid(p.cx, p.cy, p.L, p.flip);
      return;
    }
    const t = reduced ? 0 : performance.now() / 1000;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = "#fff";
    for (const s of kfuStarsArr) {
      ctx.globalAlpha = reduced ? .8 : .45 + .35 * Math.sin(t * s.s + s.p);
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, 7); ctx.fill();
    }
    ctx.strokeStyle = "rgba(232,207,143,.28)"; ctx.lineWidth = 1;
    ctx.beginPath();
    for (const [i, j] of kfuCrestObj.edges) {
      ctx.moveTo(kfuCrestObj.nodes[i].x, kfuCrestObj.nodes[i].y);
      ctx.lineTo(kfuCrestObj.nodes[j].x, kfuCrestObj.nodes[j].y);
    }
    ctx.stroke();
    for (const nd of kfuCrestObj.nodes) {
      const a = reduced ? .85 : .5 + .4 * Math.sin(t * 1.4 + nd.g * 12 + nd.x * .04);
      ctx.globalAlpha = a;
      ctx.fillStyle = pal(nd.g);
      ctx.beginPath(); ctx.arc(nd.x, nd.y, nd.g === 5 ? 1.1 : 1.6, 0, 7); ctx.fill();
    }
    ctx.globalAlpha = 1;
  })();
}

// ---------- вкладки группа/преподаватель ----------
$("tabGroup").onclick = () => setMode("group");
$("tabTeacher").onclick = () => setMode("teacher");
function setMode(m) {
  MODE = m;
  $("tabGroup").classList.toggle("on", m === "group");
  $("tabTeacher").classList.toggle("on", m === "teacher");
  $("paneGroup").hidden = m !== "group";
  $("paneTeacher").hidden = m !== "teacher";
  out.innerHTML = "";
  if (m === "group" && GROUP) render();
}

function fill(sel, items, placeholder) {
  sel.innerHTML = "";
  const o = document.createElement("option");
  o.value = ""; o.textContent = placeholder || "—";
  sel.appendChild(o);
  for (const v of items) {
    const e = document.createElement("option");
    e.value = v; e.textContent = v;
    sel.appendChild(e);
  }
  sel.disabled = items.length === 0;
}

async function loadIndex() {
  status.textContent = "Загружаю список групп…";
  const r = await fetch(api("api/index"));
  if (!r.ok) throw new Error("API недоступно: " + r.status);
  INDEX = await r.json();
  BELLS = {};
  for (const b of INDEX.bells || []) BELLS[b["пара"]] = [b["начало"], b["конец"]];
  const subs = Object.keys(INDEX.tree || {}).sort();
  fill(selSub, subs, "Выбери…");
  const all = Object.keys(INDEX.groups || {}).sort();
  codes.innerHTML = all.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  status.textContent = `Групп: ${all.length} · подразделений: ${subs.length}`;
}

function boot() {
  // глубокие ссылки: #g=ПИ-б-о-241, #find=teacher&q=Парменов, #theme=night
  const h = location.hash || "";
  if (/theme=night/.test(h)) setTheme("night");
  else if (/theme=day/.test(h)) setTheme("day");
  let m = h.match(/[#&]g=([^&]+)/);
  if (m) {
    try {
      const c = decodeURIComponent(m[1]);
      if (INDEX.groups[c]) { search.value = c; loadGroup(c); return; }
    } catch (e) { /* ignore */ }
  }
  m = h.match(/[#&]find=([^&]+)&q=([^&]+)/);
  if (m) {
    try {
      const by = decodeURIComponent(m[1]), q = decodeURIComponent(m[2]);
      if (by === "teacher" && q) { setMode("teacher"); $("tSearch").value = q; findTeacher(q); return; }
    } catch (e) { /* ignore */ }
  }
  const last = localStorage.getItem("kfu_group");
  if (last && INDEX.groups[last]) { search.value = last; loadGroup(last); }
}

loadIndex().then(boot).catch(e => { status.textContent = "Ошибка: " + e.message; });

selSub.onchange = () => {
  const dirs = Object.keys((INDEX.tree[selSub.value] || {})).sort();
  fill(selDir, dirs, "Выбери…");
  fill(selCourse, [], "—"); fill(selGroup, [], "—");
};
selDir.onchange = () => {
  const d = ((INDEX.tree[selSub.value] || {})[selDir.value] || {});
  const num = (c) => { const n = parseInt(c, 10); return isNaN(n) ? 99 : n; };
  fill(selCourse, Object.keys(d).sort((a,b) => num(a)-num(b)), "Выбери…");
  fill(selGroup, [], "—");
};
selCourse.onchange = () => {
  const g = (((INDEX.tree[selSub.value] || {})[selDir.value] || {})[selCourse.value] || []);
  fill(selGroup, g, "Выбери…");
};
selGroup.onchange = () => { if (selGroup.value) { search.value = selGroup.value; loadGroup(selGroup.value); } };

async function loadGroup(code) {
  code = (code || "").trim();
  if (!code) return;
  status.textContent = "Загружаю " + code + "…";
  out.innerHTML = "";
  try {
    const r = await fetch(api("api/group?code=" + encodeURIComponent(code)));
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
    GROUP = data;
    localStorage.setItem("kfu_group", data["код"] || code);
    // подсветить селекты по известной группе
    const info = INDEX.groups[data["код"]];
    if (info) {
      if ([...selSub.options].some(o => o.value === info.sub)) {
        selSub.value = info.sub; selSub.onchange();
        if ([...selDir.options].some(o => o.value === info.dir)) {
          selDir.value = info.dir; selDir.onchange();
          if ([...selCourse.options].some(o => o.value === String(info.course))) {
            selCourse.value = String(info.course); selCourse.onchange();
            if ([...selGroup.options].some(o => o.value === data["код"])) selGroup.value = data["код"];
          }
        }
      }
    }
    status.textContent = `${data["код"]} · занятий в шаблоне: ${(data["занятия"]||[]).length}`;
    render();
  } catch (e) {
    status.textContent = "Ошибка: " + e.message;
  }
}

document.querySelectorAll(".chip[data-f]").forEach(b => b.onclick = () => {
  document.querySelectorAll(".chip[data-f]").forEach(x => x.classList.remove("on"));
  b.classList.add("on");
  FILTER = b.dataset.f;
  render();
});
document.querySelectorAll(".chip.sub").forEach(b => b.onclick = () => {
  document.querySelectorAll(".chip.sub").forEach(x => x.classList.remove("on"));
  b.classList.add("on");
  SUB = parseInt(b.dataset.s, 10) || 0;
  localStorage.setItem("kfu_sub", String(SUB));
  render();
});
document.querySelectorAll(".chip.sub").forEach(b =>
  b.classList.toggle("on", (parseInt(b.dataset.s, 10) || 0) === SUB));
$("btnGo").onclick = () => loadGroup(search.value);
function icsEscape(s) {
  return String(s == null ? "" : s).replace(/\\/g, "\\\\").replace(/,/g, "\\,")
    .replace(/;/g, "\\;").replace(/\r/g, " ").replace(/\n/g, " ");
}
function buildIcs(code, lessons, sub) {
  // порт parser.to_ics: занятия × даты недель → ICS (для GitHub Pages без бэкенда)
  let rows = lessons || [];
  if (sub === 1 || sub === 2) rows = rows.filter(r => (r["подгруппа"] || 0) === 0 || r["подгруппа"] === sub);
  const weeks = (INDEX && INDEX.weeks) || {};
  const ch = weeks.ch || [], nch = weeks.nch || [];
  const stamp = new Date().toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
  const out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//KFU-schedule-bot//RU", "CALSCALE:GREGORIAN"];
  const addDays = (s, n) => { const d = new Date(s + "T00:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
  const dt = (day, hm) => day.replace(/-/g, "") + "T" + String(hm).replace(":", "") + "00";
  for (const z of rows) {
    if (String(z["предмет"] || "").toLowerCase().includes("электив")) continue;
    const bell = BELLS[z["пара"]];
    if (!bell || !bell[0] || !bell[1]) continue;
    let days;
    if (z["дата"]) days = [z["дата"]];
    else {
      const mons = [];
      if (z["чётность"] === "чёт" || z["чётность"] === "обе") mons.push(...ch);
      if (z["чётность"] === "нечёт" || z["чётность"] === "обе") mons.push(...nch);
      days = [...new Set(mons.map(m => addDays(m, (z["день"] || 1) - 1)))].sort();
    }
    let subj = String(z["предмет"] || "").trim();
    if (z["подгруппа"] === 1 || z["подгруппа"] === 2) subj += ` (п/гр ${z["подгруппа"]})`;
    const room = [z["аудитория"], z["корпус"]].filter(Boolean).join(", ");
    const desc = [z["вид"] || "", code, (z["преподаватели"] || []).join(", ")].filter(Boolean).join(" · ");
    for (const day of days) {
      out.push("BEGIN:VEVENT",
        `UID:${icsEscape(code)}-${z["день"]}-${z["пара"]}-${day}@kfu-schedule`,
        `DTSTAMP:${stamp}`, `DTSTART:${dt(day, bell[0])}`, `DTEND:${dt(day, bell[1])}`,
        `SUMMARY:${icsEscape(subj)}`, `LOCATION:${icsEscape(room)}`, `DESCRIPTION:${icsEscape(desc)}`,
        "END:VEVENT");
    }
  }
  out.push("END:VCALENDAR");
  return out.join("\r\n");
}
$("btnIcs").onclick = () => {
  if (!GROUP) { status.textContent = "Сначала выбери группу."; return; }
  if (DIRECT) {
    // статика: собираем ICS прямо в браузере и скачиваем
    const blob = new Blob([buildIcs(GROUP["код"], GROUP["занятия"], SUB)], { type: "text/calendar;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = GROUP["код"] + ".ics";
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    status.textContent = "Календарь скачан 📅";
  } else {
    location.href = "api/ics?code=" + encodeURIComponent(GROUP["код"]) + "&sub=" + SUB;
  }
};
search.addEventListener("keydown", e => { if (e.key === "Enter") loadGroup(search.value); });

function parityOf(date) {
  // чётность реальной недели из INDEX.weeks (понедельники).
  // Дату берём по ЛОКАЛЬНОМУ календарю: toISOString() — это UTC и врёт ±3 часа.
  const mon = new Date(date); const d = (mon.getDay()+6)%7;
  mon.setDate(mon.getDate()-d);
  const p2 = n => String(n).padStart(2, "0");
  const iso = `${mon.getFullYear()}-${p2(mon.getMonth()+1)}-${p2(mon.getDate())}`;
  if ((INDEX.weeks.ch||[]).includes(iso)) return "чёт";
  if ((INDEX.weeks.nch||[]).includes(iso)) return "нечёт";
  return INDEX.now && INDEX.now.parity ? INDEX.now.parity : "обе";
}

function lessonHtml(r, showGroup) {
  const t = BELLS[r["пара"]] ? `${BELLS[r["пара"]][0]}–${BELLS[r["пара"]][1]}` : "";
  const par = r["чётность"];
  let tag = "";
  if (par === "чёт") tag = `<span class="tag chet">чёт</span>`;
  else if (par === "нечёт") tag = `<span class="tag nechet">нечет</span>`;
  let sub = r["подгруппа"] === 1 || r["подгруппа"] === 2 ? ` <span class="tag">п/г ${r["подгруппа"]}</span>` : "";
  const who = [ ...(r["преподаватели"]||[]), [r["аудитория"], r["корпус"]].filter(Boolean).join(", ") ]
    .filter(Boolean).join(" · ");
  const note = [r["примечание"], r["онлайн"] ? ("онлайн: " + r["онлайн"]) : ""].filter(Boolean).join(" · ");
  const grp = (showGroup && r["группа"]) ? `<div><span class="grp">👥 ${esc(r["группа"])}</span></div>` : "";
  return `<div class="les"><div class="tm"><b>${r["пара"]}</b>${t}</div>
    <div><div class="subj">${esc(r["предмет"])}${r["вид"] ? " <span class='meta'>(" + esc(r["вид"]) + ")</span>" : ""}${tag}${sub}</div>
    <div class="meta">${esc(who)}${note ? " — " + esc(note) : ""}</div>${grp}</div></div>`;
}
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

function render() {
  if (!GROUP) return;
  if (FILTER === "now") { renderNow(); return; }
  let rows = GROUP["занятия"] || [];
  if (SUB === 1 || SUB === 2) rows = rows.filter(r => (r["подгруппа"] || 0) === 0 || r["подгруппа"] === SUB);
  const now = new Date();
  const today = (now.getDay()+6)%7+1;
  let days = [];
  if (FILTER === "today") days = [today];
  else if (FILTER === "tomorrow") days = [today === 7 ? 1 : today+1];
  else days = [1,2,3,4,5,6];
  let parFilter = null;
  if (FILTER === "even") parFilter = "чёт";
  else if (FILTER === "odd") parFilter = "нечёт";
  else if (FILTER === "today" || FILTER === "tomorrow" || FILTER === "week") parFilter = parityOf(now);
  const isWeekView = (FILTER === "week" || FILTER === "even" || FILTER === "odd");
  const subNote = (SUB === 1 || SUB === 2) ? ` · подгруппа ${SUB}` : "";

  out.innerHTML = days.map(d => {
    let list = rows.filter(r => r["день"] === d);
    // в режиме недели показываем всё с тегами; в дневных — фильтруем по чётности
    if (!isWeekView && parFilter && parFilter !== "обе")
      list = list.filter(r => r["чётность"] === "обе" || r["чётность"] === parFilter);
    list.sort((a,b) => (a["пара"]-b["пара"]) || ((a["подгруппа"]||0)-(b["подгруппа"]||0)));
    const head = DAY_NAMES[d] + (isWeekView ? "" : ` · ${parFilter === "обе" ? "обе недели" : parFilter + " неделя"}`) + subNote;
    if (!list.length) return isWeekView ? "" : `<div class="day"><h2>${head}</h2><div class="empty">Пар нет 🎉</div></div>`;
    return `<div class="day"><h2>${head}</h2>${list.map(x => lessonHtml(x, false)).join("")}</div>`;
  }).join("") + sessHtml() || `<div class="empty">На эту неделю пар нет.</div>`;
}

function renderNow() {
  const now = new Date();
  const day = (now.getDay()+6)%7+1;
  const mins = now.getHours()*60 + now.getMinutes();
  const par = parityOf(now);
  const tomin = hm => { const p = String(hm).split(":"); return (+p[0])*60 + (+p[1]); };
  let rows = (GROUP["занятия"] || []).filter(r => r["день"] === day);
  if (par !== "обе") rows = rows.filter(r => r["чётность"] === "обе" || r["чётность"] === par);
  if (SUB === 1 || SUB === 2) rows = rows.filter(r => (r["подгруппа"] || 0) === 0 || r["подгруппа"] === SUB);
  rows = rows.filter(r => BELLS[r["пара"]] && BELLS[r["пара"]][0] && BELLS[r["пара"]][1]);
  rows.sort((a, b) => tomin(BELLS[a["пара"]][0]) - tomin(BELLS[b["пара"]][0]));
  let cur = null, nxt = null;
  for (const r of rows) {
    const s = tomin(BELLS[r["пара"]][0]), e = tomin(BELLS[r["пара"]][1]);
    if (s <= mins && mins <= e) cur = {r, left: e - mins};
    else if (s > mins && !nxt) nxt = {r, soon: s - mins};
  }
  const subNote = (SUB === 1 || SUB === 2) ? ` · подгруппа ${SUB}` : "";
  let h = `<div class="day"><h2>🟢 Сейчас · ${DAY_NAMES[day]} · ${esc(GROUP["код"])}${subNote}</h2>`;
  if (cur) h += `<div class="meta" style="padding:10px 14px 0">Идёт ${cur.r["пара"]}-я пара, до конца ~${cur.left} мин</div>` + lessonHtml(cur.r, false);
  else h += `<div class="empty">Сейчас пар нет 🎉</div>`;
  if (nxt) h += `<div class="meta" style="padding:10px 14px 0">Следующая через ~${nxt.soon} мин</div>` + lessonHtml(nxt.r, false);
  else if (!cur) h += `<div class="empty">На сегодня пар больше нет.</div>`;
  out.innerHTML = h + `</div>`;
}

function sessRowHtml(z) {  const bits = [];
  if (z["дата"]) bits.push("📅 " + esc(z["дата"]));
  if (z["время"]) bits.push(esc(z["время"]));
  let subj = esc(z["предмет"] || z["дисциплина"] || "—");
  if (z["вид"]) subj += ` <span class='meta'>(${esc(z["вид"])})</span>`;
  const who = [...(z["преподаватели"] || []), z["преподаватель"] ? z["преподаватель"] : "",
    [z["аудитория"], z["место"] || z["корпус"]].filter(Boolean).join(", ")]
    .filter(Boolean).join(" · ");
  const note = z["примечание"] ? " — " + esc(z["примечание"]) : "";
  return `<div class="les"><div class="tm"><b>📝</b></div><div>` +
    (bits.length ? `<div class="subj">${bits.join(" ")}</div>` : "") +
    `<div class="subj">${subj}</div>` +
    (who || note ? `<div class="meta">${esc(who)}${note}</div>` : "") + `</div></div>`;
}

function sessHtml() {
  if (!GROUP) return "";
  let h = "";
  const sess = GROUP["sess"] || [];
  if (sess.length)
    h += `<div class="day"><h2>📝 Сессия</h2>${sess.map(sessRowHtml).join("")}</div>`;
  const gek = GROUP["gek"] || [];
  if (gek.length)
    h += `<div class="day"><h2>🎓 ГИА · защита ВКР</h2>` + gek.map(z => {
      const head = esc(z["направление"] || z["код"] || "Защита ВКР");
      const info = [z["дата"] ? "📅 " + esc(z["дата"]) + " " + esc(z["время"] || "") : "",
        esc([z["аудитория"], z["место"]].filter(Boolean).join(" "))].filter(Boolean).join(" · ");
      return `<div class="les"><div class="tm"><b>🎓</b></div><div><div class="subj">${head}</div>` +
        (info ? `<div class="meta">${info}</div>` : "") +
        `<div class="meta">председатель: ${esc(z["председатель"] || "—")}</div></div></div>`;
    }).join("") + `</div>`;
  return h;
}

setTheme(localStorage.getItem("kfu_theme") === "night" ? "night" : "day");

// ---------- поиск преподавателя ----------
$("btnTeacher").onclick = () => findTeacher($("tSearch").value);
$("tSearch").addEventListener("keydown", e => { if (e.key === "Enter") findTeacher(e.target.value); });

async function findTeacher(q) {
  q = (q || "").trim();
  if (q.length < 2) { status.textContent = "Введи минимум 2 буквы фамилии."; return; }
  status.textContent = "Ищу " + q + "…";
  out.innerHTML = "";
  try {
    const r = await fetch(api("api/find?by=teacher&q=" + encodeURIComponent(q)));
    const rows = await r.json();
    if (!r.ok) throw new Error(rows.error || ("HTTP " + r.status));
    if (!rows.length) { out.innerHTML = `<div class="empty">Преподавателя «${esc(q)}» не нашёл 😕</div>`; status.textContent = ""; return; }
    const names = [...new Set(rows.map(x => (x["преподаватели"] || []).join(", ")).filter(Boolean))];
    status.textContent = `Найдено пар: ${rows.length}` + (names.length ? ` · ${names.slice(0, 3).join("; ")}` : "");
    const par = parityOf(new Date());
    const byDay = {};
    for (const x of rows) {
      if (par !== "обе" && x["чётность"] !== "обе" && x["чётность"] !== par) continue;
      (byDay[x["день"]] = byDay[x["день"]] || []).push(x);
    }
    out.innerHTML = Object.keys(byDay).sort((a, b) => a - b).map(d => {
      const list = byDay[d].sort((a, b) => a["пара"] - b["пара"]);
      return `<div class="day"><h2>${DAY_NAMES[d]} · ${par === "обе" ? "обе недели" : par + " неделя"}</h2>` +
        list.map(x => lessonHtml(x, true)).join("") + `</div>`;
    }).join("") || `<div class="empty">На текущей неделе пар нет.</div>`;
  } catch (e) {
    status.textContent = "Ошибка: " + e.message;
  }
}
