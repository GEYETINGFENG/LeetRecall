import {
  getCards, saveCards, getSettings, saveSettings, upsertCard, rateCard, deleteCard, blankCard,
  buildQueue, isDue, problemUrl, todayCounts, PATTERN_PRESETS, DEFAULT_SETTINGS,
} from "../src/store.js";
import { preview, retrievability, newSchedule, formatIvl, startOfDay, DAY } from "../src/fsrs.js";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const view = $("#view");
const titleOf = (c) => `${c.id ? c.id + ". " : ""}${c.title || c.slug}`;
const RATINGS = [
  { g: 1, label: "没想起来", cls: "r1" },
  { g: 2, label: "想了很久", cls: "r2" },
  { g: 3, label: "想起来了", cls: "r3" },
  { g: 4, label: "秒想到", cls: "r4" },
];

let keyHandler = null;
function setKeys(fn) {
  if (keyHandler) document.removeEventListener("keydown", keyHandler);
  keyHandler = fn;
  if (fn) document.addEventListener("keydown", fn);
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2200);
}

function allPatterns(cards) {
  const s = new Set();
  for (const c of Object.values(cards)) (c.patterns || []).forEach((p) => s.add(p));
  return [...s].sort((a, b) => a.localeCompare(b, "zh"));
}

// ---------------- router ----------------
const routes = { welcome, review, library, stats, settings: settingsView };
async function route() {
  const v = (location.hash || "#review").slice(1).split("?")[0];
  setKeys(null);
  $$("nav a").forEach((a) => a.classList.toggle("on", a.dataset.v === v));
  await (routes[v] || review)();
}
window.addEventListener("hashchange", route);
route();

// ---------------- welcome ----------------
async function welcome() {
  view.innerHTML = `
    <h2>装好了 👋</h2>
    <div class="panel">
      <ol class="steps">
        <li>在 leetcode.com 或 leetcode.cn 正常刷题。提交 AC 后（点按钮或 Ctrl/⌘+Enter 都行），右下角会弹出<b>思路卡</b>面板。</li>
        <li>写<b>一句话思路</b>、选套路、记复杂度和易错点，然后按做题时的感觉打分。</li>
        <li>插件按 FSRS 算法排好复习日期，工具栏图标上的数字就是今天要复习的卡片数。</li>
        <li>复习时<b>翻卡</b>：先看题目自己回想思路，再翻面核对。一张卡几秒钟，真想不起来再去重做原题。</li>
      </ol>
      <p class="muted">以前刷过很多题？可以在 <a href="#settings">设置</a> 里一键导入 AC 记录。导入的题会作为新卡，每天放出一部分。</p>
      <div class="row"><a class="btn primary" href="https://leetcode.com/problemset/" target="_blank">去 LeetCode 刷题</a><a class="btn" href="#settings">导入以前的题</a></div>
    </div>`;
}

