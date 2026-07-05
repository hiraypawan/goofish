import os, base64, json, urllib.request
from io import BytesIO
from PIL import Image

KEY = os.environ["OPENROUTER_API_KEY"]

img = Image.open("/tmp/captcha_test.png")
print("Full image:", img.size)
crop = img.crop((560, 295, 800, 625))
crop.save("/tmp/captcha_crop.png")
print("Cropped:", crop.size)

buf = BytesIO()
crop.convert("RGB").save(buf, format="JPEG", quality=80)
b64 = base64.b64encode(buf.getvalue()).decode()

prompt = """This is a CAPTCHA. At the top there is Chinese instruction text (stylized/distorted). Below is a 3x3 grid of 9 photo tiles.
List ALL 9 objects you see in the grid, reading left-to-right, top-to-bottom, numbered 1-9.
Also tell me what the top instruction text says if you can read it.
Be concise."""

models = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]

for model in models:
    print("\n" + "="*60)
    print("MODEL:", model)
    print("="*60)
    payload = {
        "model": model,
        "messages": [{"role":"user","content":[
            {"type":"text","text":prompt},
            {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}
        ]}],
        "temperature": 0.1,
        "max_tokens": 600,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type":"application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
            print(data["choices"][0]["message"]["content"])
    except Exception as e:
        print("ERROR:", e)
        try:
            print(e.read().decode()[:300])
        except:
            pass
