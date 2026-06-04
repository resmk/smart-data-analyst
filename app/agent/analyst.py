import json
import time
import re
import aiosqlite
from openai import AsyncOpenAI
from typing import Optional

from app.models.database import DB_PATH
from app.utils.config import settings


client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url="https://api.groq.com/openai/v1",
)

CHART_KEYWORDS = {
    "bar": ["top", "best", "worst", "highest", "lowest", "rank", "compare", "by category", "by product", "count"],
    "line": ["trend", "over time", "per month", "per week", "per day", "growth", "change", "timeline"],
    "pie": ["share", "proportion", "percentage", "breakdown", "distribution"],
    "scatter": ["correlation", "relationship between", "vs", "versus"],
}


def _suggest_chart(question: str) -> Optional[str]:
    q = question.lower()
    for chart_type, keywords in CHART_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return chart_type
    return "table"


def _build_system_prompt(table_name: str, schema: list[dict]) -> str:
    col_descriptions = "\n".join(
        f"  - {col['name']} ({col['sql_type']}, {col['unique']} unique values)"
        for col in schema
    )
    return f"""You are an expert data analyst and SQL engineer.
The user has a SQLite table named "{table_name}" with these columns:

{col_descriptions}

Your job:
1. Write a single valid SQLite SELECT query that answers the user's question.
2. Write a clear, concise explanation (2-3 sentences) of what the query does and what insight it surfaces.

Respond ONLY with valid JSON in this exact format — no markdown, no extra text:
{{
  "sql": "<your SELECT query here>",
  "explanation": "<your explanation here>"
}}

Rules:
- Always use the exact table name: "{table_name}"
- Wrap column names in double quotes if they contain spaces or special chars
- LIMIT results to 100 rows unless the question asks for all
- Prefer readable column aliases (AS keyword)
- Never use INSERT, UPDATE, DELETE, DROP
"""


async def _run_sql(sql: str) -> tuple[list[str], list[list], int]:
    """Execute the generated SQL and return columns, rows, exec_time_ms."""
    start = time.perf_counter()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(sql)
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        data = [list(r) for r in rows]
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return columns, data, elapsed_ms


async def answer_question(
    question: str, dataset_id: int
) -> dict:
    """
    Full agent pipeline:
    1. Load dataset schema from DB
    2. Build contextual prompt
    3. Call LLM to generate SQL + explanation
    4. Execute SQL against SQLite
    5. Persist query record
    6. Return structured result
    """
    # Load dataset metadata
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT name, schema_json FROM datasets WHERE id = ?", (dataset_id,)
        )
        row = await cursor.fetchone()

    if not row:
        raise ValueError(f"Dataset {dataset_id} not found.")

    table_name = row["name"]
    schema = json.loads(row["schema_json"])

    system_prompt = _build_system_prompt(table_name, schema)

    # Call the LLM
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=800,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if the model adds them anyway
    raw = re.sub(r"```(?:json)?", "", raw).strip("`").strip()

    parsed = json.loads(raw)
    sql = parsed["sql"].strip().rstrip(";")
    explanation = parsed["explanation"]

    # Execute the query
    columns, rows, exec_time_ms = await _run_sql(sql)

    chart_type = _suggest_chart(question)

    # Persist
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO queries
               (dataset_id, question, generated_sql, result_json, chart_type, explanation, exec_time_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                dataset_id,
                question,
                sql,
                json.dumps({"columns": columns, "rows": rows[:10]}),
                chart_type,
                explanation,
                exec_time_ms,
            ),
        )
        query_id = cursor.lastrowid
        await db.commit()

    return {
        "query_id": query_id,
        "question": question,
        "generated_sql": sql,
        "explanation": explanation,
        "chart_type": chart_type,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "exec_time_ms": exec_time_ms,
    }