// ---------------- review ----------------
async function review() {
  const [cards, settings] = await Promise.all([getCards(), getSettings()]);
  const pats = allPatterns(cards);
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const scope = params.get("scope") || "due";
  const pattern = params.get("p") || "";
  const queue = buildQueue(cards, settings, { scope, pattern });
  const total = Object.keys(cards).length;

  if (!total) return welcome();

  view.innerHTML = `
    <div class="rv-bar">
      <div class="row">
        <select id="scope">
          <option value="due" ${scope === "due" ? "selected" : ""}>今日任务</option>
          <option value="pattern" ${scope === "pattern" ? "selected" : ""}>按套路专项</option>
          <option value="all" ${scope === "all" ? "selected" : ""}>全部随机抽查</option>
        </select>
        <select id="pat" ${scope === "due" ? "disabled" : ""}>
          <option value="">全部套路</option>
          ${pats.map((p) => `<option ${p === pattern ? "selected" : ""}>${esc(p)}</option>`).join("")}
        </select>
      </div>
      <div class="muted" id="cnt"></div>
    </div>
    <div class="progress"><i id="pg" style="width:0"></i></div>
    <div id="stage"></div>`;

  const go = () => {
    const s = $("#scope").value;
    const p = s === "due" ? "" : $("#pat").value;
    location.hash = `#review?scope=${s}${p ? "&p=" + encodeURIComponent(p) : ""}`;
  };
  $("#scope").onchange = go;
  $("#pat").onchange = go;

  const tally = { 1: 0, 2: 0, 3: 0, 4: 0 };
  let i = 0;
  const show = () => (i >= queue.length ? finished() : front());

  function header() {
    $("#cnt").textContent = `${Math.min(i + 1, queue.length)} / ${queue.length}`;
    $("#pg").style.width = `${(i / Math.max(1, queue.length)) * 100}%`;
  }

  function cardHead(c, showTags) {
    return `
      <div class="row" style="justify-content:space-between">
        <span class="diff ${esc(c.difficulty)}">${esc(c.difficulty || "")}</span>
        <span class="muted" style="font-size:12px">${c.sched.state === "new" ? "新卡" : `上次复习 ${Math.round((Date.now() - c.sched.last) / DAY)} 天前 · 记忆度 ${Math.round((retrievability(c.sched) ?? 0) * 100)}%`}</span>
      </div>
      <div class="q">${esc(titleOf(c))}</div>
      ${c.titleCn && c.titleCn !== c.title ? `<div class="qcn">${esc(c.titleCn)}</div>` : ""}
      ${showTags ? `<div>${(c.patterns || []).map((p) => `<span class="chip">${esc(p)}</span>`).join("")}${(c.tags || []).map((t) => `<span class="chip tag">${esc(t)}</span>`).join("")}</div>` : ""}`;
  }

  function front() {
    header();
    const c = queue[i];
    $("#stage").innerHTML = `
      <div class="flash">
        ${cardHead(c, !settings.hideTagsOnFront)}
        <div class="prompt">先别翻，在脑子里过一遍：<b>用什么套路？关键的那一步是什么？复杂度多少？</b></div>
        <div class="row">
          <button class="btn primary" id="flip">想好了，翻面 <kbd>空格</kbd></button>
          <a class="btn" href="${problemUrl(c, settings.site)}" target="_blank">打开原题 ↗</a>
        </div>
      </div>`;
    $("#flip").onclick = back;
    setKeys((e) => {
      if (e.target.matches("input, textarea, select")) return;
      if (e.code === "Space" || e.key === "Enter") (e.preventDefault(), back());
    });
  }

  function back() {
    const c = queue[i];
    const pv = preview(c.sched, Date.now(), settings);
    $("#stage").innerHTML = `
      <div class="flash">
        ${cardHead(c, true)}
        ${
          c.idea
            ? `<div class="sec"><div class="lb">思路</div><div class="idea">${esc(c.idea)}</div></div>`
            : `<div class="sec"><div class="lb">思路（还没写）</div>
                 <textarea id="newidea" rows="3" placeholder="趁现在写一句：用什么套路、关键一步是什么"></textarea>
                 <div class="row" style="margin-top:6px"><button class="btn sm" id="saveidea">保存思路</button></div></div>`
        }
        ${c.complexity ? `<div class="sec"><div class="lb">复杂度</div><div class="txt">${esc(c.complexity)}</div></div>` : ""}
        ${c.pitfalls ? `<div class="sec"><div class="lb">易错点</div><div class="txt">${esc(c.pitfalls)}</div></div>` : ""}
        ${c.code ? `<details class="sec"><summary class="muted">看代码（${esc(c.lang || "")}）</summary><pre>${esc(c.code)}</pre></details>` : ""}
        <div class="rates">
          ${RATINGS.map((r) => `<button class="rate ${r.cls}" data-g="${r.g}"><b>${r.label} <kbd>${r.g}</kbd></b><span>${formatIvl(pv[r.g].ivl)}后再见</span></button>`).join("")}
        </div>
        <div class="row" style="margin-top:14px">
          <a class="btn sm" href="${problemUrl(c, settings.site)}" target="_blank">想不起来？去重做 ↗</a>
          <button class="btn sm" id="edit">编辑这张卡</button>
          <button class="btn sm" id="skip">跳过</button>
        </div>
      </div>`;
    $$(".rate").forEach((b) => (b.onclick = () => rate(Number(b.dataset.g))));
    $("#edit").onclick = () => editModal(c.slug, async () => { queue[i] = (await getCards())[c.slug] || c; back(); });
    $("#skip").onclick = () => (i++, show());
    const si = $("#saveidea");
    if (si) si.onclick = async () => {
      const v = $("#newidea").value.trim();
      if (!v) return;
      queue[i] = await upsertCard(c.slug, { idea: v });
      back();
    };
    setKeys((e) => {
      if (e.target.matches("input, textarea, select")) return;
      if (["1", "2", "3", "4"].includes(e.key)) rate(Number(e.key));
    });
  }

  async function rate(g) {
    await rateCard(queue[i].slug, g, "card");
    tally[g]++;
    i++;
    show();
  }

  function finished() {
    header();
    $("#pg").style.width = "100%";
    setKeys(null);
    const n = tally[1] + tally[2] + tally[3] + tally[4];
    $("#stage").innerHTML = `
      <div class="flash done">
        <div class="big">${n ? "🎉" : "☕"}</div>
        <h2>${n ? `复习完 ${n} 张` : queue.length ? "这一组看完了" : "这里没有要复习的卡"}</h2>
        ${n ? `<p class="muted">没想起来 ${tally[1]} · 想了很久 ${tally[2]} · 想起来了 ${tally[3]} · 秒想到 ${tally[4]}</p>` : ""}
        ${tally[1] ? `<p>没想起来的 ${tally[1]} 道，建议今天找时间去重做一遍。</p>` : ""}
        <div class="row" style="justify-content:center;margin-top:16px">
          <a class="btn" href="#review?scope=pattern">按套路专项练</a>
          <a class="btn" href="#review?scope=all">随机抽查几张</a>
          <a class="btn" href="#stats">看统计</a>
        </div>
      </div>`;
    chrome.runtime.sendMessage({ type: "refreshBadge" });
  }

  show();
}

