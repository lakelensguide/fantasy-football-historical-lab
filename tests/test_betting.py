import unittest

import pandas as pd

from src.betting import consensus_for_threshold, filter_metric_market


class BettingMarketTests(unittest.TestCase):
    def test_metric_filter_avoids_combined_markets(self):
        odds = pd.DataFrame(
            {
                "marketSubtype": [
                    "PLAYER_TOTAL_PASS_YARDS",
                    "PLAYER_TOTAL_PASS_RUSH_YARDS",
                    "PLAYER_TOTAL_RUSH_YARDS",
                    "PLAYER_TOTAL_RECEIVING_YARDS",
                ]
            }
        )

        passing = filter_metric_market(odds, "passing_yards")
        rushing = filter_metric_market(odds, "rushing_yards")
        receiving = filter_metric_market(odds, "receiving_yards")

        self.assertEqual(passing["marketSubtype"].tolist(), ["PLAYER_TOTAL_PASS_YARDS"])
        self.assertEqual(rushing["marketSubtype"].tolist(), ["PLAYER_TOTAL_RUSH_YARDS"])
        self.assertEqual(
            receiving["marketSubtype"].tolist(),
            ["PLAYER_TOTAL_RECEIVING_YARDS"],
        )

    def test_consensus_compares_market_line_to_historical_target(self):
        rows = []
        for sportsbook, line in [("book_a", 1099.5), ("book_b", 1100.5)]:
            rows.extend(
                [
                    {
                        "playerId": "wr1",
                        "playerName": "Receiver One",
                        "marketSubtype": "PLAYER_TOTAL_RECEIVING_YARDS",
                        "sportsbook": sportsbook,
                        "side": "OVER",
                        "line": line,
                        "priceAmerican": -110,
                        "updated": "2026-08-30T12:00:00Z",
                    },
                    {
                        "playerId": "wr1",
                        "playerName": "Receiver One",
                        "marketSubtype": "PLAYER_TOTAL_RECEIVING_YARDS",
                        "sportsbook": sportsbook,
                        "side": "UNDER",
                        "line": line,
                        "priceAmerican": -110,
                        "updated": "2026-08-30T12:00:00Z",
                    },
                ]
            )
        for sportsbook, line in [("book_a", 899.5), ("book_b", 900.5)]:
            rows.extend(
                [
                    {
                        "playerId": "wr2",
                        "playerName": "Receiver Two",
                        "marketSubtype": "PLAYER_TOTAL_RECEIVING_YARDS",
                        "sportsbook": sportsbook,
                        "side": "OVER",
                        "line": line,
                        "priceAmerican": -110,
                        "updated": "2026-08-30T12:00:00Z",
                    },
                    {
                        "playerId": "wr2",
                        "playerName": "Receiver Two",
                        "marketSubtype": "PLAYER_TOTAL_RECEIVING_YARDS",
                        "sportsbook": sportsbook,
                        "side": "UNDER",
                        "line": line,
                        "priceAmerican": -110,
                        "updated": "2026-08-30T12:00:00Z",
                    },
                ]
            )

        history = pd.DataFrame(
            [
                {"player_display_name": "Receiver One", "position": "WR", "season": 2025},
                {"player_display_name": "Receiver Two", "position": "WR", "season": 2025},
            ]
        )
        result = consensus_for_threshold(
            pd.DataFrame(rows),
            metric="receiving_yards",
            position="WR",
            target=1000.0,
            season_history=history,
        )

        one = result.loc[result["Player"].eq("Receiver One")].iloc[0]
        two = result.loc[result["Player"].eq("Receiver Two")].iloc[0]

        self.assertAlmostEqual(float(one["Market line"]), 1100.0)
        self.assertEqual(one["Expectation"], "Likely clears")
        self.assertAlmostEqual(float(one["Over probability"]), 0.5)
        self.assertEqual(int(one["Books"]), 2)

        self.assertAlmostEqual(float(two["Market line"]), 900.0)
        self.assertEqual(two["Expectation"], "Likely below")


if __name__ == "__main__":
    unittest.main()
