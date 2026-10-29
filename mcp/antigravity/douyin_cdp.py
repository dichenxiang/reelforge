#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抖音网页视频抓取（CDP 直连）。
绕开 yt-dlp 的 a_bogus 签名问题：用真实 Chrome 打开页面，
监听网络请求拿到播放器实际请求的视频流地址，再下载。

用法:
  python douyin_cdp.py grab  "<url>" [--wait 20] [--out out.mp4]
  python douyin_cdp.py probe "<url>" [--wait 20]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

import requests
import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def normalize(url: str) -> str:
    """把 jingxuan?modal_id=xxx 之类的链接转成 /video/xxx。"""
    m = re.search(r"modal_id=(\d+)", url)
    if m:
        return f"https://www.douyin.com/video/{m.group(1)}"
    m = re.search(r"/share/video/(\d+)", url)
    if m:
        return f"https://www.douyin.com/video/{m.group(1)}"
    return url


def is_video_url(u: str) -> bool:
    if not u:
        return False
    keys = ("douyinvod.com", "/video/tos/", "mime_type=video", "media-video")
    if any(k in u for k in keys):
        return True
    if u.split("?")[0].lower().endswith((".mp4", ".m3u8", ".webm")):
        return True
    return False


def launch(url: str, port: int, udd: str) -> subprocess.Popen:
    args = [
        CHROME,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={udd}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--autoplay-policy=no-user-gesture-required",
        "--mute-audio",
        "--window-size=1400,900",
        url,
    ]
    return subprocess.Popen(args)


def find_ws(port: int, timeout: float = 30.0) -> str | None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2).read()
            data = json.loads(raw)
            pages = [d for d in data if d.get("type") == "page"]
            if pages:
                pages.sort(key=lambda d: 0 if "douyin" in (d.get("url") or "") else 1)
                return pages[0].get("webSocketDebuggerUrl")
        except Exception:
            pass
        time.sleep(0.5)
    return None


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=5)
        self.mid = 0
        self.media: list[str] = []
        self.title = ""
        self.page_url = ""

    def send(self, method: str, params: dict | None = None) -> int:
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params or {}}))
        return self.mid

    def pump(self, seconds: float, eval_every: float = 4.0) -> None:
        t0 = time.time()
        last_eval = 0.0
        while time.time() - t0 < seconds:
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                continue
            m = msg.get("method")
            if m == "Network.requestWillBeSent":
                u = (msg.get("params", {}).get("request", {}) or {}).get("url", "")
                if is_video_url(u) and u not in self.media:
                    self.media.append(u)
            elif m == "Page.frameNavigated":
                fr = msg.get("params", {}).get("frame", {}) or {}
                if not fr.get("parentId"):
                    self.page_url = fr.get("url", "")
            elif m == "Runtime.executionContextCreated":
                pass
            # 定期戳一下播放器 + 读标题
            now = time.time() - t0
            if now - last_eval > eval_every:
                last_eval = now
                self.send(
                    "Runtime.evaluate",
                    {
                        "expression": (
                            "(()=>{document.querySelectorAll('video').forEach(v=>{"
                            "v.muted=true;if(v.paused){v.play().catch(()=>{})}});"
                            "return document.title})()"
                        ),
                        "returnByValue": True,
                    },
                )

    def evaluate(self, expr: str):
        try:
            mid = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        except Exception:
            return None
        t0 = time.time()
        while time.time() - t0 < 5:
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                break
            if msg.get("id") == mid:
                return msg.get("result", {}).get("result", {}).get("value")
        return None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def cookies_for(ws_url: str, url: str) -> dict:
    """从 CDP 拿当前页面的 cookie。"""
    try:
        ws = websocket.create_connection(ws_url, timeout=5)
        ws.send(json.dumps({"id": 99, "method": "Network.getCookies", "params": {"urls": [url]}}))
        t0 = time.time()
        while time.time() - t0 < 5:
            msg = json.loads(ws.recv())
            if msg.get("id") == 99:
                jar = msg.get("result", {}).get("cookies", []) or []
                ws.close()
                return {c["name"]: c["value"] for c in jar if "name" in c}
        ws.close()
    except Exception:
        pass
    return {}


