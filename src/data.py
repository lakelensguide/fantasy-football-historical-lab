from __future__ import annotations

from io import BytesIO
import numpy as np
import pandas as pd
import requests
import streamlit as st

PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.parquet"
)
NGS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "nextgen_stats/ngs_{kind}.parquet"
)

SEASONS = list(range(2016, 2026))
CORE_POSITIONS = ["QB", "RB", "WR", "TE"]

def _download_parquet(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    return pd.read_parquet(BytesIO(r.content))

@st.cache_data(show_spinner="Loading historical nflverse player data…", ttl=86400)
def load_weekly() -> pd.DataFrame:
    frames = [_download_parquet(PLAYER_STATS_URL.format(season=s)) for s in SEASONS]
    df = pd.concat(frames, ignore_index=True)
    if "season_type" in df.columns:
        df = df[df["season_type"].eq("REG")]
    df = df[df["season"].isin(SEASONS)].copy()
    if "position" in df.columns:
        df["position"] = df["position"].replace({"FB": "RB"})
    if "team" not in df.columns and "recent_team" in df.columns:
        df["team"] = df["recent_team"]
    return df

def _safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    out = pd.to_numeric(num, errors="coerce") / pd.to_numeric(den, errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan)

def aggregate_season(weekly: pd.DataFrame) -> pd.DataFrame:
    id_cols = ["player_id", "player_display_name", "position", "season"]
    missing = [c for c in id_cols if c not in weekly.columns]
    if missing:
        raise ValueError(f"Required columns missing from nflverse data: {missing}")

    numeric = weekly.select_dtypes(include="number").columns.tolist()
    exclude = {"season", "week", "passing_cpoe"}
    sum_cols = [c for c in numeric if c not in exclude]

    grouped = weekly.groupby(id_cols, dropna=False)
    season = grouped[sum_cols].sum(min_count=1).reset_index()

    if "game_id" in weekly.columns:
        games = grouped["game_id"].nunique().rename("games").reset_index()
    else:
        games = grouped.size().rename("games").reset_index()
    season = season.merge(games, on=id_cols, how="left")

    # CPOE is a rate, so aggregate it by attempts rather than summing weekly values.
    if {"passing_cpoe", "attempts"}.issubset(weekly.columns):
        cpoe = weekly[id_cols + ["passing_cpoe", "attempts"]].copy()
        cpoe["_weighted_cpoe"] = (
            pd.to_numeric(cpoe["passing_cpoe"], errors="coerce")
            * pd.to_numeric(cpoe["attempts"], errors="coerce")
        )
        agg = cpoe.groupby(id_cols, dropna=False).agg(
            _weighted_cpoe=("_weighted_cpoe", "sum"),
            _cpoe_attempts=("attempts", "sum"),
        ).reset_index()
        agg["passing_cpoe"] = _safe_ratio(agg["_weighted_cpoe"], agg["_cpoe_attempts"])
        season = season.merge(agg[id_cols + ["passing_cpoe"]], on=id_cols, how="left")

    if "team" in weekly.columns:
        w = weekly.copy()
        last_team = (
            w.sort_values(["season", "week"])
            .groupby(id_cols, dropna=False)["team"]
            .last()
            .rename("team")
            .reset_index()
        )
        season = season.merge(last_team, on=id_cols, how="left")

        # Build denominators from the actual team-weeks associated with each player.
        # This avoids assigning an entire traded player's season to only his final team.
        player_team_weeks = w[id_cols + ["week", "team"]].drop_duplicates()
        for metric, out_name in [
            ("targets", "team_targets"),
            ("carries", "team_carries"),
            ("receiving_air_yards", "team_receiving_air_yards"),
        ]:
            if metric in w.columns:
                team_week = (
                    w.groupby(["season", "week", "team"], dropna=False)[metric]
                    .sum(min_count=1)
                    .rename(out_name)
                    .reset_index()
                )
                player_den = (
                    player_team_weeks
                    .merge(team_week, on=["season", "week", "team"], how="left")
                    .groupby(id_cols, dropna=False)[out_name]
                    .sum(min_count=1)
                    .reset_index()
                )
                season = season.merge(player_den, on=id_cols, how="left")

    if {"targets", "team_targets"}.issubset(season.columns):
        season["target_share"] = _safe_ratio(season["targets"], season["team_targets"])
    if {"carries", "team_carries"}.issubset(season.columns):
        season["carry_share"] = _safe_ratio(season["carries"], season["team_carries"])
    if {"receiving_air_yards", "team_receiving_air_yards"}.issubset(season.columns):
        season["air_yard_share"] = _safe_ratio(
            season["receiving_air_yards"], season["team_receiving_air_yards"]
        )
    if {"carries", "targets"}.issubset(season.columns):
        season["opportunities"] = season["carries"].fillna(0) + season["targets"].fillna(0)
    if {"receiving_yards", "targets"}.issubset(season.columns):
        season["yards_per_target"] = _safe_ratio(season["receiving_yards"], season["targets"])
    if {"receptions", "targets"}.issubset(season.columns):
        season["catch_rate"] = _safe_ratio(season["receptions"], season["targets"])
    if {"rushing_yards", "carries"}.issubset(season.columns):
        season["yards_per_carry"] = _safe_ratio(season["rushing_yards"], season["carries"])
    if {"passing_yards", "attempts"}.issubset(season.columns):
        season["yards_per_attempt"] = _safe_ratio(season["passing_yards"], season["attempts"])

    return season

@st.cache_data(show_spinner="Loading Next Gen Stats enrichment…", ttl=86400)
def load_ngs_optional() -> pd.DataFrame:
    frames = []
    for kind in ("passing", "rushing", "receiving"):
        try:
            x = _download_parquet(NGS_URL.format(kind=kind))
            if "season_type" in x.columns:
                x = x[x["season_type"].eq("REG")]
            if "week" in x.columns:
                x = x[x["week"].eq(0)]
            x = x[x["season"].isin(SEASONS)].copy()

            if "player_gsis_id" not in x.columns:
                continue

            keep_ids = ["season", "player_gsis_id"]
            value_cols = [
                c for c in x.columns
                if c not in {
                    "season", "season_type", "week", "player_gsis_id",
                    "player_display_name", "player_position", "team_abbr",
                    "player_first_name", "player_last_name",
                    "player_short_name", "player_jersey_number"
                }
                and pd.api.types.is_numeric_dtype(x[c])
            ]
            x = x[keep_ids + value_cols]
            x = x.rename(columns={c: f"ngs_{kind}_{c}" for c in value_cols})
            frames.append(x)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    out = frames[0]
    for x in frames[1:]:
        out = out.merge(x, on=["season", "player_gsis_id"], how="outer")
    return out

def enrich_with_ngs(season: pd.DataFrame) -> pd.DataFrame:
    ngs = load_ngs_optional()
    if ngs.empty:
        return season
    return season.merge(
        ngs,
        left_on=["season", "player_id"],
        right_on=["season", "player_gsis_id"],
        how="left",
    ).drop(columns=["player_gsis_id"], errors="ignore")