// ---------------- library ----------------
async function library() {
  const [cards, settings] = await Promise.all([getCards(), getSettings()]);
  const pats = allPatterns(cards);
  view.innerHTML = `
    <div class="row" style="justify-content:space-between;margin-bottom:14px">
      <h2 style="margin:0">卡片库 <span class="muted" style="font-size:14px;font-weight:400">${Object.keys(cards).length} 张</span></h2>
      <button class="btn primary" id="add">+ 手动添加</button>
    </div>
    <div class="row" style="margin-bottom:12px">
      <input id="q" placeholder="搜索题号 / 标题 / 思路" style="flex:1;min-width:200px" />
      <select id="fd"><option value="">全部难度</option><option>Easy</option><option>Medium</option><option>Hard</option></select>
      <select id="fp"><option value="">全部套路</option>${pats.map((p) => `<option>${esc(p)}</option>`).join("")}<option value="__none">（未分类）</option></select>
      <select id="fs">
        <option value="due">按复习时间</option>
        <option value="weak">记忆度从低到高</option>
        <option value="recent">最近添加</option>
        <option value="noidea">没写思路的优先</option>
      </select>
    </div>
    <div id="list"></div>`;

  const render = () => {
    const q = $("#q").value.trim().toLowerCase();
    const fd = $("#fd").value, fp = $("#fp").value, fs = $("#fs").value;
    const now = Date.now();
    let list = Object.values(cards).filter((c) => {
      if (fd && c.difficulty !== fd) return false;
      if (fp === "__none" && (c.patterns || []).length) return false;
      if (fp && fp !== "__none" && !(c.patterns || []).includes(fp)) return false;
      if (q && ![c.id, c.title, c.titleCn, c.slug, c.idea, ...(c.patterns || [])].join(" ").toLowerCase().includes(q)) return false;
      return true;
    });
    const R = (c) => retrievability(c.sched, now) ?? -1;
    const sorters = {
      due: (a, b) => (a.sched.state === "new") - (b.sched.state === "new") || a.sched.due - b.sched.due,
      weak: (a, b) => R(a) - R(b),
      recent: (a, b) => b.createdAt - a.createdAt,
      noidea: (a, b) => !!a.idea - !!b.idea || a.sched.due - b.sched.due,
    };
    list.sort(sorters[fs]);
    $("#list").innerHTML = list.length
      ? `<table><thead><tr><th>题目</th><th>套路</th><th>记忆度</th><th>下次复习</th><th>次数</th></tr></thead><tbody>
        ${list
          .map((c) => {
            const r = retrievability(c.sched, now);
            const days = Math.round((c.sched.due - startOfDay(now)) / DAY);
            const color = r == null ? "var(--line)" : r > 0.85 ? "var(--r3)" : r > 0.7 ? "var(--r2)" : "var(--r1)";
            return `<tr data-slug="${esc(c.slug)}">
              <td><div>${esc(titleOf(c))} <span class="diff ${esc(c.difficulty)}">${esc(c.difficulty)}</span>${c.suspended ? ' <span class="muted">（已暂停）</span>' : ""}</div>
                  <div class="idea1">${c.idea ? esc(c.idea) : '<i>还没写思路</i>'}</div></td>
              <td>${(c.patterns || []).map((p) => `<span class="chip">${esc(p)}</span>`).join("")}</td>
              <td>${r == null ? '<span class="muted">新卡</span>' : `<span class="rbar"><i style="width:${Math.round(r * 100)}%;background:${color}"></i></span>${Math.round(r * 100)}%`}</td>
              <td>${c.sched.state === "new" ? '<span class="muted">待引入</span>' : isDue(c, now) ? "<b>今天</b>" : `${days} 天后`}</td>
              <td>${(c.history || []).length}</td></tr>`;
          })
          .join("")}</tbody></table>`
      : `<div class="panel muted">没有符合条件的卡片。</div>`;
    $$("#list tbody tr").forEach((tr) => (tr.onclick = () => editModal(tr.dataset.slug, library)));
  };
  ["#q", "#fd", "#fp", "#fs"].forEach((s) => ($(s).oninput = render));
  $("#add").onclick = () => addModal();
  render();
}

