from __future__ import annotations
import pandas as pd

SCORING_PRESETS = {
    "PPR": 1.0,
    "Half PPR": 0.5,
    "Standard": 0.0,
}

def fantasy_points(df: pd.DataFrame, reception_points: float = 1.0) -> pd.Series:
    """Common offensive fantasy scoring. Missing columns are treated as zero."""
    def col(name: str) -> pd.Series:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").fillna(0)
        return pd.Series(0.0, index=df.index)

    passing_ints = col("passing_interceptions")
    if "passing_interceptions" not in df.columns and "interceptions" in df.columns:
        passing_ints = col("interceptions")

    pts = (
        col("passing_yards") * 0.04
        + col("passing_tds") * 4
        - passing_ints * 2
        + col("rushing_yards") * 0.10
        + col("rushing_tds") * 6
        + col("receptions") * reception_points
        + col("receiving_yards") * 0.10
        + col("receiving_tds") * 6
        + col("passing_2pt_conversions") * 2
        + col("rushing_2pt_conversions") * 2
        + col("receiving_2pt_conversions") * 2
    )
    return pts.astype(float)