def download(url: str, out: str, cookies: dict) -> tuple[bool, str]:
    headers = {
        "User-Agent": UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    try:
        with requests.get(url, headers=headers, stream=True, timeout=120, allow_redirects=True) as r:
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            total = 0
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            with open(out, "wb") as f:
                for chunk in r.iter_content(1 << 18):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            return True, f"{total/1024/1024:.2f} MB"
    except Exception as e:
        return False, str(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["probe", "grab"])
    ap.add_argument("url")
    ap.add_argument("--wait", type=float, default=20)
    ap.add_argument("--out", default="douyin.mp4")
    ap.add_argument("--port", type=int, default=9333)
    a = ap.parse_args()

    url = normalize(a.url)
    udd = os.path.join(tempfile.gettempdir(), "cdp_douyin_profile")
    os.makedirs(udd, exist_ok=True)
    print(f"[cdp] 打开: {url}")
    p = launch(url, a.port, udd)
    ws_url = find_ws(a.port)
    if not ws_url:
        print("[cdp] 连不上 Chrome 调试端口")
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        return 1

    cdp = CDP(ws_url)
    cdp.send("Network.enable")
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    print(f"[cdp] 监听 {a.wait:.0f} 秒...")
    cdp.pump(a.wait)

    title = cdp.evaluate("document.title") or ""
    vids = cdp.evaluate(
        "JSON.stringify([...document.querySelectorAll('video')].map(v=>({src:v.currentSrc||v.src,"
        "dur:v.duration, w:v.videoWidth, h:v.videoHeight, paused:v.paused})))"
    )
    cdp.close()

    print(f"[cdp] 页面标题: {title}")
    print(f"[cdp] video 元素: {vids}")
    print(f"[cdp] 捕获视频流 {len(cdp.media)} 条")
    for i, u in enumerate(cdp.media[:6]):
        print(f"  [{i}] {u[:160]}")

    rc = 0
    if a.action == "grab":
        vids_ = [u for u in cdp.media if ("media-video" in u or "avc1" in u) and "douyinstatic.com" not in u]
        auds = [u for u in cdp.media if ("media-audio" in u or "mp4a" in u) and "douyinstatic.com" not in u]
        if not vids_:
            print("[cdp] 没有捕获到视频轨，无法下载")
            rc = 2
        else:
            import shutil

            ff = shutil.which("ffmpeg") or "ffmpeg"
            tmpdir = tempfile.mkdtemp(prefix="dy_")
            vpath = os.path.join(tmpdir, "v.mp4")
            ok, info = download(vids_[0], vpath, {})
            print(f"[cdp] 视频轨{'成功' if ok else '失败'}: {info}")
            apath = None
            ok2 = False
            if auds:
                apath = os.path.join(tmpdir, "a.mp4")
                ok2, info2 = download(auds[0], apath, {})
                print(f"[cdp] 音频轨{'成功' if ok2 else '失败'}: {info2}")
            if not ok:
                rc = 3
            elif apath and ok2 and os.path.exists(ff):
                r = subprocess.run(
                    [ff, "-y", "-i", vpath, "-i", apath, "-c", "copy", "-movflags", "+faststart", a.out],
                    capture_output=True,
                )
                if r.returncode == 0:
                    print(f"[cdp] 已合并音视频: {os.path.abspath(a.out)} ({os.path.getsize(a.out)/1024/1024:.2f} MB)")
                else:
                    shutil.copy(vpath, a.out)
                    print(f"[cdp] 合并失败，已保存纯视频轨: {os.path.abspath(a.out)}")
            else:
                shutil.copy(vpath, a.out)
                print(f"[cdp] 已保存: {os.path.abspath(a.out)}")

    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
