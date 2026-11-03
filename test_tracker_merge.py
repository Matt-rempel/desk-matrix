"""One tracker in the catalog; old saved trackers preserve their behavior."""
import copy
from datetime import datetime, timezone
import unittest

import catalog
from blocks import RenderContext, frame
from clock_faces import draw_face
from library import default_library, validate_library, validate_screen


class TrackerMergeTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 3, 9, 37, 36, 600000, tzinfo=timezone.utc)

    def test_time_gallery_starts_with_everyday_clocks_and_has_one_tracker(self):
        ids = next(s['items'] for s in catalog.SHELVES if s['id'] == 'time')
        self.assertEqual(ids[:3], ['time-classic', 'time-big', 'time-analog'])
        self.assertEqual(ids[-2:], ['time-clockwork', 'time-minute-runner'])
        self.assertIn('time-tracker', ids)
        self.assertNotIn('time-minute-track', ids)
        self.assertNotIn('time-seconds-track', ids)
        choices = catalog.BLOCKS['clock_design']['options']['design']['choices']
        self.assertIn('tracker', choices)
        self.assertNotIn('minute_track', choices)
        self.assertNotIn('seconds_track', choices)
        for old in ('time-minute-track', 'time-seconds-track'):
            self.assertTrue(catalog.BUILTINS[old]['hidden'])

    def test_new_tracker_switches_units_without_changing_time_or_typography(self):
        self.assertIn('tracker', catalog.BLOCKS['clock_design']['options']['design']['choices'])
        for family in ('standard', 'outline'):
            a = draw_face('tracker', self.now, track_unit='minutes', font_family=family, font_size='max')
            b = draw_face('tracker', self.now, track_unit='seconds', font_family=family, font_size='max')
            self.assertEqual(a[:20*64], b[:20*64])
            self.assertTrue(a[20*64:27*64] != b[20*64:27*64])
            self.assertEqual(a[27*64:], b[27*64:])
            self.assertEqual(a, draw_face('minute_track', self.now, font_family=family, font_size='max'))
            self.assertEqual(b, draw_face('seconds_track', self.now, font_family=family, font_size='max'))

    def test_old_saved_trackers_migrate_in_memory_without_losing_lineup_or_pin(self):
        for old, unit in (('minute_track', 'minutes'), ('seconds_track', 'seconds')):
            sid = 'custom-' + 'b'*32
            old_id = 'time-' + old.replace('_', '-')
            item = {'id':sid, 'name':'My tracker', 'layout':'full', 'based_on':old_id,
                    'style':{'palette':None, 'motion':'still'}, 'slots':[{'block':'clock_design', 'color':None,
                    'options':{'design':old, 'font_family':'outline', 'font_size':'max', 'show_date':False}}]}
            original = frame(item, RenderContext(now=self.now))
            lib = default_library()
            lib['screens'] = [copy.deepcopy(item)]
            lib['lineup']['always'] = [{'screen_id':old_id, 'seconds':20}, {'screen_id':sid, 'seconds':30}]
            lib['pinned'] = {'screen_id':old_id, 'until':None}
            clean = validate_library(lib)
            options = clean['screens'][0]['slots'][0]['options']
            self.assertEqual((options['design'], options.get('track_unit')), ('tracker', unit))
            self.assertEqual(clean['pinned'], lib['pinned'])
            self.assertEqual(clean['lineup']['always'], lib['lineup']['always'])
            self.assertEqual(frame(clean['screens'][0], RenderContext(now=self.now)), original)
            self.assertEqual(frame(catalog.BUILTINS[old_id], RenderContext(now=self.now)),
                             draw_face(old, self.now, primary='#FFFFFF'))
            # An explicit new choice wins over the old design name when editing.
            item['slots'][0]['options']['track_unit'] = 'seconds' if unit == 'minutes' else 'minutes'
            edited = validate_screen(item)['slots'][0]['options']
            self.assertEqual(edited['track_unit'], item['slots'][0]['options']['track_unit'])


if __name__ == '__main__': unittest.main()
