from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class DatasetUploadResponse(BaseModel):
    dataset_id: int
    name: str
    row_count: int
    columns: list[dict]
    message: str


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=500, example="Which product category had the highest revenue?")
    dataset_id: int


class QueryResult(BaseModel):
    query_id: int
    question: str
    generated_sql: str
    explanation: str
    chart_type: Optional[str]
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    exec_time_ms: int


class DatasetInfo(BaseModel):
    id: int
    name: str
    description: Optional[str]
    row_count: int
    columns: list[dict]
    created_at: str


class HealthResponse(BaseModel):
    status: str
    version: str
