# -*- coding: utf-8 -*-
"""Скачивание файла через headless Chrome по CDP (обходит диалог сохранения)."""
import asyncio
import json
import os
import sys
import time

import httpx
import websockets

PORT = 9223


async def main(url: str, dest_dir: str, timeout: int = 1800) -> int:
    os.makedirs(dest_dir, exist_ok=True)
    version = httpx.get(f"http://127.0.0.1:{PORT}/json/version", timeout=5).json()
    ws_url = version["webSocketDebuggerUrl"]
    counter = iter(range(1, 10_000))

    async with websockets.connect(ws_url, max_size=None) as ws:
        async def cmd(method, params=None, sid=None):
            mid = next(counter)
            msg = {"id": mid, "method": method, "params": params or {}}
            if sid:
                msg["sessionId"] = sid
            await ws.send(json.dumps(msg))
            while True:
                raw = await ws.recv()
                data = json.loads(raw)
                if data.get("id") == mid:
                    return data

        await cmd("Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": dest_dir,
            "eventsEnabled": True,
        })
        target = await cmd("Target.createTarget", {"url": "about:blank"})
        target_id = target["result"]["targetId"]
        attached = await cmd("Target.attachToTarget",
                            {"targetId": target_id, "flatten": True})
        sid = attached["result"]["sessionId"]
        print("navigate:", url, flush=True)
        await cmd("Page.navigate", {"url": url}, sid)

        t0 = time.time()
        last = -1
        while time.time() - t0 < timeout:
            await asyncio.sleep(3)
            parts = []
            for name in os.listdir(dest_dir):
                p = os.path.join(dest_dir, name)
                if os.path.isfile(p):
                    parts.append((os.path.getsize(p), name))
            if not parts:
                continue
            size, name = max(parts)
            if size != last:
                print(f"  {name}: {size / 1e6:.1f} MB "
                      f"({size / 1e6 / max(time.time() - t0, 1):.1f} MB/s)", flush=True)
                last = size
            downloading = any(n.endswith(".crdownload") for _, n in parts)
            if not downloading and size > 0:
                print(f"DONE {name}: {size / 1e6:.1f} MB за {time.time() - t0:.0f}s",
                      flush=True)
                return size
        print("TIMEOUT", flush=True)
        return 0


if __name__ == "__main__":
    url, dest = sys.argv[1], sys.argv[2]
    size = asyncio.run(main(url, dest))
    print("RESULT", size)
