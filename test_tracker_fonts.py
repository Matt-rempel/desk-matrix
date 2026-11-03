"""Tracker clock typography changes only the time, and respects 12/24-hour formatting."""
import copy
from datetime import datetime, timezone
import unittest

import catalog
from blocks import RenderContext, frame
from clock_canvas import Canvas
from clock_faces import draw_face
from library import validate_screen


class TrackerFontsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 3, 9, 37, 36, 600000, tzinfo=timezone.utc)

    def test_trackers_hide_only_the_12_hour_leading_zero(self):
        for design in ('minute_track', 'seconds_track'):
            for hour, h24, literal in ((0, False, '12:37'), (1, False, '1:37'), (9, False, '9:37'),
                                       (12, False, '12:37'), (13, False, '1:37'), (23, False, '11:37'),
                                       (0, True, '00:37'), (9, True, '09:37'), (13, True, '13:37')):
                with self.subTest(design=design, hour=hour, h24=h24):
                    actual = draw_face(design, self.now.replace(hour=hour), h24=h24)
                    expected = Canvas()
                    expected.text(literal, 0, 0, 64, 14, '#F4F2EE', face='standard', size='large')
                    self.assertTrue(actual[:14*64] == expected.pixels[:14*64])

    def test_font_and_size_choices_render_and_keep_date_unstyled(self):
        self.assertIn('font_family', catalog.BLOCKS['clock_design']['options'])
        for design in ('minute_track', 'seconds_track'):
            original = draw_face(design, self.now)
            family_shapes = []
            for family in ('standard', 'block', 'outline', 'digital'):
                shapes = set()
                for size in ('auto', 'max', 'xl', 'large', 'medium', 'small', 'tiny'):
                    pixels = draw_face(design, self.now, font_family=family, font_size=size)
                    self.assertEqual(len(pixels), 2048)
                    self.assertGreater(sum(any(p) for p in pixels[:20*64]), 20)
                    self.assertEqual(pixels[27*64:], original[27*64:])
                    shapes.add(tuple(pixels[:20*64]))
                    if size == 'large': family_shapes.append(tuple(pixels[:14*64]))
                self.assertGreaterEqual(len(shapes), 5)
            self.assertEqual(len(set(family_shapes)), 4)

    def test_max_uses_more_height_when_date_hidden_and_ruler_still_fits(self):
        self.assertIn('font_size', catalog.BLOCKS['clock_design']['options'])
        for design in ('minute_track', 'seconds_track'):
            with_date = draw_face(design, self.now, font_size='max')
            without = draw_face(design, self.now, font_size='max', show_date=False)
            # Top-row time fills 20 pixels with a date, 25 without one. The
            # ruler's selected value occupies 21..25 or 26..30 respectively.
            for pixels, start in ((with_date, 21), (without, 26)):
                self.assertTrue(any(any(p) for y in range(start, start+5) for p in pixels[y*64+29:y*64+36]))
            self.assertTrue(with_date[:25*64] != without[:25*64])
            self.assertTrue(any(any(p) for p in without[31*64:]))  # ruler baseline

    def test_saved_tracker_uses_font_and_size_in_native_renderer(self):
        self.assertIn('font_family', catalog.BLOCKS['clock_design']['options'])
        for design in ('minute_track', 'seconds_track'):
            sid = 'time-' + design.replace('_', '-')
            template = copy.deepcopy(catalog.BUILTINS[sid])
            item = {k: v for k, v in template.items() if k in ('name', 'layout', 'slots', 'style')}
            item.update(id='custom-'+'d'*32, based_on=sid)
            item['slots'][0]['options'].update(font_family='outline', font_size='max', h24=False)
            clean = validate_screen(item)
            expected = draw_face(design, self.now, primary='#FFFFFF', font_family='outline', font_size='max')
            self.assertEqual(frame(clean, RenderContext(now=self.now)), expected)


if __name__ == '__main__': unittest.main()
