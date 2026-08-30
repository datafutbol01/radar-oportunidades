# Radar de Oportunidades

Sistema automatizado que detecta oportunidades de negocio analizando quejas reales de usuarios en foros y comunidades online. Usa IA (Claude de Anthropic) para clasificar los posts, detectar intención de pago y generar briefs accionables por categoría.

## Dashboard

**https://radar-oportunidades-flpfxsjeibbhyuzcj9snqp.streamlit.app/**

El dashboard tiene 4 tabs:
- **Ranking** — categorias ordenadas por volumen de quejas y porcentaje de intención de pago
- **Tendencias** — evolución semanal por categoria y señales (creciendo, spike, estable, declinando)
- **Oportunidades** — briefs generados por Claude con resumen ejecutivo, ideas de producto y pasos para validar
- **Explorar** — tabla filtrable con todos los posts clasificados, descargable como CSV

En el sidebar hay un filtro por idioma/region para ver solo los posts de una fuente especifica.

## Fuentes de datos

| Fuente | Idioma |
|--------|--------|
| Hacker News | Ingles |
| Stack Exchange (StackOverflow, UX, WebApps, SoftwareRecs) | Ingles |
| Reddit: r/SomebodyMakeThis, r/Entrepreneur, r/startups, r/mildlyinfuriating, r/rant, r/techsupport, r/productivity, r/smallbusiness | Ingles |
| Reddit: r/argentina, r/es | Espanol |
| Reddit: r/brasil, r/portugal | Portugues |
| Reddit: r/france, r/Quebec | Frances |
| Reddit: r/de, r/Austria | Aleman |
| Reddit: r/italy, r/italyInformatica | Italiano |

## Como funciona el pipeline

1. **Recoleccion** (`collector.py`) — descarga posts de los ultimos 30 dias buscando frases de queja e intencion de compra
2. **Clasificacion** (`analyzer.py`) — Claude Haiku clasifica cada post por categoria y le asigna un score de intencion de pago (0-3)
3. **Tendencias** — calcula evolucion semanal y detecta categorias en crecimiento vs picos momentaneos
4. **Briefs** (`analyzer.py`) — Claude Haiku genera un brief de oportunidad en español para las top categorias
5. **Guardado** — los resultados se guardan en `data/latest.json` y en `data/history/YYYY-MM-DD.json`
6. **Dashboard** (`app.py`) — Streamlit lee el JSON y muestra todo en una UI interactiva

## Automatizacion

GitHub Actions corre el pipeline automaticamente los **lunes y jueves a las 12:00 del mediodia Argentina (15:00 UTC)**.

Para correrlo manualmente desde GitHub: Actions → "Analisis programado" → Run workflow.

## Correr localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Generar reporte manualmente

```bash
python generate_report.py
```

## Secrets necesarios en GitHub

- `ANTHROPIC_OAUTH_TOKEN` — token OAuth de Anthropic (Claude)
- `STACK_EXCHANGE_KEY` — API key de Stack Exchange
