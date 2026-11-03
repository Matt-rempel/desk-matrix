import json
from pathlib import Path
import time
from unittest.mock import patch

import flicker
import web_server
from settings import Settings,save_settings
import test_web_server as fixtures


class FlickerApiTest(fixtures.ServerTestCase):
    def setUp(self):
        super().setUp()
        self.root=self.settings_path.parent
        save_settings(Settings(),self.settings_path)
        p=patch.object(web_server,'FLICKER_ROOT',self.root,create=True);p.start();self.addCleanup(p.stop)
        flicker.write_json(self.root/'flicker-live.json',{'updated_at':time.time(),'restart_supported':True,
            'driver':{'baseline':{'gpio_slowdown':2,'pwm_bits':11,'pwm_lsb_nanoseconds':130,'pwm_dither_bits':0,'limit_refresh_rate_hz':0}}})
        self.start={'action':'start','profiles':['baseline','gpio-3'],'screens':['time-classic','pattern:contrast'],
            'duration_minutes':15,'profile_minutes':5,'screen_seconds':30,'brightness':20}

    def test_trial_routes_require_pairing_and_same_origin(self):
        self.assertStatus(401,self.get,'/api/flicker',key=None)
        self.assertStatus(401,self.post,'/api/flicker',self.start,key=None)
        self.assertStatus(403,self.post,'/api/flicker',self.start,origin='https://other.test')

    def test_start_stop_and_export_preserve_normal_library_and_settings(self):
        self.get_json('/api/library')
        before=self.settings_path.read_bytes(),self.library_path.read_bytes()
        result=self.post('/api/flicker',self.start)
        self.assertEqual(result['state'],'running')
        self.assertEqual(result['trial']['profile_id'],'baseline')
        exported=self.get_json('/api/flicker')
        self.assertEqual(exported['current']['screens'],['time-classic','pattern:contrast'])
        self.assertEqual(self.post('/api/flicker',{'action':'stop'})['state'],'stopped')
        self.assertEqual((self.settings_path.read_bytes(),self.library_path.read_bytes()),before)

    def test_invalid_experiments_are_rejected(self):
        self.assertStatus(400,self.post,'/api/flicker',{**self.start,'profiles':['hardware-pwm']})
        self.assertStatus(400,self.post,'/api/flicker',{**self.start,'screens':['/etc/passwd']})
        self.assertStatus(400,self.post,'/api/flicker',{**self.start,'command':'sudo reboot'})
