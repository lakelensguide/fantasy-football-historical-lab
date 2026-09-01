import unittest

import pandas as pd

from src.analysis import available_metrics
from src.betting import filter_metric_market
from src.data import aggregate_season


class RBTotalYardsTests(unittest.TestCase):
    def test_total_yards_is_rushing_plus_receiving(self):
        weekly = pd.DataFrame(
            [
                {
                    "player_id": "RB1",
                    "player_display_name": "Runner One",
                    "position": "RB",
                    "season": 2025,
                    "week": 1,
                    "rushing_yards": 80,
                    "receiving_yards": 25,
                },
                {
                    "player_id": "RB1",
                    "player_display_name": "Runner One",
                    "position": "RB",
                    "season": 2025,
                    "week": 2,
                    "rushing_yards": 60,
                    "receiving_yards": 35,
                },
            ]
        )
        season = aggregate_season(weekly)
        rb = season.iloc[0]
        self.assertEqual(float(rb["rushing_yards"]), 140.0)
        self.assertEqual(float(rb["receiving_yards"]), 60.0)
        self.assertEqual(float(rb["total_yards"]), 200.0)
        self.assertIn("total_yards", available_metrics(season, "RB"))

    def test_total_yards_market_requires_rush_and_receiving_yards(self):
        odds = pd.DataFrame(
            {
                "marketSubtype": [
                    "PLAYER_TOTAL_RUSH_RECEIVING_YARDS",
                    "PLAYER_TOTAL_RUSH_YARDS",
                    "PLAYER_TOTAL_PASS_RUSH_YARDS",
                    "PLAYER_TOTAL_RECEIVING_YARDS",
                ]
            }
        )
        matched = filter_metric_market(odds, "total_yards")
        self.assertEqual(
            matched["marketSubtype"].tolist(),
            ["PLAYER_TOTAL_RUSH_RECEIVING_YARDS"],
        )


if __name__ == "__main__":
    unittest.main()
