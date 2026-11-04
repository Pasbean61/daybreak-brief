"""Daily entry point: collect -> edit -> write -> publish JSON for the site.

    python -m pipeline.run                    # yesterday's edition (in BRIEF_TZ)
    python -m pipeline.run --date 2026-11-03  # a specific day
    python -m pipeline.run --force            # rebuild even if it exists
    python -m pipeline.run --collect-only     # just dump candidates (no API key needed)
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
from datetime import date as Date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.collect import article_text, collect

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EDITIONS = DATA / "editions"
TZ = ZoneInfo(os.environ.get("BRIEF_TZ", "Europe/London"))

N_AI = int(os.environ.get("BRIEF_AI_STORIES", "6"))
N_WORLD = int(os.environ.get("BRIEF_WORLD_STORIES", "6"))
N_QUICK = int(os.environ.get("BRIEF_QUICK_HITS", "10"))
MAX_CANDIDATES = int(os.environ.get("BRIEF_MAX_CANDIDATES", "520"))


def window(day: Date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0, 0), TZ) - timedelta(hours=3)  # small overlap: late-night stories
    end = datetime.combine(day + timedelta(days=1), time(0, 0), TZ) + timedelta(hours=2)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def trim(items: list[dict]) -> list[dict]:
    """Keep the prompt focused: per-feed cap, then strongest signals first."""
    per_feed: dict[str, int] = {}
    out = []
    ranked = sorted(items, key=lambda x: -(len(x.get("echo_sources", [])) * 2 + x.get("weight", 1) + min(x.get("signal", 0), 600) / 150))
    for it in ranked:
        n = per_feed.get(it["feed"], 0)
        if n >= 25:
            continue
        per_feed[it["feed"]] = n + 1
        out.append(it)
    return out[:MAX_CANDIDATES]


def source_list(ids: list[int], items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for i in ids:
        if 0 <= i < len(items) and items[i]["url"] not in seen:
            seen.add(items[i]["url"])
            out.append({"name": items[i]["source"], "url": items[i]["url"], "title": items[i]["title"]})
    return out[:6]


def update_index() -> None:
    entries = []
    for f in sorted(EDITIONS.glob("*.json"), reverse=True):
        e = json.loads(f.read_text())
        entries.append(
            {
                "date": e["date"],
                "headline": e["headline"],
                "lede": e["lede"],
                "counts": {"ai": len(e["sections"]["ai"]), "world": len(e["sections"]["world"]), "quick": len(e["quick_hits"])},
            }
        )
    (DATA / "index.json").write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "editions": entries}, ensure_ascii=False, indent=1))


def build(day: Date, force: bool, collect_only: bool) -> int:
    out_path = EDITIONS / f"{day.isoformat()}.json"
    if out_path.exists() and not force and not collect_only:
        print(f"Edition {day} already exists — skipping (use --force to rebuild).")
        return 0

    start, end = window(day)
    print(f"▸ Collecting {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M} UTC")
    items = trim(collect(start, end))
    print(f"  {len(items)} candidates after dedupe/trim")
    if collect_only:
        p = ROOT / "candidates.json"
        p.write_text(json.dumps(items, ensure_ascii=False, indent=1))
        print(f"  wrote {p}")
        return 0
    if len(items) < 15:
        print("Too few items collected — refusing to publish a thin edition.", file=sys.stderr)
        return 2

    from pipeline import writer  # imported late so --collect-only needs no API key

    print("▸ Editor-in-chief is planning the edition")
    plan = writer.edit(items, day.isoformat(), N_AI, N_WORLD, N_QUICK)
    desks = {d: [s for s in plan["stories"] if s["section"] == d] for d in ("ai", "world")}

    print("▸ Reading the source articles")
    wanted = sorted({i for s in plan["stories"] for i in s["item_ids"][:4] if 0 <= i < len(items)})
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        texts = dict(zip(wanted, pool.map(lambda i: article_text(items[i]["url"]), wanted)))
    print(f"  got readable text for {sum(1 for t in texts.values() if t)}/{len(wanted)} articles")

    print("▸ Writers are drafting both desks")
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futs = {d: pool.submit(writer.write, desks[d], items, texts, day.isoformat(), d) for d in desks if desks[d]}
        drafted = {d: f.result() for d, f in futs.items()}

    sections = {"ai": [], "world": []}
    for d, stories in drafted.items():
        for s in stories:
            k = s.pop("plan_index")
            ids = s.pop("source_ids") or (desks[d][k]["item_ids"] if 0 <= k < len(desks[d]) else [])
            s["sources"] = source_list(ids, items)
            sections[d].append(s)

    quick = []
    for q in plan["quick_hits"]:
        quick.append({"section": q["section"], "title": q["title"], "line": q["line"], "sources": source_list(q["item_ids"], items)[:2]})

    edition = {
        "date": day.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": writer.MODEL,
        "headline": plan["headline"],
        "lede": plan["lede"],
        "sections": sections,
        "quick_hits": quick,
        "stats": {"candidates": len(items), "outlets": len({i["source"] for i in items})},
    }
    EDITIONS.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(edition, ensure_ascii=False, indent=1))
    update_index()
    print(f"✓ Published {out_path.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="edition date YYYY-MM-DD (default: yesterday in BRIEF_TZ)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--collect-only", action="store_true")
    ap.add_argument("--reindex", action="store_true", help="only rebuild data/index.json")
    a = ap.parse_args()
    if a.reindex:
        update_index()
        return 0
    day = Date.fromisoformat(a.date) if a.date else (datetime.now(TZ).date() - timedelta(days=1))
    return build(day, a.force, a.collect_only)


if __name__ == "__main__":
    sys.exit(main())
