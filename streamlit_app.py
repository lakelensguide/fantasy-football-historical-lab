from __future__ import annotations

import numpy as np
import plotly.express as px
import streamlit as st

from src.analysis import LABELS, available_metrics, importance_table, rank_frame, threshold_summary
from src.betting import (
    consensus_for_threshold,
    load_2026_season_player_props,
    load_nfl_player_catalog,
    metric_supported,
)
from src.data import CORE_POSITIONS, aggregate_season, enrich_with_ngs, load_weekly
from src.scoring import SCORING_PRESETS, fantasy_points

st.set_page_config(page_title="Fantasy Football Historical Lab", layout="wide")
st.title("Fantasy Football Historical Lab")
st.caption("2016–2025 historical analysis · 2026 season-market overlay")


@st.cache_data(show_spinner=False, ttl=900)
def _cached_2026_props(api_key: str | None):
    return load_2026_season_player_props(api_key)


@st.cache_data(show_spinner=False, ttl=86400)
def _cached_nfl_player_catalog(api_key: str | None):
    return load_nfl_player_catalog(api_key)


def _sportwizzard_key() -> str | None:
    try:
        value = st.secrets.get("SPORTWIZZARD_API_KEY")
        return str(value).strip() if value else None
    except Exception:
        return None


with st.sidebar:
    st.header("Fantasy settings")
    scoring = st.selectbox("Reception scoring", list(SCORING_PRESETS), index=0)
    outcome_label = st.radio("Rank players by", ["Season total", "Points per game"])
    min_games = st.slider(
        "Minimum games for PPG ranks",
        4, 16, 8,
        disabled=outcome_label == "Season total",
    )
    st.caption("Historical rankings exclude 2026 until the season is complete.")
    st.caption("2026 betting lines are shown separately as a live market overlay.")

try:
    weekly = load_weekly()
except Exception as e:
    st.error("The nflverse download failed. Check your internet connection and try again.")
    st.exception(e)
    st.stop()

season = aggregate_season(weekly)
season["fantasy_points"] = fantasy_points(season, SCORING_PRESETS[scoring])
season["fantasy_ppg"] = season["fantasy_points"] / season["games"].replace(0, np.nan)

with st.spinner("Adding optional Next Gen Stats…"):
    season = enrich_with_ngs(season)

outcome = "fantasy_points" if outcome_label == "Season total" else "fantasy_ppg"

tab1, tab2, tab3, tab4 = st.tabs(
    ["Threshold Explorer", "What Matters?", "Player Explorer", "Scatter Lab"]
)

