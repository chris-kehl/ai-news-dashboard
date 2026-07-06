#!/usr/bin/env python3
"""Dashboard bridge server — runs locally on the M5 MacBook Air.

Endpoints:
  POST /update  → sync location to macbook1 scraper config + trigger remote scrape
  GET  /local?city=<c>&state=<s>&source=<reddit|news|x>&limit=<n>
                → run local scraper code for the given city and return JSON

Browser hits http://127.0.0.1:8787 (same-origin, no CORS issues).
Uses ThreadingHTTPServer to prevent one slow scraper from blocking others.
"""

import http.server
import json
import os
import subprocess
import socketserver
import sys
import urllib.parse
import threading

MACBOOK1 = os.environ.get("MACBOOK1_HOST", "chriskehl@192.168.4.32")
REMOTE_DIR = os.path.expanduser(os.path.join(os.path.dirname(os.path.abspath(__file__))))
SCRAPER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper")

if SCRAPER_DIR not in sys.path:
    sys.path.insert(0, SCRAPER_DIR)

# Lazy imports: delay expensive + flaky module init until request time
def _get_ddg_scraper():
    try:
        from ddg_scraper import ddg_local_news
        return ddg_local_news
    except Exception as e:
        print(f"[bridge] ddg_scraper unavailable: {e}")
        return None


def _get_x_scraper():
    """get_local_x_posts from x_scraper.py — uses requests + regex HTML parsing (no Playwright)."""
    try:
        from x_scraper import get_local_x_posts
        return get_local_x_posts
    except Exception as e:
        print(f"[bridge] x_scraper unavailable: {e}")
        return None


def _get_channels_scraper():
    """get_local_channel_news from local_channels_scraper.py — dynamic TV/paper discovery."""
    try:
        from local_channels_scraper import get_local_channel_news
        return get_local_channel_news
    except Exception as e:
        print(f"[bridge] local_channels_scraper unavailable: {e}")
        return None


