// Runs in the page's MAIN world. Watches LeetCode's own submit / check requests
// (both the Submit button and Ctrl/Cmd+Enter go through them) and forwards
// results to the isolated content script via window.postMessage.
(() => {
  if (window.__leetRecallHooked) return;
  window.__leetRecallHooked = true;

  const SRC = "leetrecall";
  const pending = new Map(); // submission id -> { slug, code, lang }
  const SUBMIT_RE = /\/problems\/([^/?#]+)\/submit\/?(?:[?#]|$)/;
  const CHECK_RE = /\/submissions\/detail\/([^/?#]+)\/check\/?/;

  function post(type, data) {
    window.postMessage({ src: SRC, type, ...data }, location.origin);
  }

  function parseBody(body) {
    try {
      return typeof body === "string" ? JSON.parse(body) : null;
    } catch {
      return null;
    }
  }

  function onSubmitResponse(url, reqBody, json) {
    const m = url.match(SUBMIT_RE);
    if (!m || !json || json.submission_id == null) return;
    const body = parseBody(reqBody) || {};
    const id = String(json.submission_id);
    pending.set(id, { slug: m[1], code: body.typed_code || "", lang: body.lang || "" });
    post("submit", { slug: m[1], id });
  }

  function onCheckResponse(url, json) {
    const m = url.match(CHECK_RE);
    if (!m || !json || json.state !== "SUCCESS") return;
    const id = String(m[1]);
    const info = pending.get(id);
    if (!info) return; // a "Run" (test) result, not a real submission
    pending.delete(id);
    post("result", {
      id,
      slug: info.slug,
      code: info.code,
      lang: info.lang || json.lang || "",
      accepted: json.status_code === 10 || json.status_msg === "Accepted",
      statusMsg: json.status_msg || "",
      runtime: json.status_runtime || "",
      memory: json.status_memory || "",
    });
  }

  function route(url, reqBody, text) {
    if (!url || (!SUBMIT_RE.test(url) && !CHECK_RE.test(url))) return;
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      return;
    }
    if (SUBMIT_RE.test(url)) onSubmitResponse(url, reqBody, json);
    else onCheckResponse(url, json);
  }

  // fetch
  const origFetch = window.fetch;
  window.fetch = async function (input, init) {
    const res = await origFetch.apply(this, arguments);
    try {
      const url = typeof input === "string" ? input : input && input.url;
      if (url && (SUBMIT_RE.test(url) || CHECK_RE.test(url))) {
        const body = init && init.body;
        res.clone().text().then((t) => route(url, body, t)).catch(() => {});
      }
    } catch {}
    return res;
  };

  // XMLHttpRequest
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__lrUrl = String(url);
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    const url = this.__lrUrl;
    if (url && (SUBMIT_RE.test(url) || CHECK_RE.test(url))) {
      this.addEventListener("load", () => {
        try {
          route(url, body, this.responseText);
        } catch {}
      });
    }
    return origSend.apply(this, arguments);
  };
})();
