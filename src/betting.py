from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd
import requests

SPORTWIZZARD_ODDS_URL = "https://api.sportwizzard.com/api/v1/odds"
SPORTWIZZARD_PLAYERS_URL = "https://api.sportwizzard.com/api/v1/players"

SUPPORTED_METRICS = {
    "attempts",
    "completions",
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_tds",
}

POSITION_ALIASES = {
    "HB": "RB",
    "FB": "RB",
    "TAILBACK": "RB",
    "RUNNING BACK": "RB",
    "QUARTERBACK": "QB",
    "WIDE RECEIVER": "WR",
    "TIGHT END": "TE",
}


def _headers(api_key: str | None) -> dict[str, str]:
    return {"X-Api-Key": api_key} if api_key else {}


def _paged_get(url: str, params: dict, api_key: str | None = None, max_pages: int = 20):
    rows: list[dict] = []
    meta: dict = {}
    cursor = None
    for _ in range(max_pages):
        call_params = dict(params)
        if cursor:
            call_params["cursor"] = cursor
        response = requests.get(url, params=call_params, headers=_headers(api_key), timeout=45)
        response.raise_for_status()
        payload = response.json()
        rows.extend(payload.get("data") or [])
        meta = payload.get("meta") or meta
        cursor = payload.get("nextCursor")
        if not cursor:
            break
    return pd.DataFrame(rows), meta


def load_2026_season_player_props(api_key: str | None = None):
    """Load active NFL regular-season player total markets.

    SportWizzard currently permits anonymous reads during its transition period,
    but an API key is supported and recommended for deployed use.
    """
    params = {
        "scope": "season",
        "league": "nfl",
        "market": "PLAYER_TOTAL",
        "is_main": "true",
        "limit": 1000,
    }
    odds, meta = _paged_get(SPORTWIZZARD_ODDS_URL, params, api_key=api_key)
    if odds.empty:
        return odds, meta

    if "marketScope" in odds.columns:
        odds = odds[odds["marketScope"].astype(str).str.upper().eq("SEASON")]
    if "period" in odds.columns:
        odds = odds[odds["period"].astype(str).str.upper().eq("REG_SEASON")]
    if "suspended" in odds.columns:
        odds = odds[~odds["suspended"].fillna(False).astype(bool)]
    if "line" in odds.columns:
        odds["line"] = pd.to_numeric(odds["line"], errors="coerce")
        odds = odds[odds["line"].notna()]
    return odds.reset_index(drop=True), meta


def load_nfl_player_catalog(api_key: str | None = None):
    players, _ = _paged_get(
        SPORTWIZZARD_PLAYERS_URL,
        {"league": "nfl", "limit": 1000},
        api_key=api_key,
    )
    return players


def metric_supported(metric: str) -> bool:
    return metric in SUPPORTED_METRICS


def _subtype_mask(subtypes: pd.Series, metric: str) -> pd.Series:
    s = subtypes.fillna("").astype(str).str.upper()

    def has(*tokens: str):
        mask = pd.Series(True, index=s.index)
        for token in tokens:
            mask &= s.str.contains(token, regex=False)
        return mask

    td = s.str.contains("TD", regex=False) | s.str.contains("TOUCHDOWN", regex=False)
    yards = s.str.contains("YARD", regex=False)

    if metric == "passing_yards":
        return has("PASS") & yards & ~s.str.contains("RUSH", regex=False)
    if metric == "attempts":
        return has("PASS", "ATTEMPT")
    if metric == "completions":
        return has("PASS", "COMPLET")
    if metric == "passing_tds":
        return has("PASS") & td & ~s.str.contains("RUSH", regex=False)
    if metric == "passing_interceptions":
        return has("PASS", "INTERCEPTION")
    if metric == "rushing_yards":
        return has("RUSH") & yards & ~s.str.contains("PASS", regex=False) & ~s.str.contains("RECEIV", regex=False)
    if metric == "carries":
        return has("RUSH", "ATTEMPT")
    if metric == "rushing_tds":
        return has("RUSH") & td & ~s.str.contains("PASS", regex=False) & ~s.str.contains("RECEIV", regex=False)
    if metric == "receiving_yards":
        return (s.str.contains("RECEIV", regex=False) | s.str.contains("RECEPTION", regex=False)) & yards & ~s.str.contains("RUSH", regex=False)
    if metric == "receptions":
        return (
            s.str.contains("RECEPTION", regex=False)
            & ~yards
            & ~td
            & ~s.str.contains("LONG", regex=False)
        )
    if metric == "receiving_tds":
        return (
            (s.str.contains("RECEIV", regex=False) | s.str.contains("RECEPTION", regex=False))
            & td
            & ~s.str.contains("RUSH", regex=False)
        )
    if metric == "targets":
        return s.str.contains("TARGET", regex=False)
    return pd.Series(False, index=s.index)


def filter_metric_market(odds: pd.DataFrame, metric: str) -> pd.DataFrame:
    if odds.empty or "marketSubtype" not in odds.columns or not metric_supported(metric):
        return odds.iloc[0:0].copy()
    return odds[_subtype_mask(odds["marketSubtype"], metric)].copy()


