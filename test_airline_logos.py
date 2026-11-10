import copy
import hashlib
from pathlib import Path
import unittest

import blocks
import catalog
from airline_logos import AIRLINES, LOGOS, airline_for
from render import BLACK, rasterize


class AirlineLogoTests(unittest.TestCase):
    def test_callsigns_and_legacy_provider_hints(self):
        for code in ('ACA150', 'AC150', 'AC 150'):
            self.assertEqual(airline_for({'callsign': code}), 'aircanada')
        for code in ('WJA123', 'WEN321', 'WS123', 'WR321'):
            self.assertEqual(airline_for({'callsign': code}), 'westjet')
        for code in ('UAL123', 'UA123', 'UA 123'):
            self.assertEqual(airline_for({'callsign': code}), 'united')
        for code in ('DAL123', 'DL123', 'DL 123'):
            self.assertEqual(airline_for({'callsign': code}), 'delta')
        for code in ('AAL123', 'AA123', 'AA 123'):
            self.assertEqual(airline_for({'callsign': code}), 'american')
        for code in ('FLE804', 'F8804', 'F8 804'):
            self.assertEqual(airline_for({'callsign': code}), 'flair')
        for code in ('ASP836', 'asp 836'):
            self.assertEqual(airline_for({'callsign': code}), 'airsprint')
        self.assertEqual(airline_for({'callsign': 'XYZ123', 'icon': 'delta'}), 'delta')
        self.assertEqual(airline_for({'callsign': 'AC150', 'icao': 'ACA150'}), 'aircanada')
        self.assertEqual(airline_for({'callsign': 'XYZ123', 'icon': 'maple'}), 'aircanada')
        for code in ('ACME12', 'WSH12', 'UALPHA12', 'UAV123', 'DLAB123', 'AALPHA12', 'FLEX12', 'ASPIRE12', 'CGABC', '', None):
            self.assertIsNone(airline_for({'callsign': code}))

    def test_art_is_large_source_derived_and_valid(self):
        root = Path(__file__).parent / 'tools' / 'logo-sources'
        self.assertEqual(set(AIRLINES),set(LOGOS))
        for name in AIRLINES:
            logo = LOGOS[name]
            self.assertEqual(logo['source_sha256'], hashlib.sha256((root / f'{name}.png').read_bytes()).hexdigest())
            wide=logo.get('placement')=='wide'
            self.assertTrue(16 <= len(logo['rows']) <= 18 if wide else 18 <= len(logo['rows']) <= 22)
            self.assertTrue(all(len(row)==len(logo['rows'][0]) for row in logo['rows']))
            self.assertTrue(40 <= len(logo['rows'][0]) <= 64 if wide else len(logo['rows'][0])==22)
            self.assertTrue(all(c == '.' or int(c, 16) < len(logo['palette'])
                                for row in logo['rows'] for c in row))
            self.assertGreater(len(logo['palette']), 1)
        self.assertEqual(len(LOGOS['aircanada']['rows']), 22)
        self.assertEqual(LOGOS['aircanada']['rows'][0][0], '.')
        self.assertTrue(all(int(c[3:5], 16) < 100 and int(c[5:7], 16) < 100
                            for c in LOGOS['aircanada']['palette']))
        self.assertNotEqual(LOGOS['westjet']['rows'], LOGOS['aircanada']['rows'])
        # United's blue background is intentional; its globe should stay white.
        united = LOGOS['united']
        self.assertTrue(any(min(int(c[i:i+2], 16) for i in (1, 3, 5)) > 220 for c in united['palette']))
        self.assertTrue(any(int(c[5:7], 16) > 120 and int(c[1:3], 16) < 80 for c in united['palette']))
        self.assertNotEqual(united['rows'][0][0], '.')
        delta = LOGOS['delta']
        self.assertEqual(delta['rows'][0][0], '.')
        self.assertTrue(any(int(c[1:3], 16) > 180 and int(c[3:5], 16) < 70 for c in delta['palette']))
        self.assertTrue(any(80 < int(c[1:3], 16) < 180 and int(c[3:5], 16) < 70 for c in delta['palette']))
        american = LOGOS['american']
        rgb = [tuple(int(c[i:i+2], 16) for i in (1, 3, 5)) for c in american['palette']]
        self.assertTrue(any(r > b + 60 for r, g, b in rgb))
        self.assertTrue(any(b > r + 50 for r, g, b in rgb))
        self.assertTrue(any(min(c) > 100 and max(c) - min(c) < 55 for c in rgb))
        self.assertGreater(sum(row.count('.') for row in american['rows']), 100)
        self.assertEqual(american['rows'][0][-1], '.')
        flair=LOGOS['flair']
        self.assertTrue(any(int(c[3:5],16)>200 and int(c[5:7],16)<180 for c in flair['palette']))
        self.assertTrue(any(max(int(c[i:i+2],16) for i in (1,3,5))<60 for c in flair['palette']))
        self.assertEqual(LOGOS['airsprint']['placement'],'wide')
        self.assertGreater(sum(row.count('.') for row in LOGOS['airsprint']['rows']),100)

    def test_nearby_and_follow_preserve_data_beside_logo(self):
        for callsign in ('ACA150', 'WJA123', 'UAL123', 'DAL123', 'AAL123', 'FLE804', 'ASP836', 'CGABC'):
            for mode in ('nearby', 'follow'):
                ctx = blocks.sample_context()
                plane = {'callsign': callsign, 'route': 'YYC>YVR', 'distance_nm': 3.2,
                         'altitude_ft': 12000, 'origin': 'YYC', 'destination': 'YVR',
                         'progress': .62, 'remaining_min': 72}
                ctx.data['aircraft'].update(nearby=[plane], tracked=plane)
                screen = copy.deepcopy(catalog.BUILTINS['sky-nearby'])
                screen['slots'][0]['options'].update(source=mode, callsign=callsign)
                layers = blocks.render_screen(screen, ctx, strict=True)
                logo = rasterize([layers[0]])
                wide=callsign.startswith('ASP')
                self.assertTrue(any(any(p) for p in logo))
                self.assertTrue(all(p == BLACK for i, p in enumerate(logo)
                                    if (i // 64 >= 18 if wide else i % 64 >= 22 or i // 64 >= 22)))
                texts = [l for l in layers if l['t'] == 'text']
                self.assertEqual(texts[0]['s'][0], callsign)
                self.assertEqual(texts[1]['s'][0], 'YYC>YVR')
                self.assertIn('72M LEFT' if mode == 'follow' else '3.2NM 12K', texts[2]['s'])
                self.assertTrue(all(l['y']>=19 for l in texts[:2]) if wide else all(l['x']>=24 for l in texts[:2]))
                frame = blocks.frame(screen, ctx)
                self.assertEqual(len(frame), 2048)
                self.assertTrue(any(any(p) for p in frame[27 * 64:]))


if __name__ == '__main__':
    unittest.main()
