from __future__ import annotations

import numpy as np
import pandas as pd

LABELS = {
    "targets": "Targets",
    "receptions": "Receptions",
    "receiving_yards": "Receiving yards",
    "receiving_tds": "Receiving TDs",
    "receiving_air_yards": "Receiving air yards",
    "target_share": "Target share",
    "air_yard_share": "Air-yard share",
    "yards_per_target": "Yards / target",
    "catch_rate": "Catch rate",
    "carries": "Carries",
    "rushing_yards": "Rushing yards",
    "rushing_tds": "Rushing TDs",
    "total_yards": "Total yards",
    "carry_share": "Carry share",
    "opportunities": "Carries + targets",
    "yards_per_carry": "Yards / carry",
    "attempts": "Pass attempts",
    "completions": "Completions",
    "passing_yards": "Passing yards",
    "passing_tds": "Passing TDs",
    "passing_interceptions": "Interceptions",
    "passing_air_yards": "Passing air yards",
    "passing_epa": "Passing EPA",
    "passing_cpoe": "Passing CPOE",
    "yards_per_attempt": "Yards / attempt",
    "fantasy_points": "Fantasy points",
    "fantasy_ppg": "Fantasy points / game",
}

POSITION_CANDIDATES = {
    "QB": [
        "attempts", "completions", "passing_yards", "passing_tds",
        "passing_interceptions", "passing_air_yards", "passing_epa",
        "passing_cpoe", "yards_per_attempt", "carries", "rushing_yards",
        "rushing_tds",
    ],
    "RB": [
        "opportunities", "total_yards", "carries", "targets", "carry_share", "target_share",
        "rushing_yards", "receiving_yards", "rushing_tds", "receiving_tds",
        "receptions", "yards_per_carry", "yards_per_target",
    ],
    "WR": [
        "targets", "target_share", "receptions", "receiving_yards",
        "receiving_tds", "receiving_air_yards", "air_yard_share",
        "yards_per_target", "catch_rate",
    ],
    "TE": [
        "targets", "target_share", "receptions", "receiving_yards",
        "receiving_tds", "receiving_air_yards", "air_yard_share",
        "yards_per_target", "catch_rate",
    ],
}

def available_metrics(df: pd.DataFrame, position: str) -> list[str]:
    base = [m for m in POSITION_CANDIDATES.get(position, []) if m in df.columns]
    prefixes = {
        "QB": ("ngs_passing_", "ngs_rushing_"),
        "RB": ("ngs_rushing_", "ngs_receiving_"),
        "WR": ("ngs_receiving_",),
        "TE": ("ngs_receiving_",),
    }.get(position, ("ngs_",))
    advanced = [
        c for c in df.columns
        if c.startswith(prefixes) and pd.api.types.is_numeric_dtype(df[c])
    ]
    return base + sorted(advanced)

def rank_frame(df: pd.DataFrame, position: str, outcome: str, min_games: int) -> pd.DataFrame:
    x = df[df["position"].eq(position)].copy()
    if outcome == "fantasy_ppg":
        x = x[x["games"].ge(min_games)]
    x["position_rank"] = (
        x.groupby("season")[outcome]
        .rank(method="first", ascending=False)
        .astype("Int64")
    )
    return x

def threshold_summary(
    df: pd.DataFrame,
    position: str,
    metric: str,
    outcome: str,
    top_n: int,
    min_games: int,
):
    x = rank_frame(df, position, outcome, min_games)
    x = x[pd.to_numeric(x[metric], errors="coerce").notna()].copy()
    qualifiers = x[x["position_rank"].le(top_n)].copy()
    if qualifiers.empty:
        return pd.DataFrame(), {}

    yearly = (
        qualifiers.groupby("season")
        .agg(
            minimum=(metric, "min"),
            median=(metric, "median"),
            maximum=(metric, "max"),
            qualifiers=("player_id", "count"),
        )
        .reset_index()
    )

    vals = pd.to_numeric(qualifiers[metric], errors="coerce").dropna()
    threshold_80 = float(vals.quantile(0.20))
    above = x[pd.to_numeric(x[metric], errors="coerce").ge(threshold_80)]
    hit_rate = float((above["position_rank"] <= top_n).mean()) if len(above) else np.nan

    summary = {
        "historical_min": float(vals.min()),
        "typical_yearly_floor": float(yearly["minimum"].median()),
        "threshold_80": threshold_80,
        "hit_rate": hit_rate,
        "qualifier_count": int(len(qualifiers)),
    }
    return yearly, summary

def importance_table(
    df: pd.DataFrame,
    position: str,
    outcome: str,
    mode: str,
    min_games: int,
) -> pd.DataFrame:
    metrics = available_metrics(df, position)
    x = df[df["position"].eq(position)].copy()
    if outcome == "fantasy_ppg":
        x = x[x["games"].ge(min_games)]

    rows = []
    if mode == "Same-season relationship":
        pairs = [(x, outcome)]
    else:
        nxt = x[["player_id", "season", outcome]].copy()
        nxt["season"] = nxt["season"] - 1
        nxt = nxt.rename(columns={outcome: "next_outcome"})
        z = x.merge(nxt, on=["player_id", "season"], how="inner")
        pairs = [(z, "next_outcome")]

    data, target = pairs[0]
    for metric in metrics:
        season_rhos = []
        for _, g in data.groupby("season"):
            a = pd.to_numeric(g[metric], errors="coerce")
            b = pd.to_numeric(g[target], errors="coerce")
            valid = a.notna() & b.notna()
            if valid.sum() >= 8 and a[valid].nunique() >= 3 and b[valid].nunique() >= 3:
                season_rhos.append(a[valid].rank(method="average").corr(b[valid].rank(method="average")))

        season_rhos = [r for r in season_rhos if pd.notna(r)]
        if season_rhos:
            med = float(np.median(season_rhos))
            consistency = float(np.mean(np.sign(season_rhos) == np.sign(med)))
            rows.append((metric, med, consistency, len(season_rhos)))

    out = pd.DataFrame(rows, columns=["metric", "median_rho", "direction_consistency", "seasons"])
    if out.empty:
        return out

    out["importance"] = out["median_rho"].abs() * out["direction_consistency"]
    out["label"] = out["metric"].map(LABELS)
    missing = out["label"].isna()
    out.loc[missing, "label"] = (
        out.loc[missing, "metric"]
        .str.replace("_", " ", regex=False)
        .str.replace("ngs ", "NGS ", regex=False)
        .str.title()
    )
    return out.sort_values("importance", ascending=False).reset_index(drop=True)
