from __future__ import annotations

import numpy as np
import plotly.express as px
import streamlit as st

from src.analysis import LABELS, available_metrics, importance_table, rank_frame, threshold_summary
from src.data import CORE_POSITIONS, aggregate_season, enrich_with_ngs, load_weekly
from src.scoring import SCORING_PRESETS, fantasy_points

st.set_page_config(page_title="Fantasy Football Historical Lab", layout="wide")
st.title("Fantasy Football Historical Lab")
st.caption("2016–2025 · Thresholds, positional drivers, predictive signals, and player history")

with st.sidebar:
    st.header("Fantasy settings")
    scoring = st.selectbox("Reception scoring", list(SCORING_PRESETS), index=0)
    outcome_label = st.radio("Rank players by", ["Season total", "Points per game"])
    min_games = st.slider(
        "Minimum games for PPG ranks",
        4, 16, 8,
        disabled=outcome_label == "Season total",
    )
    st.caption("The 2026 season is excluded until complete.")

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
- **Window:** 2016–2025 regular seasons.
- **Top-N ranks:** recalculated separately within each season and position using the selected fantasy scoring preset.
- **PPG mode:** applies the minimum-games filter before ranking.
- **Thresholds:** a minimum is descriptive, not sufficient. The hit-rate statistic shows how many non-elite players also clear the same volume threshold.
- **Advanced stats:** NGS data has minimum-attempt eligibility rules; missing values are not zeros.
- **Predictive signal:** current-season metric vs next-season fantasy outcome for the same player.
- **Era changes:** thresholds are shown season-by-season, so the 16-to-17-game schedule change is visible rather than silently blended away.
""")
