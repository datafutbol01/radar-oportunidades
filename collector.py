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
                        "language": "en",
                    })

                time.sleep(0.2)
            except Exception as e:
                print(f"[HN] Error en query '{query}' tag={tag}: {e}")

    return posts


# ── Stack Exchange ─────────────────────────────────────────────────────────────

SE_SITES = [
    # (site, descripcion, intitle_keywords)
    ("softwarerecs", "Software Recs",
     ["tool for", "alternative to", "software that", "app that", "automate",
      "looking for", "recommend", "need software", "best way to", "open source"]),
    ("ux", "UX Stack Exchange",
     ["frustrating", "confusing", "bad ux", "improve", "users complain",
      "annoying", "difficult to", "hard to use", "poor experience", "accessibility"]),
    ("stackoverflow", "Stack Overflow",
     ["not working", "broken", "issue with", "problem with", "failed to",
      "impossible to", "no way to", "limitation", "workaround", "bug in"]),
    ("webapps", "Web Apps SE",
     ["doesn't work", "missing feature", "alternative", "how to export", "how to cancel",
      "no longer works", "broken since", "how to automate", "wish there was"]),
    ("workplace", "Workplace SE",
     ["frustrated", "problem with", "annoying", "inefficient", "waste of time",
      "no solution", "bad process", "need a tool", "automate"]),
    ("money", "Money SE",
     ["problem with", "frustrated", "alternative", "no way to", "wish there was",
      "difficult to", "bad experience", "hidden fee"]),
    ("superuser", "Super User",
     ["not working", "broken", "alternative to", "how to automate", "no way to",
      "workaround", "impossible", "limitation", "missing feature"]),
    ("askubuntu", "Ask Ubuntu",
     ["not working", "broken", "alternative", "how to automate", "no way to",
      "workaround", "missing feature", "wish there was"]),
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
                    "pagesize": 100,
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
                        "language": "en",
                    })

                time.sleep(0.5)
            except Exception as e:
                print(f"[SE] Error en site={site} kw='{kw}': {e}")

    return posts


# ── Reddit (API publica JSON) ───────────────────────────────────────────────────

REDDIT_SUBREDDITS = [
    "SomebodyMakeThis",
    "Entrepreneur",
    "startups",
    "mildlyinfuriating",
    "rant",
    "techsupport",
    "productivity",
    "smallbusiness",
]

REDDIT_QUERIES = [
    "wish there was",
    "I'd pay for",
    "nobody builds",
    "why doesn't exist",
    "need a tool",
    "frustrated with",
    "someone should make",
    "annoying problem",
    "no good solution",
]

REDDIT_SUBREDDITS_ES = [
    "argentina",
    "es",
]

REDDIT_QUERIES_ES = [
    "ojala existiera",
    "pagaria por",
    "nadie hace",
    "por que no existe",
    "necesito una herramienta",
    "me tiene harto",
    "alguien deberia hacer",
    "problema horrible",
    "no hay solucion",
    "me quejo",
    "una porqueria",
    "que fastidio",
]

REDDIT_SUBREDDITS_PT = ["brasil", "portugal"]
REDDIT_QUERIES_PT = [
    "queria que existisse",
    "pagaria por",
    "ninguem faz",
    "por que nao existe",
    "preciso de uma ferramenta",
    "me irrita muito",
    "alguem deveria criar",
    "problema terrivel",
    "nao tem solucao",
]

REDDIT_SUBREDDITS_FR = ["france", "Quebec"]
REDDIT_QUERIES_FR = [
    "j'aimerais qu'il existe",
    "je paierais pour",
    "personne ne fait",
    "pourquoi ca n'existe pas",
    "j'ai besoin d'un outil",
    "ca m'enerve",
    "quelqu'un devrait creer",
    "probleme horrible",
    "aucune solution",
]

