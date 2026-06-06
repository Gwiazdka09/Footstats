"""
data.py – Pydantic validation + deduplication for scraped game data.

Exports:
    GameRecord: Pydantic model for single match
    validate_games(df) -> (valid_df, errors_df)
    deduplicate_games(df) -> df_unique
"""

from datetime import datetime
from typing import Optional
import logging
import pandas as pd
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class GameRecord(BaseModel):
    """Single match record with validation."""

    match_date: str = Field(..., description="ISO date YYYY-MM-DD")
    team_home: str = Field(..., min_length=1, max_length=100)
    team_away: str = Field(..., min_length=1, max_length=100)
    league: str = Field(default="", max_length=100)
    gole_g: Optional[int] = Field(default=None, ge=0, le=20)
    gole_a: Optional[int] = Field(default=None, ge=0, le=20)
    xg_g: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    xg_a: Optional[float] = Field(default=None, ge=0.0, le=10.0)

    @field_validator("match_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format: {v}")
        return v

    @field_validator("team_home", "team_away")
    @classmethod
    def validate_teams_not_equal(cls, v: str, info) -> str:
        if info.field_name == "team_away" and hasattr(info, "data"):
            home = info.data.get("team_home", "")
            if v.strip().lower() == home.strip().lower():
                raise ValueError("team_home and team_away cannot be equal")
        return v


def validate_games(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Validate game records. Return (valid_df, errors_df).
    Log validation errors. Errors written to validation_errors.csv.
    """
    if df.empty:
        return df, pd.DataFrame()

    valid_records = []
    error_records = []

    for idx, row in df.iterrows():
        try:
            rec = GameRecord(
                match_date=row.get("match_date", ""),
                team_home=row.get("team_home", ""),
                team_away=row.get("team_away", ""),
                league=row.get("league", ""),
                gole_g=row.get("gole_g"),
                gole_a=row.get("gole_a"),
                xg_g=row.get("xg_g"),
                xg_a=row.get("xg_a"),
            )
            valid_records.append(rec.model_dump())
        except (OSError, ValueError, KeyError) as exc:
            error_msg = str(exc)
            logger.warning(f"[Data] Validation error row {idx}: {error_msg}")
            row_copy = row.to_dict()
            row_copy["_error"] = error_msg
            error_records.append(row_copy)

    valid_df = pd.DataFrame(valid_records) if valid_records else pd.DataFrame()
    errors_df = pd.DataFrame(error_records) if error_records else pd.DataFrame()

    if not errors_df.empty:
        errors_df.to_csv("validation_errors.csv", index=False)
        logger.info(f"[Data] {len(errors_df)} validation errors → validation_errors.csv")

    return valid_df, errors_df


def deduplicate_games(df: pd.DataFrame, keep: str = "first") -> pd.DataFrame:
    """
    Remove duplicate game records. Deduplication key: (match_date, team_home, team_away).
    keep: 'first' or 'last'
    """
    if df.empty:
        return df

    cols = ["match_date", "team_home", "team_away"]
    if not all(c in df.columns for c in cols):
        logger.warning(f"[Data] Missing dedup columns. Available: {df.columns.tolist()}")
        return df

    before = len(df)
    df_dedup = df.drop_duplicates(subset=cols, keep=keep)
    after = len(df_dedup)

    if before > after:
        logger.info(f"[Data] Deduplicated {before - after} rows. {after} unique games remain.")

    return df_dedup
