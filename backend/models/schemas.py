from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from typing import Literal


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

class CleaningAction(BaseModel):
    """Records one atomic cleaning action on a column or the whole dataset."""
    stage:       str            # e.g. "missing_values", "outliers"
    column:      Optional[str]  # None = whole-dataset action
    action:      str            # e.g. "imputed_mean", "dropped_duplicate"
    rows_affected: int
    detail:      str            # human-readable description


class OutlierInfo(BaseModel):
    """Outlier statistics for one numeric column."""
    column:       str
    method:       str           # "iqr" or "zscore"
    outlier_count: int
    lower_bound:  Optional[float]
    upper_bound:  Optional[float]
    action_taken: str           # "capped", "flagged", "dropped"


class CleaningReport(BaseModel):
    """
    Full audit report returned after the cleaning pipeline runs.
    This is stored in SQLite and sent to the frontend.
    """
    session_id:           str
    original_row_count:   int
    cleaned_row_count:    int
    original_col_count:   int
    cleaned_col_count:    int
    rows_removed:         int
    cols_removed:         int
    total_nulls_before:   int
    total_nulls_after:    int
    duplicates_removed:   int
    outliers_detected:    int
    quality_score:        float          # 0.0 – 100.0
    quality_grade:        str            # "A", "B", "C", "D", "F"
    actions:              List[CleaningAction]
    outlier_details:      List[OutlierInfo]
    column_type_map:      Dict[str, str] # col → inferred type


class CleaningResponse(BaseModel):
    """Returned to frontend after /api/clean is called."""
    success:        bool
    message:        str
    report:         Optional[CleaningReport] = None
    preview:        Optional[List[Dict[str, Any]]] = None  # first 10 cleaned rows

    
class TransformRecord(BaseModel):
    """
    Records one transformation applied to one column.
    Contains enough information to replay the transform on new data.
    """
    column:        str
    transform:     str          # e.g. "one_hot", "minmax_scale", "log_transform"
    params:        Dict[str, Any]  # e.g. {"min": 0.0, "max": 100.0}
    new_columns:   List[str]    # columns created (may be multiple for one-hot)
    original_dtype: str
    output_dtype:  str
    note:          str          # human-readable explanation


class ValidationRule(BaseModel):
    """A single validation rule applied to a column."""
    column:  str
    rule:    str          # e.g. "range_check", "no_nulls", "unique_values"
    passed:  bool
    detail:  str


class EngineeringReport(BaseModel):
    """Full report returned after the engineering pipeline runs."""
    session_id:         str
    original_col_count: int
    engineered_col_count: int
    new_cols_created:   int
    transforms:         List[TransformRecord]
    validation_results: List[ValidationRule]
    validation_passed:  bool
    feature_summary:    Dict[str, str]  # col → final type label
    ml_ready:           bool            # True if no nulls, all numeric/bool


class EngineeringResponse(BaseModel):
    success:  bool
    message:  str
    report:   Optional[EngineeringReport] = None
    preview:  Optional[List[Dict[str, Any]]] = None