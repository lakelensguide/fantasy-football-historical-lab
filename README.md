# Fantasy Football Historical Lab

A Streamlit dashboard for exploring the 10 completed NFL seasons from 2016 through 2025 using public nflverse data.

## Features

- **Threshold Explorer** — choose QB/RB/WR/TE, a fantasy finish tier, and a stat to see historical minimums, a typical yearly floor, an 80% qualifier threshold, and the hit rate above that threshold.
- **What Matters?** — ranks position-specific metrics by same-season relationship with fantasy production or next-season predictive signal.
- **Player Explorer** — season-by-season and weekly detail for players across the historical window.
- **Scatter Lab** — compare any two available metrics and highlight Top-5/10/12/24 positional finishes.
- **Scoring presets** — PPR, Half PPR, and Standard reception scoring.
- **Ranking modes** — season totals or fantasy points per game.

## Data

Primary source: nflverse player stats from the `stats_player` GitHub release, using season-specific weekly parquet files and aggregating regular-season results inside the app.

Optional enrichment: nflverse NFL Next Gen Stats for passing, rushing, and receiving, available from 2016 onward.

The app excludes the incomplete 2026 season until it is complete.

## Run locally

```bash
python -m venv .venv
# Activate .venv, then:
pip install -r requirements.txt
streamlit run streamlit_app.py
```

No API keys or secrets are required for the public nflverse data used by this version.

## Tests

Core scoring, threshold math, traded-player usage shares, and season-level CPOE aggregation are covered by regression tests.

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs the same tests plus a source compilation check on pushes to `main` and pull requests.

## Streamlit Community Cloud

The deployed app should use:

- Branch: `main`
- Entry point: `streamlit_app.py`
- Python: 3.12 (set by `.python-version`)
- Dependencies: `requirements.txt`

Commits to `main` are picked up by the existing Streamlit Community Cloud deployment created from this repository.

## Methodology notes

A literal historical minimum can be distorted by an unusual season, so the Threshold Explorer also reports a typical yearly floor and an 80% threshold. The hit-rate calculation answers the inverse question: among players who clear that stat threshold, how often did they actually achieve the selected fantasy finish?

The **What Matters?** view deliberately separates same-season association from next-season signal. Importance is based on median season-by-season rank correlation with a consistency adjustment; it is descriptive and should not be interpreted as causal.