def _normalize_name(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(JR|SR|II|III|IV|V)\b\.?", "", text.upper())
    return re.sub(r"[^A-Z0-9]+", "", text)


def _normalize_position(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    p = str(value).strip().upper()
    return POSITION_ALIASES.get(p, p)


def _catalog_position_lookup(catalog: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    if catalog.empty:
        return {}, {}

    id_col = next((c for c in ["id", "playerId", "player_id"] if c in catalog.columns), None)
    name_col = next(
        (c for c in ["name", "playerName", "fullName", "displayName", "player_name"] if c in catalog.columns),
        None,
    )
    pos_col = next(
        (
            c
            for c in [
                "position",
                "positionAbbreviation",
                "positionCode",
                "primaryPosition",
                "positionName",
            ]
            if c in catalog.columns
        ),
        None,
    )
    if not pos_col:
        return {}, {}

    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    if id_col:
        for _, row in catalog[[id_col, pos_col]].dropna().iterrows():
            by_id[str(row[id_col])] = _normalize_position(row[pos_col])
    if name_col:
        for _, row in catalog[[name_col, pos_col]].dropna().iterrows():
            by_name[_normalize_name(row[name_col])] = _normalize_position(row[pos_col])
    return by_id, by_name


def _historical_position_lookup(season: pd.DataFrame) -> dict[str, str]:
    if season.empty or not {"player_display_name", "position", "season"}.issubset(season.columns):
        return {}
    latest = (
        season[["player_display_name", "position", "season"]]
        .dropna(subset=["player_display_name", "position"])
        .sort_values("season")
        .drop_duplicates("player_display_name", keep="last")
    )
    return {
        _normalize_name(row["player_display_name"]): _normalize_position(row["position"])
        for _, row in latest.iterrows()
    }


def _american_implied(price: object) -> float:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return np.nan
    if p == 0:
        return np.nan
    return (-p / (-p + 100.0)) if p < 0 else (100.0 / (p + 100.0))


def _book_no_vig_over(g: pd.DataFrame) -> float:
    if "side" not in g.columns or "priceAmerican" not in g.columns:
        return np.nan
    sides = g["side"].astype(str).str.upper()
    over = g.loc[sides.eq("OVER"), "priceAmerican"]
    under = g.loc[sides.eq("UNDER"), "priceAmerican"]
    if over.empty or under.empty:
        return np.nan
    po = _american_implied(over.iloc[0])
    pu = _american_implied(under.iloc[0])
    if pd.isna(po) or pd.isna(pu) or (po + pu) <= 0:
        return np.nan
    return po / (po + pu)


def consensus_for_threshold(
    odds: pd.DataFrame,
    metric: str,
    position: str,
    target: float,
    season_history: pd.DataFrame,
    player_catalog: pd.DataFrame | None = None,
) -> pd.DataFrame:
    market = filter_metric_market(odds, metric)
    if market.empty:
        return pd.DataFrame()

    market = market.copy()
    if "playerName" not in market.columns:
        return pd.DataFrame()
    market = market[market["playerName"].notna()]
    market["_name_key"] = market["playerName"].map(_normalize_name)

    catalog = player_catalog if player_catalog is not None else pd.DataFrame()
    catalog_by_id, catalog_by_name = _catalog_position_lookup(catalog)
    historical_by_name = _historical_position_lookup(season_history)

    def resolve_position(row):
        pid = str(row.get("playerId", ""))
        if pid and pid in catalog_by_id:
            return catalog_by_id[pid]
        name_key = row["_name_key"]
        if name_key in catalog_by_name:
            return catalog_by_name[name_key]
        return historical_by_name.get(name_key, "")

    market["position"] = market.apply(resolve_position, axis=1)
    selected = _normalize_position(position)
    market = market[(market["position"].eq(selected)) | market["position"].eq("")]
    if market.empty:
        return pd.DataFrame()

    group_cols = ["playerName"]
    if "playerId" in market.columns:
        group_cols = ["playerId", "playerName"]

    output = []
    for keys, g in market.groupby(group_cols, dropna=False):
        player_name = keys[-1] if isinstance(keys, tuple) else keys
        book_lines = (
            g.dropna(subset=["line"])
            .groupby("sportsbook", dropna=False)["line"]
            .median()
            if "sportsbook" in g.columns
            else g["line"]
        )
        if book_lines.empty:
            continue

        over_probs = []
        if {"sportsbook", "line"}.issubset(g.columns):
            for _, bg in g.groupby(["sportsbook", "line"], dropna=False):
                p = _book_no_vig_over(bg)
                if pd.notna(p):
                    over_probs.append(float(p))

        resolved_positions = g["position"][g["position"].ne("")]
        resolved_position = resolved_positions.iloc[0] if len(resolved_positions) else ""

        consensus = float(book_lines.median())
        min_line = float(book_lines.min())
        max_line = float(book_lines.max())
        diff = consensus - float(target)
        tolerance = max(0.5, abs(float(target)) * 0.01)
        if diff > tolerance:
            expectation = "Likely clears"
        elif diff < -tolerance:
            expectation = "Likely below"
        else:
            expectation = "Borderline"

        updated = None
        if "updated" in g.columns:
            parsed = pd.to_datetime(g["updated"], errors="coerce", utc=True)
            if parsed.notna().any():
                updated = parsed.max()

        output.append(
            {
                "Player": player_name,
                "Position": resolved_position or "Unknown",
                "Market line": consensus,
                "Target": float(target),
                "Vs target": diff,
                "Expectation": expectation,
                "Over probability": float(np.median(over_probs)) if over_probs else np.nan,
                "Books": int(book_lines.index.nunique()) if hasattr(book_lines, "index") else int(len(book_lines)),
                "Low line": min_line,
                "High line": max_line,
                "Updated": updated,
            }
        )

    if not output:
        return pd.DataFrame()

    result = pd.DataFrame(output)
    order = pd.Categorical(
        result["Expectation"],
        ["Likely clears", "Borderline", "Likely below"],
        ordered=True,
    )
    result["_expectation_order"] = order
    return (
        result.sort_values(["_expectation_order", "Vs target"], ascending=[True, False])
        .drop(columns="_expectation_order")
        .reset_index(drop=True)
    )
