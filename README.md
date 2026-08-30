# Radar de Oportunidades

Dashboard que analiza quejas en foros y redes para detectar oportunidades de negocio.

## Dashboard

**https://radar-oportunidades-flpfxsjeibbhyuzcj9snqp.streamlit.app/**

## Como funciona

1. GitHub Actions corre automaticamente los lunes y jueves a las 04:00 Argentina
2. Recolecta posts de distintas fuentes y los clasifica con IA
3. Genera `data/latest.json` y lo sube al repo
4. Streamlit muestra los datos actualizados automaticamente

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

- `ANTHROPIC_OAUTH_TOKEN` — API key de Anthropic
- `STACK_EXCHANGE_KEY` — API key de Stack Exchange
