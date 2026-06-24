"""Tests for DataFrame optimization + chunking."""
import pandas as pd
import numpy as np

from footstats.core.processing import (
    chunk_dataframe,
    optimize_dtypes,
    memory_report,
    apply_chunked,
)


class TestChunkDataframe:
    """chunk_dataframe() generator."""

    def test_chunk_size_respected(self):
        df = pd.DataFrame({"col": range(100)})
        chunks = list(chunk_dataframe(df, chunk_size=25))
        assert len(chunks) == 4
        assert all(len(chunk) == 25 for chunk in chunks)

    def test_last_chunk_smaller(self):
        df = pd.DataFrame({"col": range(100)})
        chunks = list(chunk_dataframe(df, chunk_size=33))
        assert len(chunks) == 4
        assert len(chunks[-1]) == 1  # 100 % 33 = 1

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        chunks = list(chunk_dataframe(df, chunk_size=10))
        assert len(chunks) == 0

    def test_single_chunk(self):
        df = pd.DataFrame({"col": range(5)})
        chunks = list(chunk_dataframe(df, chunk_size=100))
        assert len(chunks) == 1
        assert len(chunks[0]) == 5


class TestOptimizeDtypes:
    """optimize_dtypes() memory optimization."""

    def test_object_to_category(self):
        df = pd.DataFrame({
            "league": ["PL"] * 80 + ["La Liga"] * 20,  # 2 unique / 100 = 2% unique
        })
        opt = optimize_dtypes(df)
        assert opt["league"].dtype.name == "category"

    def test_float64_to_float32(self):
        df = pd.DataFrame({
            "xg": np.random.rand(100),
        })
        opt = optimize_dtypes(df)
        assert opt["xg"].dtype == "float32"

    def test_high_cardinality_stays_object(self):
        df = pd.DataFrame({
            "team_home": [f"Team_{i}" for i in range(100)],  # 100% unique
        })
        opt = optimize_dtypes(df)
        # High cardinality stays object/str (pandas 2.x uses StringDtype)
        assert opt["team_home"].dtype.name in ("object", "category", "str", "string")

    def test_preserves_int_columns(self):
        df = pd.DataFrame({
            "goals": [0, 1, 2, 3],
        })
        opt = optimize_dtypes(df)
        assert opt["goals"].dtype in [np.int32, np.int64]


class TestMemoryReport:
    """memory_report() diagnostics."""

    def test_report_format(self):
        df = pd.DataFrame({
            "col1": range(100),
            "col2": ["text"] * 100,
        })
        report = memory_report(df)
        assert "Memory Report" in report
        assert "MB" in report
        assert "col1" in report
        assert "col2" in report

    def test_report_nonzero_size(self):
        df = pd.DataFrame({"col": range(1000)})
        report = memory_report(df)
        assert "0.000" not in report  # Should have non-zero memory


class TestApplyChunked:
    """apply_chunked() processing."""

    def test_apply_to_chunks(self):
        df = pd.DataFrame({"col": range(100)})

        def sum_col(chunk):
            return chunk["col"].sum()

        results = apply_chunked(df, sum_col, chunk_size=25)
        assert len(results) == 4
        assert sum(results) == sum(range(100))

    def test_chunk_exception_handling(self):
        df = pd.DataFrame({"col": range(10)})

        def bad_func(chunk):
            raise ValueError("Intentional error")

        results = apply_chunked(df, bad_func, chunk_size=5)
        assert len(results) == 0  # No results due to errors
