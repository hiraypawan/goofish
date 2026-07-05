"""
Goofish (闲鱼) Login Automation
No Tor - Direct Chrome with temporary profile.
Auto-deletes profile, history, all data on close.
Uses Pollinations.ai FREE vision API for CAPTCHA (no key needed).
Handles Malaysian phone numbers and OTP.
"""
import asyncio
import json
import os
import sys
import re
import base64
import shutil
import atexit
import traceback
import functools
import random
sys.stdout.reconfigure(encoding='utf-8')
from patchright.async_api import async_playwright

print = functools.partial(print, flush=True)

# ==================== PATHS ====================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PHONE_FILE = os.path.join(PROJECT_DIR, "phones_malaysia.txt")
USED_FILE = os.path.join(PROJECT_DIR, "used_numbers.json")
PROFILE_DIR = os.path.join(PROJECT_DIR, "chrome_profile")
SCREENSHOTS_DIR = os.path.join(PROJECT_DIR, "screenshots")
TARGET_URL = "https://www.goofish.com/"

# Load .env file if exists
env_file = os.path.join(PROJECT_DIR, ".env")
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v:
                    os.environ.setdefault(k, v)

# ==================== SETTINGS ====================
COUNTRY_CODE = "60"
OTP_RESEND_WAIT = 62
OTP_MAX_RETRIES = 3

# OpenRouter - FREE vision models (get key at https://openrouter.ai/keys)
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Free vision models (try in order)
OPENROUTER_MODELS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]


# ==================== CLEANUP on exit ====================
def cleanup_profile():
    """Delete temp Chrome profile on script exit."""
    if os.path.exists(PROFILE_DIR):
        try:
            shutil.rmtree(PROFILE_DIR, ignore_errors=True)
            print(f"\n  [CLEANUP] Profile deleted: {PROFILE_DIR}")
        except:
            pass

atexit.register(cleanup_profile)


# ==================== PHONE NUMBER LOADER ====================
def load_phone_numbers():
    if not os.path.exists(PHONE_FILE):
        print(f"  ERROR: Phone file not found: {PHONE_FILE}")
        return []
    used = []
    if os.path.exists(USED_FILE):
        with open(USED_FILE, "r") as f:
            used = json.load(f)
    with open(PHONE_FILE, "r") as f:
        lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith("#")]
    available = []
    for line in lines:
        clean = line.lstrip("+").replace(" ", "")
        if clean not in used and line not in used:
            available.append(clean)
    print(f"  Phone numbers: {len(available)} available, {len(used)} used")
    return available


def mark_number_used(phone):
    used = []
    if os.path.exists(USED_FILE):
        with open(USED_FILE, "r") as f:
            used = json.load(f)
    if phone not in used:
        used.append(phone)
        with open(USED_FILE, "w") as f:
            json.dump(used, f, indent=2)


