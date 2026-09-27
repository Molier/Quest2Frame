# SPDX-License-Identifier: GPL-3.0-only
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from bridge import Bridge, digest, launcher_text
from storage import select_storage, card_launcher

class StorageTests(unittest.TestCase):
    def test_uuid_selection_ignores_label_and_mount_name(self):
        entry={'id':'uuid:abcd','uuid':'abcd','mount':'/run/media/user/New Card Name'}
        self.assertEqual(select_storage([entry],'uuid:abcd')['mount'],entry['mount'])
        with self.assertRaises(RuntimeError):select_storage([{'id':'internal'}],'uuid:abcd')
    def test_launcher_resolves_uuid_and_keeps_internal_compatible(self):
        script=launcher_text('/old/name/com.test.game',42,'/home/user/Lepton',card_launcher('abcd','com.test.game'))
        self.assertIn('UUID=abcd',script);self.assertIn('mountpoint -q',script)
        self.assertIn('"$storage_mount"/Applications/quest-frame/com.test.game',script)
        self.assertNotIn('@STORAGE_SETUP@',script)
        self.assertNotIn('storage_mount',launcher_text('/home/user/game',42,'/Lepton'))
    def test_settings_resolve_current_mount(self):
        b=Bridge(lambda _:None)
        with patch.object(b,'storage_locations',return_value=[dict(id='uuid:abc',mount='/new label')]):
            self.assertEqual(b.deployment_base(None,dict(storage_uuid='abc',package='com.test.game',remote='/old')),
                             '/new label/Applications/quest-frame/com.test.game')
    def exercise_install(self,storage_id='uuid:abc',old=None,free=10**12):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'game.apk').write_bytes(b'test apk')
            backup=folder/'backup';backup.mkdir()
            game=dict(package='com.test.game',backup=str(backup),title='Test',scale=100,controllers=True,foveation=True,steam_id='',sha256=digest(folder/'game.apk'))
            (folder/'game.json').write_text(json.dumps(game))
            b=Bridge(lambda _:None);commands=[];writes={}
            def remote(client,command,check=True):
                commands.append(command)
                if command=='printf %s "$HOME"':return '/home/tester'
                if command=='cat /etc/machine-id':return 'machine'
                if command.startswith('cat ') and command.endswith('/deployment.json'):return json.dumps(old) if old else ''
                if command.startswith('sha256sum '):return game['sha256']+' game.apk'
                return ''
            choices=[dict(id='internal',uuid='',mount='/home/tester',free=free),
                     dict(id='uuid:abc',uuid='abc',mount='/run/media/tester/Any Card',free=free)]
            with patch.object(b,'storage_locations',return_value=choices),patch.object(b,'devices',return_value=['frame']),patch.object(b,'shell',return_value='machine'),patch.object(b,'remote',side_effect=remote),patch.object(b,'adb_run') as adb,patch.object(b,'put_text',side_effect=lambda c,p,t:writes.update({p:t})),patch.object(b,'add_shortcut') as shortcut:
                result=b.install(folder,None,True,None,storage_id)
                deployment=json.loads((folder/'deployment.json').read_text())
                return result,deployment,commands,writes,adb.call_args_list,shortcut.call_args
    def test_sd_install_data_on_card_launcher_internal(self):
        result,deployment,commands,writes,pushes,shortcut=self.exercise_install()
        self.assertEqual(result[0],'/run/media/tester/Any Card/Applications/quest-frame/com.test.game')
        self.assertEqual(deployment['storage_uuid'],'abc')
        self.assertIn('/home/tester/Applications/quest-frame/com.test.game/launch.sh',writes)
        self.assertIn('/run/media/tester/Any Card/',str(pushes[0]))
        self.assertEqual(shortcut.args[1],'/home/tester/Applications/quest-frame/com.test.game')
    def test_existing_game_cannot_silently_move(self):
        with self.assertRaisesRegex(RuntimeError,'different storage'):
            self.exercise_install(old={'appid':123,'package':'com.test.game'})
    def test_selected_storage_space_checked(self):
        with self.assertRaisesRegex(RuntimeError,'selected storage'):self.exercise_install(free=1)
    def test_internal_paths_unchanged(self):
        result,deployment,*_=self.exercise_install(storage_id='internal')
        self.assertEqual(result[0],'/home/tester/Applications/quest-frame/com.test.game')
        self.assertEqual(deployment['storage_uuid'],'')
