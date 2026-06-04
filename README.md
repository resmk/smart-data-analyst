# Smart Data Analyst Agent

Ask questions about your data in plain English. The agent writes the SQL, runs it, and explains what it found.

---

## What it does

You upload a CSV. Then you ask things like:

- *"Which product category had the highest revenue last quarter?"*
- *"Show me the top 5 countries by number of returns."*
- *"Is there a trend in sales over time?"*

The backend sends your question and the table schema to a Groq-hosted LLM (Llama 3.3 70B by default), gets back a SQL query, runs it against your data, and returns the results — with a plain-English explanation and a chart type suggestion.

No frontend required. Everything is exposed as a REST API you can call from Postman, curl, or wire up to any UI.

---

## Why I built this

My previous projects (an E-Commerce Analytics Platform, a network flow visualizer) were fixed pipelines — you define the queries upfront, and that's what you get. I wanted to build something more flexible: a system where the analysis adapts to the question, not the other way around.

This project sits at the intersection of data engineering and applied AI. The ETL layer is real (Pandas cleaning, schema inference, SQLite loading), the AI layer is practical (structured prompting, SQL validation, error handling), and the API layer is production-ready (FastAPI, async, Docker, CI/CD).

I used Groq as the inference provider because of its speed — responses come back in under a second, which makes the agent feel interactive rather than batch-like.

---

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI (async) |
| AI Agent | Groq API — Llama 3.3 70B |
| ETL / Data Cleaning | Pandas |
| Database | SQLite via aiosqlite |
| Config | pydantic-settings |
| Containerization | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Testing | pytest + pytest-asyncio |

---

## Project structure

```
smart-data-analyst/
├── app/
│   ├── main.py              # FastAPI app + lifespan
│   ├── api/
│   │   └── routes.py        # All API endpoints
│   ├── agent/
│   │   └── analyst.py       # LLM prompt builder + SQL runner
│   ├── etl/
│   │   └── ingest.py        # CSV parsing, cleaning, schema inference
│   ├── models/
│   │   ├── database.py      # SQLite init + async connection
│   │   └── schemas.py       # Pydantic request/response models
│   └── utils/
│       └── config.py        # Settings via .env
├── data/
│   └── samples/
│       └── ecommerce_orders.csv   # Sample dataset to get started
├── tests/
│   └── test_api.py
├── .github/workflows/ci.yml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Getting started

### 1. Clone the repo

```bash
git clone https://github.com/resmk/smart-data-analyst.git
cd smart-data-analyst
```

### 2. Get a Groq API key

Sign up for free at [console.groq.com](https://console.groq.com) → API Keys → Create key.

### 3. Set up your environment

```bash
cp .env.example .env
```

Open `.env` and add your Groq API key:

```
OPENAI_API_KEY=gsk_...your-groq-key-here...
OPENAI_MODEL=llama-3.3-70b-versatile
```

> The variable is named `OPENAI_API_KEY` because Groq uses the OpenAI-compatible API format — no extra SDK needed.

### 4. Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000`. Open `http://localhost:8000/docs` for the interactive Swagger UI.

### 5. Run with Docker

```bash
docker-compose up --build
```

Same URL: `http://localhost:8000/docs`

---

## API walkthrough

### Upload a dataset

```bash
curl -X POST http://localhost:8000/api/v1/datasets/upload \
  -F "file=@data/samples/ecommerce_orders.csv" \
  -F "description=Sample e-commerce orders"
```

Response:
```json
{
  "dataset_id": 1,
  "name": "ds_ecommerce_orders",
  "row_count": 25,
  "columns": [...],
  "message": "Dataset loaded successfully with 25 rows."
}
```

### Ask a question

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": 1,
    "question": "Which product category had the highest total revenue?"
  }'
```

Response:
```json
{
  "query_id": 1,
  "question": "Which product category had the highest total revenue?",
  "generated_sql": "SELECT category, SUM(total_revenue) AS total_revenue FROM \"ds_ecommerce_orders\" GROUP BY category ORDER BY total_revenue DESC LIMIT 100",
  "explanation": "Electronics came out on top, driven by higher unit prices and multiple purchases.",
  "chart_type": "bar",
  "columns": ["category", "total_revenue"],
  "rows": [["Electronics", 999.91]],
  "row_count": 1,
  "exec_time_ms": 8
}
```

### See past queries

```bash
curl http://localhost:8000/api/v1/queries/1
```

### List all datasets

```bash
curl http://localhost:8000/api/v1/datasets
```

---

## How the AI agent works

When you ask a question, the agent:

1. Loads the table's schema from the database (column names, types, cardinality)
2. Builds a structured system prompt that includes the schema and strict output format rules
3. Sends your question to Groq with `temperature=0.1` (low randomness — we want consistent SQL, not creative SQL)
4. Parses the JSON response to extract the SQL query and explanation
5. Executes the SQL against the actual data in SQLite
6. Persists everything (question, SQL, result, timing) for auditing
7. Suggests a chart type based on keyword matching in your question

The prompt instructs the model to respond only in JSON, which makes parsing reliable. If the model adds markdown fences anyway, they're stripped before parsing.

---

## Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

The tests don't require a real Groq key — they test the API, upload flow, and input validation independently of the LLM.

---

## What I'd add next

- **PostgreSQL support** — swap SQLite for a real database for larger datasets
- **LangChain agent loop** — retry on SQL errors, self-correct the query
- **Chart rendering** — generate Plotly charts server-side and return them as base64
- **Authentication** — JWT-protected endpoints so multiple users can manage their own datasets
- **Streaming responses** — stream the LLM explanation token by token via SSE

---

## License

MIT
