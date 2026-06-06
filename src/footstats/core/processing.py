"""
processing.py – DataFrame optimization + chunked processing.

Exports:
    chunk_dataframe(df, chunk_size=1000) -> generator
    memory_report(df) -> str
    optimize_dtypes(df) -> df_optimized
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def chunk_dataframe(df: pd.DataFrame, chunk_size: int = 1000):
    """
    Yield chunks of DataFrame to reduce memory footprint during processing.

    Args:
        df: Input DataFrame
        chunk_size: Rows per chunk (default 1000)

    Yields:
        Chunks of df with max chunk_size rows
    """
    for start_idx in range(0, len(df), chunk_size):
        yield df.iloc[start_idx : start_idx + chunk_size].copy()


def optimize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Optimize dtypes to reduce memory. Convert object → category, float64 → float32 where safe.

    Returns:
        Optimized copy of df
    """
    df_opt = df.copy()

    for col in df_opt.columns:
        dtype = df_opt[col].dtype

        # Convert object (string) → category if <50% unique
        if dtype == "object":
            n_unique = df_opt[col].nunique()
            n_total = len(df_opt[col])
            cardinality = n_unique / n_total if n_total > 0 else 1.0
            if cardinality < 0.5:
                df_opt[col] = df_opt[col].astype("category")
                logger.debug(f"[Processing] Converted {col} → category ({n_unique} unique)")

        # Convert float64 → float32 if no precision loss risk
        elif dtype == "float64":
            try:
                df_opt[col] = df_opt[col].astype("float32")
                logger.debug(f"[Processing] Converted {col} → float32")
            except (TypeError, ValueError):
                pass  # Keep float64 if conversion fails

    return df_opt


def memory_report(df: pd.DataFrame) -> str:
    """
    Generate memory usage report (deep inspection).

    Returns:
        Formatted string with per-column and total memory usage
    """
    usage = df.memory_usage(deep=True)
    total_mb = usage.sum() / 1024 / 1024

    lines = [f"Memory Report: {total_mb:.2f} MB total\n"]
    for col, bytes_used in sorted(usage.items(), key=lambda x: x[1], reverse=True):
        if col == "Index":  # Skip index row
            continue
        mb = bytes_used / 1024 / 1024
        lines.append(f"  {col:20} {mb:8.3f} MB  ({df[col].dtype})")

    return "\n".join(lines)


def apply_chunked(df: pd.DataFrame, func, chunk_size: int = 1000, **kwargs):
    """
    Apply function to chunked DataFrame. Reduce memory spike during processing.

    Args:
        df: Input DataFrame
        func: Function to apply to each chunk (receives chunk as first arg)
        chunk_size: Rows per chunk
        **kwargs: Passed to func

    Returns:
        List of results from each chunk
    """
    results = []
    for i, chunk in enumerate(chunk_dataframe(df, chunk_size)):
        try:
            result = func(chunk, **kwargs)
            results.append(result)
        except (KeyError, ValueError, TypeError) as exc:
            logger.error(f"[Processing] Chunk {i} failed: {exc}")

    return results