def _run_ssh(cmd: str, timeout: int = 20) -> tuple:
    res = subprocess.run(
        ["ssh", MACBOOK1, cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return res.returncode, res.stdout, res.stderr


def _write_remote_config(config: dict) -> str:
    payload = json.dumps({"config": config})
    import base64
    b64 = base64.b64encode(payload.encode()).decode()
    remote_cmd = f"echo '{b64}' | base64 -d > ~/ai-news-dashboard/scraper/config.json"
    rc, out, err = _run_ssh(remote_cmd, timeout=15)
    msg = (out + err).strip()
    if rc != 0:
        raise RuntimeError(f"SSH write failed: {msg}")
    return msg


def _trigger_remote_scraper() -> str:
    rc, out, err = _run_ssh(
        "cd ~/ai-news-dashboard && nohup bash -c 'python3 scraper/main.py && ./deploy.sh' > /tmp/scraper.out 2>&1 &",
        timeout=30,
    )
    return (out + err).strip()


# ----- direct Reddit RSS fetcher (requests, no Playwright) -----
def _fetch_reddit_rss(city: str, state: str, limit: int = 8):
    """Fetch city/state subreddits via old.reddit.com RSS. Requests-based, very fast."""
    import re
    import time
    import requests
    import xml.etree.ElementTree as ET
    import html as html_mod

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/atom+xml,application/rss+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://old.reddit.com/",
    }
    base_rss = "https://old.reddit.com"

    def raw_sub(name: str) -> str:
        n = name.lower().strip()
        n = re.sub(r"['\.\u2019]", "", n)
        n = re.sub(r"[^a-z0-9]", "", n)
        return n

    subs = []
    cs = raw_sub(city)
    ss = raw_sub(state)
    if cs:
        subs.append(cs)
    if ss and ss != cs:
        subs.append(ss)

    all_posts = []
    for i, sr in enumerate(subs[:2]):  # max 2 subs to keep it fast
        url = f"{base_rss}/r/{sr}/.rss?limit=10&sort=new"
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 429:
                time.sleep(5)
                r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                try:
                    title_el = entry.find("atom:title", ns)
                    link_el = entry.find("atom:link", ns)
                    updated_el = entry.find("atom:updated", ns)
                    title = title_el.text or "" if title_el is not None else ""
                    permalink = link_el.get("href", "") if link_el is not None else ""
                    if permalink:
                        from urllib.parse import urlparse
                        permalink = urlparse(permalink).path or permalink
                    url_str = f"https://www.reddit.com{permalink}" if permalink else ""
                    updated_str = updated_el.text or "" if updated_el is not None else ""
                    if not url_str:
                        continue
                    if title.startswith("[") and "moderator" in title.lower():
                        continue
                    all_posts.append({
                        "title": title.strip()[:200],
                        "subreddit": sr,
                        "score": "—",
                        "comments": "—",
                        "url": url_str,
                        "created": updated_str,
                    })
                except Exception:
                    continue
        except Exception:
            continue
        if i < len(subs) - 1:
            time.sleep(1)

    return all_posts[:limit]


class BridgeHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        print(f"[bridge] {self.address_string()} {format % args}")

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path != "/update":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            self._send_json(400, {"ok": False, "error": "empty body"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode())
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "bad json"})
            return

        city = body.get("city", "")
        state = body.get("state", "")
        lat = body.get("lat", 0)
        lon = body.get("lon", 0)
        zip_code = body.get("zip", "")
        if not city or not state:
            self._send_json(400, {"ok": False, "error": "city+state required"})
            return

        result = {"ok": True, "server_sync": False, "scrape_triggered": False, "message": ""}
        try:
            msg = _write_remote_config({
                "city": city, "state": state, "lat": lat, "lon": lon, "zip": zip_code,
            })
            result["server_sync"] = True
            result["message"] = f"Config updated: {city}, {state}"
        except Exception as e:
            result.update({"ok": False, "message": str(e)})
            self._send_json(500, result)
            return

        try:
            _trigger_remote_scraper()
            result["scrape_triggered"] = True
            result["message"] += f". Scraper started on {MACBOOK1}."
        except Exception as e:
            result["message"] += f". Scraper trigger failed: {e}"

        self._send_json(200, result)

    def do_GET(self):
        if not self.path.startswith("/local"):
            self.send_error(404)
            return
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        city = qs.get("city", [""])[0]
        state = qs.get("state", [""])[0]
        source = qs.get("source", ["news"])[0].lower()
        limit = min(int(qs.get("limit", ["8"])[0]), 20)

        if not city or not state:
            self._send_json(400, {"ok": False, "error": "city+state required"})
            return

        data = []
        try:
            if source == "reddit":
                data = _fetch_reddit_rss(city, state, limit)
            elif source == "news":
                fn = _get_ddg_scraper()
                if fn:
                    data = fn(city, state, max_results=limit)
                else:
                    data = [{"error": "ddg_scraper not available"}]
            elif source == "channels":
                fn = _get_channels_scraper()
                if fn:
                    data = fn(city, state, max_per_station=6, max_sites=6)
                else:
                    data = [{"error": "local_channels_scraper not available"}]
            elif source == "x":
                fn = _get_x_scraper()
                if fn:
                    data = fn(city, state, max_results=limit)
                else:
                    data = [{"error": "x_scraper not available"}]
            else:
                data = [{"error": f"unknown source: {source}"}]
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return

        self._send_json(200, {
            "ok": True,
            "source": source,
            "city": city,
            "state": state,
            "count": len(data),
            "data": data,
        })


class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(os.environ.get("BRIDGE_PORT", "8787"))
    with ThreadedHTTPServer(("127.0.0.1", port), BridgeHandler) as srv:
        print(f"[bridge] listening on http://127.0.0.1:{port}")
        print(f"[bridge] forwarding /update to {MACBOOK1}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n[bridge] shutting down")
