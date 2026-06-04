import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.models.schemas import (
    DatasetUploadResponse,
    QuestionRequest,
    QueryResult,
    DatasetInfo,
    HealthResponse,
)
from app.models.database import get_db
from app.etl.ingest import ingest_csv
from app.agent.analyst import answer_question

router = APIRouter()


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ─── Datasets ────────────────────────────────────────────────────────────────

@router.post("/datasets/upload", response_model=DatasetUploadResponse, tags=["Datasets"])
async def upload_dataset(
    file: UploadFile = File(..., description="CSV file to upload"),
    description: str = Form("", description="Optional description of the dataset"),
):
    """
    Upload a CSV file. The system will:
    - Parse and clean the data with Pandas
    - Infer the schema
    - Load it into SQLite
    - Return the dataset ID you'll use for questions
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    try:
        contents = await file.read()
        import io
        result = await ingest_csv(io.BytesIO(contents), file.filename, description)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to ingest file: {str(e)}")

    return DatasetUploadResponse(
        dataset_id=result["dataset_id"],
        name=result["name"],
        row_count=result["row_count"],
        columns=result["columns"],
        message=f"Dataset loaded successfully with {result['row_count']} rows.",
    )


@router.get("/datasets", response_model=list[DatasetInfo], tags=["Datasets"])
async def list_datasets(db=Depends(get_db)):
    """List all uploaded datasets."""
    cursor = await db.execute(
        "SELECT id, name, description, schema_json, row_count, created_at FROM datasets ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [
        DatasetInfo(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            row_count=r["row_count"] or 0,
            columns=json.loads(r["schema_json"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/datasets/{dataset_id}", response_model=DatasetInfo, tags=["Datasets"])
async def get_dataset(dataset_id: int, db=Depends(get_db)):
    """Get details of a specific dataset."""
    cursor = await db.execute(
        "SELECT id, name, description, schema_json, row_count, created_at FROM datasets WHERE id = ?",
        (dataset_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return DatasetInfo(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        row_count=row["row_count"] or 0,
        columns=json.loads(row["schema_json"]),
        created_at=row["created_at"],
    )


# ─── Queries (AI Agent) ───────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResult, tags=["AI Agent"])
async def ask_question(body: QuestionRequest):
    """
    Ask a natural language question about your dataset.
    The AI agent will:
    1. Generate a SQL query tailored to your question and schema
    2. Execute it against your data
    3. Return the results with a human-readable explanation
    4. Suggest a chart type to visualize the results
    """
    try:
        result = await answer_question(body.question, body.dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    return QueryResult(**result)


@router.get("/queries/{dataset_id}", tags=["AI Agent"])
async def get_query_history(dataset_id: int, db=Depends(get_db)):
    """Return past questions and generated SQL for a dataset."""
    cursor = await db.execute(
        """SELECT id, question, generated_sql, chart_type, explanation, exec_time_ms, created_at
           FROM queries WHERE dataset_id = ? ORDER BY created_at DESC LIMIT 50""",
        (dataset_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