function parseSlug(input) {
  const s = input.trim();
  const m = s.match(/leetcode\.(?:com|cn)\/problems\/([^/?#]+)/);
  return (m ? m[1] : s).toLowerCase().replace(/\s+/g, "-");
}

async function fetchMeta(slug, site) {
  const host = site === "cn" ? "leetcode.cn" : "leetcode.com";
  const fields = site === "cn"
    ? "questionFrontendId title translatedTitle difficulty topicTags { name translatedName }"
    : "questionFrontendId title difficulty topicTags { name }";
  try {
    const res = await fetch(`https://${host}/graphql/`, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: `query lrQ($titleSlug: String!) { question(titleSlug: $titleSlug) { ${fields} } }`, variables: { titleSlug: slug } }),
    });
    const q = (await res.json())?.data?.question;
    if (!q) return null;
    return { id: q.questionFrontendId, title: q.title, titleCn: q.translatedTitle || "", difficulty: q.difficulty, tags: (q.topicTags || []).map((t) => t.translatedName || t.name) };
  } catch {
    return null;
  }
}

async function addModal() {
  const settings = await getSettings();
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal">
    <h2>手动添加</h2>
    <label>题目链接或 slug</label>
    <input id="u" placeholder="https://leetcode.com/problems/two-sum/ 或 two-sum" />
    <p class="muted" style="font-size:12px">会尝试从 LeetCode 自动获取题号、标题和难度；获取不到也没关系，之后可以手动改。</p>
    <div class="ft"><span></span><div class="row"><button class="btn" id="c">取消</button><button class="btn primary" id="ok">添加并编辑</button></div></div>
  </div>`;
  document.body.appendChild(bg);
  $("#u", bg).focus();
  $("#c", bg).onclick = () => bg.remove();
  $("#ok", bg).onclick = async () => {
    const raw = $("#u", bg).value;
    const slug = parseSlug(raw);
    if (!slug) return;
    const site = /leetcode\.cn/.test(raw) ? "cn" : settings.site;
    $("#ok", bg).textContent = "获取中…";
    const cards = await getCards();
    if (!cards[slug]) {
      const meta = (await fetchMeta(slug, site)) || {};
      await upsertCard(slug, { ...meta, site });
    }
    bg.remove();
    editModal(slug, library);
  };
}

async function editModal(slug, after) {
  const [cards, settings] = await Promise.all([getCards(), getSettings()]);
  const c = cards[slug];
  if (!c) return;
  const pats = [...new Set([...allPatterns(cards), ...PATTERN_PRESETS])];
  let chosen = [...(c.patterns || [])];
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal">
    <div class="row" style="justify-content:space-between"><h2 style="margin:0">${esc(titleOf(c))}</h2><a href="${problemUrl(c, settings.site)}" target="_blank">原题 ↗</a></div>
    <div class="row" style="margin-top:6px">
      <input id="e-id" placeholder="题号" style="width:80px" value="${esc(c.id)}" />
      <input id="e-title" placeholder="标题" style="flex:1" value="${esc(c.title)}" />
      <select id="e-diff">${["", "Easy", "Medium", "Hard"].map((d) => `<option ${d === c.difficulty ? "selected" : ""}>${d}</option>`).join("")}</select>
    </div>
    <label>一句话思路</label><textarea id="e-idea" rows="3">${esc(c.idea)}</textarea>
    <label>套路</label>
    <div id="e-chips"></div>
    <input id="e-pat" list="e-pats" placeholder="输入或选择套路，回车添加" />
    <datalist id="e-pats">${pats.map((p) => `<option value="${esc(p)}">`).join("")}</datalist>
    <label>复杂度</label><input id="e-cx" value="${esc(c.complexity)}" />
    <label>易错点</label><textarea id="e-pit" rows="2">${esc(c.pitfalls)}</textarea>
    <label>代码 ${c.lang ? `（${esc(c.lang)}）` : ""}</label><textarea id="e-code" rows="6" style="font-family:ui-monospace,Menlo,monospace;font-size:12px">${esc(c.code)}</textarea>
    <label class="row" style="color:var(--fg)"><input type="checkbox" id="e-susp" ${c.suspended ? "checked" : ""} /> 暂停这张卡（不再出现在复习里）</label>
    <p class="muted" style="font-size:12px">复习 ${(c.history || []).length} 次 · 遗忘 ${c.sched.lapses || 0} 次 · ${c.sched.state === "new" ? "新卡" : `下次 ${new Date(c.sched.due).toLocaleDateString()}`}${c.stats?.lastSolveMinutes ? ` · 上次做题约 ${c.stats.lastSolveMinutes} 分钟` : ""}</p>
    <div class="ft">
      <div class="row"><button class="btn danger" id="e-del">删除</button><button class="btn" id="e-reset">重置复习进度</button></div>
      <div class="row"><button class="btn" id="e-cancel">取消</button><button class="btn primary" id="e-save">保存</button></div>
    </div>
  </div>`;
  document.body.appendChild(bg);
  const renderChips = () => {
    $("#e-chips", bg).innerHTML = chosen.length
      ? chosen.map((p) => `<span class="chip" data-p="${esc(p)}" style="cursor:pointer">${esc(p)} ×</span>`).join("")
      : '<span class="muted" style="font-size:12px">未分类</span>';
  };
  renderChips();
  $("#e-chips", bg).onclick = (e) => { const p = e.target.dataset.p; if (p) (chosen = chosen.filter((x) => x !== p)), renderChips(); };
  $("#e-pat", bg).onkeydown = (e) => {
    if (e.key !== "Enter") return;
    const v = e.target.value.trim();
    if (v && !chosen.includes(v)) chosen.push(v), renderChips();
    e.target.value = "";
  };
  const close = () => (bg.remove(), after && after());
  $("#e-cancel", bg).onclick = () => bg.remove();
  $("#e-save", bg).onclick = async () => {
    await upsertCard(slug, {
      id: $("#e-id", bg).value.trim(), title: $("#e-title", bg).value.trim() || slug, difficulty: $("#e-diff", bg).value,
      idea: $("#e-idea", bg).value.trim(), patterns: chosen, complexity: $("#e-cx", bg).value.trim(),
      pitfalls: $("#e-pit", bg).value.trim(), code: $("#e-code", bg).value, suspended: $("#e-susp", bg).checked,
    });
    toast("已保存");
    close();
  };
  $("#e-del", bg).onclick = async () => {
    if (!confirm(`确定删除「${titleOf(c)}」这张卡？`)) return;
    await deleteCard(slug);
    close();
  };
  $("#e-reset", bg).onclick = async () => {
    if (!confirm("把这张卡变回新卡？复习记录会保留，但排期会重新开始。")) return;
    const all = await getCards();
    all[slug].sched = newSchedule();
    await saveCards(all);
    close();
  };
}