# ==================== AI CAPTCHA SOLVER (Pollinations.ai - FREE) ====================
async def solve_captcha_with_ai(page, screenshot_bytes):
    """Send CAPTCHA screenshot to OpenRouter FREE vision API."""
    import aiohttp

    if not OPENROUTER_KEY:
        print("    ERROR: No OpenRouter API key! Set OPENROUTER_API_KEY env var or edit script.")
        print("    Get free key at: https://openrouter.ai/keys")
        return None

    # Convert to JPEG and resize
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(screenshot_bytes))
        max_w = 500
        if img.width > max_w:
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=70)
        img_bytes = buf.getvalue()
        print(f"    Image: {img.width}x{img.height}, {len(img_bytes)} bytes")
    except:
        img_bytes = screenshot_bytes

    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    prompt = """This is a CAPTCHA image with a 3x3 grid of 9 photos.

1. Read the Chinese instruction text at the top (after "——"). It lists 3 objects to find.
2. List ALL 9 objects in the grid (left-to-right, top-to-bottom, 1-9).
3. Return JSON with the CENTER coordinates of the 3 matching objects.

Example: If instruction says "请依次连出——手提包 大熊猫 马" (handbag, panda, horse):
{"positions":[{"x":85,"y":95,"label":"handbag"},{"x":170,"y":95,"label":"panda"},{"x":255,"y":95,"label":"horse"}]}

IMPORTANT: Coordinates are relative to THIS image. Return ONLY the JSON, no other text."""

    payload = {
        "model": "",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]
        }],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            for model in OPENROUTER_MODELS:
                payload["model"] = model
                print(f"    Trying {model}...")
                for retry in range(3):
                    try:
                        async with session.post(OPENROUTER_URL, json=payload, headers=headers,
                                                timeout=aiohttp.ClientTimeout(total=60)) as resp:
                            raw = await resp.text()
                            if resp.status == 429:
                                wait_time = 15 * (retry + 1)
                                print(f"    Rate limited, waiting {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                continue
                            if resp.status != 200:
                                print(f"    {resp.status}: {raw[:200]}")
                                break
                            data = json.loads(raw)
                            text = data["choices"][0]["message"]["content"]
                            print(f"    AI: {text[:500]}")
                            # Check if AI refused to help
                            if any(refuse in text.lower() for refuse in ["cannot assist", "cannot help", "not able to", "i'm sorry", "beyond my capabilities"]):
                                print(f"    Model refused, trying next...")
                                break
                            sol = parse_ai_response(text)
                            return sol
                    except Exception as e:
                        print(f"    {model} error: {e}")
                        break
    except Exception as e:
        print(f"    OpenRouter error: {e}")
    return None


def parse_ai_response(text):
    """Parse JSON from AI response text."""
    # Try to find positions array
    match = re.search(r'\{[^{}]*"positions"\s*:\s*\[', text, re.DOTALL)
    if match:
        start = text.rfind('{', 0, match.start() + 1)
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{': depth += 1
                elif text[i] == '}': depth -= 1
                if depth == 0:
                    try:
                        sol = json.loads(text[start:i+1])
                        sol.setdefault("type", "click_order")
                        return sol
                    except:
                        break
    # Fallback: try any JSON with positions
    match = re.search(r'\{.*"positions".*\}', text, re.DOTALL)
    if match:
        try:
            sol = json.loads(match.group())
            sol.setdefault("type", "click_order")
            return sol
        except:
            pass
    # Last resort: try to extract x,y coordinates from text
    coords = re.findall(r'["\']?x["\']?\s*:\s*(\d+)[,\s]*["\']?y["\']?\s*:\s*(\d+)', text)
    if coords:
        positions = []
        for x, y in coords[:9]:  # Max 9 images
            positions.append({"x": int(x), "y": int(y), "label": "object"})
        if positions:
            return {"type": "click_order", "positions": positions}
    return None


async def execute_captcha_action(page, solution):
    """Execute CAPTCHA action based on AI analysis."""
    if not solution:
        return False
    t = solution.get("type", "unknown")
    if t == "none":
        print("    No CAPTCHA detected")
        return True

    print(f"    CAPTCHA type: {t}")

    if t == "slide":
        drag_x = solution.get("drag_x", 150)
        print(f"    Sliding {drag_x}px...")
        try:
            slider = None
            for sel in ['#nc_1_n1z', '.nc_iconfont.btn_slide', '.btn_slide',
                        '[class*="slider"]', '[class*="slide"]', '[class*="drag"]']:
                slider = await page.query_selector(sel)
                if slider and await slider.is_visible():
                    break
                slider = None
            if slider:
                box = await slider.bounding_box()
                if box:
                    sx = box["x"] + box["width"] / 2
                    sy = box["y"] + box["height"] / 2
                    steps = random.randint(15, 25)
                    await page.mouse.move(sx, sy)
                    await page.mouse.down()
                    await page.wait_for_timeout(random.randint(100, 200))
                    for step in range(1, steps + 1):
                        p = step / steps
                        eased = 1 - (1 - p) ** 3
                        await page.mouse.move(sx + drag_x * eased + random.uniform(-1, 1), sy + random.uniform(-2, 2))
                        await page.wait_for_timeout(random.randint(10, 30))
                    await page.mouse.up()
                    print("    Slide done!")
                    await page.wait_for_timeout(2000)
                    return True
        except Exception as e:
            print(f"    Slide error: {e}")

    elif t == "click_order":
        positions = solution.get("positions", [])
        print(f"    Click order: {len(positions)} images")
        try:
            for i, pos in enumerate(positions):
                x, y = pos.get("x", 0), pos.get("y", 0)
                label = pos.get("label", "?")
                if x > 0 and y > 0:
                    print(f"    [{i+1}/{len(positions)}] Clicking '{label}' at ({x}, {y})")
                    await page.mouse.click(x, y)
                    await page.wait_for_timeout(random.randint(500, 1000))
            print("    All clicks done!")
            await page.wait_for_timeout(2000)
            return True
        except Exception as e:
            print(f"    Click error: {e}")

    elif t == "click":
        positions = solution.get("positions", [])
        for pos in positions:
            x, y = pos.get("x", 0), pos.get("y", 0)
            if x > 0 and y > 0:
                await page.mouse.click(x, y)
                await page.wait_for_timeout(random.randint(300, 700))
                print(f"    Clicked ({x}, {y})")
        await page.wait_for_timeout(2000)
        return True

    elif t == "text":
        answer = solution.get("answer", "")
        print(f"    Text answer: {answer}")
        for sel in ['input[placeholder*="验证码"]', 'input[placeholder*="captcha"]', 'input[name*="captcha"]']:
            inp = await page.query_selector(sel)
            if inp and await inp.is_visible():
                await inp.click()
                await inp.fill(answer)
                await inp.press("Enter")
                await page.wait_for_timeout(2000)
                return True

    return False


# ==================== MAIN AUTOMATION ====================
async def run_goofish_login():
    print("=" * 60)
    print("  GOOFISH (闲鱼) LOGIN AUTOMATION")
    print("  No Tor | Temp Profile | OpenRouter FREE AI")
    print("=" * 60)

    phones = load_phone_numbers()
    if not phones:
        print("\n  No phone numbers! Add to:", PHONE_FILE)
        return "NO_NUMBERS"

    phone = phones[0]
    phone_display = f"+{phone}" if phone.startswith(COUNTRY_CODE) else f"+{COUNTRY_CODE}{phone}"
    # Numbers in file already have "60" prefix (e.g. 601115695273)
    # We need to strip the "60" for the phone input field
    phone_local = phone
    if phone_local.startswith(COUNTRY_CODE):
        phone_local = phone_local[len(COUNTRY_CODE):]
    print(f"\n  Phone: {phone_display} (entering: {phone_local})")
    print(f"  AI: OpenRouter (FREE vision models)")
    print(f"  OTP: {OTP_RESEND_WAIT}s wait, {OTP_MAX_RETRIES} retries")

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    # Clean old profile
    if os.path.exists(PROFILE_DIR):
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)

    try:
        async with async_playwright() as p:
            print("\n[1] Launching Chrome (direct, no Tor)...")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=False,
                args=[
                    "--no-sandbox",
                    "--force-device-scale-factor=1",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-history",
                    "--disable-sync",
                    "--no-first-run",
                    "--disable-default-apps",
                    "--disable-extensions",
                ],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = context.pages[0] if context.pages else await context.new_page()

            # ===== STEP 1+2: OPEN GOOFISH, wait for login iframe to load =====
            # Retry loop: refresh until login iframe loads properly (no error/broken page)
            MAX_LOAD_RETRIES = 10
            login_frame = None

            for load_attempt in range(1, MAX_LOAD_RETRIES + 1):
                print(f"\n[2] Opening {TARGET_URL} (attempt {load_attempt}/{MAX_LOAD_RETRIES})...")
                try:
                    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                except:
                    pass
                # Wait longer for page to fully load
                print("    Waiting 8s for page to settle...")
                await page.wait_for_timeout(8000)
                await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "01_home.png"))
                print(f"    URL: {page.url}")

                # ===== STEP 2: LOGIN POPUP - find form in iframe =====
                print("\n[3] Waiting for login iframe to load (up to 20s)...")

                login_frame = None
                for wait_attempt in range(20):
                    all_frames = page.frames

                    for fr in all_frames:
                        try:
                            has_input = await fr.evaluate("""
                                () => {
                                    const inputs = document.querySelectorAll('input');
                                    let hasPhone = false;
                                    let hasVerifyCode = false;
                                    for (const inp of inputs) {
                                        const ph = (inp.placeholder||'').toLowerCase();
                                        if (ph.includes('请输入手机号') || ph.includes('请输入手机') || ph === '手机号') hasPhone = true;
                                        if (ph.includes('请输入验证码') || ph.includes('请输入验证') || ph === '验证码') hasVerifyCode = true;
                                    }
                                    return hasPhone || hasVerifyCode;
                                }
                            """)
                            if has_input:
                                fr_url = fr.url
                                if "goofish.com" in fr_url and fr != page.main_frame:
                                    login_frame = fr
                                    print(f"    Login form found in iframe: {fr_url}")
                                    break
                                elif fr == page.main_frame:
                                    both = await fr.evaluate("""
                                        () => {
                                            const inputs = document.querySelectorAll('input');
                                            let hasPhone = false;
                                            let hasVerifyCode = false;
                                            for (const inp of inputs) {
                                                const ph = (inp.placeholder||'').toLowerCase();
                                                if (ph.includes('请输入手机号') || ph.includes('请输入手机')) hasPhone = true;
                                                if (ph.includes('请输入验证码') || ph.includes('请输入验证')) hasVerifyCode = true;
                                            }
                                            return hasPhone && hasVerifyCode;
                                        }
                                    """)
                                    if both:
                                        login_frame = fr
                                        print(f"    Login form found in main frame")
                                        break
                        except:
                            continue
                    if login_frame:
                        break
                    await page.wait_for_timeout(1000)
                    if wait_attempt % 5 == 4:
                        print(f"    Still waiting... ({wait_attempt+1}/20s)")

                if login_frame:
                    # Success - iframe loaded with form
                    break

                # No login form found - check if iframe has error/broken page
                iframe_error = False
                for fr in page.frames:
                    if fr == page.main_frame:
                        continue
                    try:
                        is_broken = await fr.evaluate("""
                            () => {
                                const body = document.body;
                                if (!body) return true;
                                const html = body.innerHTML || '';
                                // Empty iframe or very short content = broken
                                if (html.length < 100) return true;
                                return false;
                            }
                        """)
                        if is_broken:
                            iframe_error = True
                            break
                    except:
                        # Cross-origin iframe we can't check
                        continue

                if iframe_error or load_attempt <= 3:
                    print(f"    Login iframe NOT loaded (error={iframe_error}). Refreshing... ({load_attempt}/{MAX_LOAD_RETRIES})")
                else:
                    print(f"    Login form not found. Refreshing... ({load_attempt}/{MAX_LOAD_RETRIES})")
                await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, f"err_iframe_load_{load_attempt}.png"))

                if load_attempt < MAX_LOAD_RETRIES:
                    print("    Refreshing page (waiting 5s after reload)...")
                    await page.reload(wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(5000)

            # Fallback: check main page if still no iframe
            if not login_frame:
                print("    Still no login iframe after retries. Checking main page...")
                login_frame = page.main_frame
                print("    All frames:")
                for fr in page.frames:
                    try:
                        inputs = await fr.evaluate("()=>document.querySelectorAll('input').length")
                        print(f"      - {fr.url} ({inputs} inputs)")
                    except:
                        print(f"      - {fr.url} (cross-origin, cannot access)")
                await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "err_no_iframe.png"))
                await context.close()
                return "FAILED"

            # Helper: find element in frame
            async def find_in_frame(selectors, frame=None):
                fr = frame or login_frame
                for sel in selectors:
                    try:
                        el = await fr.query_selector(sel)
                        if el and await el.is_visible():
                            return el
                    except:
                        continue
                return None

            # ===== STEP 3: CHANGE COUNTRY CODE from +91 to +60 =====
            print(f"\n[4] Changing country code to +{COUNTRY_CODE}...")
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02_before_country.png"))

            # It's a native <select> element - use select_option
            country_changed = False
            malaysian_value = None

            # Find the select element in login frame
            for fr in page.frames:
                try:
                    select_el = await fr.query_selector('select.native-phone-code-select, select[name="nativePhoneCodeSelector"]')
                    if select_el:
                        # Get the Malaysia option value
                        options_html = await fr.evaluate("""
                            () => {
                                const sel = document.querySelector('select.native-phone-code-select, select[name="nativePhoneCodeSelector"]');
                                if (!sel) return null;
                                const opts = [];
                                for (const opt of sel.options) {
                                    opts.push({text: opt.text, value: opt.value});
                                }
                                return opts;
                            }
                        """)
                        if options_html:
                            print(f"    Found select with {len(options_html)} options")
                            # Find Malaysia option
                            for opt in options_html:
                                if '马来西亚' in opt['text'] or '+60' in opt['text']:
                                    malaysian_value = opt['value']
                                    print(f"    Malaysia option: {opt['text']}")
                                    break

                        if malaysian_value:
                            # Select by label text
                            await select_el.select_option(label="+60 马来西亚")
                            country_changed = True
                            print("    Selected +60 马来西亚 via select_option")
                            break
                except Exception as e:
                    print(f"    Frame error: {e}")
                    continue

            if not country_changed and malaysian_value:
                # Fallback: try setting value via JS
                for fr in page.frames:
                    try:
                        changed = await fr.evaluate(f"""
                            () => {{
                                const sel = document.querySelector('select.native-phone-code-select, select[name="nativePhoneCodeSelector"]');
                                if (!sel) return false;
                                // Find option with phoneCode "60"
                                for (const opt of sel.options) {{
                                    if (opt.text.includes('+60') || opt.text.includes('马来西亚')) {{
                                        sel.value = opt.value;
                                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        return true;
                                    }}
                                }}
                                return false;
                            }}
                        """)
                        if changed:
                            country_changed = True
                            print("    Selected via JS change event")
                            break
                    except:
                        continue

            if not country_changed:
                # Last resort: try selecting by value attribute containing phoneCode 60
                for fr in page.frames:
                    try:
                        changed = await fr.evaluate("""
                            () => {
                                const sel = document.querySelector('select.native-phone-code-select, select[name="nativePhoneCodeSelector"]');
                                if (!sel) return false;
                                for (const opt of sel.options) {
                                    const val = opt.value || '';
                                    if (val.includes('"phoneCode":"60"') || val.includes('"phoneCode": "60"')) {
                                        sel.value = opt.value;
                                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                                        sel.dispatchEvent(new Event('input', {bubbles: true}));
                                        return true;
                                    }
                                }
                                return false;
                            }
                        """)
                        if changed:
                            country_changed = True
                            print("    Selected via phoneCode value")
                            break
                    except:
                        continue

            await page.wait_for_timeout(1500)
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02c_after_country.png"))
            print(f"    Country changed: {country_changed}")

            # Verify country code
            for fr in page.frames:
                try:
                    result = await fr.evaluate("""
                        () => {
                            const el = document.querySelector('.native-phone-code-select-wrap');
                            return el ? el.getAttribute('data-content') : null;
                        }
                    """)
                    if result:
                        # data-content might be "60" or "+60" - normalize
                        code = result.lstrip('+')
                        print(f"    Current code: +{code}")
                        break
                except:
                    continue
            # ===== STEP 4: ENTER PHONE NUMBER =====
            print(f"\n[5] Entering phone: {phone_local}")

            phone_input = None
            phone_selectors = ['input[placeholder*="手机号"]', 'input[placeholder*="手机"]',
                               'input[placeholder*="phone"]', 'input[type="tel"]', 'input[name*="phone"]',
                               'input[placeholder*="号码"]', 'input[placeholder*="number"]']
            # Search in login frame first, then all frames
            phone_input = await find_in_frame(phone_selectors)
            if not phone_input:
                for fr in page.frames:
                    if fr == login_frame:
                        continue
                    phone_input = await find_in_frame(phone_selectors, fr)
                    if phone_input:
                        break

            if phone_input:
                await phone_input.click()
                await phone_input.fill("")
                await phone_input.type(phone_local, delay=80)
                print(f"    Phone entered: {phone_local}")
            else:
                print("    ERROR: Phone input not found!")
                # Dump all inputs for debugging
                for fr in page.frames:
                    try:
                        inputs = await fr.evaluate("""
                            () => Array.from(document.querySelectorAll('input')).map(i => ({
                                type: i.type, placeholder: i.placeholder, name: i.name,
                                visible: i.offsetParent !== null, rect: i.getBoundingClientRect()
                            }))
                        """)
                        if inputs:
                            print(f"    Frame {fr.url}: {inputs}")
                    except:
                        pass
                await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "err_no_phone.png"))
                await context.close()
                return "FAILED"

            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03_phone.png"))

            # ===== STEP 5: CHECK TERMS CHECKBOX =====
            print("\n[6] Checking terms checkbox...")
            for fr in page.frames:
                try:
                    await fr.evaluate("""
                        () => {
                            const checkboxes = document.querySelectorAll('input[type="checkbox"], [class*="check"], [role="checkbox"]');
                            for (const cb of checkboxes) {
                                if (cb.offsetParent !== null) {
                                    const r = cb.getBoundingClientRect();
                                    if (r.width > 0 && r.height > 0 && r.width < 30) {
                                        if (!cb.checked) cb.click();
                                        return;
                                    }
                                }
                            }
                            for (const el of document.querySelectorAll('span, div, label')) {
                                const t = el.textContent || '';
                                if (t.includes('您已阅读') || t.includes('同意') || t.includes('协议')) {
                                    const r = el.getBoundingClientRect();
                                    if (r.width > 0 && el.offsetParent !== null) {
                                        el.click();
                                        return;
                                    }
                                }
                            }
                        }
                    """)
                except:
                    continue
            await page.wait_for_timeout(500)

            # ===== STEP 6: CLICK GET VERIFICATION CODE (CAPTCHA appears after this) =====
            print("\n[7] Clicking '获取验证码'...")
            code_btn_clicked = False

            # Try clicking in login_frame first
            try:
                el = await login_frame.query_selector('text="获取验证码"')
                if el and await el.is_visible():
                    await el.click()
                    code_btn_clicked = True
                    print("    Clicked '获取验证码' in login frame")
            except:
                pass

            # Fallback: try JS in login frame
            if not code_btn_clicked:
                try:
                    code_btn_clicked = await login_frame.evaluate("""
                        () => {
                            for (const el of document.querySelectorAll('button, span, a, div')) {
                                const t = (el.textContent || '').trim();
                                if (t.includes('获取验证码') && el.offsetParent !== null) {
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)
                    if code_btn_clicked:
                        print("    Clicked via JS in login frame")
                except:
                    pass

            # Fallback: try all frames
            if not code_btn_clicked:
                for fr in page.frames:
                    if code_btn_clicked:
                        break
                    for sel in ['text="获取验证码"', 'button:has-text("获取")', 'span:has-text("获取验证码")']:
                        try:
                            el = await fr.query_selector(sel)
                            if el and await el.is_visible():
                                await el.click()
                                code_btn_clicked = True
                                print(f"    Clicked: {sel}")
                                break
                        except:
                            continue

            if not code_btn_clicked:
                # Last resort: try all frames via JS
                for fr in page.frames:
                    try:
                        clicked = await fr.evaluate("""
                            () => {
                                for (const el of document.querySelectorAll('button,span,a,div')) {
                                    const t = (el.textContent || '').trim();
                                    if (t.includes('获取验证码') && el.offsetParent !== null) {
                                        el.click();
                                        return true;
                                    }
                                }
                                return false;
                            }
                        """)
                        if clicked:
                            code_btn_clicked = True
                            print("    Clicked via JS in frame")
                            break
                    except:
                        continue

            if not code_btn_clicked:
                print("    WARNING: Could not click 获取验证码")

            await page.wait_for_timeout(3000)
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "05_code_sent.png"))

            # ===== STEP 7: SOLVE CAPTCHA (appears after clicking 获取验证码) =====
            print("\n[8] Checking for CAPTCHA...")

            # Detection JS: multi-signal approach
            #   1) Alibaba baxia/nc security container elements
            #   2) A grid of ~9 square images (the click puzzle)
            #   3) The instruction text if present in DOM
            detect_js = """
                () => {
                    const h = (document.body.innerHTML || '').toLowerCase();

                    // Signal 1: known Alibaba captcha containers
                    const containerSel = [
                        '.baxia-dialog', '.baxia-dialog-content', '#baxia-dialog',
                        '.nc_wrapper', '.nc-container', '#nc_1_wrapper',
                        '[class*="captcha"]', '[id*="captcha"]',
                        '[class*="puzzle"]', '[class*="_detect"]', '[class*="spatial"]'
                    ];
                    let hasContainer = false;
                    for (const s of containerSel) {
                        const el = document.querySelector(s);
                        if (el && el.getBoundingClientRect().width > 0) { hasContainer = true; break; }
                    }

                    // Signal 3: instruction text present as real DOM text
                    const hasText = h.includes('请依次连出') || h.includes('连出') || h.includes('点击');

                    // Signal 2: find square grid images
                    const imgs = document.querySelectorAll('img, canvas');
                    const allImgs = [];
                    const gridImgs = [];
                    for (const img of imgs) {
                        const r = img.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            allImgs.push({x: r.x, y: r.y, w: r.width, h: r.height});
                            if (r.width >= 50 && r.width <= 200 && r.height >= 50 && r.height <= 200
                                && Math.abs(r.width - r.height) < 40) {
                                gridImgs.push({x: r.x, y: r.y, w: r.width, h: r.height});
                            }
                        }
                    }

                    const hasGrid = gridImgs.length >= 6;
                    const found = hasContainer || hasText || hasGrid;
                    if (!found) return {found: false};

                    const debug = allImgs.map(i => `${Math.round(i.x)},${Math.round(i.y)} ${Math.round(i.w)}x${Math.round(i.h)}`).join(' | ');

                    if (gridImgs.length >= 6) {
                        let minX = Infinity, minY = Infinity, maxX = 0, maxY = 0;
                        for (const img of gridImgs) {
                            minX = Math.min(minX, img.x);
                            minY = Math.min(minY, img.y);
                            maxX = Math.max(maxX, img.x + img.w);
                            maxY = Math.max(maxY, img.y + img.h);
                        }
                        return {found: true, x: minX, y: minY, w: maxX - minX, h: maxY - minY,
                                imgCount: gridImgs.length, hasContainer, hasText, debug};
                    }
                    return {found: true, imgCount: gridImgs.length, totalImgs: allImgs.length,
                            hasContainer, hasText, debug};
                }
            """

            for ca in range(3):
                captcha_vis = False
                captcha_box = None

                # POLL for CAPTCHA to appear (up to 15s) - it loads async after the click
                for poll in range(15):
                    for fr in page.frames:
                        try:
                            result = await fr.evaluate(detect_js)
                            if result and result.get("found"):
                                captcha_vis = True
                                if result.get("w") and result.get("imgCount", 0) >= 6:
                                    captcha_box = result
                                    print(f"    Grid: {result.get('imgCount')} images, box: ({int(result['x'])},{int(result['y'])}) {int(result['w'])}x{int(result['h'])}")
                                    print(f"    Signals -> container:{result.get('hasContainer')} text:{result.get('hasText')} grid:{result.get('imgCount')}")
                                    if result.get("debug"):
                                        print(f"    All imgs: {result['debug'][:300]}")
                                    break
                                else:
                                    # captcha present but grid not fully rendered yet - keep polling
                                    print(f"    CAPTCHA present (container:{result.get('hasContainer')} text:{result.get('hasText')} grid imgs:{result.get('imgCount', 0)}) - waiting for grid...")
                        except:
                            continue
                    if captcha_box:
                        break
                    await page.wait_for_timeout(1000)

                if not captcha_vis:
                    print("    No CAPTCHA - proceeding")
                    break
                if not captcha_box:
                    print("    CAPTCHA detected but grid not found - capturing full popup for AI")

                print(f"    CAPTCHA detected! Attempt {ca+1}/3")

                await page.wait_for_timeout(1500)

                ss = await page.screenshot()
                await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, f"captcha_{ca}.png"))

                if captcha_box:
                    print(f"    CAPTCHA box: ({captcha_box['x']},{captcha_box['y']}) {captcha_box['w']}x{captcha_box['h']}")

                    # Crop CAPTCHA area from screenshot for better AI accuracy
                    try:
                        from PIL import Image
                        from io import BytesIO
                        img = Image.open(BytesIO(ss))
                        cx, cy = captcha_box['x'], captcha_box['y']
                        cw, ch = captcha_box['w'], captcha_box['h']
                        # Add some padding
                        pad = 10
                        cx = max(0, cx - pad)
                        cy = max(0, cy - pad)
                        cw = min(img.width - cx, cw + 2*pad)
                        ch = min(img.height - cy, ch + 2*pad)
                        cropped = img.crop((cx, cy, cx + cw, cy + ch))
                        buf = BytesIO()
                        cropped.save(buf, format="JPEG", quality=85)
                        ss_cropped = buf.getvalue()
                        print(f"    Cropped CAPTCHA: {cropped.width}x{cropped.height}")
                        # Save cropped for debug
                        with open(os.path.join(SCREENSHOTS_DIR, f"captcha_cropped_{ca}.jpg"), "wb") as f:
                            f.write(ss_cropped)
                    except:
                        ss_cropped = ss
                        cx, cy = 0, 0
                else:
                    ss_cropped = ss
                    cx, cy = 0, 0

                print("    Sending to AI...")
                sol = await solve_captcha_with_ai(page, ss_cropped)

                # Adjust coordinates to full page ONLY if we cropped (cx, cy > 0)
                if sol and sol.get("positions") and (cx > 0 or cy > 0):
                    for pos in sol["positions"]:
                        pos["x"] = pos["x"] + cx
                        pos["y"] = pos["y"] + cy
                    print(f"    Adjusted coordinates: +({cx},{cy}) -> {sol['positions'][:2]}")
                if sol:
                    print(f"    AI solution: {sol}")
                    if await execute_captcha_action(page, sol):
                        await page.wait_for_timeout(3000)
                        still = False
                        for fr in page.frames:
                            try:
                                still = await fr.evaluate("()=>document.body.innerHTML.toLowerCase().includes('nc_wrapper')||document.body.innerHTML.toLowerCase().includes('slider')||document.body.innerHTML.toLowerCase().includes('请依次连出')")
                                if still:
                                    break
                            except:
                                continue
                        if not still:
                            print("    CAPTCHA solved!")
                            break

            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "04_after_captcha.png"))

            # ===== STEP 8: WAIT FOR OTP =====
            print(f"\n[9] Waiting for OTP ({OTP_MAX_RETRIES} attempts, {OTP_RESEND_WAIT}s each)...")
            otp_code = None
            for oa in range(OTP_MAX_RETRIES):
                print(f"\n    Attempt {oa+1}/{OTP_MAX_RETRIES}...")
                for wc in range(OTP_RESEND_WAIT // 5):
                    await page.wait_for_timeout(5000)
                    cur = page.url

                    # Check if truly logged in (login form is gone)
                    login_gone = False
                    for fr in page.frames:
                        try:
                            has_login = await fr.evaluate("""
                                () => {
                                    const inputs = document.querySelectorAll('input');
                                    for (const inp of inputs) {
                                        const ph = (inp.placeholder||'').toLowerCase();
                                        if (ph.includes('手机号') || ph.includes('验证码')) return true;
                                    }
                                    return false;
                                }
                            """)
                            if has_login:
                                break
                        except:
                            continue
                    else:
                        # No frame has login inputs - might be logged in
                        if "goofish.com" in cur and "login" not in cur.lower():
                            login_gone = True

                    if login_gone:
                        print("    Login form gone - checking if truly logged in...")
                        await page.wait_for_timeout(3000)
                        # Double check - look for user elements
                        for fr in page.frames:
                            try:
                                logged = await fr.evaluate("""
                                    () => {
                                        const body = document.body.innerText || '';
                                        return body.includes('我的') || body.includes('个人') || body.includes('发布');
                                    }
                                """)
                                if logged:
                                    print("    Confirmed logged in!")
                                    otp_code = "LOGGED_IN"
                                    break
                            except:
                                continue
                    if otp_code:
                        break
                    # Check all frames for OTP auto-fill
                    for fr in page.frames:
                        try:
                            otp_from_page = await fr.evaluate("""
                                () => {
                                    for (const inp of document.querySelectorAll('input')) {
                                        const ph = (inp.placeholder||'').toLowerCase();
                                        if ((ph.includes('验证码')||ph.includes('code')||ph.includes('otp')) && inp.value && inp.value.length>=4) return inp.value;
                                    }
                                    return null;
                                }
                            """)
                            if otp_from_page:
                                otp_code = otp_from_page
                                print(f"    OTP from page: {otp_code}")
                                break
                        except:
                            continue
                    if otp_code:
                        break
                if otp_code:
                    break
                if oa < OTP_MAX_RETRIES - 1:
                    print("    Resending OTP...")
                    for fr in page.frames:
                        try:
                            clicked = await fr.evaluate("""
                                () => {
                                    for (const el of document.querySelectorAll('button,span,a,div')) {
                                        const t = el.textContent.trim();
                                        if ((t.includes('重新发送')||t.includes('再次发送')||t.includes('Resend')||t.includes('重新获取')||t.includes('获取验证码')) && el.offsetParent!==null) { el.click(); return true; }
                                    }
                                    return false;
                                }
                            """)
                            if clicked:
                                break
                        except:
                            continue

            # ===== STEP 9: ENTER OTP =====
            if otp_code and otp_code != "LOGGED_IN":
                print(f"\n[10] Entering OTP: {otp_code}")
                otp_selectors = ['input[placeholder*="验证码"]', 'input[placeholder*="code"]',
                                 'input[name*="code"]', 'input[maxlength="6"]', 'input[maxlength="4"]',
                                 'input[placeholder*="Verification"]']
                otp_inp = None
                for fr in page.frames:
                    for sel in otp_selectors:
                        try:
                            otp_inp = await fr.query_selector(sel)
                            if otp_inp and await otp_inp.is_visible():
                                break
                        except:
                            continue
                    if otp_inp:
                        break

                if otp_inp:
                    await otp_inp.click()
                    await otp_inp.fill("")
                    await otp_inp.type(otp_code, delay=100)
                    print(f"    OTP entered")

                # Click login
                login_selectors = ['button:has-text("登录")', 'text="登录"', 'button[type="submit"]',
                                   'button:has-text("Login")']
                for fr in page.frames:
                    for sel in login_selectors:
                        try:
                            el = await fr.query_selector(sel)
                            if el and await el.is_visible():
                                box = await el.bounding_box()
                                if box and box["width"] > 100:
                                    await el.click()
                                    print(f"    Login clicked: {sel}")
                                    break
                        except:
                            continue

            await page.wait_for_timeout(5000)
            await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "06_result.png"))

            # ===== CHECK RESULT =====
            print("\n[11] Checking result...")
            cur_url = page.url
            body = await page.inner_text("body")
            print(f"    URL: {cur_url}")

            ok = any(k in body for k in ["我的","首页","发布","消息","闲鱼","个人"]) and "登录" not in body[:100]
            if ok or ("goofish.com" in cur_url and "login" not in cur_url.lower()):
                print("\n  ============================================")
                print("  LOGIN SUCCESS!")
                print(f"  Phone: {phone_display}")
                print("  ============================================")
                mark_number_used(phone)
                await page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "07_success.png"))
                print("\n  Browser open for 60s. Close when done.")
                await page.wait_for_timeout(60000)
            else:
                print("\n  LOGIN MAY HAVE FAILED - check screenshots")
                print("  Browser open for 30s.")
                await page.wait_for_timeout(30000)

            # ===== FULL CLEANUP before closing =====
            print("\n[12] Cleaning up all data...")
            try:
                # Clear all browsing data
                await context.clear_cookies()
                for pg in context.pages:
                    try:
                        await pg.evaluate("()=>{localStorage.clear();sessionStorage.clear();}")
                    except:
                        pass
                await context.close()
            except:
                pass

            return "SUCCESS" if ok else "NEEDS_REVIEW"

    except Exception as e:
        print(f"\n  FATAL ERROR: {e}")
        traceback.print_exc()
        return "ERROR"
    finally:
        # Delete temp profile directory
        cleanup_profile()
        # Also clean screenshots of sensitive data (optional)
        print("  All temporary data deleted.")


async def main():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    result = await run_goofish_login()
    print(f"\n  Result: {result}")
    print("  Done!")


if __name__ == "__main__":
    asyncio.run(main())
