# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import zipfile

from bridge import Bridge, check_headset_build, check_rect_build, rect_fix_value, digest
from headset_profile import headset_value, patch_runtime, patch_unreal_smali, QUEST2_ID, QUEST3_ID
import test_app


class HeadsetTests(unittest.TestCase):
    def test_rect_setting_requires_rebuild_and_recognizes_legacy_fix(self):
        check_rect_build({})
        with self.assertRaisesRegex(ValueError,'Rebuild APK'):check_rect_build({},True)
        legacy={'compatibility_fix':'swapchain-rectangle-rounding'}
        self.assertTrue(rect_fix_value(legacy))
        check_rect_build(legacy,True)
        with self.assertRaises(ValueError):check_rect_build(legacy,False)
        check_rect_build({'rect_fix':True,'built_rect_fix':True})
    def test_profiles(self):
        for value in ('Default','Quest 2','Quest 3'): self.assertEqual(headset_value(value),value)
        for value in ('Quest 3S',None,'quest3'):
            with self.assertRaises(ValueError): headset_value(value)
        check_headset_build({})
        with self.assertRaisesRegex(ValueError,'Rebuild APK'): check_headset_build({},'Quest 3')

    def test_runtime_patches_only_identity_and_requires_hash(self):
        data=b'ELF'+QUEST2_ID+b'helloOculus Quest2\0end'
        with self.assertRaises(ValueError):patch_runtime(data,'Quest 3')
        with patch('headset_profile.OVR_HASH',hashlib.sha256(data).hexdigest()):
            result=patch_runtime(data,'Quest 3')
            self.assertEqual(len(result),len(data))
            self.assertIn(QUEST3_ID,result);self.assertIn(b'Meta Quest 3\0',result)
            self.assertEqual(patch_runtime(data,'Quest 2'),data)
        self.assertEqual(patch_runtime(data,'Default'),data)

    def test_unreal_model_constant(self):
        text='const-string v1, "Quest 2"\nconst-string/jumbo v2, "Quest 2"\nconst-string v0, "Quest 2 graphics"'
        result=patch_unreal_smali(text)
        self.assertEqual(result.count('"Quest 3"'),2)
        self.assertIn('"Quest 2 graphics"',result)

    def test_rebuild_preserves_other_libraries_and_obb_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'source';folder.mkdir()
            with zipfile.ZipFile(folder/'game.apk','w') as apk:
                apk.writestr('lib/arm64-v8a/libopenxr_loader.so',b'custom passthrough')
                apk.writestr('lib/arm64-v8a/libopenxr_loader_generic.so',b'Q2F_REFRESH_RATE_V1 custom fixes')
                apk.writestr('assets/game-data',b'keep me')
            manifest=dict(package='com.test.game',title='Test',backup='do-not-read-OBBs',sha256=digest(folder/'game.apk'))
            (folder/'game.json').write_text(json.dumps(manifest))
            b=Bridge(lambda _:None)
            def run(args):
                args=list(map(str,args))
                if 'zipalign.exe' in args[0]:Path(args[-1]).write_bytes(Path(args[-2]).read_bytes())
                if 'sign' in args:Path(args[args.index('--out')+1]).write_bytes(Path(args[-1]).read_bytes())
                return ''
            with patch('bridge.ROOT',root),patch.object(b,'toolchain',return_value=(root/'java',root/'jar',root,None)),patch.object(b,'run',side_effect=run):
                output=b.rebuild_apk(folder,'Test',125,True,True,'',90)
            game=json.loads((output/'game.json').read_text())
            self.assertEqual(game['backup'],'do-not-read-OBBs')
            self.assertEqual(game['refresh_rate'],90)
            self.assertEqual(game['identity_base_sha256'],manifest['sha256'])
            self.assertEqual(digest(folder/'game.apk'),manifest['sha256'])
            with zipfile.ZipFile(output/'game.apk') as apk:
                self.assertEqual(apk.read('lib/arm64-v8a/libopenxr_loader.so'),b'custom passthrough')
                self.assertIn(b'custom fixes',apk.read('lib/arm64-v8a/libopenxr_loader_generic.so'))
                self.assertIn(b'scale=1.250',apk.read('lib/arm64-v8a/libframe_settings.so'))

    def test_apk_only_install_never_transfers_obb_or_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'game.apk').write_bytes(b'apk')
            game=dict(package='com.test.game',sha256=digest(folder/'game.apk'),update_source_sha256='old',scale=100,controllers=True,foveation=True)
            deployment=dict(package=game['package'],appid=123,remote='/game',anchor='/game',storage_uuid='card-uuid')
            (folder/'game.json').write_text(json.dumps(game));(folder/'deployment.json').write_text(json.dumps(deployment))
            b=Bridge(lambda _:None); commands=[]
            def remote(client,cmd,check=True):
                commands.append(cmd)
                if cmd.startswith('cat '):return json.dumps(deployment)
                if cmd.startswith('sha256sum '):return (game['sha256'] if '.staging-' in cmd else 'old')+' file'
                return ''
            with patch.object(b,'deployment_base',return_value='/mounted-by-uuid/game'),patch.object(b,'remote',side_effect=remote),patch.object(b,'transfer_file') as transfer,patch.object(b,'put_text'):
                b.install_apk_only(folder,MagicMock())
            transfer.assert_called_once()
            self.assertEqual(transfer.call_args.args[1],folder/'game.apk')
            self.assertFalse(any('obb' in c or 'baked' in c for c in commands))
            self.assertTrue(any('previous-apk-' in c for c in commands))

    def test_installed_mismatch_stops_before_transfer(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'game.apk').write_bytes(b'apk')
            game=dict(package='com.test.game',sha256=digest(folder/'game.apk'),update_source_sha256='expected')
            deployment=dict(package=game['package'],appid=123,remote='/game',storage_uuid='')
            (folder/'game.json').write_text(json.dumps(game));(folder/'deployment.json').write_text(json.dumps(deployment))
            b=Bridge(lambda _:None)
            def remote(client,cmd,check=True):
                if cmd.startswith('cat '):return json.dumps(deployment)
                if cmd.startswith('sha256sum '):return 'different file'
                return ''
            with patch.object(b,'deployment_base',return_value='/game'),patch.object(b,'remote',side_effect=remote),patch.object(b,'transfer_file') as transfer:
                with self.assertRaisesRegex(ValueError,'differs'):b.install_apk_only(folder,MagicMock())
                transfer.assert_not_called()


class HeadsetUITests(unittest.TestCase):
    setUp=test_app.ArtworkUITests.setUp
    tearDown=test_app.ArtworkUITests.tearDown

    def test_selection(self):
        self.assertEqual(self.app.options()['headset'],'Default')
        self.app.vars['headset'].set('Quest 3')
        self.assertEqual(self.app.options()['headset'],'Quest 3')
        self.assertFalse(self.app.options()['rect_fix'])
        self.app.rect_fix.set(True)
        self.assertTrue(self.app.options()['rect_fix'])