with tab1:
    st.subheader("Threshold Explorer")
    st.write(
        "Choose any position, finish tier, and metric. The result shows both the literal historical floor "
        "and more stable thresholds, so one unusual season does not become a fake rule."
    )
    c1, c2, c3 = st.columns(3)
    position = c1.selectbox("Position", CORE_POSITIONS, index=2, key="threshold_pos")
    top_n = c2.selectbox(
        "Fantasy finish", [5, 10, 12, 24, 36], index=1,
        format_func=lambda x: f"Top {x}",
    )
    metrics = available_metrics(season, position)
    if not metrics:
        st.warning("No metrics are available for this position.")
    else:
        preferred = {"WR": "targets", "TE": "targets", "RB": "opportunities", "QB": "attempts"}
        default_idx = metrics.index(preferred[position]) if preferred.get(position) in metrics else 0
        metric = c3.selectbox(
            "Stat", metrics, index=default_idx,
            format_func=lambda m: LABELS.get(m, m.replace("_", " ").title()),
        )
        yearly, summary = threshold_summary(season, position, metric, outcome, top_n, min_games)
        if not summary:
            st.info("Not enough data for this combination.")
        else:
            a, b, c, d = st.columns(4)
            is_rate = "share" in metric or "rate" in metric or "percentage" in metric
            fmt = lambda v: f"{v:.1%}" if is_rate and abs(v) <= 1.5 else f"{v:,.1f}"
            a.metric("Historical minimum", fmt(summary["historical_min"]))
            b.metric("Typical yearly floor", fmt(summary["typical_yearly_floor"]))
            c.metric("80% threshold", fmt(summary["threshold_80"]))
            d.metric("Hit rate above 80% threshold", f"{summary['hit_rate']:.0%}")
            st.caption(
                "80% threshold = level met or exceeded by 80% of qualifying player-seasons. "
                "Hit rate answers the inverse question: how often players above that level actually achieved the finish."
            )
            fig = px.line(
                yearly,
                x="season",
                y=["minimum", "median"],
                markers=True,
                labels={
                    "value": LABELS.get(metric, metric),
                    "season": "Season",
                    "variable": "Qualifier statistic",
                },
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(yearly, use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("#### 2026 sportsbook expectation")
            st.write(
                "Compare this historical threshold with current **regular-season player total** lines. "
                "The consensus line is the median main line across available sportsbooks."
            )

            target_choice = st.radio(
                "Compare 2026 market lines with",
                ["80% threshold", "Typical yearly floor", "Historical minimum"],
                horizontal=True,
                key=f"market_target_{position}_{metric}_{top_n}",
            )
            target_map = {
                "80% threshold": summary["threshold_80"],
                "Typical yearly floor": summary["typical_yearly_floor"],
                "Historical minimum": summary["historical_min"],
            }
            market_target = float(target_map[target_choice])

            if not metric_supported(metric):
                st.info(
                    f"No direct season-long sportsbook market is mapped to "
                    f"{LABELS.get(metric, metric.replace('_', ' ').title())}. "
                    "The historical analysis remains valid, but the app will not invent a betting proxy for this stat."
                )
            else:
                api_key = _sportwizzard_key()
                try:
                    with st.spinner("Loading current 2026 season lines…"):
                        season_odds, market_meta = _cached_2026_props(api_key)
                        player_catalog = _cached_nfl_player_catalog(api_key)
                except Exception as e:
                    st.warning(
                        "Current season betting lines could not be loaded. "
                        "For reliable deployed access, add SPORTWIZZARD_API_KEY to Streamlit secrets."
                    )
                    st.caption(str(e))
                else:
                    comparison = consensus_for_threshold(
                        season_odds,
                        metric=metric,
                        position=position,
                        target=market_target,
                        season_history=season,
                        player_catalog=player_catalog,
                    )
                    if comparison.empty:
                        st.info(
                            "No active 2026 regular-season player-total market is available for this stat/position "
                            "from the current provider. Sportsbooks do not post every stat as a season future."
                        )
                    else:
                        clears = int(comparison["Expectation"].eq("Likely clears").sum())
                        borderline = int(comparison["Expectation"].eq("Borderline").sum())
                        below = int(comparison["Expectation"].eq("Likely below").sum())
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Market target", fmt(market_target))
                        m2.metric("Likely clears", clears)
                        m3.metric("Borderline", borderline)
                        m4.metric("Likely below", below)

                        display = comparison.copy()
                        display["Market line"] = display["Market line"].round(1)
                        display["Target"] = display["Target"].round(1)
                        display["Vs target"] = display["Vs target"].round(1)
                        display["Line range"] = display.apply(
                            lambda r: f"{r['Low line']:,.1f}–{r['High line']:,.1f}", axis=1
                        )
                        display["Over probability"] = (
                            display["Over probability"] * 100
                        ).round(1)
                        display["Updated"] = display["Updated"].dt.strftime("%Y-%m-%d %H:%M UTC")

                        st.dataframe(
                            display[
                                [
                                    "Player",
                                    "Position",
                                    "Expectation",
                                    "Market line",
                                    "Target",
                                    "Vs target",
                                    "Over probability",
                                    "Books",
                                    "Line range",
                                    "Updated",
                                ]
                            ],
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Over probability": st.column_config.NumberColumn(
                                    "No-vig over %", format="%.1f%%"
                                ),
                            },
                        )

                        chart_rows = comparison.head(30).sort_values("Market line")
                        market_fig = px.scatter(
                            chart_rows,
                            x="Market line",
                            y="Player",
                            color="Expectation",
                            hover_data=["Books", "Low line", "High line"],
                            labels={"Market line": f"2026 {LABELS.get(metric, metric)} line"},
                        )
                        market_fig.add_vline(
                            x=market_target,
                            line_dash="dash",
                            annotation_text=target_choice,
                        )
                        st.plotly_chart(market_fig, use_container_width=True)

                        freshest = comparison["Updated"].dropna()
                        if len(freshest):
                            st.caption(
                                "Latest included line update: "
                                f"{freshest.max().strftime('%Y-%m-%d %H:%M UTC')}. "
                                "“Likely clears” means the median sportsbook line is materially above the selected "
                                "historical target; it is a market expectation, not a guarantee or betting recommendation."
                            )
                        elif market_meta:
                            st.caption(
                                "Lines are current provider data. “Likely clears” compares the median sportsbook "
                                "line with the selected historical target; it is not a guarantee or betting recommendation."
                            )

with tab2:
    st.subheader("What Matters?")
    st.write(
        "Same-season importance is descriptive. Next-season signal is more useful for draft-style prediction. "
        "Both use median season-by-season Spearman relationships so one era or outlier season does not dominate."
    )
    c1, c2 = st.columns(2)
    ipos = c1.selectbox("Position", CORE_POSITIONS, index=2, key="importance_pos")
    mode = c2.radio(
        "Analysis",
        ["Same-season relationship", "Next-season signal"],
        horizontal=True,
    )
    imp = importance_table(season, ipos, outcome, mode, min_games)
    if imp.empty:
        st.info("Not enough data for this analysis.")
    else:
        show = imp.head(15).copy()
        show["rho"] = show["median_rho"].round(3)
        show["consistency"] = (
            (show["direction_consistency"] * 100)
            .round()
            .astype(int)
            .astype(str)
            + "%"
        )
        fig = px.bar(
            show.sort_values("importance"),
            x="importance",
            y="label",
            orientation="h",
            hover_data=["rho", "consistency", "seasons"],
            labels={"importance": "Stable importance score", "label": "Metric"},
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            show[["label", "rho", "consistency", "seasons", "importance"]],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Importance = |median Spearman correlation| × directional consistency. "
            "This is an interpretable association ranking, not a causal claim."
        )

