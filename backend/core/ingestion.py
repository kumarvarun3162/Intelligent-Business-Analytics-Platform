# backend/core/ingestion.py

import uuid
import chardet
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Any

from models.schemas import (
    ColumnInfo, FileMetadata, FileType, UploadStatus
)


# ──────────────────────────────────────────────
# 1. Encoding detection
# ──────────────────────────────────────────────

def detect_encoding(file_bytes: bytes) -> str:
    """
    Use chardet to detect the character encoding of raw file bytes.
    Falls back to 'utf-8' when confidence is low.

    Why this matters: a file saved in Windows Excel often uses
    'Windows-1252' encoding. If we assume UTF-8 and it's not,
    pandas will throw a UnicodeDecodeError or silently mangle text.
    """
    result = chardet.detect(file_bytes)
    encoding = result.get("encoding", "utf-8")
    confidence = result.get("confidence", 0)

    # If chardet isn't confident, default to utf-8
    if not encoding or confidence < 0.6:
        return "utf-8"

    return encoding.lower()


# ──────────────────────────────────────────────
# 2. File parsing
# ──────────────────────────────────────────────

def parse_file(
    file_bytes: bytes,
    filename: str,
    encoding: str
) -> pd.DataFrame:
    """
    Parse raw bytes into a pandas DataFrame.
    Supports CSV, Excel (.xlsx/.xls), and JSON.

    We use BytesIO so we never have to write to disk just to read.
    """
    from io import BytesIO

    ext = Path(filename).suffix.lower().lstrip(".")
    buffer = BytesIO(file_bytes)

    if ext == "csv":
        # Try the detected encoding first; fall back to latin-1
        # (latin-1 accepts any byte, so it never raises on bad chars)
        try:
            df = pd.read_csv(buffer, encoding=encoding)
        except UnicodeDecodeError:
            buffer.seek(0)
            df = pd.read_csv(buffer, encoding="latin-1")

    elif ext in ("xlsx", "xls"):
        # Excel files are binary — encoding doesn't apply
        df = pd.read_excel(buffer, engine="openpyxl")

    elif ext == "json":
        # Try records format first (list of dicts), then columnar
        try:
            df = pd.read_json(buffer, encoding=encoding)
        except ValueError:
            buffer.seek(0)
            df = pd.read_json(buffer, orient="records", encoding=encoding)

    else:
        raise ValueError(f"Unsupported file type: .{ext}")

    return df


# ──────────────────────────────────────────────
# 3. Column profiling
# ──────────────────────────────────────────────

def profile_column(series: pd.Series) -> ColumnInfo:
    """
    Extract structural information about one column.

    This is non-destructive — we're just observing, not cleaning.
    The cleaning phase (Phase 2) will act on what we find here.
    """
    total     = len(series)
    null_count = int(series.isna().sum())
    non_null  = total - null_count

    # Get sample values: first 3 non-null unique values
    unique_vals  = series.dropna().unique()
    sample_count = min(3, len(unique_vals))
    samples = []
    for v in unique_vals[:sample_count]:
        # Convert numpy types to native Python for JSON serialization
        if isinstance(v, (np.integer,)):
            samples.append(int(v))
        elif isinstance(v, (np.floating,)):
            samples.append(float(v))
        else:
            samples.append(str(v))

    return ColumnInfo(
        name            = series.name,
        dtype           = str(series.dtype),
        non_null_count  = non_null,
        null_count      = null_count,
        null_percentage = round((null_count / total) * 100, 2) if total > 0 else 0.0,
        unique_count    = int(series.nunique()),
        sample_values   = samples,
    )


# ──────────────────────────────────────────────
# 4. Build full metadata
# ──────────────────────────────────────────────

def extract_metadata(
    df:        pd.DataFrame,
    filename:  str,
    file_size: int,
    encoding:  str,
) -> FileMetadata:
    """
    Given a parsed DataFrame, build the complete FileMetadata object
    that describes this dataset to the frontend.
    """
    ext = Path(filename).suffix.lower().lstrip(".")

    columns = [profile_column(df[col]) for col in df.columns]

    return FileMetadata(
        session_id    = str(uuid.uuid4()),
        original_name = filename,
        file_type     = FileType(ext) if ext in FileType._value2member_map_ else FileType.CSV,
        file_size_kb  = round(file_size / 1024, 2),
        encoding      = encoding,
        row_count     = len(df),
        column_count  = len(df.columns),
        columns       = columns,
        status        = UploadStatus.COMPLETED,
    )


# ──────────────────────────────────────────────
# 5. Preview rows
# ──────────────────────────────────────────────

def get_preview(df: pd.DataFrame, n: int = 10) -> list:
    """
    Return the first n rows as a list of dicts (JSON-serializable).

    We replace NaN with None so JSON serialization works cleanly
    (JSON has no NaN; it would produce invalid output otherwise).
    """
    preview_df = df.head(n).copy()

    # Replace NaN/NaT/inf with None for clean JSON
    preview_df = preview_df.where(pd.notnull(preview_df), other=None)

    # Convert numpy types in cells to native Python
    records = preview_df.to_dict(orient="records")
    cleaned = []
    for row in records:
        clean_row = {}
        for k, v in row.items():
            if isinstance(v, (np.integer,)):
                clean_row[k] = int(v)
            elif isinstance(v, (np.floating,)):
                clean_row[k] = float(v) if not np.isnan(v) else None
            else:
                clean_row[k] = v
        cleaned.append(clean_row)

    return cleaned


# ──────────────────────────────────────────────
# 6. Master ingest function (called by the route)
# ──────────────────────────────────────────────

def ingest_file(
    file_bytes: bytes,
    filename:   str,
    file_size:  int,
) -> Tuple[pd.DataFrame, FileMetadata, list]:
    """
    Top-level function that orchestrates the full ingestion pipeline:
    detect encoding → parse → profile → preview.

    Returns: (dataframe, metadata, preview_rows)
    """
    encoding = detect_encoding(file_bytes)
    df       = parse_file(file_bytes, filename, encoding)
    metadata = extract_metadata(df, filename, file_size, encoding)
    preview  = get_preview(df)

    return df, metadata, preview