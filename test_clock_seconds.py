"""Seconds options stay readable, wrap correctly, and preserve existing clocks by default."""
import copy
from datetime import datetime, timezone
import unittest

import catalog
from blocks import RenderContext, frame, render_screen
from clock_faces import draw_face
from library import validate_screen


class ClockSecondsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 3, 23, 59, 36, tzinfo=timezone.utc)

    def test_seconds_track_template_and_second_rollover(self):
        self.assertIn('time-seconds-track', catalog.BUILTINS)
        item = catalog.BUILTINS['time-seconds-track']
        self.assertIn(item['id'], next(s['items'] for s in catalog.SHELVES if s['id'] == 'time'))
        before = draw_face('seconds_track', self.now.replace(second=59), animate=False)
        after = draw_face('seconds_track', self.now.replace(second=0), animate=False)
        self.assertNotEqual(before, after)
        self.assertEqual(len(after), 2048)
        # The centered ruler is the selected second, not the minute or a decimal counter.
        from clock_canvas import Canvas
        expected = Canvas()
        expected.text('00', 29, 18, 7, 5, '#59DBCD')
        for y in range(18, 23):
            self.assertEqual(after[y*64+29:y*64+36], expected.pixels[y*64+29:y*64+36])

    def test_seconds_track_slides_each_second_and_can_tick_without_animation(self):
        first = self.now.replace(microsecond=50000)
        second = self.now.replace(microsecond=900000)
        self.assertTrue(draw_face('seconds_track', first) != draw_face('seconds_track', second))
        self.assertEqual(draw_face('seconds_track', first, animate=False),
                         draw_face('seconds_track', second, animate=False))

    def test_optional_seconds_are_off_by_default_and_follow_current_time(self):
        for design in ('platform', 'time_stack', 'minute_track', 'clockwork', 'perpetual_card', 'week_strip'):
            with self.subTest(design=design):
                off = draw_face(design, self.now, animate=False)
                self.assertEqual(off, draw_face(design, self.now, animate=False, seconds_display='off'))
                self.assertEqual(off, draw_face(design, self.now.replace(second=37), animate=False))
                for mode in ('number', 'bar'):
                    a = draw_face(design, self.now, animate=False, seconds_display=mode)
                    b = draw_face(design, self.now.replace(second=37 if mode == 'number' else 59), animate=False, seconds_display=mode)
                    self.assertTrue(a != off, (design, mode))
                    self.assertTrue(a != b, (design, mode))
                    self.assertEqual(len(a), 2048)

    def test_seconds_options_validate_and_preserve_palette(self):
        template = copy.deepcopy(catalog.BUILTINS['time-platform'])
        template = {k: v for k, v in template.items() if k in ('name', 'layout', 'slots', 'style')}
        template.update(id='custom-'+'e'*32, based_on='time-platform')
        template['slots'][0]['options']['seconds_display'] = 'number'
        clean = validate_screen(template)
        self.assertEqual(clean['slots'][0]['options']['seconds_display'], 'number')
        pixels = frame(clean, RenderContext(now=self.now), palette='night')
        self.assertTrue(all(r >= g and r >= b for r, g, b in pixels))

    def test_standard_world_and_analog_clocks_tick_with_seconds_enabled(self):
        for block in ('time', 'world_clock', 'analog_clock'):
            with self.subTest(block=block):
                screen = {'layout':'full', 'slots':[{'block':block, 'color':'#FFFFFF', 'options':{}}]}
                opts = screen['slots'][0]['options']
                still = frame(screen, RenderContext(now=self.now))
                opts['show_seconds'] = True
                a = frame(screen, RenderContext(now=self.now))
                b = frame(screen, RenderContext(now=self.now.replace(second=37)))
                self.assertTrue(a != still)
                self.assertTrue(a != b)
                if block == 'time':
                    value = render_screen(screen, RenderContext(now=self.now), strict=True)[0]['s']
                    self.assertIn('23:59:36', value)
                    # A requested legacy Large font must fit the whole time rather than scroll.
                    opts['font'] = 'large'
                    narrow = {**screen, 'layout': 'split', 'slots': [screen['slots'][0], {'block': 'none', 'options': {}}]}
                    layer = render_screen(narrow, RenderContext(now=self.now), strict=True)[0]
                    self.assertEqual(layer['f'], 'auto')


if __name__ == '__main__': unittest.main()
