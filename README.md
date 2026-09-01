# Fantasy Football Historical Lab

A Streamlit dashboard for exploring the 10 completed NFL seasons from 2016 through 2025 using public nflverse data, with a separate 2026 season-long sportsbook overlay.

## Features

- **Threshold Explorer** — choose QB/RB/WR/TE, a fantasy finish tier, and a stat to see historical minimums, a typical yearly floor, an 80% qualifier threshold, and the hit rate above that threshold.
- **2026 sportsbook expectation** — for stats with season-long player-total markets, compare current consensus betting lines with the historical threshold and see which players the market places above, near, or below it.
- **What Matters?** — ranks position-specific metrics by same-season relationship with fantasy production or next-season predictive signal.
- **Player Explorer** — season-by-season and weekly detail for players across the historical window.
- **Scatter Lab** — compare any two available metrics and highlight Top-5/10/12/24 positional finishes.
- **Scoring presets** — PPR, Half PPR, and Standard reception scoring.
- **Ranking modes** — season totals or fantasy points per game.

## Data

Historical source: nflverse player stats from the `stats_player` GitHub release, using season-specific weekly parquet files and aggregating regular-season results inside the app.

Optional historical enrichment: nflverse NFL Next Gen Stats for passing, rushing, and receiving, available from 2016 onward.

Current-market source: SportWizzard season-long NFL `PLAYER_TOTAL` markets. The app requests only regular-season (`REG_SEASON`) season futures and uses the median main line across available sportsbooks as the consensus line. Betting data is kept separate from the completed-season historical dataset.

The historical analysis excludes the incomplete 2026 season until it is complete.

## Run locally

```bash
python -m venv .venv
# Activate .venv, then:
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The historical nflverse data requires no API key. SportWizzard currently supports a free API key and the dashboard can attempt anonymous reads while their transitional access permits it, but a key is recommended for reliable deployment.

Create `.streamlit/secrets.toml` locally using `.streamlit/secrets.toml.example` as the template:

```toml
SPORTWIZZARD_API_KEY = "sw_live_your_api_key_here"
```

For Streamlit Community Cloud, add the same value under **App settings → Secrets**. Never commit the real `secrets.toml`; it is already ignored by Git.

## Betting overlay behavior

The overlay currently maps direct season markets for common counting stats when sportsbooks offer them:

- QB: pass attempts, completions, passing yards, passing TDs, interceptions, rushing yards/attempts/TDs when posted.
- RB: carries, rushing yards/TDs, targets, receptions, receiving yards/TDs when posted.
- WR/TE: targets, receptions, receiving yards, receiving TDs when posted.

Derived analytics such as target share, air-yard share, yards per target, catch rate, EPA, CPOE, and carries + targets are intentionally not assigned fake betting lines. The dashboard displays that no direct market is available instead.

For each supported stat, the user can compare 2026 consensus lines against the historical 80% threshold, typical yearly floor, or literal historical minimum. “Likely clears” means the median sportsbook line is materially above the selected historical target; “Likely below” means it is materially below it. This is a market expectation, not a guarantee, probability model, or betting recommendation.

## Tests

Core scoring, threshold math, traded-player usage shares, season-level CPOE aggregation, betting-market matching, and market-vs-threshold classification are covered by regression tests.

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
- Optional secret: `SPORTWIZZARD_API_KEY`

Commits to `main` are picked up by the existing Streamlit Community Cloud deployment created from this repository.

## Methodology notes

A literal historical minimum can be distorted by an unusual season, so the Threshold Explorer also reports a typical yearly floor and an 80% threshold. The hit-rate calculation answers the inverse question: among players who clear that stat threshold, how often did they actually achieve the selected fantasy finish?

The **What Matters?** view deliberately separates same-season association from next-season signal. Importance is based on median season-by-season rank correlation with a consistency adjustment; it is descriptive and should not be interpreted as causal.
