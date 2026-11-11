// Service worker: message router, badge counter and daily reminder.
import { preview } from "./fsrs.js";
import {
  getCard, getCards, getSettings, upsertCard, rateCard, dueCount, PATTERN_PRESETS,
} from "./store.js";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  handle(msg)
    .then(sendResponse)
    .catch((e) => {
      console.error("[LeetRecall]", e);
      sendResponse(null);
    });
  return true; // async response
});

async function handle(msg) {
  switch (msg && msg.type) {
    case "getSettings":
      return getSettings();
    case "getCard":
      return getCard(msg.slug);
    case "preview": {
      const [card, settings] = await Promise.all([getCard(msg.slug), getSettings()]);
      return preview(card && card.sched, Date.now(), settings);
    }
    case "getPatterns": {
      const cards = await getCards();
      const used = new Set();
      for (const c of Object.values(cards)) (c.patterns || []).forEach((p) => used.add(p));
      return [...new Set([...used, ...PATTERN_PRESETS])];
    }
    case "saveFromPage": {
      let card = await upsertCard(msg.slug, msg.fields || {});
      if (msg.rating) card = await rateCard(msg.slug, msg.rating, msg.mode || "card");
      return card;
    }
    case "refreshBadge":
      await updateBadge();
      return true;
    default:
      return null;
  }
}

async function updateBadge() {
  const n = await dueCount();
  await chrome.action.setBadgeBackgroundColor({ color: "#5b6cff" });
  await chrome.action.setBadgeText({ text: n ? String(n > 99 ? "99+" : n) : "" });
}

async function scheduleReminder() {
  await chrome.alarms.clear("daily");
  const { reminderHour } = await getSettings();
  if (reminderHour == null || reminderHour < 0) return;
  const t = new Date();
  t.setHours(reminderHour, 0, 0, 0);
  if (t.getTime() <= Date.now()) t.setDate(t.getDate() + 1);
  chrome.alarms.create("daily", { when: t.getTime(), periodInMinutes: 24 * 60 });
}

chrome.alarms.onAlarm.addListener(async (a) => {
  await updateBadge();
  if (a.name !== "daily") return;
  const n = await dueCount();
  if (!n) return;
  chrome.notifications.create("lr-daily", {
    type: "basic",
    iconUrl: chrome.runtime.getURL("icons/icon128.png"),
    title: "LeetRecall 思路卡",
    message: `今天有 ${n} 张思路卡要复习，大概 ${Math.max(1, Math.round(n / 3))} 分钟。`,
    priority: 1,
  });
});

chrome.notifications.onClicked.addListener((id) => {
  if (id === "lr-daily") chrome.tabs.create({ url: chrome.runtime.getURL("pages/app.html#review") });
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.cards || changes.settings) updateBadge();
  if (changes.settings) scheduleReminder();
});

chrome.runtime.onInstalled.addListener(async (d) => {
  chrome.alarms.create("tick", { periodInMinutes: 30 });
  await scheduleReminder();
  await updateBadge();
  if (d.reason === "install") chrome.tabs.create({ url: chrome.runtime.getURL("pages/app.html#welcome") });
});

chrome.runtime.onStartup.addListener(async () => {
  chrome.alarms.create("tick", { periodInMinutes: 30 });
  await scheduleReminder();
  await updateBadge();
});
