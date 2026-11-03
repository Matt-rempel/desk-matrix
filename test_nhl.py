from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest import mock

import blocks
import catalog
import nhl
import providers
from nhl_logos import LOGOS
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
    def test_detail_preserves_intermission_shots_and_clock_flags(self):
        raw = game("LIVE", "2026-10-12T18:00:00Z", away="SJS", home_score=1, away_score=0,
                   period=1, clock="00:00")
        raw["clock"].update(secondsRemaining=0, running=False, inIntermission=True)
        raw["homeTeam"]["sog"], raw["awayTeam"]["sog"] = 12, 9
        base = nhl.parse_schedule({"games": [raw]}, "CGY", NOW)
        detail = nhl.parse_game_detail(raw, base, NOW)
        self.assertEqual((detail["home_shots"], detail["away_shots"]), (12, 9))
        self.assertTrue(detail["intermission"])
        self.assertFalse(detail["clock_running"])
        self.assertEqual(nhl.game_status(detail, NOW), "1ST INT")
        detail["intermission"], detail["clock_running"] = False, True
        detail["clock_seconds"], detail["period"] = 600, 2
        self.assertEqual(nhl.game_status(detail, NOW + timedelta(seconds=12)), "P2 09:48")
        detail["clock_running"] = False
        self.assertEqual(nhl.game_status(detail, NOW + timedelta(seconds=12)), "P2 10:00")

    def test_details_reject_mismatched_game_and_team(self):
        raw = game("LIVE", "2026-10-12T18:00:00Z", home_score=1, away_score=0)
        base = nhl.parse_schedule({"games": [raw]}, "CGY", NOW)
        raw["id"] += 1
        with self.assertRaises(ValueError):nhl.parse_game_detail(raw, base, NOW)
        raw["id"] = base["game_id"]
        raw["awayTeam"]["abbrev"] = "SJS"
        with self.assertRaises(ValueError):nhl.parse_game_detail(raw, base, NOW)

    def test_status_handles_final_overtime_shootout_missing_and_stale_data(self):
        base = {"state": "live", "period": 2, "period_type": "REG", "clock": "10:00",
                "clock_seconds": 600, "clock_running": True, "clock_observed_at": NOW.isoformat()}
        self.assertEqual(nhl.game_status(base, NOW + timedelta(seconds=40)), "P2 SYNC")
        self.assertEqual(nhl.game_status(dict(base, age_s=190), NOW), "STALE")
        self.assertEqual(nhl.game_status(dict(base, error="HTTP 503"), NOW), "STALE")
        self.assertEqual(nhl.game_status(dict(base, period_type="OT"), NOW), "OT 10:00")
        self.assertEqual(nhl.game_status(dict(base, period_type="SO"), NOW), "SHOOTOUT")
        self.assertEqual(nhl.game_status(dict(base, state="final", intermission=True), NOW), "FINAL")
        self.assertEqual(nhl.game_status(dict(base, state="final", period_type="OT"), NOW), "FINAL/OT")
        self.assertEqual(nhl.game_status({"state": "live", "period": 1}, NOW), "P1")
        self.assertEqual(nhl.game_status(dict(base, clock_seconds=0), NOW), "P2 00:00")
        self.assertEqual(nhl.game_status(dict(base, clock_seconds=2), NOW + timedelta(seconds=8)), "P2 00:00")

    def test_logo_scoreboard_keeps_all_information_visible_and_orients_to_followed_team(self):
        item = catalog.BUILTINS["nhl-scoreboard"]
        current = {"team": "CGY", "state": "live", "home": "SJS", "away": "CGY",
                   "home_score": 0, "away_score": 1, "period": 1, "period_type": "REG",
                   "intermission": True, "home_shots": 9, "away_shots": 12}
        ctx = blocks.RenderContext(now=NOW, data={"nhl": {"CGY": current}})
        layers = blocks.render_screen(item, ctx, strict=True)
        values = [l["s"] if isinstance(l["s"], str) else l["s"][0] for l in layers if l["t"] == "text"]
        for value in ("1-0", "CGY", "SJS", "SH12-9", "1ST INT"):self.assertIn(value, values)
        self.assertEqual(sum(l["t"] == "pts" for l in layers), 2)
        self.assertEqual(len(blocks.frame(item, ctx)), 2048)
        ctx.elapsed = 20
        self.assertEqual(blocks.render_screen(item, ctx, strict=True), layers)

    def test_logos_cover_all_teams_and_have_bounded_pixels(self):
        self.assertEqual(set(LOGOS), set(nhl.TEAMS))
        for logo in LOGOS.values():
            self.assertTrue(logo["rows"])
            self.assertLessEqual(len(logo["rows"]), 14)
            self.assertTrue(all(len(row) == len(logo["rows"][0]) <= 14 for row in logo["rows"]))
            for row in logo["rows"]:
                self.assertTrue(all(c == "." or int(c, 36) < len(logo["palette"]) for c in row))

    def test_provider_fetches_live_details_and_uses_live_interval_on_first_result(self):
        clock = Clock(NOW.timestamp())
        provider = providers.Providers(FakeSettings(), executor=InlineExecutor(),
                                       now_fn=lambda: clock.wall, monotonic_fn=lambda: clock.mono)
        raw = game("LIVE", "2026-10-12T18:00:00Z", home_score=1, away_score=0)
        raw["clock"].update(secondsRemaining=620, running=True, inIntermission=False)
        raw["homeTeam"]["sog"] = 12
        with mock.patch.object(providers, "_nhl_json", side_effect=[{"games": [raw]}, raw]) as fetch:
            provider.update({"nhl:CGY"})
        self.assertEqual(fetch.call_count, 2)
        self.assertIn('/gamecenter/2026020001/landing', fetch.call_args_list[-1].args[0])
        self.assertEqual(provider.snapshot()["nhl"]["CGY"]["home_shots"], 12)
        self.assertEqual(provider._sources["nhl:CGY"].next_due - clock.mono, 15)
        old = provider.snapshot()["nhl"]["CGY"]
        clock.mono += 16;clock.wall += 16
        with mock.patch.object(providers, "_nhl_json", side_effect=[{"games": [raw]}, ValueError("Bad detail")]):
            provider.update({"nhl:CGY"})
        saved = provider.snapshot()["nhl"]["CGY"]
        self.assertEqual(saved["home_score"], old["home_score"])
        self.assertEqual(saved["home_shots"], old["home_shots"])
        self.assertTrue(saved["error"])

    def test_missing_and_invalid_shots_do_not_turn_into_zero(self):
        raw = game("LIVE", "2026-10-12T18:00:00Z", home_score=1, away_score=0)
        raw["homeTeam"]["sog"], raw["awayTeam"]["sog"] = True, -1
        parsed = nhl.parse_schedule({"games": [raw]}, "CGY", NOW)
        self.assertIsNone(parsed["home_shots"])
        self.assertIsNone(parsed["away_shots"])
        item = catalog.BUILTINS["nhl-scoreboard"]
        layers = blocks.render_screen(item, blocks.RenderContext(now=NOW, data={"nhl": {"CGY": parsed}}))
        self.assertIn(["SH---"], [l["s"] for l in layers if l["t"] == "text"])

    def test_final_schedule_score_survives_detail_failure(self):
        clock = Clock(NOW.timestamp())
        provider = providers.Providers(FakeSettings(), executor=InlineExecutor(),
                                       now_fn=lambda: clock.wall, monotonic_fn=lambda: clock.mono)
        raw = game("OFF", "2026-10-12T16:00:00Z", home_score=3, away_score=2)
        with mock.patch.object(providers, "_nhl_json", side_effect=[{"games": [raw]}, ValueError("Offline")]):
            provider.update({"nhl:CGY"})
        final = provider.snapshot()["nhl"]["CGY"]
        self.assertEqual((final["state"], final["home_score"], final["away_score"]), ("final", 3, 2))
        self.assertIsNone(final["home_shots"])
        self.assertEqual(nhl.game_status(final, NOW), "FINAL")

    def test_scoreboard_handles_upcoming_shots_toggle_and_large_scores(self):
        import copy
        item = copy.deepcopy(catalog.BUILTINS["nhl-scoreboard"])
        current = {"state": "live", "home": "CGY", "away": "SJS", "home_score": 10, "away_score": 12,
                   "home_shots": 100, "away_shots": 101, "period": 3, "clock": "00:01"}
        ctx = blocks.RenderContext(now=NOW, data={"nhl": {"CGY": current}})
        layers = blocks.render_screen(item, ctx, strict=True)
        self.assertIn(["10-12"], [l["s"] for l in layers if l["t"] == "text"])
        self.assertIn(["S100-101"], [l["s"] for l in layers if l["t"] == "text"])
        self.assertEqual(len(blocks.frame(item, ctx)), 2048)
        item["slots"][0]["options"]["show_shots"] = False
        values = [l["s"] for l in blocks.render_screen(item, ctx) if l["t"] == "text"]
        self.assertNotIn(["S100-101"], values)
        current.update(state="upcoming", start="2026-10-13T02:00:00Z")
        values = [l["s"] for l in blocks.render_screen(item, ctx) if l["t"] == "text"]
        self.assertIn(["VS"], values)
        self.assertTrue(any("MON" in v[0] or "TUE" in v[0] for v in values))

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

    def test_scores_and_status_stay_visible_together(self):
        screen = catalog.BUILTINS["data-score"]
        self.assertEqual(blocks.data_needs(screen), {"nhl:CGY"})
        current = {"team": "CGY", "state": "live", "home": "CGY", "away": "EDM",
                   "home_score": 2, "away_score": 1, "period": 3, "period_type": "REG",
                   "clock": "12:34", "age_s": 20}
        ctx = blocks.RenderContext(now=NOW, data={"nhl": {"CGY": current}})
        self.assertEqual([x["s"][0] for x in blocks.render_screen(screen, ctx) if x["t"] == "text"],
                         ["CGY 2", "EDM 1", "P3 12:34"])
        ctx.elapsed = 10
        self.assertEqual([x["s"][0] for x in blocks.render_screen(screen, ctx) if x["t"] == "text"],
                         ["CGY 2", "EDM 1", "P3 12:34"])
        current["age_s"] = 190
        self.assertEqual(blocks.render_screen(screen, ctx)[2]["s"], ["STALE"])
        current["state"] = "final"
        self.assertEqual(blocks.render_screen(screen, ctx)[2]["s"], ["FINAL"])
        current.update(state="upcoming", start="2026-10-14T02:00:00+00:00", away="VAN")
        ctx.now = NOW.astimezone(blocks.ZoneInfo("America/Edmonton"))
        self.assertEqual([x["s"][0] for x in blocks.render_screen(screen, ctx) if x["t"] == "text"],
                         ["CGY VAN", "TUE 8:00P"])
        ctx.data = {"nhl": {"CGY": {"state": "none"}}}
        self.assertEqual(blocks.render_screen(screen, ctx)[1]["s"], ["NO GAME"])


if __name__ == "__main__":
    unittest.main()
