"""
Recoleccion de datos desde Hacker News y Stack Exchange.
Sin credenciales — APIs publicas gratuitas.
"""

import os
import time
import requests
from datetime import datetime, timedelta, timezone

HEADERS = {"User-Agent": "radar-oportunidades/2.0 (investigacion personal)"}

# ── Hacker News (Algolia API) ──────────────────────────────────────────────────

HN_URL = "https://hn.algolia.com/api/v1/search_by_date"

HN_QUERIES = [
    # Frustraciones directas
    "frustrated with",
    "I hate when",
    "annoying problem",
    "terrible experience",
    "bad design",
    "broken",
    # Deseos de solucion (alta intension de pago)
    "wish there was",
    "why doesn't exist",
    "nobody builds",
    "I'd pay for",
    "need a tool",
    "someone should build",
    # Ask HN: pedidos de recomendacion (pain points implicitos)
    "Ask HN: Is there a tool",
    "Ask HN: How do you",
    "Ask HN: Why is",
    # Pain points tecnicos
    "pain point",
    "impossible to",
    "no good solution",
]


def fetch_hn(days: int = 30) -> list[dict]:
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    posts = []
    seen = set()

    for query in HN_QUERIES:
        for tag in ["story", "comment"]:
            try:
                params = {
                    "query": query,
                    "tags": tag,
                    "numericFilters": f"created_at_i>{cutoff_ts}",
                    "hitsPerPage": 100,
                }
                resp = requests.get(HN_URL, params=params, timeout=10)
                resp.raise_for_status()

                for hit in resp.json().get("hits", []):
                    uid = hit.get("objectID", "")
                    if uid in seen:
                        continue
                    seen.add(uid)

                    title = hit.get("title") or hit.get("comment_text", "")[:120] or ""
                    text = (hit.get("story_text") or hit.get("comment_text") or "")[:600]
                    created_raw = hit.get("created_at", "")
                    try:
                        dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                        date_str = dt.strftime("%Y-%m-%d")
                    except Exception:
                        date_str = ""

                    url = hit.get("url") or f"https://news.ycombinator.com/item?id={uid}"
                    posts.append({
                        "source": "Hacker News",
                        "title": title,
                        "text": text,
                        "score": hit.get("points") or 0,
                        "url": url,
                        "date": date_str,
                    })

                time.sleep(0.2)
            except Exception as e:
                print(f"[HN] Error en query '{query}' tag={tag}: {e}")

    return posts


# ── Stack Exchange ─────────────────────────────────────────────────────────────

SE_SITES = [
    # (site, descripcion, intitle_keywords)
    ("softwarerecs", "Software Recs",
     ["tool for", "alternative to", "software that", "app that", "automate"]),
    ("ux", "UX Stack Exchange",
     ["frustrating", "confusing", "bad ux", "improve", "users complain"]),
    ("stackoverflow", "Stack Overflow",
     ["not working", "broken", "issue with", "problem with", "failed to"]),
    ("webapps", "Web Apps SE",
     ["doesn't work", "missing feature", "alternative", "how to export", "how to cancel"]),
]


def fetch_stackoverflow(days: int = 30) -> list[dict]:
    key = os.getenv("STACK_EXCHANGE_KEY", "")
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    posts = []
    seen = set()

    for site, site_label, keywords in SE_SITES:
        for kw in keywords:
            try:
                params = {
                    "site": site,
                    "intitle": kw,
                    "fromdate": cutoff_ts,
                    "order": "desc",
                    "sort": "creation",
                    "pagesize": 50,
                }
                if key:
                    params["key"] = key

                resp = requests.get(
                    "https://api.stackexchange.com/2.3/search",
                    params=params,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

                # Verificar cuota restante
                remaining = data.get("quota_remaining", 999)
                if remaining < 10:
                    print(f"[SE] Cuota casi agotada ({remaining} restantes). Deteniendose.")
                    return posts

                for item in data.get("items", []):
                    uid = str(item.get("question_id", ""))
                    if uid in seen:
                        continue
                    seen.add(uid)

                    created_ts = item.get("creation_date", 0)
                    dt = datetime.fromtimestamp(created_ts, tz=timezone.utc)
                    # Sin filter=withbody, body no viene — usamos excerpt si existe
                    text_raw = item.get("body", "") or item.get("excerpt", "")
                    import re
                    text_clean = re.sub(r"<[^>]+>", " ", text_raw)[:600]

                    posts.append({
                        "source": f"Stack Exchange / {site_label}",
                        "title": item.get("title", ""),
                        "text": text_clean,
                        "score": item.get("score", 0),
                        "url": item.get("link", ""),
                        "date": dt.strftime("%Y-%m-%d"),
                    })

                time.sleep(0.5)
            except Exception as e:
                print(f"[SE] Error en site={site} kw='{kw}': {e}")

    return posts


# ── Punto de entrada unificado ─────────────────────────────────────────────────

def fetch_all(days: int = 30, sources: list[str] | None = None) -> list[dict]:
    if sources is None:
        sources = ["Hacker News", "Stack Overflow"]

    all_posts = []

    if "Hacker News" in sources:
        hn = fetch_hn(days=days)
        print(f"[Collector] HN: {len(hn)} posts")
        all_posts.extend(hn)

    if "Stack Overflow" in sources:
        so = fetch_stackoverflow(days=days)
        print(f"[Collector] SO: {len(so)} posts")
        all_posts.extend(so)

    # Deduplicar por URL
    seen = set()
    unique = []
    for p in all_posts:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)

    print(f"[Collector] Total unicos: {len(unique)}")
    return unique
