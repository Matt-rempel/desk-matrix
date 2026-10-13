from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest import mock

import blocks
import catalog
import nhl
import providers
from test_providers import Clock, FakeSettings, InlineExecutor

NOW = datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc)


def game(state, start, *, home="CGY", away="EDM", home_score=None, away_score=None,
         period=2, clock="10:20"):
    return {"id": 2026020001, "gameState": state, "startTimeUTC": start,
            "homeTeam": {"abbrev": home, "score": home_score},
            "awayTeam": {"abbrev": away, "score": away_score},
            "periodDescriptor": {"number": period, "periodType": "REG"},
            "clock": {"timeRemaining": clock}}


class NHLTests(unittest.TestCase):
    def test_selection_prefers_live_then_recent_final_then_next(self):
        payload = {"games": [
            game("OFF", "2026-10-12T15:00:00Z", home_score=3, away_score=1),
            game("FUT", "2026-10-14T02:00:00Z", away="VAN"),
            game("LIVE", "2026-10-12T18:00:00Z", home="EDM", away="CGY",
                 home_score=2, away_score=4),
        ]}
        result = nhl.parse_schedule(payload, "CGY", NOW)
        self.assertEqual((result["state"], result["away"], result["away_score"]), ("live", "CGY", 4))
        self.assertEqual(result["game_id"], 2026020001)
        payload["games"].pop()
        self.assertEqual(nhl.parse_schedule(payload, "CGY", NOW)["state"], "final")
        self.assertEqual(nhl.parse_schedule(payload, "CGY", NOW.replace(day=13))["state"], "upcoming")

    def test_empty_and_invalid_data(self):
        self.assertEqual(nhl.parse_schedule({"games": []}, "CGY", NOW)["state"], "none")
        with self.assertRaises(ValueError):
            nhl.parse_schedule({"games": {}}, "CGY", NOW)
        with self.assertRaises(ValueError):
            nhl.parse_schedule({"games": []}, "INVALID", NOW)

    def test_provider_fetches_week_and_falls_back_to_season(self):
        clock = Clock(NOW.timestamp())
        executor = InlineExecutor()
        provider = providers.Providers(FakeSettings(), executor=executor,
                                       now_fn=lambda: clock.wall, monotonic_fn=lambda: clock.mono)
        future = {"games": [game("FUT", "2026-10-14T02:00:00Z", away="VAN")]}
        with mock.patch.object(providers, "_nhl_json", side_effect=[{"games": []}, future]) as fetch:
            provider.update({"nhl:CGY"})
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(provider.snapshot()["nhl"]["CGY"]["state"], "upcoming")
        self.assertEqual(executor.calls, 1)
        self.assertNotIn("nhl:INVALID", provider._sources)
        provider.update({"nhl:INVALID"})

    def test_render_two_line_states_and_team_need(self):
        screen = catalog.BUILTINS["data-score"]
        self.assertEqual(blocks.data_needs(screen), {"nhl:CGY"})
        current = {"team": "CGY", "state": "live", "home": "CGY", "away": "EDM",
                   "home_score": 2, "away_score": 1, "period": 3, "period_type": "REG",
                   "clock": "12:34", "age_s": 20}
        ctx = blocks.RenderContext(now=NOW, data={"nhl": {"CGY": current}})
        self.assertEqual([x["s"][0] for x in blocks.render_screen(screen, ctx) if x["t"] == "text"],
                         ["CGY 2", "EDM 1"])
        ctx.elapsed = 10
        self.assertEqual([x["s"][0] for x in blocks.render_screen(screen, ctx) if x["t"] == "text"],
                         ["CGY 2", "P3 12:34"])
        current["age_s"] = 190
        self.assertEqual(blocks.render_screen(screen, ctx)[1]["s"], ["STALE"])
        current["state"] = "final"
        self.assertEqual(blocks.render_screen(screen, ctx)[1]["s"], ["FINAL"])
        current.update(state="upcoming", start="2026-10-14T02:00:00+00:00", away="VAN")
        ctx.now = NOW.astimezone(blocks.ZoneInfo("America/Edmonton"))
        self.assertEqual([x["s"][0] for x in blocks.render_screen(screen, ctx) if x["t"] == "text"],
                         ["CGY VAN", "TUE 8:00P"])
        ctx.data = {"nhl": {"CGY": {"state": "none"}}}
        self.assertEqual(blocks.render_screen(screen, ctx)[1]["s"], ["NO GAME"])


if __name__ == "__main__":
    unittest.main()
