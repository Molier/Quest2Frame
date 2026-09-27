# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from manage_remote import inspect_game, inventory, delete_game
from steam_shortcuts import upsert, remove, decode, encode

class UninstallTests(unittest.TestCase):
    def fixture(self,root,package='com.test.game'):
        base=Path(root)/'Applications/quest-frame'/package
        (base/'lepton-app').mkdir(parents=True)
        (base/'lepton-app/game.apk').write_bytes(b'test')
        (base/'lepton-data').mkdir();(base/'lepton-data/save').write_text('progress')
        (base/'deployment.json').write_text(json.dumps(dict(package=package,appid=123)))
        (base/'launch.sh').write_text('export STEAM_COMPAT_INSTALL_PATH="$app_dir/lepton-app"')
        return base
    def test_only_managed_directories_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(tmp)
            (Path(tmp)/'Applications/quest-frame/other').mkdir()
            self.assertEqual([g['package'] for g in inventory(tmp,[])],['com.test.game'])
    def test_preserves_saves_and_other_games(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=self.fixture(tmp);other=self.fixture(tmp,'com.test.other')
            expected=inspect_game(tmp,'com.test.game',[])
            with patch('manage_remote.subprocess.check_output',return_value=''):
                result=delete_game(tmp,'com.test.game',[],expected,True)
            self.assertFalse(base.exists());self.assertTrue(other.exists())
            self.assertEqual((Path(result['saves'])/'lepton-data/save').read_text(),'progress')
            self.assertFalse((Path(result['saves'])/'lepton-app').exists())
    def test_delete_saves_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=self.fixture(tmp);expected=inspect_game(tmp,'com.test.game',[])
            with patch('manage_remote.subprocess.check_output',return_value=''):
                result=delete_game(tmp,'com.test.game',[],expected,False)
            self.assertIsNone(result['saves']);self.assertFalse(base.exists())
    def test_reject_traversal_missing_marker_and_changed_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=self.fixture(tmp)
            with self.assertRaises(ValueError):inspect_game(tmp,'../outside',[])
            expected=inspect_game(tmp,'com.test.game',[]);expected['appid']=999
            with self.assertRaises(ValueError):delete_game(tmp,'com.test.game',[],expected,False)
            self.assertTrue(base.exists())
    def test_running_game_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=self.fixture(tmp);expected=inspect_game(tmp,'com.test.game',[])
            with patch('manage_remote.subprocess.check_output',return_value='lepton-steamlaunch-123\n'):
                with self.assertRaises(ValueError):delete_game(tmp,'com.test.game',[],expected,False)
            self.assertTrue(base.exists())
    def test_missing_card_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=self.fixture(tmp)
            (base/'deployment.json').write_text(json.dumps(dict(package='com.test.game',appid=123,storage_uuid='missing')))
            with self.assertRaisesRegex(ValueError,'unavailable'):inspect_game(tmp,'com.test.game',[])
            self.assertTrue(base.exists())
    def test_sd_uninstall_preserves_saves_on_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'home';card=Path(tmp)/'Renamed Card';home.mkdir();card.mkdir()
            anchor=self.fixture(home);base=self.fixture(card)
            (anchor/'deployment.json').write_text(json.dumps(dict(package='com.test.game',appid=123,storage_uuid='card-uuid')))
            mounts=[dict(uuid='card-uuid',mount=str(card))]
            def output(args,**kwargs):
                return json.dumps({'filesystems':[{'uuid':'card-uuid'}]}) if args[0]=='findmnt' else ''
            with patch('manage_remote.os.path.ismount',side_effect=lambda path:Path(path)==card),patch('manage_remote.subprocess.check_output',side_effect=output):
                expected=inspect_game(home,'com.test.game',mounts)
                result=delete_game(home,'com.test.game',mounts,expected,True)
            self.assertFalse(anchor.exists());self.assertFalse(base.exists())
            self.assertTrue(Path(result['saves']).is_relative_to(card))
    def test_vdf_removal_preserves_other_entries_and_unknown_fields(self):
        data,ident=upsert(b'','"/a/launch.sh"','A','/a')
        data,_=upsert(data,'"/b/launch.sh"','B','/b')
        tree=decode(data);tree['custom']='retained';data=encode(tree)
        result=decode(remove(data,'"/a/launch.sh"',ident))
        self.assertEqual(result['custom'],'retained')
        self.assertEqual([v['appname'] for v in result['shortcuts'].values()],['B'])
        with self.assertRaises(ValueError):remove(data,'"/wrong/launch.sh"',ident)
