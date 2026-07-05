"""
Goofish DEBUG SCRIPT - with iframe support
Opens browser, dumps ALL elements in main page AND iframes.
Share the output so I can fix the selectors.
"""
import asyncio
import os
import sys
import json
import shutil
import functools
sys.stdout.reconfigure(encoding='utf-8')
from patchright.async_api import async_playwright

print = functools.partial(print, flush=True)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(PROJECT_DIR, "chrome_profile_debug")
SCREENSHOTS_DIR = os.path.join(PROJECT_DIR, "screenshots")


async def main():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    print("=" * 60)
    print("  GOOFISH DEBUG (with iframes)")
    print("=" * 60)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # ===== OPEN GOOFISH =====
        print("\n[1] Opening goofish.com...")
        try:
            await page.goto("https://www.goofish.com/", wait_until="domcontentloaded", timeout=30000)
        except:
            pass
        await page.wait_for_timeout(5000)
        await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "debug_01.png"))

        # ===== LIST ALL FRAMES =====
        print("\n[2] ALL FRAMES:")
        for i, fr in enumerate(page.frames):
            print(f"  Frame {i}: {fr.url}")
            # Check for elements in this frame
            try:
                inputs = await fr.evaluate("""
                    () => {
                        const results = [];
                        for (const inp of document.querySelectorAll('input, textarea')) {
                            const r = inp.getBoundingClientRect();
                            if (r.width > 0) {
                                results.push({
                                    type: inp.type || '',
                                    id: inp.id || '',
                                    name: inp.name || '',
                                    placeholder: inp.placeholder || '',
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                });
                            }
                        }
                        return results;
                    }
                """)
                if inputs:
                    print(f"    {len(inputs)} inputs found:")
                    for inp in inputs:
                        print(f"      - type={inp['type']} id=#{inp['id']} placeholder='{inp['placeholder']}' pos=({inp['x']},{inp['y']}) size={inp['w']}x{inp['h']}")
                else:
                    print(f"    No inputs")
            except Exception as e:
                print(f"    CROSS-ORIGIN (cannot access): {e}")

        # ===== FIND COUNTRY CODES IN ALL FRAMES =====
        print("\n[3] COUNTRY CODES (+xx) in all frames:")
        for i, fr in enumerate(page.frames):
            try:
                codes = await fr.evaluate("""
                    () => {
                        const results = [];
                        for (const el of document.querySelectorAll('span, div, a, button')) {
                            const t = (el.textContent || '').trim();
                            if (t.match(/^\\+\\d{1,4}$/) && el.offsetParent !== null) {
                                const r = el.getBoundingClientRect();
                                results.push({
                                    tag: el.tagName,
                                    text: t,
                                    class: (el.className || '').substring(0, 80),
                                    x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                                    w: Math.round(r.width),
                                });
                            }
                        }
                        return results;
                    }
                """)
                if codes:
                    print(f"  Frame {i}:")
                    for c in codes:
                        print(f"    <{c['tag']}> '{c['text']}' class='{c['class']}' pos=({c['x']},{c['y']})")
            except:
                pass

        # ===== FIND ALL BUTTONS IN ALL FRAMES =====
        print("\n[4] BUTTONS in all frames:")
        for i, fr in enumerate(page.frames):
            try:
                btns = await fr.evaluate("""
                    () => {
                        const results = [];
                        for (const el of document.querySelectorAll('button, [role="button"], span.btn, div.btn')) {
                            const r = el.getBoundingClientRect();
                            const t = (el.textContent || '').trim().substring(0, 60);
                            if (r.width > 0 && el.offsetParent !== null && t) {
                                results.push({
                                    tag: el.tagName,
                                    text: t,
                                    class: (el.className || '').substring(0, 80),
                                    x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                                });
                            }
                        }
                        return results;
                    }
                """)
                if btns:
                    print(f"  Frame {i}:")
                    for b in btns:
                        print(f"    <{b['tag']}> '{b['text']}' class='{b['class']}' pos=({b['x']},{b['y']})")
            except:
                pass

        # ===== LOG ALL CLICKS =====
        clicks_log = []

        async def on_click(click_event):
            try:
                info = await page.evaluate("""(evt) => {
                    const el = document.elementFromPoint(evt.clientX, evt.clientY);
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return {
                        tag: el.tagName,
                        id: el.id || '',
                        class: el.className ? el.className.substring(0, 150) : '',
                        text: (el.textContent || '').trim().substring(0, 80),
                        placeholder: el.placeholder || '',
                        type: el.type || '',
                        name: el.name || '',
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        width: Math.round(r.width),
                        height: Math.round(r.height),
                    };
                }""", {"clientX": click_event.x, "clientY": click_event.y})
                if info:
                    clicks_log.append(info)
                    print(f"\n  [CLICK #{len(clicks_log)}] <{info['tag']}> '{info['text'][:40]}' pos=({info['x']},{info['y']}) size={info['width']}x{info['height']}")
            except:
                pass

        page.on("click", on_click)

        # ===== WAIT FOR USER =====
        print("\n" + "=" * 60)
        print("  BROWSER OPEN - Click around the login form")
        print("  Close browser when done")
        print("=" * 60)

        try:
            while True:
                await page.wait_for_timeout(2000)
                if page.is_closed():
                    break
        except:
            pass

        # Save log
        log_path = os.path.join(SCREENSHOTS_DIR, "debug_click_log.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(clicks_log, f, indent=2, ensure_ascii=False)

        # Cleanup
        await context.close()
        if os.path.exists(PROFILE_DIR):
            shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        print("  Debug done!")


if __name__ == "__main__":
    asyncio.run(main())
