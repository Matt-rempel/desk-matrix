"""Clock collection: calendar boundaries, exact words, animation and real RGB output."""
import importlib.util
import unittest
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

HAS_FACES = importlib.util.find_spec('clock_faces') is not None
if HAS_FACES:
    from clock_faces import DESIGN_NAMES, draw_face, time_words, week_dates, month_cells


class ClockFacesTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HAS_FACES, 'Native clock collection renderer is not implemented')
        self.now = datetime(2026, 11, 3, 10, 24, 36, tzinfo=ZoneInfo('America/Edmonton'))

    def test_twelve_distinct_native_designs_and_both_time_formats(self):
        frames = []
        for design in DESIGN_NAMES:
            for h24 in (False, True):
                with self.subTest(design=design, h24=h24):
                    frame = draw_face(design, self.now, h24=h24)
                    self.assertEqual(len(frame), 2048)
                    self.assertGreater(sum(any(pixel) for pixel in frame), 70)
                    self.assertTrue(all(len(p) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in p) for p in frame))
                    if h24: frames.append(tuple(frame))
        self.assertEqual(len(set(frames)), 12)

    def test_week_crosses_year_and_starts_monday(self):
        self.assertEqual(week_dates(datetime(2027, 1, 1)),
                         [date(2026, 12, 28) + timedelta(days=i) for i in range(7)])

    def test_month_cells_handle_leap_years_and_six_rows(self):
        for year, count in ((1900, 28), (2000, 29), (2024, 29), (2100, 28)):
            days = [d for row in month_cells(datetime(year, 2, 1)) for d in row if d]
            self.assertEqual(days, list(range(1, count + 1)))
        rows = month_cells(self.now)
        self.assertEqual(len(rows), 6)  # November 2026 begins on Sunday
        self.assertEqual(rows[0], [0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(rows[-1], [30, 0, 0, 0, 0, 0, 0])

    def test_exact_word_time_including_midnight_and_single_minutes(self):
        for hour, minute, expected in ((0, 0, ('IT IS', 'TWELVE', "O'CLOCK", '')),
                                        (13, 1, ('IT IS', 'ONE', 'OH', 'ONE')),
                                        (10, 24, ('IT IS', 'TEN', 'TWENTY', 'FOUR')),
                                        (23, 59, ('IT IS', 'ELEVEN', 'FIFTY', 'NINE')),
                                        (7, 17, ('IT IS', 'SEVEN', 'SEVENTEEN', ''))):
            self.assertEqual(time_words(self.now.replace(hour=hour, minute=minute)), expected)
        for minute in range(60):
            self.assertTrue(all(len(word) <= 10 for word in time_words(self.now.replace(minute=minute))))

    def test_all_clockwork_digits_draw_distinctly(self):
        shapes = []
        for digit in range(10):
            frame = draw_face('clockwork', self.now.replace(minute=digit), animate=False)
            shapes.append(tuple(tuple(frame[y*64+48:y*64+64]) for y in range(24)))
        self.assertEqual(len(set(shapes)), 10)

    def test_static_modes_ignore_fractional_seconds(self):
        for design in DESIGN_NAMES:
            with self.subTest(design=design):
                self.assertEqual(draw_face(design, self.now, animate=False),
                                 draw_face(design, self.now.replace(microsecond=950000), animate=False))

    def test_motion_settles_and_date_changes_at_midnight(self):
        for design in ('platform', 'minute_track', 'clockwork'):
            with self.subTest(design=design):
                now = self.now.replace(second=3)
                self.assertEqual(draw_face(design, now), draw_face(design, now, animate=False))
                self.assertNotEqual(draw_face(design, now.replace(second=0, microsecond=100000)),
                                    draw_face(design, now.replace(second=0, microsecond=100000), animate=False))
        for design in DESIGN_NAMES:
            before = self.now.replace(hour=23, minute=59, second=59)
            after = (before + timedelta(seconds=4))
            self.assertNotEqual(draw_face(design, before), draw_face(design, after), design)

    def test_dst_flip_uses_the_actual_preceding_minute(self):
        zone = ZoneInfo('America/Edmonton')
        for moment, previous in (
            (datetime(2026, 3, 8, 3, 0, tzinfo=zone), datetime(2026, 3, 8, 1, 59, tzinfo=zone)),
            (datetime(2025, 11, 2, 1, 0, fold=1, tzinfo=zone), datetime(2025, 11, 2, 1, 59, tzinfo=zone)),
        ):
            self.assertTrue(draw_face('platform', moment, show_date=False) ==
                            draw_face('platform', previous, show_date=False, animate=False), moment.isoformat())
        repeated = datetime(2025, 11, 2, 1, 0, 0, 50000, fold=1, tzinfo=zone)
        moving = draw_face('clockwork', repeated)
        still = draw_face('clockwork', repeated, animate=False)
        self.assertTrue(all(moving[y*64:y*64+32] == still[y*64:y*64+32] for y in range(24)),
                        'Fallback must not rotate the unchanged hour dials')

    def test_accent_control_changes_each_design(self):
        for design in DESIGN_NAMES:
            self.assertTrue(draw_face(design, self.now, accent='#FF0000') !=
                            draw_face(design, self.now, accent='#0000FF'), design)

    def test_night_tint_contains_no_blue_or_green_accents(self):
        for design in DESIGN_NAMES:
            frame = draw_face(design, self.now, primary='#FF0000', accent='#800000', tinted=True)
            self.assertTrue(all(g == b == 0 for r, g, b in frame), design)



class ClockCollectionIntegrationTest(unittest.TestCase):
    def test_templates_are_offline_full_panel_and_save_with_the_same_pixels(self):
        import copy
        import catalog
        from blocks import RenderContext, data_needs, frame, render_screen
        from library import validate_screen
        selected = ('time-platform', 'time-station', 'time-stack', 'time-orbit',
                    'time-minute-track', 'time-clockwork', 'time-perpetual-card',
                    'time-week-strip', 'time-month-map', 'time-date-poster',
                    'time-word-glow', 'time-minute-runner')
        shelf = next(s for s in catalog.SHELVES if s['id'] == 'time')['items']
        ctx = RenderContext(now=datetime(2026, 11, 3, 23, 59, 36))
        for sid in selected:
            with self.subTest(sid=sid):
                self.assertIn(sid, shelf)
                item = copy.deepcopy(catalog.BUILTINS[sid])
                self.assertEqual(data_needs(item), set())
                self.assertEqual(item['layout'], 'full')
                self.assertNotEqual(item['family'], 'clock')
                native = frame(item, ctx)
                self.assertGreater(sum(any(p) for p in native), 70)
                render_screen(item, ctx, strict=True)
                item['id'] = 'custom-' + 'f' * 32
                item['based_on'] = sid
                opts = item['slots'][0]['options']
                opts.update(h24=True, show_date=False, show_seconds=False, animate=False, accent='#AABBCC')
                item = {k: v for k, v in item.items() if k in ('id', 'name', 'layout', 'slots', 'style', 'based_on')}
                saved = validate_screen(item)
                self.assertEqual(frame(saved, ctx), frame(item, ctx))
                tinted = frame(saved, ctx, palette='night')
                self.assertTrue(all(r >= g and r >= b for r, g, b in tinted))


class ClockPreviewTest(unittest.TestCase):
    def test_gallery_is_settled_while_editor_animates_at_minute_boundary(self):
        from unittest.mock import patch
        import catalog
        import web_server
        from library import default_library
        from settings import validate_settings
        from render import to_hex
        moment = datetime(2026, 11, 3, 10, 25, 0, 100000)
        template = catalog.BUILTINS['time-platform']
        item = {k: v for k, v in template.items() if k in ('id', 'name', 'layout', 'slots', 'style', 'based_on')}
        with patch.object(web_server, 'datetime', wraps=datetime) as clock:
            clock.now.return_value = moment
            still = web_server.render_previews({'screens': [item]}, validate_settings({}), default_library())[0]
            moving = web_server.render_previews({'screens': [item], 'animate': True}, validate_settings({}), default_library())[0]
        self.assertEqual(still, to_hex(draw_face('platform', moment, primary='#FFFFFF', animate=False)))
        self.assertNotEqual(moving, still)


if __name__ == '__main__': unittest.main()
