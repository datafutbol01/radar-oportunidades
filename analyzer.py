"""
Analisis con LLM (Claude):
- Clasificacion inteligente por categoria con descubrimiento de categorias nuevas
- Deteccion de intencion de pago
- Deteccion de tendencias reales vs picos momentaneos
- Generacion de briefs de oportunidad para las categorias top
"""

import json
import math
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import anthropic
from categories import BASE_CATEGORIES

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

BATCH_SIZE = 20  # posts por llamada de clasificacion


def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ── 1. Clasificacion ───────────────────────────────────────────────────────────

CLASSIFY_SYSTEM = """You are an analyst identifying business opportunities from online complaints and frustrations.

For each post in the JSON list, return a JSON array with one object per post containing:
- "id": the post id (integer, same as input)
- "category": one category from the provided list OR a new concise category name if none fit
- "is_new_category": true if you invented a category not in the list
- "payment_intent": integer 0-3
  * 0 = general frustration or informational, no desire for a product
  * 1 = implicit wish (inefficiency described, person is stuck)
  * 2 = explicit wish ("wish there was", "why doesn't X exist", "I need a tool")
  * 3 = would clearly pay ("I'd pay", "shut up and take my money", "need this desperately")
- "problem_summary": one sentence (max 15 words) describing the core problem

Rules:
- Be precise with categories — prefer specific over generic
- Infer payment intent from context, not just keywords
- If a post is not really a complaint, set payment_intent to 0
- Return ONLY the JSON array, no markdown, no explanation
"""


