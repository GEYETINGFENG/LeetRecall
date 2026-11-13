# End-to-end test: loads the unpacked extension in Chrome, serves a mock LeetCode
# problem page, and checks that Run / Wrong Answer are ignored, AC opens the panel,
# rating schedules the card, and the review page works from the keyboard.
# Usage: pip install playwright && CHROME=/path/to/chrome-for-testing python tests/e2e_mock_leetcode.py
import json, asyncio, time
from playwright.async_api import async_playwright
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = ROOT
OUT = os.environ.get("LR_OUT", "/tmp/leetrecall-e2e"); os.makedirs(OUT, exist_ok=True)
# Needs Chrome for Testing or Chromium: branded Google Chrome ignores --load-extension.
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
PAGE = """<!doctype html><html><head><title>1. Two Sum - LeetCode</title></head><body style="background:#1a1a1a;color:#ddd;font-family:sans-serif;padding:30px">
<h1>1. Two Sum (mock)</h1><p>Fake problem page for testing.</p>
<button id="run">Run</button> <button id="sub">Submit</button> <button id="subwa">Submit (wrong)</button>
<script>
async function poll(id){ const r = await fetch('/submissions/detail/'+id+'/check/'); return r.json(); }
document.getElementById('run').onclick = async()=>{ await poll('runcode_1'); };
document.getElementById('subwa').onclick = async()=>{ const r = await fetch('/problems/two-sum/submit/',{method:'POST',body:JSON.stringify({lang:'python3',typed_code:'wrong'})}); const j=await r.json(); await poll(j.submission_id); };
document.getElementById('sub').onclick = ()=>{ const x=new XMLHttpRequest(); x.open('POST','/problems/two-sum/submit/'); x.onload=()=>{ poll(JSON.parse(x.responseText).submission_id); }; x.send(JSON.stringify({lang:'python3',typed_code:'class Solution:\\n    def twoSum(self, nums, target):\\n        seen = {}\\n        for i, x in enumerate(nums):\\n            if target - x in seen: return [seen[target-x], i]\\n            seen[x] = i'})); };
</script></body></html>"""
sub_id=[100]
async def handler(route):
    url=route.request.url
    if "/graphql" in url:
        return await route.fulfill(json={"data":{"question":{"questionFrontendId":"1","title":"Two Sum","difficulty":"Easy","topicTags":[{"name":"Array"},{"name":"Hash Table"}]}}})
    if url.endswith("/submit/"):
        sub_id[0]+=1; return await route.fulfill(json={"submission_id":sub_id[0]})
    if "/check/" in url:
        sid=url.split("/detail/")[1].split("/")[0]
        if sid.startswith("runcode"): return await route.fulfill(json={"state":"SUCCESS","status_code":10,"status_msg":"Accepted","run_success":True})
        acc = sub_id[0]!=101  # first submit is the wrong one
        return await route.fulfill(json={"state":"SUCCESS","status_code":10 if acc else 11,"status_msg":"Accepted" if acc else "Wrong Answer","status_runtime":"3 ms","status_memory":"17 MB","lang":"python3"})
    return await route.fulfill(body=PAGE, content_type="text/html")

