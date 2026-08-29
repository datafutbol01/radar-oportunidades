"""
generate_report.py — corre en GitHub Actions los lunes y jueves.
Descarga posts, clasifica con Claude, guarda resultados en data/.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from collector import fetch_all
from analyzer import run_analysis

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
HISTORY_DIR = DATA_DIR / "history"
HISTORY_DIR.mkdir(exist_ok=True)

PERIOD_DAYS = 30
SOURCES = ["Hacker News", "Stack Overflow"]
TOP_N_BRIEFS = 3


def main():
    print(f"[{datetime.now().isoformat()}] Iniciando recoleccion...")

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: falta ANTHROPIC_API_KEY")
        sys.exit(1)

    posts = fetch_all(days=PERIOD_DAYS, sources=SOURCES)
    print(f"Posts recolectados: {len(posts)}")

    if not posts:
        print("Sin posts. Abortando.")
        sys.exit(1)

    results = run_analysis(
        posts,
        period_days=PERIOD_DAYS,
        include_google_trends=True,
        top_n_for_briefs=TOP_N_BRIEFS,
    )

    # Guardar latest.json
    latest_path = DATA_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, default=str, indent=2)
    print(f"Guardado: {latest_path}")

    # Guardar en historial
    today = datetime.now().strftime("%Y-%m-%d")
    history_path = HISTORY_DIR / f"{today}.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, default=str, indent=2)
    print(f"Historial: {history_path}")

    meta = results.get("meta", {})
    print(f"Analisis completo: {meta.get('total_posts')} posts, "
          f"{meta.get('total_categories')} categorias, "
          f"{meta.get('high_intent_count')} con intencion de pago")


if __name__ == "__main__":
    main()