def classify_posts(posts: list[dict], progress_callback=None) -> list[dict]:
    """
    Clasifica todos los posts usando Claude Haiku en batches.
    Agrega los campos: category, is_new_category, payment_intent, problem_summary
    """
    client = _get_client()
    categories_str = "\n".join(f"- {c}" for c in BASE_CATEGORIES)
    classified = []
    total_batches = math.ceil(len(posts) / BATCH_SIZE)

    for batch_idx in range(total_batches):
        batch = posts[batch_idx * BATCH_SIZE : (batch_idx + 1) * BATCH_SIZE]

        # Preparar input para el LLM
        batch_input = [
            {"id": i, "title": p["title"], "text": p["text"][:300]}
            for i, p in enumerate(batch)
        ]

        prompt = f"""Available categories:
{categories_str}

Posts to classify:
{json.dumps(batch_input, ensure_ascii=False)}"""

        try:
            response = client.messages.create(
                model=HAIKU,
                max_tokens=2048,
                system=CLASSIFY_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Parsear JSON (puede venir con o sin code block)
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            results = json.loads(raw)

            for item in results:
                idx = item.get("id", 0)
                if 0 <= idx < len(batch):
                    post = dict(batch[idx])
                    post["category"] = item.get("category", "Sin categoria")
                    post["is_new_category"] = item.get("is_new_category", False)
                    post["payment_intent"] = item.get("payment_intent", 0)
                    post["problem_summary"] = item.get("problem_summary", "")
                    classified.append(post)

        except Exception as e:
            print(f"[Analyzer] Error en batch {batch_idx}: {e}")
            # Fallback: agregar posts sin clasificar
            for post in batch:
                post_copy = dict(post)
                post_copy.update({
                    "category": "Sin clasificar",
                    "is_new_category": False,
                    "payment_intent": 0,
                    "problem_summary": "",
                })
                classified.append(post_copy)

        if progress_callback:
            progress_callback(batch_idx + 1, total_batches)

        time.sleep(0.5)  # evitar rate limit

    return classified


# ── 2. Tendencias temporales ───────────────────────────────────────────────────

def compute_temporal_trends(posts: list[dict], period_days: int) -> dict:
    """
    Agrupa posts por categoria y por semana/periodo.
    Calcula: volumen actual vs promedio historico → señal de tendencia.

    Retorna:
    {
      "weekly_series": {categoria: {fecha_semana: count}},
      "trend_signals": {categoria: {"signal": "creciendo"|"estable"|"declinando"|"spike", "ratio": float}}
    }
    """
    now = datetime.now(timezone.utc).date()
    weekly_series: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for post in posts:
        date_str = post.get("date", "")
        cat = post.get("category", "Sin categoria")
        if not date_str:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            # Agrupar por semana (lunes de la semana)
            week_start = dt - timedelta(days=dt.weekday())
            weekly_series[cat][str(week_start)] += 1
        except Exception:
            continue

    trend_signals = {}
    for cat, weeks in weekly_series.items():
        counts = [v for _, v in sorted(weeks.items())]
        if len(counts) < 2:
            trend_signals[cat] = {"signal": "insuficiente", "ratio": 1.0}
            continue

        current = counts[-1]
        previous = counts[:-1]
        avg_prev = sum(previous) / len(previous)

        if avg_prev == 0:
            ratio = 2.0 if current > 0 else 1.0
        else:
            ratio = current / avg_prev

        # Detectar pico vs tendencia real
        if ratio > 2.0:
            # Verificar si la semana anterior tambien era alta (tendencia real) o no (pico)
            if len(previous) >= 2 and previous[-1] > avg_prev * 1.3:
                signal = "creciendo"
            else:
                signal = "spike"
        elif ratio > 1.3:
            signal = "creciendo"
        elif ratio < 0.7:
            signal = "declinando"
        else:
            signal = "estable"

        trend_signals[cat] = {"signal": signal, "ratio": round(ratio, 2)}

    return {
        "weekly_series": {k: dict(v) for k, v in weekly_series.items()},
        "trend_signals": trend_signals,
    }


# ── 3. Google Trends ───────────────────────────────────────────────────────────

def fetch_google_trends(categories_keywords: dict[str, list[str]], period_days: int) -> dict:
    """
    Dado un dict {categoria: [keywords]}, consulta Google Trends
    y devuelve series temporales de interes relativo.
    Retorna {} si pytrends falla o no esta instalado.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("[Trends] pytrends no instalado.")
        return {}

    timeframe_map = {
        7: "now 7-d",
        14: "now 14-d",
        30: "today 1-m",
        60: "today 2-m",
        90: "today 3-m",
    }
    tf = timeframe_map.get(period_days) or "today 1-m"

    results = {}
    try:
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))

        for cat, keywords in list(categories_keywords.items())[:4]:  # max 4 cats
            kws = keywords[:5]  # max 5 keywords por request
            if not kws:
                continue
            try:
                pt.build_payload(kws, timeframe=tf)
                df = pt.interest_over_time()
                if df.empty:
                    continue
                df = df.drop(columns=["isPartial"], errors="ignore")
                # Convertir a dict serializable
                results[cat] = df.reset_index().rename(columns={"date": "fecha"}).to_dict(orient="records")
                time.sleep(1.5)  # Google Trends rate limit
            except Exception as e:
                print(f"[Trends] Error en categoria '{cat}': {e}")
    except Exception as e:
        print(f"[Trends] Error inicializando pytrends: {e}")

    return results


def extract_keywords_per_category(posts: list[dict], top_cats: list[str]) -> dict[str, list[str]]:
    """Extrae las keywords mas frecuentes por categoria para Google Trends."""
    import re
    from collections import Counter

    stop = {
        "a","an","the","and","or","but","in","on","at","to","for","of","with",
        "by","is","it","my","i","we","you","this","that","not","no","so","just",
        "how","what","when","why","which","there","their","your","our","as","up",
        "if","about","than","then","some","can","get","do","be","have","am",
        "im","like","still","always","never","even","also","any","all","use",
        "using","used","make","making","made","want","need","try","trying",
    }

    cat_words: dict[str, Counter] = defaultdict(Counter)

    for post in posts:
        cat = post.get("category", "")
        if cat not in top_cats:
            continue
        title = post.get("title", "").lower()
        words = [w for w in re.findall(r"[a-z]{3,}", title) if w not in stop]
        cat_words[cat].update(words)

    return {cat: [w for w, _ in counter.most_common(5)] for cat, counter in cat_words.items()}


# ── 4. Briefs de oportunidad ───────────────────────────────────────────────────

BRIEF_SYSTEM = """Eres un estratega de producto y asesor de startups especializado en detectar oportunidades de negocio a partir de quejas online.

Tu tarea es analizar un conjunto de quejas reales y generar un brief accionable en ESPANOL.

El brief debe ser concreto, honesto sobre los riesgos, y util para alguien que quiere decidir si vale la pena explorar esta oportunidad.
"""


def generate_opportunity_briefs(
    posts: list[dict],
    top_categories: list[str],
    trend_signals: dict,
) -> dict[str, str]:
    """
    Genera un brief de oportunidad para cada categoria top usando Claude Sonnet.
    Retorna {categoria: markdown_brief}
    """
    client = _get_client()
    briefs = {}

    for cat in top_categories:
        cat_posts = [p for p in posts if p.get("category") == cat]
        if not cat_posts:
            continue

        total = len(cat_posts)
        high_intent = [p for p in cat_posts if p.get("payment_intent", 0) >= 2]
        intent_count = len(high_intent)

        # Top summaries para contexto
        top_summaries = [
            p["problem_summary"] for p in
            sorted(cat_posts, key=lambda x: x.get("payment_intent", 0), reverse=True)[:15]
            if p.get("problem_summary")
        ]

        intent_examples = [
            f'- "{p["title"]}"' for p in high_intent[:5]
        ]

        trend_info = trend_signals.get(cat, {})
        trend_signal = trend_info.get("signal", "desconocida")
        trend_ratio = trend_info.get("ratio", 1.0)

        prompt = f"""Categoria: {cat}
Total de quejas detectadas: {total}
Quejas con intencion de pago (score 2-3): {intent_count}
Tendencia: {trend_signal} (ratio semana actual vs promedio: {trend_ratio}x)

Principales problemas identificados:
{chr(10).join(f'- {s}' for s in top_summaries)}

Ejemplos de alta intencion de pago:
{chr(10).join(intent_examples) if intent_examples else '(ninguno detectado)'}

Genera el brief de oportunidad con esta estructura exacta:

## Oportunidad: {cat}

**Resumen ejecutivo**: [2-3 oraciones que expliquen el problema y por que es una oportunidad]

**Problema central**: [descripcion concreta del dolor, con datos del volumen]

**Ideas de producto o servicio**:
1. [idea especifica + razon por la que resuelve el problema]
2. [idea especifica + razon por la que resuelve el problema]
3. [idea especifica + razon por la que resuelve el problema]

**Por que ahora**: [2 oraciones sobre timing de mercado, tendencias tecnologicas o cambios de contexto]

**Senales de demanda**: [menciona el ratio de intencion de pago y lo que implica]

**Riesgos clave**:
- [riesgo 1]
- [riesgo 2]
- [riesgo 3]

**Primeros pasos para validar**:
1. [accion concreta]
2. [accion concreta]
"""

        try:
            response = client.messages.create(
                model=SONNET,
                max_tokens=1200,
                system=BRIEF_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            briefs[cat] = response.content[0].text.strip()
        except Exception as e:
            print(f"[Analyzer] Error generando brief para '{cat}': {e}")
            briefs[cat] = f"*Error generando brief: {e}*"

        time.sleep(1)

    return briefs


# ── 5. Pipeline completo ───────────────────────────────────────────────────────

def run_analysis(
    posts: list[dict],
    period_days: int,
    include_google_trends: bool = True,
    top_n_for_briefs: int = 3,
    progress_callback=None,
) -> dict:
    """
    Pipeline completo: clasifica → calcula tendencias → genera briefs.
    Retorna un dict con todos los resultados listos para la UI.
    """

    # Paso 1: Clasificacion LLM
    if progress_callback:
        progress_callback("Clasificando posts con Claude Haiku...", 0.2)
    classified = classify_posts(posts, progress_callback=None)

    # Paso 2: Agrupar por categoria
    by_category: dict[str, list] = defaultdict(list)
    for post in classified:
        by_category[post.get("category", "Sin categoria")].append(post)

    # Top categorias por volumen
    top_cats = sorted(by_category.keys(), key=lambda c: len(by_category[c]), reverse=True)

    # Paso 3: Tendencias temporales
    if progress_callback:
        progress_callback("Calculando tendencias temporales...", 0.5)
    trends_data = compute_temporal_trends(classified, period_days)

    # Paso 4: Google Trends (opcional)
    google_trends_data = {}
    if include_google_trends:
        if progress_callback:
            progress_callback("Consultando Google Trends...", 0.65)
        kw_map = extract_keywords_per_category(classified, top_cats[:4])
        google_trends_data = fetch_google_trends(kw_map, period_days)

    # Paso 5: Briefs de oportunidad para top N categorias
    if progress_callback:
        progress_callback("Generando briefs de oportunidad con Claude Sonnet...", 0.75)
    top_for_briefs = top_cats[:top_n_for_briefs]
    briefs = generate_opportunity_briefs(
        classified,
        top_for_briefs,
        trends_data["trend_signals"],
    )

    if progress_callback:
        progress_callback("Analisis completo.", 1.0)

    return {
        "posts": classified,
        "by_category": dict(by_category),
        "top_categories": top_cats,
        "trends": trends_data,
        "google_trends": google_trends_data,
        "briefs": briefs,
        "meta": {
            "period_days": period_days,
            "total_posts": len(classified),
            "total_categories": len(by_category),
            "new_categories": list({p["category"] for p in classified if p.get("is_new_category")}),
            "high_intent_count": sum(1 for p in classified if p.get("payment_intent", 0) >= 2),
            "run_at": datetime.now().isoformat(),
        },
    }