// ---------------- stats ----------------
async function stats() {
  const cards = await getCards();
  const list = Object.values(cards);
  const now = Date.now();
  const t0 = startOfDay(now);
  const settings = await getSettings();
  const dayCount = new Map();
  for (const c of list) for (const h of c.history || []) {
    const d = startOfDay(h.t);
    dayCount.set(d, (dayCount.get(d) || 0) + 1);
  }
  let streak = 0;
  const prevDay = (d) => startOfDay(d - DAY / 2);
  for (let d = dayCount.has(t0) ? t0 : prevDay(t0); dayCount.has(d); d = prevDay(d)) streak++;
  const reviewedCards = list.filter((c) => c.sched.state !== "new");
  const avgR = reviewedCards.length ? reviewedCards.reduce((s, c) => s + retrievability(c.sched, now), 0) / reviewedCards.length : 0;
  const week = [...dayCount.entries()].filter(([d]) => d > t0 - 7 * DAY).reduce((s, [, n]) => s + n, 0);

  const byPat = new Map();
  for (const c of reviewedCards) for (const p of c.patterns?.length ? c.patterns : ["（未分类）"]) {
    const e = byPat.get(p) || { n: 0, r: 0, due: 0, lapses: 0 };
    e.n++; e.r += retrievability(c.sched, now); e.lapses += c.sched.lapses || 0; if (isDue(c, now)) e.due++;
    byPat.set(p, e);
  }
  const patRows = [...byPat.entries()].map(([p, e]) => ({ p, ...e, avg: e.r / e.n })).sort((a, b) => a.avg - b.avg);

  const weeks = 18;
  const startDay = t0 - ((weeks - 1) * 7 + new Date(t0).getDay()) * DAY + DAY / 2; // noon, DST-safe
  let cells = "";
  for (let d = startDay; d <= t0 + DAY; d += DAY) {
    const n = dayCount.get(startOfDay(d)) || 0;
    const l = n === 0 ? "" : n < 5 ? "l1" : n < 12 ? "l2" : n < 25 ? "l3" : "l4";
    cells += `<i class="${l}" title="${new Date(d).toLocaleDateString()}：${n} 次"></i>`;
  }

  view.innerHTML = `
    <h2>统计</h2>
    <div class="grid4">
      <div class="stat"><b>${list.length}</b><span>卡片总数（${list.filter((c) => c.idea).length} 张写了思路）</span></div>
      <div class="stat"><b>${buildQueue(cards, settings).length}</b><span>今天待复习</span></div>
      <div class="stat"><b>${reviewedCards.length ? Math.round(avgR * 100) + "%" : "—"}</b><span>平均记忆度（估计）</span></div>
      <div class="stat"><b>${streak} 天</b><span>连续复习 · 近 7 天 ${week} 次</span></div>
    </div>
    <h3>复习热力图</h3>
    <div class="panel"><div class="heat">${cells}</div></div>
    <h3>各套路掌握情况 <span class="muted" style="font-size:12px;font-weight:400">最薄弱的排在前面，点套路名直接专项练</span></h3>
    ${
      patRows.length
        ? `<table><thead><tr><th>套路</th><th>卡片数</th><th>平均记忆度</th><th>遗忘次数</th><th>今天到期</th></tr></thead><tbody>
          ${patRows.map((r) => `<tr class="pr" data-p="${esc(r.p)}"><td><span class="chip">${esc(r.p)}</span></td><td>${r.n}</td><td>${Math.round(r.avg * 100)}%</td><td>${r.lapses}</td><td>${r.due}</td></tr>`).join("")}
          </tbody></table>`
        : `<div class="panel muted">复习过几张卡之后这里会出现各套路的掌握情况。</div>`
    }`;
  $$("tr.pr").forEach((tr) => (tr.onclick = () => {
    if (tr.dataset.p === "（未分类）") return;
    location.hash = `#review?scope=pattern&p=${encodeURIComponent(tr.dataset.p)}`;
  }));
}

