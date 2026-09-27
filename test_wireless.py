# SPDX-License-Identifier: GPL-3.0-only
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from bridge import Bridge, digest
from batch import run_batch


class WirelessTests(unittest.TestCase):
    def exercise(self, corrupt=False, transport='wifi'):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); backup=folder/'backup'
            (backup/'obb').mkdir(parents=True); (backup/'data/files').mkdir(parents=True)
            (folder/'game.apk').write_bytes(b'apk')
            (backup/'obb/main.obb').write_bytes(b'obb')
            (backup/'data/files/save.sav').write_bytes(b'old quest progress')
            (backup/'data/files/new.dat').write_bytes(b'new data')
            game=dict(package='com.test.game',backup=str(backup),title='Test',scale=125,
                      controllers=True,foveation=True,steam_id='',sha256=digest(folder/'game.apk'))
            (folder/'game.json').write_text(json.dumps(game))
            b=Bridge(lambda _:None); client=MagicMock(); uploaded={}; commands=[]
            client.open_sftp.return_value.__enter__.return_value.put.side_effect=lambda local,remote,**kwargs: uploaded.update({remote:Path(local)})
            def remote(c,cmd,check=True):
                commands.append(cmd)
                if cmd=='printf %s "$HOME"':return '/home/test'
                if cmd.startswith('if test -e ') and 'save.sav' in cmd:return 'EXISTS'
                if cmd.startswith('sha256sum '):
                    path=cmd[len('sha256sum '):].strip("'")
                    return ('bad' if corrupt else digest(uploaded[path]))+' file'
                return ''
            with patch.object(b,'devices',side_effect=AssertionError('Wi-Fi must not query ADB')), \
                 patch.object(b,'adb_run',side_effect=AssertionError('Wi-Fi must not use ADB')), \
                 patch.object(b,'remote',side_effect=remote),patch.object(b,'put_text'), \
                 patch.object(b,'storage_locations',return_value=[dict(id='internal',uuid='',mount='/home/test',free=10**12)]):
                if corrupt:
                    with self.assertRaisesRegex(RuntimeError,'verification failed'):
                        b.install(folder,client,False,transport=transport)
                    self.assertFalse(any('previous-app-' in c for c in commands))
                    self.assertFalse((folder/'deployment.json').exists())
                else:
                    b.install(folder,client,False,transport=transport)
                    self.assertTrue((folder/'deployment.json').exists())
            return uploaded

    def test_wifi_installs_without_adb_and_preserves_existing_saves(self):
        uploads=self.exercise()
        names=[p.name for p in uploads.values()]
        self.assertCountEqual(names,['game.apk','main.obb','new.dat'])

    def test_bad_transfer_does_not_replace_installed_app(self):self.exercise(corrupt=True)

    def test_invalid_transport_fails_before_accessing_files(self):
        with self.assertRaises(ValueError):Bridge().install('missing',None,transport='invalid')

    def test_usb_still_uses_adb(self):
        b=Bridge()
        with patch.object(b,'adb_run') as adb:
            b.transfer_file(None,Path('game.apk'),'/remote/game.apk','usb')
            adb.assert_called_once_with('frame','push','-Z',Path('game.apk'),'/remote/game.apk')

    def test_batch_passes_wireless_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'game.json').write_text(json.dumps(dict(package='com.test.game',title='Test')))
            entry=dict(package='com.test.game',build=tmp,options=dict(title='',steam_id=''))
            bridge=MagicMock()
            run_batch([entry],'install',bridge,None,{},False,lambda:None,transport='wifi')
            self.assertEqual(entry['status'],'Installed')
            self.assertEqual(bridge.install.call_args.args[-1],'wifi')