REDDIT_SUBREDDITS_DE = ["de", "Austria"]
REDDIT_QUERIES_DE = [
    "ich wunschte es gabe",
    "ich wurde bezahlen fur",
    "niemand baut",
    "warum gibt es das nicht",
    "ich brauche ein tool",
    "nervt mich",
    "jemand sollte das bauen",
    "schreckliches problem",
    "keine gute losung",
]

REDDIT_SUBREDDITS_IT = ["italy", "italyInformatica"]
REDDIT_QUERIES_IT = [
    "vorrei che esistesse",
    "pagherei per",
    "nessuno lo fa",
    "perche non esiste",
    "ho bisogno di uno strumento",
    "mi fa arrabbiare",
    "qualcuno dovrebbe creare",
    "problema terribile",
    "nessuna soluzione",
]


def _fetch_reddit_subreddits(subreddits: list[str], queries: list[str], days: int, seen: set, language: str = "en") -> list[dict]:
    posts = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for subreddit in subreddits:
        for query in queries:
            try:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {
                    "q": query,
                    "sort": "new",
                    "limit": 50,
                    "restrict_sr": 1,
                    "t": "month",
                }
                resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
                if resp.status_code != 200:
                    continue

                for child in resp.json().get("data", {}).get("children", []):
                    item = child.get("data", {})
                    uid = item.get("id", "")
                    if uid in seen:
                        continue
                    seen.add(uid)

                    created_ts = item.get("created_utc", 0)
                    dt = datetime.fromtimestamp(created_ts, tz=timezone.utc)
                    if dt < cutoff:
                        continue

                    text = (item.get("selftext") or "")[:600]
                    posts.append({
                        "source": f"Reddit / r/{subreddit}",
                        "title": item.get("title", ""),
                        "text": text,
                        "score": item.get("score", 0),
                        "url": f"https://reddit.com{item.get('permalink', '')}",
                        "date": dt.strftime("%Y-%m-%d"),
                        "language": language,
                    })

                time.sleep(0.5)
            except Exception as e:
                print(f"[Reddit] Error en r/{subreddit} query='{query}': {e}")

    return posts


def fetch_reddit(days: int = 30) -> list[dict]:
    seen = set()
    posts = _fetch_reddit_subreddits(REDDIT_SUBREDDITS, REDDIT_QUERIES, days, seen, language="en")
    posts += _fetch_reddit_subreddits(REDDIT_SUBREDDITS_ES, REDDIT_QUERIES_ES, days, seen, language="es")
    posts += _fetch_reddit_subreddits(REDDIT_SUBREDDITS_PT, REDDIT_QUERIES_PT, days, seen, language="pt")
    posts += _fetch_reddit_subreddits(REDDIT_SUBREDDITS_FR, REDDIT_QUERIES_FR, days, seen, language="fr")
    posts += _fetch_reddit_subreddits(REDDIT_SUBREDDITS_DE, REDDIT_QUERIES_DE, days, seen, language="de")
    posts += _fetch_reddit_subreddits(REDDIT_SUBREDDITS_IT, REDDIT_QUERIES_IT, days, seen, language="it")
    return posts


# ── Punto de entrada unificado ─────────────────────────────────────────────────

def fetch_all(days: int = 30, sources: list[str] | None = None) -> list[dict]:
    if sources is None:
        sources = ["Hacker News", "Stack Overflow", "Reddit"]

    all_posts = []

    if "Hacker News" in sources:
        hn = fetch_hn(days=days)
        print(f"[Collector] HN: {len(hn)} posts")
        all_posts.extend(hn)

    if "Stack Overflow" in sources:
        so = fetch_stackoverflow(days=days)
        print(f"[Collector] SO: {len(so)} posts")
        all_posts.extend(so)

    if "Reddit" in sources:
        rd = fetch_reddit(days=days)
        print(f"[Collector] Reddit: {len(rd)} posts")
        all_posts.extend(rd)

    # Deduplicar por URL
    seen = set()
    unique = []
    for p in all_posts:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)

    print(f"[Collector] Total unicos: {len(unique)}")
    return unique
