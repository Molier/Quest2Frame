# SPDX-License-Identifier: GPL-3.0-only
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from bridge import Bridge, refresh_value, settings_text, check_refresh_adapter
import test_app


class RefreshTests(unittest.TestCase):
    def test_rates(self):
        for value in ('Default',0,72,80,90,120,144):
            self.assertIn('refresh_rate='+str(refresh_value(value)),settings_text(refresh_rate=value))
        for value in (-1,60,91,float('nan'),float('inf'),'90; reboot'):
            with self.assertRaises(ValueError): refresh_value(value)

    def test_old_build_default_and_explicit_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(Path(tmp)/'game.apk','w') as apk:
                apk.writestr('lib/arm64-v8a/libopenxr_loader_generic.so',b'old')
            check_refresh_adapter(tmp,0)
            with self.assertRaisesRegex(ValueError,'reconversion'):check_refresh_adapter(tmp,90)
            b=Bridge()
            with patch.object(b,'remote') as remote,patch.object(b,'put_text') as put:
                with self.assertRaises(ValueError):b.update_settings(tmp,None,100,True,True,90)
                remote.assert_not_called();put.assert_not_called()

    def test_update_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            with zipfile.ZipFile(folder/'game.apk','w') as apk:
                apk.writestr('lib/arm64-v8a/libopenxr_loader_generic.so',b'Q2F_REFRESH_RATE_V1')
            (folder/'game.json').write_text('{}')
            (folder/'deployment.json').write_text(json.dumps({'package':'com.example.game'}))
            b=Bridge(lambda _:None)
            with patch.object(b,'deployment_base',return_value='/safe/game'),patch.object(b,'put_text') as put:
                b.update_settings(folder,None,100,True,True,90)
                self.assertEqual(put.call_count,2)
                for call in put.call_args_list:self.assertIn('refresh_rate=90\n',call.args[2])
            self.assertEqual(json.loads((folder/'game.json').read_text())['refresh_rate'],90)


class RefreshUITests(unittest.TestCase):
    setUp=test_app.ArtworkUITests.setUp
    tearDown=test_app.ArtworkUITests.tearDown

    def test_ui_selection(self):
        self.assertEqual(self.app.options()['refresh_rate'],0)
        self.app.vars['refresh_rate'].set('90')
        self.assertEqual(self.app.options()['refresh_rate'],90)
