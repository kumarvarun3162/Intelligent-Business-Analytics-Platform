from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class FileType(str, Enum):
    CSV  = "csv"
    XLSX = "xlsx"
    XLS  = "xls"
    JSON = "json"


class UploadStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"


class ColumnInfo(BaseModel):
    """Describes a single column in the uploaded dataset."""
    name:          str
    dtype:         str           # e.g. "int64", "object", "float64"
    non_null_count: int
    null_count:    int
    null_percentage: float       # 0.0 to 100.0
    unique_count:  int
    sample_values: List[Any]     # first 3 unique values for preview


class FileMetadata(BaseModel):
    """Everything we know about an uploaded file after parsing."""
    session_id:    str
    original_name: str
    file_type:     FileType
    file_size_kb:  float
    encoding:      str
    row_count:     int
    column_count:  int
    columns:       List[ColumnInfo]
    status:        UploadStatus = UploadStatus.COMPLETED


class UploadResponse(BaseModel):
    """Returned to the frontend after a successful upload."""
    success:   bool
    message:   str
    metadata:  Optional[FileMetadata] = None
    preview:   Optional[List[Dict[str, Any]]] = None  # first 10 rows


class ErrorResponse(BaseModel):
    """Returned when something goes wrong."""
    success: bool = False
    error:   str
    detail:  Optional[str] = None