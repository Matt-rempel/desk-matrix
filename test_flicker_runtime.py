import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace

import flightboard as app
import flicker
import library
from settings import Settings,save_settings
import test_flightboard as fixtures


class Aircraft:
    def __init__(self):self.updates=[]
    def update(self,needs):self.updates.append(needs)
    def snapshot(self):return None
    def close(self):pass
    def set_settings(self,settings):pass


class FlickerRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.settings=self.root/'settings.json';save_settings(Settings(brightness=40),self.settings)
        self.libpath=self.root/'library.json'
        lib=library.default_library();lib['lineup']['always']=[{'screen_id':'play-fire','seconds':30}]
        library.save_library(lib,self.libpath)
        self.lib=lib;self.store=flicker.Store(self.root)
        self.args=app.parse_args(['--settings',str(self.settings),'--library',str(self.libpath)])
        self.matrix=fixtures.FakeMatrix();self.providers=fixtures.FakeProviders();self.aircraft=Aircraft()

    def plan(self,profile):
        self.store.action({'action':'start','profiles':[profile],'screens':['play-fire'],
            'duration_minutes':15,'profile_minutes':5,'screen_seconds':30,'brightness':20},self.lib,
            {'updated_at':time.time(),'restart_supported':True,'driver':{'baseline':{'gpio_slowdown':2}}})
        self.args._flicker_target=self.store.active()['target']

    def run_loop(self):
        return app.run(self.matrix,self.args,stop_after=10,state_dir=self.root,
            providers=self.providers,aircraft=self.aircraft,monotonic=fixtures.Ticker(.05),sleep=lambda s:None)

    def test_freeze_holds_pixels_and_test_brightness_without_saving_settings(self):
        self.plan('freeze')
        before=self.settings.read_bytes(),self.libpath.read_bytes()
        self.assertEqual(self.run_loop(),0)
        self.assertEqual(self.matrix.swaps,1)
        self.assertEqual(self.matrix.brightness,20)
        self.assertEqual((self.settings.read_bytes(),self.libpath.read_bytes()),before)
        status=json.loads((self.root/'status.json').read_text())
        self.assertEqual(status['mode'],'flicker')
        self.assertEqual(status['screen_id'],'play-fire')

    def test_quiet_profile_stops_new_provider_work_but_keeps_rendering(self):
        self.plan('quiet');self.run_loop()
        self.assertEqual(self.providers.updates,[])
        self.assertEqual(self.aircraft.updates,[])
        self.assertGreater(self.matrix.swaps,1)

    def test_stop_requests_controlled_service_restart_to_restore_driver_baseline(self):
        self.plan('freeze')
        self.store.action({'action':'stop'},self.lib,{})
        self.assertEqual(self.run_loop(),flicker.RESTART_EXIT)
        self.assertGreaterEqual(self.matrix.clears,2)

    def test_expiry_and_profile_boundary_request_driver_restart(self):
        for advance in (301,901):
            with self.subTest(advance=advance):
                state=self.store.action({'action':'start','profiles':['baseline','gpio-3'],'screens':['play-fire'],
                    'duration_minutes':15,'profile_minutes':5,'screen_seconds':30,'brightness':20},self.lib,
                    {'updated_at':time.time(),'restart_supported':True,'driver':{'baseline':{'gpio_slowdown':2}}})
                started=state['current']['started_at']
                self.args._flicker_target=self.store.active()['target']
                active=flicker.Store.active
                with patch.object(flicker.Store,'active',lambda store,now=None:active(store,started+advance)):
                    self.assertEqual(self.run_loop(),flicker.RESTART_EXIT)
                self.store.action({'action':'stop'},self.lib,{})

    def test_failed_driver_candidate_is_blocked_on_next_startup_before_baseline_init(self):
        self.plan('gpio-3')
        calls=[]
        def options():
            return SimpleNamespace(pwm_bits=11,pwm_lsb_nanoseconds=130,pwm_dither_bits=0,limit_refresh_rate_hz=0)
        def matrix(options):
            calls.append(options.gpio_slowdown)
            if options.gpio_slowdown==3:raise RuntimeError('Simulated driver init failure')
            return self.matrix
        driver=SimpleNamespace(RGBMatrixOptions=options,RGBMatrix=matrix)
        original_read=Path.read_text
        def read(path,*args,**kwargs):
            return '' if str(path)=='/proc/modules' else original_read(path,*args,**kwargs)
        with patch.object(Path,'read_text',read),patch.dict('sys.modules',{'rgbmatrix':driver}),patch.object(app,'STATE_DIR',self.root),patch.object(app,'configured',return_value=Settings()),patch.object(app.signal,'signal'),patch.object(app,'run',return_value=0):
            with self.assertRaises(RuntimeError):app.main(['--gpio-slowdown','2','--software-pulse'])
            self.assertEqual(app.main(['--gpio-slowdown','2','--software-pulse']),0)
        self.assertEqual(calls,[3,2])
        self.assertEqual(self.store.status({},now=time.time())['state'],'error')
