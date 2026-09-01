import unittest

import numpy as np
import pandas as pd

from src.analysis import threshold_summary
from src.data import aggregate_season
from src.scoring import fantasy_points


class FantasyScoringTests(unittest.TestCase):
    def test_common_scoring(self):
        df = pd.DataFrame(
            {
                "passing_yards": [250],
                "passing_tds": [2],
                "passing_interceptions": [1],
                "rushing_yards": [30],
                "rushing_tds": [1],
            }
        )
        # 10 passing yards points + 8 pass TD - 2 INT + 3 rush yards + 6 rush TD.
        self.assertAlmostEqual(float(fantasy_points(df, 1.0).iloc[0]), 25.0)


class AggregationTests(unittest.TestCase):
    def test_traded_player_share_uses_actual_team_weeks(self):
        weekly = pd.DataFrame(
            [
                # Player P has 5 targets for Team A, then 5 for Team B.
                {"player_id": "P", "player_display_name": "Player P", "position": "WR", "season": 2025, "week": 1, "team": "A", "targets": 5},
                {"player_id": "A1", "player_display_name": "A Teammate", "position": "WR", "season": 2025, "week": 1, "team": "A", "targets": 5},
                {"player_id": "P", "player_display_name": "Player P", "position": "WR", "season": 2025, "week": 2, "team": "B", "targets": 5},
                {"player_id": "B1", "player_display_name": "B Teammate", "position": "WR", "season": 2025, "week": 2, "team": "B", "targets": 15},
            ]
        )
        season = aggregate_season(weekly)
        p = season.loc[season["player_id"].eq("P")].iloc[0]

        self.assertEqual(float(p["targets"]), 10.0)
        self.assertEqual(float(p["team_targets"]), 30.0)
        self.assertAlmostEqual(float(p["target_share"]), 1.0 / 3.0)
        self.assertEqual(p["team"], "B")

    def test_cpoe_is_attempt_weighted_and_ignores_missing_cpoe_attempts(self):
        weekly = pd.DataFrame(
            [
                {"player_id": "Q", "player_display_name": "QB Q", "position": "QB", "season": 2025, "week": 1, "attempts": 10, "passing_cpoe": 10.0},
                {"player_id": "Q", "player_display_name": "QB Q", "position": "QB", "season": 2025, "week": 2, "attempts": 30, "passing_cpoe": 20.0},
                {"player_id": "Q", "player_display_name": "QB Q", "position": "QB", "season": 2025, "week": 3, "attempts": 40, "passing_cpoe": np.nan},
            ]
        )
        season = aggregate_season(weekly)
        q = season.iloc[0]

        self.assertEqual(float(q["attempts"]), 80.0)
        self.assertAlmostEqual(float(q["passing_cpoe"]), 17.5)


class ThresholdTests(unittest.TestCase):
    def test_threshold_summary(self):
        season = pd.DataFrame(
            [
                {"player_id": "A", "position": "WR", "season": 2024, "games": 17, "fantasy_points": 200, "targets": 100},
                {"player_id": "B", "position": "WR", "season": 2024, "games": 17, "fantasy_points": 180, "targets": 80},
                {"player_id": "C", "position": "WR", "season": 2024, "games": 17, "fantasy_points": 160, "targets": 70},
                {"player_id": "D", "position": "WR", "season": 2025, "games": 17, "fantasy_points": 220, "targets": 120},
                {"player_id": "E", "position": "WR", "season": 2025, "games": 17, "fantasy_points": 200, "targets": 90},
                {"player_id": "F", "position": "WR", "season": 2025, "games": 17, "fantasy_points": 190, "targets": 85},
            ]
        )

        yearly, summary = threshold_summary(
            season,
            position="WR",
            metric="targets",
            outcome="fantasy_points",
            top_n=2,
            min_games=8,
        )

        self.assertEqual(list(yearly["minimum"]), [80, 90])
        self.assertEqual(summary["historical_min"], 80.0)
        self.assertEqual(summary["typical_yearly_floor"], 85.0)
        self.assertAlmostEqual(summary["threshold_80"], 86.0)
        self.assertAlmostEqual(summary["hit_rate"], 1.0)
        self.assertEqual(summary["qualifier_count"], 4)


if __name__ == "__main__":
    unittest.main()
