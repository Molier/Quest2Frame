# SPDX-License-Identifier: GPL-3.0-only
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
import json
import core
from core import options, config_text, package_name, normalized, atomic_text, Engine

class CoreTests(unittest.TestCase):
    def test_scale_bounds(self):
        for scale in (49,201,float('nan'),float('inf')):
            with self.assertRaises(ValueError):options({'scale':scale})
        self.assertIn('scale=0.750',config_text(options({'scale':75})))
    def test_package_validation(self):
        for value in ('../data','com.game;id','com/game','x',None):
            with self.assertRaises(ValueError):package_name(value)
        self.assertEqual(package_name('com.example.Game'),'com.example.Game')
    def test_options_no_coercion(self):
        for data in ({'controllers':'false'},{'steam_id':'1;id'},{'title':'hi\0there'}):
            with self.assertRaises(ValueError):options(data)
    def test_title_match(self):self.assertEqual(normalized('SUPERHOT VR'),'superhot')
    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'nested/config';atomic_text(path,'one');atomic_text(path,'two')
            self.assertEqual(path.read_text(),'two');self.assertEqual(len(list(path.parent.iterdir())),1)
    def test_scan_quest_only(self):
        with tempfile.TemporaryDirectory() as d,patch.object(core,'DATA',Path(d)),patch.object(core,'INSTALLS',Path(d)/'installs'):
            engine=Engine()
            with patch.object(engine,'adb',return_value='List of devices attached\nQ device\nL device\n'),patch.object(engine,'shell',side_effect=['Quest 3','Meta','Lepton','Lineage','package:com.game.one\n']):
                self.assertEqual(engine.scan()[0]['package'],'com.game.one')
                self.assertEqual(engine.state['selected_device'],'Q')
    def test_unauthorized(self):
        with tempfile.TemporaryDirectory() as d,patch.object(core,'DATA',Path(d)),patch.object(core,'INSTALLS',Path(d)/'installs'):
            engine=Engine()
            with patch.object(engine,'adb',return_value='List of devices attached\nQ unauthorized\n'):
                self.assertEqual(engine.scan(),[]);self.assertIn('Allow USB debugging',engine.state['message'])
    def test_transfer_requires_scan(self):
        with tempfile.TemporaryDirectory() as d,patch.object(core,'DATA',Path(d)),patch.object(core,'INSTALLS',Path(d)/'installs'):
            with self.assertRaises(ValueError):Engine().transfer('Q','com.game.one',{})
    def test_no_split_transfer(self):
        with tempfile.TemporaryDirectory() as d,patch.object(core,'DATA',Path(d)),patch.object(core,'INSTALLS',Path(d)/'installs'):
            engine=Engine();engine.update(selected_device='Q',packages=[{'package':'com.game.one'}])
            with patch.object(engine,'shell',return_value='package:/a/base.apk\npackage:/a/split.apk'),patch.object(engine,'adb') as adb:
                with self.assertRaisesRegex(ValueError,'Split APK'):engine.transfer('Q','com.game.one',{})
                adb.assert_not_called()
    def test_existing_windows_install_discovered(self):
        with tempfile.TemporaryDirectory() as d,patch.object(core,'DATA',Path(d)),patch.object(core,'INSTALLS',Path(d)/'installs'):
            folder=core.INSTALLS/'com.example.game';folder.mkdir(parents=True)
            (folder/'deployment.json').write_text(json.dumps({'package':'com.example.game','appid':123}))
            (folder/'settings.conf').write_text('scale=0.75\ncontroller_fix=0\nfoveation_fix=1\n')
            installed=Engine().state['installed'][0]
            self.assertEqual(installed['options']['scale'],75);self.assertFalse(installed['options']['controllers'])

if __name__=='__main__':unittest.main()