// ---------------- settings / import / export ----------------
function download(name, text, type = "text/plain") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: type + ";charset=utf-8" }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const stamp = () => new Date().toISOString().slice(0, 10);

function toMarkdown(cards) {
  const groups = new Map();
  for (const c of Object.values(cards)) for (const p of c.patterns?.length ? c.patterns : ["未分类"]) {
    if (!groups.has(p)) groups.set(p, []);
    groups.get(p).push(c);
  }
  let md = `# LeetCode 思路卡\n\n导出于 ${stamp()}，共 ${Object.keys(cards).length} 题。\n`;
  for (const [p, list] of [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0], "zh"))) {
    md += `\n## ${p}\n`;
    for (const c of list.sort((a, b) => Number(a.id) - Number(b.id))) {
      md += `\n### ${titleOf(c)}${c.difficulty ? ` (${c.difficulty})` : ""}\n\n`;
      md += `- 链接：${problemUrl(c)}\n`;
      if (c.idea) md += `- 思路：${c.idea.replace(/\n/g, " ")}\n`;
      if (c.complexity) md += `- 复杂度：${c.complexity}\n`;
      if (c.pitfalls) md += `- 易错点：${c.pitfalls.replace(/\n/g, " ")}\n`;
      if (c.code) md += `\n\`\`\`${(c.lang || "").replace(/\d+$/, "")}\n${c.code}\n\`\`\`\n`;
    }
  }
  return md;
}

