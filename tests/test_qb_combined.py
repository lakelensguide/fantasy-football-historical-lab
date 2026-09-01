import unittest

import pandas as pd

from src.analysis import available_metrics
from src.betting import filter_metric_market, metric_supported


class QBCombinedMetricTests(unittest.TestCase):
    def test_qb_combined_yards_and_tds_are_derived(self):
        season = pd.DataFrame(
            {
                "player_id": ["Q1"],
                "player_display_name": ["QB One"],
                "position": ["QB"],
                "season": [2025],
                "passing_yards": [4100],
                "rushing_yards": [450],
                "passing_tds": [31],
                "rushing_tds": [5],
            }
        )

        metrics = available_metrics(season, "QB")

        self.assertIn("qb_total_yards", metrics)
        self.assertIn("qb_total_tds", metrics)
        self.assertEqual(float(season.loc[0, "qb_total_yards"]), 4550.0)
        self.assertEqual(float(season.loc[0, "qb_total_tds"]), 36.0)

    def test_qb_combo_market_requires_both_pass_and_rush(self):
        odds = pd.DataFrame(
            {
                "marketSubtype": [
                    "PASS_RUSH_YARDS",
                    "PASS_YARDS",
                    "RUSH_YARDS",
                    "PASS_RUSH_REC_YARDS",
                    "PASS_RUSH_TDS",
                    "PASS_TDS",
                ],
                "line": [4500.5, 4100.5, 450.5, 4550.5, 35.5, 30.5],
            }
        )

        yards = filter_metric_market(odds, "qb_total_yards")
        tds = filter_metric_market(odds, "qb_total_tds")

        self.assertTrue(metric_supported("qb_total_yards"))
        self.assertTrue(metric_supported("qb_total_tds"))
        self.assertEqual(yards["marketSubtype"].tolist(), ["PASS_RUSH_YARDS"])
        self.assertEqual(tds["marketSubtype"].tolist(), ["PASS_RUSH_TDS"])


if __name__ == "__main__":
    unittest.main()
