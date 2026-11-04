"""Collect yesterday's raw news from RSS/Atom feeds, Hacker News and (optionally) X.

Standard library only, so it runs anywhere. Every source is best-effort: a dead
feed is logged and skipped, never fatal.
"""
from __future__ import annotations

import concurrent.futures as cf
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

UA = "Mozilla/5.0 (compatible; DaybreakBrief/1.0; +https://github.com/)"
HERE = Path(__file__).resolve().parent


def http_get(url: str, timeout: int = 20, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- text utils
class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form") and self._skip:
            self._skip -= 1
        if tag in ("p", "br", "li", "h2", "h3", "div"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def strip_html(s: str) -> str:
    if not s:
        return ""
    p = _Text()
    try:
        p.feed(s)
        out = "".join(p.parts)
    except Exception:
        out = re.sub(r"<[^>]+>", " ", s)
    out = html.unescape(out)
    out = re.sub(r"[ \t\r\f\v]+", " ", out)
    out = re.sub(r"\n\s*\n+", "\n", out)
    return out.strip()


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        d = None
    if d is None:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(el, *names) -> str:
    for c in el:
        if _local(c.tag) in names:
            if (c.text or "").strip():
                return c.text.strip()
            # atom content may be nested xhtml
            inner = "".join(c.itertext()).strip()
            if inner:
                return inner
    return ""


def _link(el) -> str:
    for c in el:
        if _local(c.tag) == "link":
            href = c.attrib.get("href")
            rel = c.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                return href.strip()
            if (c.text or "").strip():
                return c.text.strip()
    for c in el:
        if _local(c.tag) == "link" and c.attrib.get("href"):
            return c.attrib["href"].strip()
    return _child_text(el, "guid", "id")


# ---------------------------------------------------------------- feeds
def parse_feed(raw: bytes, source: dict) -> list[dict]:
    root = ET.fromstring(raw)
    items = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    out = []
    for it in items:
        title = strip_html(_child_text(it, "title"))
        link = _link(it)
        summary = strip_html(_child_text(it, "description", "summary", "content", "encoded"))
        date = parse_date(_child_text(it, "pubdate", "published", "updated", "date", "issued"))
        publisher = ""
        for c in it:
            if _local(c.tag) == "source" and (c.text or "").strip():
                publisher = c.text.strip()  # Google News carries the real outlet here
        if not title or not link:
            continue
        # Google News titles end with " - Outlet"
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3].strip()
        out.append(
            {
                "title": title,
                "url": link,
                "summary": summary[:600],
                "published": date.isoformat() if date else None,
                "source": publisher or source["name"],
                "feed": source["name"],
                "section": source["section"],
                "weight": source.get("weight", 1),
            }
        )
    return out


def fetch_feed(source: dict) -> tuple[dict, list[dict], str | None]:
    try:
        return source, parse_feed(http_get(source["url"]), source), None
    except Exception as e:  # noqa: BLE001 - every feed is best effort
        return source, [], f"{type(e).__name__}: {e}"[:160]


def fetch_hackernews(cfg: dict, start: datetime, end: datetime) -> list[dict]:
    q = urllib.parse.urlencode(
        {
            "tags": "story",
            "numericFilters": f"created_at_i>{int(start.timestamp())},created_at_i<{int(end.timestamp())},points>{cfg.get('min_points', 120)}",
            "hitsPerPage": 60,
        }
    )
    data = json.loads(http_get("https://hn.algolia.com/api/v1/search?" + q))
    out = []
    for h in data.get("hits", []):
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
        site = urllib.parse.urlparse(url).netloc.replace("www.", "") or "news.ycombinator.com"
        out.append(
            {
                "title": h.get("title", ""),
                "url": url,
                "summary": f"Hacker News: {h.get('points', 0)} points, {h.get('num_comments', 0)} comments.",
                "published": h.get("created_at"),
                "source": site if site != "news.ycombinator.com" else "Hacker News",
                "feed": "Hacker News",
                "section": cfg.get("section", "ai"),
                "weight": 1,
                "signal": int(h.get("points", 0)),
            }
        )
    return out


def fetch_x(cfg: dict, start: datetime, end: datetime, token: str) -> list[dict]:
    """X API v2 recent search over a curated account list (needs a paid X API tier)."""
    accounts = cfg.get("accounts", [])
    out: list[dict] = []
    # query length is capped at 512 chars on Basic — chunk the account list
    chunks, cur = [], []
    for a in accounts:
        cand = cur + [a]
        if len(" OR ".join(f"from:{x}" for x in cand)) > 400:
            chunks.append(cur)
            cur = [a]
        else:
            cur = cand
    if cur:
        chunks.append(cur)
    for chunk in chunks:
        query = "(" + " OR ".join(f"from:{a}" for a in chunk) + ") -is:retweet -is:reply"
        params = urllib.parse.urlencode(
            {
                "query": query,
                "max_results": 100,
                "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_time": min(end, datetime.now(timezone.utc) - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tweet.fields": "created_at,public_metrics,author_id",
                "expansions": "author_id",
                "user.fields": "username,name",
            }
        )
        data = json.loads(
            http_get("https://api.x.com/2/tweets/search/recent?" + params, headers={"Authorization": f"Bearer {token}"})
        )
        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
        for t in data.get("data", []):
            u = users.get(t.get("author_id"), {})
            m = t.get("public_metrics", {})
            handle = u.get("username", "x")
            out.append(
                {
                    "title": t["text"].split("\n")[0][:180],
                    "url": f"https://x.com/{handle}/status/{t['id']}",
                    "summary": t["text"][:600],
                    "published": t.get("created_at"),
                    "source": f"X @{handle}",
                    "feed": "X",
                    "section": "world" if handle.lower() in ("reuters", "ap", "bbcbreaking") else "ai",
                    "weight": 1,
                    "signal": int(m.get("like_count", 0)) + 3 * int(m.get("retweet_count", 0)),
                }
            )
    return out


# ---------------------------------------------------------------- clustering
_STOP = set("the a an of to in on for and or with at by from is are be as its it this that new after over says say said will has have was were how why what who".split())


def _tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in _STOP and len(w) > 2}


def dedupe(items: list[dict]) -> list[dict]:
    """Drop exact URL dupes, then count near-duplicate titles as cross-source signal."""
    seen_url: dict[str, dict] = {}
    for it in items:
        key = it["url"].split("?")[0].rstrip("/") if "news.google.com" not in it["url"] else it["title"].lower()
        if key in seen_url:
            continue
        seen_url[key] = it
    uniq = list(seen_url.values())
    toks = [_tokens(i["title"]) for i in uniq]
    for i, it in enumerate(uniq):
        echoes = set()
        for j, other in enumerate(uniq):
            if i == j or not toks[i] or not toks[j]:
                continue
            inter = len(toks[i] & toks[j])
            if inter >= 3 and inter / min(len(toks[i]), len(toks[j])) >= 0.5:
                echoes.add(other["source"])
        it["echo_sources"] = sorted(echoes - {it["source"]})
    return uniq


# ---------------------------------------------------------------- article text
def article_text(url: str, limit: int = 3500) -> str:
    """Best-effort readable text of an article (for the writer's context)."""
    if "news.google.com" in url or url.startswith("https://x.com"):
        return ""
    try:
        raw = http_get(url, timeout=15).decode("utf-8", "ignore")
    except Exception:
        return ""
    m = re.search(r"<article[\s\S]*?</article>", raw, re.I)
    body = m.group(0) if m else raw
    paras = re.findall(r"<p[^>]*>([\s\S]*?)</p>", body, re.I)
    lines = (ln.strip() for p in paras for ln in strip_html(p).split("\n"))
    text = "\n".join(ln for ln in lines if len(ln) > 60 and not re.search(r"(?i)register now|subscribe|sign up|cookie", ln))
    return text[:limit]


# ---------------------------------------------------------------- main entry
def collect(start: datetime, end: datetime, log=print) -> list[dict]:
    cfg = json.loads((HERE / "sources.json").read_text())
    items: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=12) as pool:
        for source, got, err in pool.map(fetch_feed, cfg["feeds"]):
            if err:
                log(f"  ✗ {source['name']}: {err}")
            else:
                log(f"  ✓ {source['name']}: {len(got)} items")
            items.extend(got)
    try:
        hn = fetch_hackernews(cfg.get("hackernews", {}), start, end)
        log(f"  ✓ Hacker News: {len(hn)} items")
        items.extend(hn)
    except Exception as e:  # noqa: BLE001
        log(f"  ✗ Hacker News: {e}")
    token = os.environ.get("X_BEARER_TOKEN")
    if token:
        try:
            xs = fetch_x(cfg.get("x", {}), start, end, token)
            log(f"  ✓ X: {len(xs)} posts")
            items.extend(xs)
        except Exception as e:  # noqa: BLE001
            log(f"  ✗ X: {e}")
    else:
        log("  · X: skipped (no X_BEARER_TOKEN)")

    # keep the target window; undated items are kept only from primary sources
    kept = []
    for it in items:
        d = parse_date(it.get("published"))
        if d is None:
            continue
        if start <= d < end:
            kept.append(it)
    out = dedupe(kept)
    out.sort(key=lambda x: (x["section"], -(len(x.get("echo_sources", [])) + x.get("weight", 1))))
    return out


if __name__ == "__main__":
    import sys

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=int(sys.argv[1]) if len(sys.argv) > 1 else 30)
    res = collect(start, end)
    print(f"{len(res)} items")
    Path(os.environ.get("OUT", "candidates.json")).write_text(json.dumps(res, ensure_ascii=False, indent=1))