function toAnki(cards) {
  const cell = (s) => String(s || "").replace(/\t/g, " ").replace(/\r?\n/g, "<br>");
  const escH = (s) => esc(s);
  let out = "#separator:tab\n#html:true\n#tags column:3\n";
  for (const c of Object.values(cards)) {
    if (!c.idea) continue;
    const front = `<b>${escH(titleOf(c))}</b>${c.difficulty ? ` <small>${c.difficulty}</small>` : ""}${c.titleCn ? `<br>${escH(c.titleCn)}` : ""}<br><br><small>用什么套路？关键一步？复杂度？</small>`;
    const back = [
      `<b>思路</b><br>${escH(c.idea)}`,
      c.complexity && `<b>复杂度</b><br>${escH(c.complexity)}`,
      c.pitfalls && `<b>易错点</b><br>${escH(c.pitfalls)}`,
      `<a href="${problemUrl(c)}">原题</a>`,
    ].filter(Boolean).join("<br><br>");
    const tags = ["leetcode", ...(c.patterns || [])].map((t) => t.replace(/\s+/g, "_")).join(" ");
    out += `${cell(front)}\t${cell(back)}\t${tags}\n`;
  }
  return out;
}

async function importAc(site) {
  const host = site === "cn" ? "leetcode.cn" : "leetcode.com";
  const res = await fetch(`https://${host}/api/problems/all/`, { credentials: "include" });
  const data = await res.json();
  if (!data.user_name) throw new Error(`没有检测到登录状态，请先在浏览器里登录 ${host}`);
  const cards = await getCards();
  const diff = { 1: "Easy", 2: "Medium", 3: "Hard" };
  let added = 0;
  for (const p of data.stat_status_pairs || []) {
    if (p.status !== "ac") continue;
    const slug = p.stat.question__title_slug;
    if (cards[slug]) continue;
    cards[slug] = {
      ...blankCard(slug),
      id: String(p.stat.frontend_question_id || ""),
      title: p.stat.question__title || slug,
      difficulty: diff[p.difficulty?.level] || "",
      site,
      createdAt: Date.now() + added, // keep a stable order
    };
    added++;
  }
  await saveCards(cards);
  return { added, user: data.user_name };
}

