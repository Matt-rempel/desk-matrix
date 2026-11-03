"""Bounded trials, deterministic comparisons, restart recovery and honest measurements."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HAS = importlib.util.find_spec('flicker') is not None
if HAS:
    import flicker
import library


class FlickerTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HAS, 'Flicker trial mode is not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = flicker.Store(Path(self.tmp.name))
        self.lib = library.default_library()
        self.body = {'action':'start', 'profiles':['baseline','gpio-3','pwm-9'],
                     'screens':['time-classic','time-clockwork'], 'duration_minutes':60,
                     'profile_minutes':5, 'screen_seconds':30, 'brightness':20}
        self.live = {'restart_supported':True, 'driver':{'baseline':{
            'gpio_slowdown':2, 'pwm_bits':11, 'pwm_lsb_nanoseconds':130,
            'pwm_dither_bits':0, 'limit_refresh_rate_hz':0}}, 'updated_at':1000}

    def start(self):
        return self.store.action(self.body, self.lib, self.live, now=1000)

    def test_trial_rotates_same_screens_for_each_profile_and_expires_without_browser(self):
        self.start()
        a = self.store.active(1000)
        b = self.store.active(1030)
        c = self.store.active(1300)
        self.assertEqual((a['profile_id'],a['screen_id']), ('baseline','time-classic'))
        self.assertEqual(b['screen_id'], 'time-clockwork')
        self.assertEqual((c['profile_id'],c['screen_id']), ('gpio-3','time-classic'))
        self.assertNotEqual(a['target'],c['target'])
        self.assertIsNone(self.store.active(4600))
        self.assertEqual(self.store.status(self.live,now=4600)['state'],'completed')

    def test_one_profile_runs_continuously_without_periodic_driver_restarts(self):
        self.body['profiles']=['baseline']
        self.start()
        self.assertEqual(self.store.active(1000)['target'],self.store.active(2301)['target'])
        self.assertGreater(self.store.active(2301)['profile_remaining_s'],1000)

    def test_profiles_change_only_requested_controls_from_actual_baseline(self):
        self.start()
        baseline = self.live['driver']['baseline']
        settings = flicker.driver_settings(baseline, self.store.active(1300))
        self.assertEqual(settings, {**baseline, 'gpio_slowdown':3})
        self.assertEqual(flicker.driver_settings(baseline, None),baseline)
        # No profile can change wiring, power mode, audio, or system commands.
        forbidden = {'hardware_mapping','disable_hardware_pulsing','command','governor'}
        self.assertTrue(all(not forbidden.intersection(p['driver']) for p in flicker.PROFILES.values()))

    def test_stop_restores_normal_and_keeps_saved_library_untouched(self):
        before = json.dumps(self.lib,sort_keys=True)
        self.start()
        self.store.action({'action':'stop'},self.lib,self.live,now=1010)
        self.assertIsNone(self.store.active(1011))
        self.assertEqual(self.store.status(self.live,now=1011)['state'],'stopped')
        self.assertEqual(json.dumps(self.lib,sort_keys=True),before)

    def test_invalid_requests_cannot_write_or_select_unknown_screens_or_profiles(self):
        for changes in ({'profiles':['shell']},{'screens':['../../etc/passwd']},
                        {'duration_minutes':999999},{'brightness':100}, {'screen_seconds':True},
                        {'profile_minutes':0},{'extra':'x'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.store.action({**self.body,**changes},self.lib,self.live,now=1000)
        self.assertIsNone(self.store.active(1000))
        unsupported = {**self.live, 'driver':{'baseline':{'gpio_slowdown':2}}}
        with self.assertRaises(ValueError):self.store.action(self.body,self.lib,unsupported,now=1000)
        with self.assertRaises(ValueError):self.store.action(self.body,self.lib,{},now=1000)

    def test_repeated_start_failure_blocks_trial_and_returns_to_baseline(self):
        self.start()
        active = self.store.startup(now=1001)
        self.assertIsNotNone(active)
        self.assertIsNone(self.store.startup(now=1005))
        self.assertIsNone(self.store.active(1006))
        self.assertEqual(self.store.status(self.live,now=1006)['state'],'error')

    def test_ratings_use_acknowledged_profile_not_queued_next_profile(self):
        self.start()
        active = self.store.active(1000)
        live = {**self.live, 'trial':active}
        self.store.action({'action':'note','rating':'same','text':'Random rows still flash'},self.lib,live,now=1301)
        note = self.store.status(live,now=1301)['notes'][-1]
        self.assertEqual(note['profile_id'],'baseline')
        self.assertEqual(note['screen_id'],'time-classic')
        self.assertEqual(note['rating'],'same')
        # No software counter falsely reports visible physical glitch counts.
        self.assertNotIn('glitches',self.store.status(live,now=1301))

    def test_observation_cannot_be_assigned_to_an_unacknowledged_new_run(self):
        self.start()
        live={**self.live,'trial':{'run_id':'0'*32,'profile_id':'gpio-3','screen_id':'time-clockwork'}}
        for observed in (live,self.live):
            with self.assertRaises(ValueError):
                self.store.action({'action':'note','rating':'none','text':'Waiting'},self.lib,observed,now=1001)

    def test_measurements_distinguish_render_paint_swap_and_software_errors(self):
        self.start();trial=self.store.active(1000)
        measurements=flicker.Measurements()
        measurements.add(trial,2,4,True,paint_ms=3,error=True)
        measurements.add(trial,6,0,False,paint_ms=0,error=False)
        row=measurements.report()[0]
        self.assertEqual(row['render_ms_mean'],4)
        self.assertEqual(row['paint_ms_mean'],3)
        self.assertEqual(row['swap_ms_mean'],4)
        self.assertEqual(row['render_errors'],1)
        self.assertNotIn('panel_refresh_hz',row)

    def test_live_metrics_follow_current_screen_when_a_screen_loop_repeats(self):
        self.start();a=self.store.active(1000);b={**a,'screen_id':'time-clockwork'}
        measurements=flicker.Measurements()
        measurements.add(a,2,0,False)
        measurements.add(b,9,0,False)
        measurements.add(a,4,0,False)
        self.assertEqual(measurements.current(a)['render_ms_mean'],3)
        self.assertEqual(measurements.current(b)['render_ms_mean'],9)

    def test_long_runs_keep_complete_comparison_aggregates_after_recent_rows_roll_over(self):
        self.start();base=self.store.active(1000)
        for step in range(165):
            trial={**base,'target':f'run:{step}','step':step}
            measurements=flicker.Measurements();measurements.add(trial,2,0,False)
            measurements.archive(self.store.root)
        report=self.store.status({},now=1001)
        self.assertEqual(len(report['measurements']),160)
        self.assertEqual(report['aggregates'][0]['samples'],165)
        self.assertEqual(report['aggregates'][0]['render_ms_mean'],2)

    def test_pattern_frames_are_native_and_frozen_render_really_skips_renderer(self):
        for name in flicker.PATTERNS:
            pixels = flicker.pattern(name)
            self.assertEqual(len(pixels),2048)
            self.assertTrue(all(len(p)==3 for p in pixels))
        renderer = flicker.TrialRenderer()
        trial = {'target':'a', 'screen_id':'time-classic', 'profile_id':'freeze',
                 'profile':flicker.PROFILES['freeze']}
        calls = []
        def draw():calls.append(1);return [(len(calls),0,0)]*2048,{'screen_name':'Clock'}
        first = renderer.draw(trial,draw)
        second = renderer.draw(trial,draw)
        self.assertEqual(first,second)
        self.assertEqual(len(calls),1)
        changed = {**trial,'screen_id':'time-clockwork'}
        renderer.draw(changed,draw)
        self.assertEqual(len(calls),2)