async def shadow_click(page, sel):
    await page.evaluate("s=>document.getElementById('leetrecall-host').shadowRoot.querySelector(s).click()", sel)

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(OUT + "/profile", executable_path=CHROME, headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"], viewport={"width":1280,"height":820})
        sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
        ext_id = sw.url.split("/")[2]; print("ext", ext_id)
        logs=[]
        await ctx.route("https://leetcode.com/**", handler)
        page = await ctx.new_page()
        page.on("console", lambda m: logs.append(m.text)); page.on("pageerror", lambda e: logs.append("PAGEERR "+str(e)))
        await page.goto("https://leetcode.com/problems/two-sum/description/")
        await page.wait_for_timeout(1500)
        await page.click("#run"); await page.wait_for_timeout(800)
        n_panel = await page.evaluate("!!document.getElementById('leetrecall-host')?.shadowRoot.querySelector('.panel')")
        print("panel after Run (should be False):", n_panel)
        await page.click("#subwa"); await page.wait_for_timeout(800)
        print("panel after WA (should be False):", await page.evaluate("!!document.getElementById('leetrecall-host').shadowRoot.querySelector('.panel')"))
        await page.click("#sub"); await page.wait_for_timeout(1200)
        print("panel after AC:", await page.evaluate("!!document.getElementById('leetrecall-host').shadowRoot.querySelector('.panel')"))
        await page.screenshot(path=f"{OUT}/1_panel.png")
        await page.evaluate("""()=>{const r=document.getElementById('leetrecall-host').shadowRoot; const t=r.querySelector('.idea'); t.value='哈希表存 值→下标；遍历时先查 target-x 在不在表里，再把自己放进去'; r.querySelector('.cx').value='O(n) / O(n)'; r.querySelector('.pit').value='先查再存，避免同一个元素用两次'; [...r.querySelectorAll('.presets .chip')].find(c=>c.dataset.p==='哈希表').click();}""")
        await page.wait_for_timeout(200)
        await page.screenshot(path=f"{OUT}/2_panel_filled.png")
        await shadow_click(page, '.rate[data-g="3"]'); await page.wait_for_timeout(800)
        print("fab:", await page.evaluate("document.getElementById('leetrecall-host').shadowRoot.querySelector('.fab').textContent"))
        await page.screenshot(path=f"{OUT}/3_after.png")
        app = await ctx.new_page(); app.on("pageerror", lambda e: logs.append("APPERR "+str(e)))
        await app.goto(f"chrome-extension://{ext_id}/pages/app.html#library"); await app.wait_for_timeout(600)
        # seed extra cards and make them due today
        await app.evaluate("""async()=>{ const r=await chrome.storage.local.get('cards'); const c=r.cards; const now=Date.now();
          c['two-sum'].sched.due=now-1000; c['two-sum'].sched.last=now-5*864e5;
          const mk=(slug,id,title,diff,pat,idea,s,daysAgo)=>({slug,id,title,titleCn:'',difficulty:diff,tags:[],patterns:pat,idea,complexity:'O(n)',pitfalls:'',code:'',lang:'',site:'com',createdAt:now-daysAgo*864e5,updatedAt:now,suspended:false,
            sched:{state:'review',s,d:5,due:now-1000,last:now-daysAgo*864e5,reps:2,lapses:0},history:[{t:now-daysAgo*864e5,g:3,mode:'card',wasNew:false},{t:now-864e5,g:3,mode:'card',wasNew:false}],stats:{}});
          c['largest-rectangle-in-histogram']=mk('largest-rectangle-in-histogram','84','Largest Rectangle in Histogram','Hard',['单调栈'],'单调递增栈存下标；遇到更矮的柱子就出栈结算：高=出栈柱，宽=i-新栈顶-1。末尾补一个 0 把栈清空',3,9);
          c['minimum-window-substring']=mk('minimum-window-substring','76','Minimum Window Substring','Hard',['滑动窗口','哈希表'],'右指针扩张直到覆盖 t，再收缩左指针更新答案；用 need 计数 + 缺几个字符的变量 O(1) 判断是否覆盖',6,10);
          c['coin-change']=mk('coin-change','322','Coin Change','Medium',['动态规划','背包'],'',4,4);
          await chrome.storage.local.set({cards:c}); }""")
        await app.reload(); await app.wait_for_timeout(600)
        await app.screenshot(path=f"{OUT}/4_library.png", full_page=True)
        await app.goto(f"chrome-extension://{ext_id}/pages/app.html#review"); await app.wait_for_timeout(600)
        await app.screenshot(path=f"{OUT}/5_front.png")
        await app.keyboard.press("Space"); await app.wait_for_timeout(300)
        await app.screenshot(path=f"{OUT}/6_back.png")
        for k in ["3","2","3"]:
            await app.keyboard.press(k); await app.wait_for_timeout(250)
            if k=="2": await app.keyboard.press("Space"); await app.wait_for_timeout(250)
            elif k=="3": await app.keyboard.press("Space"); await app.wait_for_timeout(250)
        await app.screenshot(path=f"{OUT}/7_state.png")
        await app.keyboard.press("4"); await app.wait_for_timeout(400)
        await app.screenshot(path=f"{OUT}/8_done.png")
        await app.goto(f"chrome-extension://{ext_id}/pages/app.html#stats"); await app.wait_for_timeout(600)
        await app.screenshot(path=f"{OUT}/9_stats.png", full_page=True)
        await app.goto(f"chrome-extension://{ext_id}/pages/app.html#settings"); await app.wait_for_timeout(500)
        await app.screenshot(path=f"{OUT}/10_settings.png", full_page=True)
        pop = await ctx.new_page(); await pop.set_viewport_size({"width":340,"height":420})
        await pop.goto(f"chrome-extension://{ext_id}/pages/popup.html"); await pop.wait_for_timeout(500)
        await pop.screenshot(path=f"{OUT}/11_popup.png")
        data = await app.evaluate("async()=>{const c=(await chrome.storage.local.get('cards')).cards; const t=c['two-sum']; return {idea:t.idea, patterns:t.patterns, code:t.code.slice(0,40), attempts:t.stats.attempts, hist:t.history.map(h=>h.mode+':'+h.g), due:new Date(t.sched.due).toString()}}")
        print(json.dumps(data, ensure_ascii=False, indent=1))
        sw_badge = await sw.evaluate("chrome.action.getBadgeText({})")
        print("badge:", sw_badge)
        print("LOGS:", [l for l in logs if 'ERR' in l or 'rror' in l])
        await ctx.close()
asyncio.run(main())
