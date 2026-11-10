// Isolated-world content script on LeetCode problem pages.
// - receives submit/result events from inject.js
// - shows the "思路卡" panel (shadow DOM) to write the idea + rate
(() => {
  if (window.__leetRecallContent) return;
  window.__leetRecallContent = true;

  const SRC = "leetrecall";
  const site = location.hostname.endsWith("leetcode.cn") ? "cn" : "com";
  const send = (msg) =>
    new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (r) => resolve(chrome.runtime.lastError ? null : r));
      } catch {
        resolve(null);
      }
    });

  const state = {
    slug: null,
    openedAt: Date.now(),
    fails: 0,
    meta: null,
    lastHookAt: 0,
    solve: null, // { code, lang, minutes, attempts, runtime, memory }
    settings: null,
  };

  const RATINGS = [
    { g: 1, label: "忘了 / 看了题解", cls: "r1" },
    { g: 2, label: "很吃力", cls: "r2" },
    { g: 3, label: "想出来了", cls: "r3" },
    { g: 4, label: "秒想到", cls: "r4" },
  ];

  // ---------- page / slug tracking ----------
  function currentSlug() {
    const m = location.pathname.match(/^\/problems\/([^/]+)/);
    return m ? m[1] : null;
  }

  function onRoute() {
    const slug = currentSlug();
    if (slug === state.slug) return;
    state.slug = slug;
    state.openedAt = Date.now();
    state.fails = 0;
    state.meta = null;
    state.solve = null;
    closePanel();
    if (!slug) {
      fab && fab.remove();
      fab = null;
      return;
    }
    ensureFab();
    fetchMeta(slug).then((m) => {
      if (state.slug === slug) {
        state.meta = m;
        refreshFab();
      }
    });
  }

  // ---------- metadata ----------
  function cookie(name) {
    const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  async function fetchMeta(slug) {
    const fields =
      site === "cn"
        ? "questionFrontendId title translatedTitle difficulty topicTags { name translatedName }"
        : "questionFrontendId title difficulty topicTags { name }";
    try {
      const res = await fetch("/graphql/", {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json", "x-csrftoken": cookie("csrftoken") },
        body: JSON.stringify({
          query: `query lrQ($titleSlug: String!) { question(titleSlug: $titleSlug) { ${fields} } }`,
          variables: { titleSlug: slug },
        }),
      });
      const q = (await res.json())?.data?.question;
      if (!q) throw 0;
      return {
        id: q.questionFrontendId || "",
        title: q.title || slug,
        titleCn: q.translatedTitle || "",
        difficulty: q.difficulty || "",
        tags: (q.topicTags || []).map((t) => t.translatedName || t.name),
      };
    } catch {
      const t = document.title.replace(/\s*[-|].*$/, "").trim();
      const m = t.match(/^(\d+)\.\s*(.+)$/);
      return { id: m ? m[1] : "", title: m ? m[2] : t || slug, titleCn: "", difficulty: "", tags: [] };
    }
  }

  // ---------- events from inject.js ----------
  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || e.data.src !== SRC) return;
    const d = e.data;
    if (d.type === "result") {
      state.lastHookAt = Date.now();
      if (d.slug !== state.slug) return;
      if (!d.accepted) {
        state.fails++;
        return;
      }
      onAccepted({ code: d.code, lang: d.lang, runtime: d.runtime, memory: d.memory });
    }
  });

  // Fallback: watch the result panel in case the network hook misses something.
  let fallbackTimer = null;
  new MutationObserver(() => {
    const el = document.querySelector('[data-e2e-locator="submission-result"]');
    if (!el || el.__lrSeen) return;
    el.__lrSeen = true;
    const text = el.textContent || "";
    if (!/Accepted|通过/.test(text)) return;
    clearTimeout(fallbackTimer);
    fallbackTimer = setTimeout(() => {
      if (Date.now() - state.lastHookAt > 8000) onAccepted({});
    }, 2500);
  }).observe(document.documentElement, { childList: true, subtree: true });

  async function onAccepted(info) {
    if (!state.slug) return;
    const minutes = Math.max(1, Math.round((Date.now() - state.openedAt) / 60000));
    state.solve = { ...info, minutes, attempts: state.fails + 1 };
    state.settings = state.settings || (await send({ type: "getSettings" })) || {};
    if (state.settings.autoPopup === false) {
      refreshFab("AC ✓ 点我写思路");
      return;
    }
    openPanel();
  }

  // ---------- UI ----------
  let host = null, root = null, fab = null;

  function ensureHost() {
    if (host && document.documentElement.contains(host)) return;
    host = document.createElement("div");
    host.id = "leetrecall-host";
    host.style.cssText = "all: initial; position: fixed; z-index: 2147483000; right: 0; bottom: 0;";
    document.documentElement.appendChild(host);
    root = host.attachShadow({ mode: "open" });
    const style = document.createElement("link");
    style.rel = "stylesheet";
    style.href = chrome.runtime.getURL("src/panel.css");
    root.appendChild(style);
  }

  function ensureFab() {
    ensureHost();
    if (fab && root.contains(fab)) return;
    fab = document.createElement("button");
    fab.className = "fab";
    fab.textContent = "思路卡";
    fab.addEventListener("click", () => (root.querySelector(".panel") ? closePanel() : openPanel()));
    root.appendChild(fab);
    refreshFab();
  }

  async function refreshFab(text) {
    if (!fab) return;
    if (text) {
      fab.textContent = text;
      fab.classList.add("hot");
      return;
    }
    fab.classList.remove("hot");
    const card = state.slug ? await send({ type: "getCard", slug: state.slug }) : null;
    if (!card) fab.textContent = "思路卡 +";
    else if (card.sched.state === "new") fab.textContent = "思路卡 · 待复习";
    else {
      const days = Math.round((card.sched.due - Date.now()) / 86400000);
      fab.textContent = days <= 0 ? "思路卡 · 今天复习" : `思路卡 · ${days}天后复习`;
    }
  }

  function closePanel() {
    const p = root && root.querySelector(".panel");
    if (p) p.remove();
  }

  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  async function openPanel() {
    ensureFab();
    closePanel();
    const slug = state.slug;
    if (!slug) return;
    if (!state.meta) state.meta = await fetchMeta(slug);
    const [card, prev, patterns] = await Promise.all([
      send({ type: "getCard", slug }),
      send({ type: "preview", slug }),
      send({ type: "getPatterns" }),
    ]);
    const meta = state.meta;
    const solve = state.solve;
    const c = card || {};
    let chosen = [...(c.patterns || [])];

    const suggestRating = solve ? (solve.minutes > 30 || solve.attempts >= 3 ? 2 : 3) : 0;
    const panel = document.createElement("div");
    panel.className = "panel";
    panel.innerHTML = `
      <div class="hd">
        <div>
          <div class="title">${esc(meta.id ? meta.id + ". " : "")}${esc(meta.titleCn || meta.title)}</div>
          <div class="sub">
            ${meta.difficulty ? `<span class="diff ${esc(meta.difficulty)}">${esc(meta.difficulty)}</span>` : ""}
            ${
              solve
                ? `<span class="ok">AC ✓ 用时约 ${solve.minutes} 分钟${solve.attempts > 1 ? `，第 ${solve.attempts} 次提交` : ""}</span>`
                : card
                ? `<span>已有卡片，复习 ${c.history?.length || 0} 次</span>`
                : `<span>新建思路卡</span>`
            }
          </div>
        </div>
        <button class="x" title="关闭">×</button>
      </div>
      <label>一句话思路 <em>（翻卡时背面显示的就是这个）</em></label>
      <textarea class="idea" rows="3" placeholder="例：单调递减栈存下标；遇到更高的柱子就出栈，宽度 = 当前下标 - 新栈顶 - 1">${esc(c.idea)}</textarea>
      <label>套路</label>
      <div class="chips"></div>
      <div class="presets"></div>
      <input class="pat-in" list="lr-pats" placeholder="输入自定义套路后回车" />
      <datalist id="lr-pats">${(patterns || []).map((p) => `<option value="${esc(p)}">`).join("")}</datalist>
      <div class="row2">
        <div><label>复杂度</label><input class="cx" placeholder="时间 O(n) / 空间 O(n)" value="${esc(c.complexity)}" /></div>
      </div>
      <label>易错点</label>
      <textarea class="pit" rows="2" placeholder="例：先判空；right 要用 len-1 还是 len">${esc(c.pitfalls)}</textarea>
      ${
        solve && solve.code
          ? `<label class="chk"><input type="checkbox" class="savecode" checked /> 保存这次 AC 的代码（${esc(solve.lang || "")}）</label>`
          : ""
      }
      <div class="rate-hd">${solve ? "这道题你是怎么做出来的？" : "现在回想这道题的感觉："}</div>
      <div class="rates">
        ${RATINGS.map(
          (r) => `<button class="rate ${r.cls} ${r.g === suggestRating ? "sug" : ""}" data-g="${r.g}">
            <b>${r.label}</b><span>${prev ? prev[r.g].ivl + "天后复习" : ""}</span></button>`
        ).join("")}
      </div>
      <div class="ft">
        ${card ? `<button class="link save-only">只保存内容，不改复习时间</button>` : ""}
        ${solve && !card ? `<button class="link skip">这题不用复习</button>` : ""}
        <span class="msg"></span>
      </div>`;
    root.appendChild(panel);

    const $ = (s) => panel.querySelector(s);
    const chipsEl = $(".chips");
    const presetsEl = $(".presets");
    const quick = [...new Set([...(meta.tags || []).filter((t) => (patterns || []).includes(t)), ...(patterns || [])])].slice(0, 12);

    function renderChips() {
      chipsEl.innerHTML = chosen.length
        ? chosen.map((p) => `<span class="chip on" data-p="${esc(p)}">${esc(p)} ×</span>`).join("")
        : `<span class="hint">还没选，点下面的常用套路或自己输入</span>`;
      presetsEl.innerHTML = quick
        .filter((p) => !chosen.includes(p))
        .map((p) => `<span class="chip" data-p="${esc(p)}">${esc(p)}</span>`)
        .join("");
    }
    renderChips();
    chipsEl.addEventListener("click", (e) => {
      const p = e.target.dataset && e.target.dataset.p;
      if (p) (chosen = chosen.filter((x) => x !== p)), renderChips();
    });
    presetsEl.addEventListener("click", (e) => {
      const p = e.target.dataset && e.target.dataset.p;
      if (p && !chosen.includes(p)) chosen.push(p), renderChips();
    });
    $(".pat-in").addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") {
        const v = e.target.value.trim();
        if (v && !chosen.includes(v)) chosen.push(v), renderChips();
        e.target.value = "";
      }
    });
    // keep LeetCode's global shortcuts from firing while typing in the panel
    panel.addEventListener("keydown", (e) => e.stopPropagation());
    $(".x").addEventListener("click", closePanel);

    function collect() {
      const saveCode = panel.querySelector(".savecode");
      return {
        ...meta,
        site,
        idea: $(".idea").value.trim(),
        patterns: chosen,
        complexity: $(".cx").value.trim(),
        pitfalls: $(".pit").value.trim(),
        ...(saveCode && saveCode.checked ? { code: solve.code, lang: solve.lang } : {}),
        ...(solve ? { stats: { attempts: ((c.stats && c.stats.attempts) || 0) + solve.attempts, lastSolveMinutes: solve.minutes } } : {}),
      };
    }

    async function save(rating) {
      const r = await send({ type: "saveFromPage", slug, fields: collect(), rating, mode: solve ? "solve" : "card" });
      if (!r) {
        $(".msg").textContent = "保存失败，刷新页面再试";
        return;
      }
      state.solve = null;
      closePanel();
      refreshFab();
    }

    panel.querySelectorAll(".rate").forEach((b) => b.addEventListener("click", () => save(Number(b.dataset.g))));
    const so = panel.querySelector(".save-only");
    if (so) so.addEventListener("click", () => save(null));
    const sk = panel.querySelector(".skip");
    if (sk) sk.addEventListener("click", () => ((state.solve = null), closePanel()));
    setTimeout(() => $(".idea").focus(), 50);
  }

  // SPA navigation
  let lastPath = location.pathname;
  setInterval(() => {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      onRoute();
    }
  }, 700);
  onRoute();
})();
