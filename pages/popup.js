import { getCards, getSettings, buildQueue, todayCounts } from "../src/store.js";
import { retrievability } from "../src/fsrs.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const open = (hash) => chrome.tabs.create({ url: chrome.runtime.getURL("pages/app.html" + hash) });

const [cards, settings] = await Promise.all([getCards(), getSettings()]);
const queue = buildQueue(cards, settings);
const total = Object.keys(cards).length;
const { reviewed } = todayCounts(cards);
const root = document.getElementById("root");

root.innerHTML = `
  <div class="hd"><b>LeetRecall 思路卡</b><a href="#" id="set" class="muted">设置</a></div>
  ${
    total === 0
      ? `<p>还没有卡片。</p><p class="muted">去 LeetCode 做一道题，AC 后右下角会弹出「思路卡」，写一句思路、打个分就记下来了。也可以在设置里一键导入你以前 AC 过的题。</p>`
      : `<div class="count">${queue.length}</div>
         <div class="muted">今天待复习 · 已复习 ${reviewed} · 共 ${total} 张</div>
         <ul>${queue
           .slice(0, 6)
           .map((c) => {
             const r = retrievability(c.sched);
             return `<li><span>${esc(c.id ? c.id + ". " : "")}${esc(c.titleCn || c.title)}</span><span class="muted">${
               r == null ? "新卡" : Math.round(r * 100) + "%"
             }</span></li>`;
           })
           .join("")}${queue.length > 6 ? `<li class="muted">还有 ${queue.length - 6} 张…</li>` : ""}</ul>`
  }
  <div class="acts">
    <button class="btn primary" id="go" ${queue.length ? "" : "disabled"}>${queue.length ? "开始翻卡" : "今天复习完了"}</button>
    <button class="btn" id="lib">卡片库</button>
  </div>`;

document.getElementById("go").onclick = () => open("#review");
document.getElementById("lib").onclick = () => open("#library");
document.getElementById("set").onclick = (e) => (e.preventDefault(), open("#settings"));
