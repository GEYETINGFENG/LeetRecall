// Storage layer shared by background, popup and app pages (ES module).
import { apply, newSchedule, retrievability, startOfDay, DAY } from "./fsrs.js";

export const DEFAULT_SETTINGS = {
  dailyReview: 30, // 每天最多复习多少张到期卡
  dailyNew: 10, // 每天最多引入多少张新卡（导入但还没复习过的）
  retention: 0.9, // 目标记忆保持率
  maxInterval: 180, // 最长间隔（天）
  reminderHour: 9, // 每天几点提醒，-1 关闭
  hideTagsOnFront: true, // 翻卡正面隐藏套路标签（标签本身就是提示）
  site: "com", // 打开题目用 leetcode.com 还是 leetcode.cn
  autoPopup: true, // AC 后自动弹出写思路面板
};

export const PATTERN_PRESETS = [
  "双指针", "滑动窗口", "二分查找", "前缀和", "差分", "哈希表", "单调栈", "单调队列",
  "堆/优先队列", "BFS", "DFS/回溯", "拓扑排序", "并查集", "最短路", "动态规划", "区间DP",
  "背包", "状态压缩", "贪心", "排序", "链表技巧", "树的遍历", "二叉搜索树", "Trie",
  "线段树/树状数组", "位运算", "数学", "模拟", "字符串匹配", "设计",
];

const KEY_CARDS = "cards";
const KEY_SETTINGS = "settings";

export async function getSettings() {
  const r = await chrome.storage.local.get(KEY_SETTINGS);
  return { ...DEFAULT_SETTINGS, ...(r[KEY_SETTINGS] || {}) };
}

export async function saveSettings(patch) {
  const cur = await getSettings();
  const next = { ...cur, ...patch };
  await chrome.storage.local.set({ [KEY_SETTINGS]: next });
  return next;
}

export async function getCards() {
  const r = await chrome.storage.local.get(KEY_CARDS);
  return r[KEY_CARDS] || {};
}

export async function saveCards(cards) {
  await chrome.storage.local.set({ [KEY_CARDS]: cards });
}

export async function getCard(slug) {
  return (await getCards())[slug] || null;
}

export function blankCard(slug) {
  const now = Date.now();
  return {
    slug,
    id: "",
    title: slug,
    titleCn: "",
    difficulty: "",
    tags: [],
    patterns: [],
    idea: "",
    complexity: "",
    pitfalls: "",
    code: "",
    lang: "",
    site: "com",
    createdAt: now,
    updatedAt: now,
    suspended: false,
    sched: newSchedule(),
    history: [],
    stats: { attempts: 0, lastSolveMinutes: null },
  };
}

// Merge fields into a card (creating it if needed). Does not touch scheduling.
export async function upsertCard(slug, patch) {
  const cards = await getCards();
  const cur = cards[slug] || blankCard(slug);
  const next = { ...cur, ...stripUndefined(patch), slug, updatedAt: Date.now() };
  if (patch.stats) next.stats = { ...cur.stats, ...patch.stats };
  cards[slug] = next;
  await saveCards(cards);
  return next;
}

export async function rateCard(slug, rating, mode = "card") {
  const [cards, settings] = await Promise.all([getCards(), getSettings()]);
  const card = cards[slug];
  if (!card) throw new Error("card not found: " + slug);
  const now = Date.now();
  const wasNew = card.sched.state === "new";
  card.sched = apply(card.sched, rating, now, settings);
  card.history = [...(card.history || []), { t: now, g: rating, mode, wasNew }];
  card.updatedAt = now;
  cards[slug] = card;
  await saveCards(cards);
  return card;
}

export async function deleteCard(slug) {
  const cards = await getCards();
  delete cards[slug];
  await saveCards(cards);
}

export function endOfToday(now = Date.now()) {
  return startOfDay(now) + DAY - 1;
}

export function isDue(card, now = Date.now()) {
  return !card.suspended && card.sched.state !== "new" && card.sched.due <= endOfToday(now);
}

export function todayCounts(cards, now = Date.now()) {
  const t0 = startOfDay(now);
  let reviewed = 0, introduced = 0;
  for (const c of Object.values(cards)) {
    for (const h of c.history || []) {
      if (h.t < t0 || h.mode === "solve") continue;
      if (h.wasNew) introduced++;
      else reviewed++;
    }
  }
  return { reviewed, introduced };
}

// Build today's review queue: due cards (weakest first) then new cards.
export function buildQueue(cards, settings, { scope = "due", pattern = "" } = {}) {
  const now = Date.now();
  let list = Object.values(cards).filter((c) => !c.suspended);
  if (pattern) list = list.filter((c) => (c.patterns || []).includes(pattern) || (c.tags || []).includes(pattern));

  if (scope === "all") {
    return shuffle(list);
  }
  const { reviewed, introduced } = todayCounts(cards, now);
  const due = list
    .filter((c) => isDue(c, now))
    .sort((a, b) => (retrievability(a.sched, now) ?? 0) - (retrievability(b.sched, now) ?? 0));
  const fresh = list
    .filter((c) => c.sched.state === "new")
    .sort((a, b) => a.createdAt - b.createdAt);
  if (scope === "pattern") return [...due, ...fresh];
  return [
    ...due.slice(0, Math.max(0, settings.dailyReview - reviewed)),
    ...fresh.slice(0, Math.max(0, settings.dailyNew - introduced)),
  ];
}

export async function dueCount() {
  const [cards, settings] = await Promise.all([getCards(), getSettings()]);
  return buildQueue(cards, settings).length;
}

export function problemUrl(card, site) {
  const host = (site || card.site) === "cn" ? "leetcode.cn" : "leetcode.com";
  return `https://${host}/problems/${card.slug}/`;
}

function stripUndefined(o) {
  const r = {};
  for (const [k, v] of Object.entries(o)) if (v !== undefined) r[k] = v;
  return r;
}

function shuffle(a) {
  a = [...a];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
