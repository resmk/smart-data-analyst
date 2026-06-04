import pandas as pd
import aiosqlite
import json
import re
from pathlib import Path
from typing import BinaryIO

from app.models.database import DB_PATH


DTYPE_MAP = {
    "int64": "INTEGER",
    "float64": "REAL",
    "bool": "INTEGER",
    "datetime64[ns]": "TEXT",
    "object": "TEXT",
}


def _safe_table_name(filename: str) -> str:
    """Turn a filename into a safe SQLite table name."""
    name = Path(filename).stem
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_").lower()
    return f"ds_{name}"


def _infer_schema(df: pd.DataFrame) -> list[dict]:
    schema = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        sql_type = DTYPE_MAP.get(dtype, "TEXT")
        schema.append({
            "name": col,
            "dtype": dtype,
            "sql_type": sql_type,
            "nulls": int(df[col].isna().sum()),
            "unique": int(df[col].nunique()),
        })
    return schema


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Light cleaning: strip whitespace from string cols, parse dates where obvious."""
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
        # Attempt date parsing for columns that look like dates
        if any(kw in col.lower() for kw in ("date", "time", "created", "updated")):
            try:
                df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
    return df


async def ingest_csv(file: BinaryIO, filename: str, description: str = "") -> dict:
    """
    Ingest a CSV file:
    1. Read with Pandas
    2. Clean & validate
    3. Create a table in SQLite
    4. Register in datasets table
    Returns dataset metadata.
    """
    df = pd.read_csv(file)
    df = _clean_dataframe(df)

    table_name = _safe_table_name(filename)
    schema = _infer_schema(df)
    schema_json = json.dumps(schema)

    col_defs = ", ".join(
        f'"{s["name"]}" {s["sql_type"]}' for s in schema
    )

    async with aiosqlite.connect(DB_PATH) as db:
        # Drop existing table of the same name to allow re-upload
        await db.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        await db.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

        rows = df.where(pd.notna(df), None).values.tolist()
        placeholders = ", ".join(["?"] * len(df.columns))
        await db.executemany(
            f'INSERT INTO "{table_name}" VALUES ({placeholders})', rows
        )

        # Register dataset
        await db.execute(
            """INSERT INTO datasets (name, description, schema_json, row_count)
               VALUES (?, ?, ?, ?)""",
            (table_name, description or filename, schema_json, len(df)),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT id FROM datasets WHERE name = ? ORDER BY id DESC LIMIT 1",
            (table_name,),
        )
        row = await cursor.fetchone()
        dataset_id = row[0]

    return {
        "dataset_id": dataset_id,
        "name": table_name,
        "row_count": len(df),
        "columns": schema,
    }
