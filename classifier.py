"""
Clasificacion de posts en categorias por keywords,
y extraccion de temas especificos dentro de cada categoria.
"""

from collections import Counter, defaultdict
import re
from categories import CATEGORIES


def _score_text(text: str, keywords: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def classify_post(post: dict) -> str | None:
    """Devuelve la categoria con mayor puntaje, o None si no llega al minimo."""
    full_text = f"{post.get('title', '')} {post.get('text', '')}"
    best_cat = None
    best_score = 0

    for cat_name, kw_dict in CATEGORIES.items():
        keywords = kw_dict.get("en", []) + kw_dict.get("es", [])
        score = _score_text(full_text, keywords)
        if score > best_score:
            best_score = score
            best_cat = cat_name

    return best_cat if best_score >= 1 else None


def extract_topics(posts: list[dict], top_n: int = 10) -> list[str]:
    """
    Extrae los temas mas frecuentes de una lista de posts usando
    bigrams y trigrams del titulo. Sin dependencias de NLP externas.
    """
    stop_words = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "it", "my", "i", "me", "we", "you",
        "he", "she", "they", "this", "that", "was", "are", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "not", "no", "so", "just", "when", "why", "how", "what",
        "there", "their", "which", "who", "its", "your", "our", "as", "up",
        "if", "about", "than", "then", "some", "can", "get", "got", "every",
        "am", "im", "like", "still", "always", "never", "even", "also",
    }

    ngrams: Counter = Counter()

    for post in posts:
        title = post.get("title", "").lower()
        words = re.findall(r"[a-z']+", title)
        words = [w for w in words if w not in stop_words and len(w) > 2]

        # bigrams
        for i in range(len(words) - 1):
            ngrams[f"{words[i]} {words[i+1]}"] += 1
        # trigrams
        for i in range(len(words) - 2):
            ngrams[f"{words[i]} {words[i+1]} {words[i+2]}"] += 1

    # filtrar ngrams que aparecen al menos 2 veces
    filtered = {k: v for k, v in ngrams.items() if v >= 2}
    top = sorted(filtered.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [phrase for phrase, _ in top]


def classify_all(posts: list[dict]) -> dict:
    """
    Devuelve un dict con:
      - 'by_category': {categoria: [posts]}
      - 'uncategorized': [posts]
      - 'topics_by_category': {categoria: [temas]}
    """
    by_category: dict[str, list] = defaultdict(list)
    uncategorized = []

    for post in posts:
        cat = classify_post(post)
        if cat:
            post["category"] = cat
            by_category[cat].append(post)
        else:
            post["category"] = None
            uncategorized.append(post)

    topics_by_category = {
        cat: extract_topics(cat_posts)
        for cat, cat_posts in by_category.items()
    }

    return {
        "by_category": dict(by_category),
        "uncategorized": uncategorized,
        "topics_by_category": topics_by_category,
    }
