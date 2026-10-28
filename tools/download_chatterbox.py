# -*- coding: utf-8 -*-
"""Чанковая загрузка весов Chatterbox с ModelScope (CDN рвёт длинные сессии)."""
import os
import time

import httpx

REPO = "ResembleAI/chatterbox"
BASE = f"https://www.modelscope.cn/models/{REPO}/resolve/master"
DST = r"C:\aura_os\models\chatterbox"
FILES = [
    "t3_mtl23ls_v2.safetensors",
    "s3gen.pt",
]
CHUNK = 16 * 1024 * 1024

os.makedirs(DST, exist_ok=True)

with httpx.Client(timeout=30) as c:
    meta = c.get(
        f"https://www.modelscope.cn/api/v1/models/{REPO}/repo/files",
        params={"Revision": "master"},
    ).json()
sizes = {f["Path"]: f["Size"] for f in meta["Data"]["Files"]}


def download(name, total):
    dst = os.path.join(DST, name)
    url = f"{BASE}/{name}"
    have = os.path.getsize(dst) if os.path.exists(dst) else 0
    t0 = time.time()
    while have < total:
        end = min(have + CHUNK - 1, total - 1)
        ok = False
        for attempt in range(5):
            try:
                with httpx.Client(timeout=60, follow_redirects=True) as c:
                    r = c.get(url, headers={"Range": f"bytes={have}-{end}"})
                if r.status_code not in (200, 206) or not r.content:
                    raise RuntimeError(f"HTTP {r.status_code}, {len(r.content)} bytes")
                with open(dst, "ab") as f:
                    f.write(r.content)
                have += len(r.content)
                ok = True
                break
            except Exception as e:
                print(f"  {name}: retry {attempt + 1}/5 ({type(e).__name__}: {str(e)[:60]})",
                      flush=True)
                time.sleep(2)
        if not ok:
            print(f"FAIL {name} на {have/1e6:.0f} MB", flush=True)
            return False
        if int(have / CHUNK) % 8 == 0:
            rate = have / 1e6 / max(time.time() - t0, 1)
            print(f"  {name}: {have/1e6:.0f}/{total/1e6:.0f} MB ({rate:.1f} MB/s)",
                  flush=True)
    print(f"DONE {name}: {have/1e6:.0f} MB за {time.time()-t0:.0f}s", flush=True)
    return True


for name in FILES:
    total = sizes.get(name, 0)
    if not total:
        print(f"SKIP {name}: нет размера", flush=True)
        continue
    dst = os.path.join(DST, name)
    if os.path.exists(dst) and os.path.getsize(dst) == total:
        print(f"OK уже есть: {name} ({total/1e6:.0f} MB)", flush=True)
        continue
    if not download(name, total):
        break
print("ALL DONE", flush=True)