with tab3:
    st.subheader("Player Explorer")
    names = season["player_display_name"].dropna().drop_duplicates().sort_values().tolist()
    player = st.selectbox("Player", names)
    p = season[season["player_display_name"].eq(player)].copy().sort_values("season")
    p["Fantasy points"] = p["fantasy_points"].round(1)
    p["Fantasy PPG"] = p["fantasy_ppg"].round(2)

    cols = [
        c for c in [
            "season", "position", "team", "games", "Fantasy points", "Fantasy PPG",
            "attempts", "passing_yards", "passing_tds",
            "carries", "rushing_yards", "rushing_tds",
            "targets", "receptions", "receiving_yards", "receiving_tds",
            "target_share", "air_yard_share", "opportunities",
        ]
        if c in p.columns
    ]
    st.dataframe(p[cols], use_container_width=True, hide_index=True)

    if len(p):
        fig = px.line(
            p, x="season", y="fantasy_ppg", markers=True,
            labels={"fantasy_ppg": "Fantasy PPG"},
        )
        st.plotly_chart(fig, use_container_width=True)

        seasons_for_player = p["season"].dropna().astype(int).tolist()
        selected_season = st.selectbox(
            "Weekly detail season",
            seasons_for_player,
            index=len(seasons_for_player) - 1,
        )
        w = weekly[
            weekly["player_display_name"].eq(player)
            & weekly["season"].eq(selected_season)
        ].copy()
        w["fantasy_points"] = fantasy_points(w, SCORING_PRESETS[scoring])
        weekly_cols = [
            c for c in [
                "week", "team", "opponent_team", "fantasy_points",
                "attempts", "passing_yards", "passing_tds",
                "carries", "rushing_yards", "rushing_tds",
                "targets", "receptions", "receiving_yards", "receiving_tds",
            ]
            if c in w.columns
        ]
        st.dataframe(
            w[weekly_cols].sort_values("week"),
            use_container_width=True,
            hide_index=True,
        )

with tab4:
    st.subheader("Scatter Lab")
    c1, c2, c3 = st.columns(3)
    spos = c1.selectbox("Position", CORE_POSITIONS, index=2, key="scatter_pos")
    smetrics = available_metrics(season, spos)

    if len(smetrics) < 2:
        st.info("Not enough metrics.")
    else:
        xmetric = c2.selectbox(
            "X metric",
            smetrics,
            index=0,
            format_func=lambda m: LABELS.get(m, m.replace("_", " ").title()),
        )
        y_options = smetrics + ["fantasy_points", "fantasy_ppg"]
        ymetric = c3.selectbox(
            "Y metric",
            y_options,
            index=y_options.index("fantasy_ppg"),
            format_func=lambda m: LABELS.get(m, m.replace("_", " ").title()),
        )
        c4, c5 = st.columns(2)
        season_choice = c4.selectbox(
            "Season", ["All"] + list(range(2016, 2026)), index=0
        )
        highlight_n = c5.selectbox(
            "Highlight finish",
            [5, 10, 12, 24],
            index=1,
            format_func=lambda x: f"Top {x}",
        )

        s = rank_frame(season, spos, outcome, min_games)
        if season_choice != "All":
            s = s[s["season"].eq(season_choice)]
        s = s.copy()
        s["Finish group"] = np.where(
            s["position_rank"].le(highlight_n),
            f"Top {highlight_n}",
            "Other",
        )

        fig = px.scatter(
            s,
            x=xmetric,
            y=ymetric,
            color="Finish group",
            hover_data=["player_display_name", "season", "position_rank"],
            labels={
                xmetric: LABELS.get(xmetric, xmetric),
                ymetric: LABELS.get(ymetric, ymetric),
            },
        )
        st.plotly_chart(fig, use_container_width=True)

with st.expander("Methodology and caveats"):
    st.markdown("""
- **Historical window:** 2016–2025 regular seasons.
- **2026 market overlay:** current regular-season player total lines are kept separate from the completed-season historical dataset.
- **Sportsbook consensus:** median main line across available books; the line range shows cross-book disagreement.
- **Market expectation:** “Likely clears” / “Likely below” compares the consensus line to the selected historical threshold. This is not a probability model, guarantee, or recommendation to wager.
- **Top-N ranks:** recalculated separately within each season and position using the selected fantasy scoring preset.
- **PPG mode:** applies the minimum-games filter before ranking.
- **Thresholds:** a minimum is descriptive, not sufficient. The hit-rate statistic shows how many non-elite players also clear the same volume threshold.
- **Advanced stats:** NGS data has minimum-attempt eligibility rules; missing values are not zeros.
- **Predictive signal:** current-season metric vs next-season fantasy outcome for the same player.
- **Era changes:** thresholds are shown season-by-season, so the 16-to-17-game schedule change is visible rather than silently blended away.
""")