async function settingsView() {
  const s = await getSettings();
  view.innerHTML = `
    <h2>设置</h2>
    <div class="panel">
      <div class="grid4" style="grid-template-columns:repeat(2,1fr)">
        <label>每天最多复习（张）<br><input type="number" id="s-rev" min="1" max="500" value="${s.dailyReview}" /></label>
        <label>每天最多引入新卡（张）<br><input type="number" id="s-new" min="0" max="200" value="${s.dailyNew}" /></label>
        <label>目标记忆保持率<br><select id="s-ret">${[0.8, 0.85, 0.9, 0.95].map((v) => `<option value="${v}" ${v === s.retention ? "selected" : ""}>${v * 100}%${v === 0.9 ? "（推荐）" : ""}</option>`).join("")}</select></label>
        <label>最长间隔（天）<br><input type="number" id="s-max" min="7" max="3650" value="${s.maxInterval}" /></label>
        <label>每日提醒时间<br><select id="s-rem"><option value="-1">关闭</option>${Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${h === s.reminderHour ? "selected" : ""}>${h}:00</option>`).join("")}</select></label>
        <label>打开题目用<br><select id="s-site"><option value="com" ${s.site === "com" ? "selected" : ""}>leetcode.com</option><option value="cn" ${s.site === "cn" ? "selected" : ""}>leetcode.cn</option></select></label>
      </div>
      <p><label><input type="checkbox" id="s-hide" ${s.hideTagsOnFront ? "checked" : ""} /> 翻卡正面隐藏套路标签（标签本身就是提示，隐藏后回忆更有效）</label></p>
      <p><label><input type="checkbox" id="s-auto" ${s.autoPopup ? "checked" : ""} /> AC 后自动弹出思路卡面板</label></p>
      <div class="row"><button class="btn primary" id="s-save">保存设置</button><button class="btn" id="s-def">恢复默认</button></div>
    </div>

    <h3>导入以前 AC 过的题</h3>
    <div class="panel">
      <p class="muted">需要先在浏览器里登录对应的网站。导入的题会作为新卡（还没写思路），按「每天最多引入新卡」的数量逐天放出，翻到时顺手补一句思路就行。</p>
      <div class="row"><button class="btn" id="imp-com">从 leetcode.com 导入</button><button class="btn" id="imp-cn">从 leetcode.cn 导入</button><span class="muted" id="imp-msg"></span></div>
    </div>

    <h3>导出 / 备份</h3>
    <div class="panel">
      <div class="row">
        <button class="btn" id="ex-json">备份 JSON</button>
        <button class="btn" id="ex-md">导出 Markdown 笔记</button>
        <button class="btn" id="ex-anki">导出 Anki 卡组（手机复习）</button>
        <label class="btn" style="display:inline-block">从 JSON 恢复 / 合并<input type="file" id="im-json" accept=".json" hidden /></label>
      </div>
      <p class="muted" style="font-size:12px">Anki：在电脑版 Anki 里「文件 → 导入」选这个 .txt，同步后就能用 AnkiMobile / AnkiDroid 在手机上刷。只导出写了思路的卡。<br>换电脑：旧电脑「备份 JSON」，新电脑「从 JSON 恢复」，同一道题保留更新时间较新的那份。</p>
    </div>

    <h3>危险操作</h3>
    <div class="panel"><button class="btn danger" id="wipe">清空所有卡片</button></div>`;

  $("#s-save").onclick = async () => {
    await saveSettings({
      dailyReview: Number($("#s-rev").value) || DEFAULT_SETTINGS.dailyReview,
      dailyNew: Math.max(0, Number($("#s-new").value)),
      retention: Number($("#s-ret").value),
      maxInterval: Number($("#s-max").value) || DEFAULT_SETTINGS.maxInterval,
      reminderHour: Number($("#s-rem").value),
      site: $("#s-site").value,
      hideTagsOnFront: $("#s-hide").checked,
      autoPopup: $("#s-auto").checked,
    });
    toast("设置已保存");
  };
  $("#s-def").onclick = async () => { await saveSettings(DEFAULT_SETTINGS); settingsView(); toast("已恢复默认"); };

  for (const site of ["com", "cn"]) {
    $(`#imp-${site}`).onclick = async () => {
      $("#imp-msg").textContent = "导入中…";
      try {
        const r = await importAc(site);
        $("#imp-msg").textContent = `${r.user}：新增 ${r.added} 张卡`;
      } catch (e) {
        $("#imp-msg").textContent = "导入失败：" + (e.message || e);
      }
    };
  }

  $("#ex-json").onclick = async () => download(`leetrecall-backup-${stamp()}.json`, JSON.stringify({ app: "leetrecall", version: 1, exportedAt: Date.now(), cards: await getCards(), settings: await getSettings() }, null, 2), "application/json");
  $("#ex-md").onclick = async () => download(`leetcode-ideas-${stamp()}.md`, toMarkdown(await getCards()), "text/markdown");
  $("#ex-anki").onclick = async () => {
    const cards = await getCards();
    if (!Object.values(cards).some((c) => c.idea)) return toast("还没有写了思路的卡");
    download(`leetrecall-anki-${stamp()}.txt`, toAnki(cards));
  };
  $("#im-json").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      if (!data.cards) throw new Error("不是 LeetRecall 的备份文件");
      const cur = await getCards();
      let n = 0;
      for (const [slug, c] of Object.entries(data.cards)) {
        if (!cur[slug] || (c.updatedAt || 0) > (cur[slug].updatedAt || 0)) (cur[slug] = c), n++;
      }
      await saveCards(cur);
      toast(`合并完成，更新了 ${n} 张卡`);
    } catch (err) {
      toast("导入失败：" + err.message);
    }
    e.target.value = "";
  };
  $("#wipe").onclick = async () => {
    if (!confirm("确定清空所有卡片？建议先备份 JSON。")) return;
    await saveCards({});
    toast("已清空");
  };
}
