# SPDX-License-Identifier: GPL-3.0-only
import unittest
from pathlib import Path
from unittest.mock import patch
from bridge import Bridge, settings_text, valid_package
from steam_shortcuts import decode, encode, upsert
from bridge import artwork_candidates, artwork_query, suggested_title
import io
import json

class Tests(unittest.TestCase):
    def test_artwork_rank_and_validate(self):
        payload={'items':[{'id':2,'name':'Example Game Deluxe DLC'},
                          {'id':1,'name':'Example Game'}, {'id':1,'name':'Duplicate'},
                          {'id':'bad','name':'Invalid'}, {'id':3,'name':None}]}
        with patch('bridge.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            matches=artwork_candidates('Example Game (Quest)')
            self.assertEqual([x['id'] for x in matches],['1','2'])
            self.assertIn('term=Example+Game',request.call_args.args[0].full_url)
            self.assertEqual(request.call_args.kwargs['timeout'],15)
    def test_artwork_empty_query(self):
        with patch('bridge.urllib.request.urlopen') as request:
            self.assertEqual(artwork_candidates('  '),[]);request.assert_not_called()
    def test_artwork_query_and_package_hint(self):
        self.assertEqual(artwork_query('Tetris Effect (Quest)'),'Tetris Effect')
        self.assertEqual(suggested_title('com.MightyCoconut.WalkaboutMiniGolf'),'Walkabout Mini Golf')
    def test_artwork_no_results(self):
        with patch('bridge.urllib.request.urlopen',return_value=io.BytesIO(b'{"items":[]}')):
            self.assertEqual(artwork_candidates('Unknown'),[])
    def test_settings(self):
        self.assertIn('scale=0.750',settings_text(75))
        for value in (0,49,201,float('nan')):
            with self.assertRaises(ValueError):settings_text(value)
    def test_package(self):
        self.assertEqual(valid_package('com.example.game'),'com.example.game')
        for value in ('../oops','com.game; id','game','com.game/else'):
            with self.assertRaises(ValueError):valid_package(value)
    def test_vdf_roundtrip(self):
        value={'shortcuts':{'0':{'appid':0xFFFFFFFF,'appname':'Quest → Frame','tags':{'0':'VR'}}}}
        self.assertEqual(decode(encode(value)),value)
    def test_preserves_existing(self):
        original={'shortcuts':{'0':{'appid':12,'appname':'Existing','Exe':'"/a"','unknown':'retained'}}}
        changed,ident=upsert(encode(original),'"/b"','New','/dir')
        parsed=decode(changed)
        self.assertEqual(parsed['shortcuts']['0'],original['shortcuts']['0'])
        changed2,ident2=upsert(changed,'"/b"','Renamed','/dir')
        self.assertEqual(ident,ident2);self.assertEqual(len(decode(changed2)['shortcuts']),2)
    def test_reject_unknown_type(self):
        with self.assertRaises(ValueError):decode(b'\x05key\0value\0\x08')
    def test_real_shortcuts(self):
        path=Path(__file__).resolve().parent/'tools/frame-shortcuts-original.vdf'
        if not path.exists():self.skipTest('No local Steam fixture')
        value=decode(path.read_bytes());self.assertEqual(decode(encode(value)),value)
    def test_quest_detection_excludes_lepton_and_host(self):
        bridge=Bridge(lambda _:None)
        models={'quest':'Quest 3','frame':'/bin/sh: getprop: not found','localhost:5555':'Lepton'}
        def shell(serial,*args,**kwargs):
            return models[serial] if args[-1]=='ro.product.model' else 'unknown'
        with patch.object(bridge,'devices',return_value=list(models)),patch.object(bridge,'shell',side_effect=shell):
            self.assertEqual(bridge.quests(),[('quest','Quest 3')])
    def test_split_apk_rejected_before_copy(self):
        bridge=Bridge(lambda _:None)
        with patch.object(bridge,'shell',return_value='package:/data/base.apk\npackage:/data/split.apk'),patch.object(bridge,'adb_run') as transfer:
            with self.assertRaisesRegex(RuntimeError,'split APKs'):bridge.backup('quest','com.example.game')
            transfer.assert_not_called()
    def test_package_listing_filters_noise(self):
        bridge=Bridge(lambda _:None)
        with patch.object(bridge,'shell',return_value='package:com.z.game\nnoise\npackage:com.a.game\n'):
            self.assertEqual(bridge.packages('quest'),['com.a.game','com.z.game'])
    def test_apk_signature_and_adapter(self):
        import zipfile,json
        builds=list((Path(__file__).resolve().parent/'games').glob('*/build-*/game.json'))
        if not builds:self.skipTest('No converted APK fixture')
        folder=builds[-1].parent
        with zipfile.ZipFile(folder/'game.apk') as apk:
            self.assertTrue(apk.read('lib/arm64-v8a/libopenxr_loader_generic.so').startswith(b'\x7fELF'))
            self.assertTrue(apk.read('lib/arm64-v8a/libopenxr_loader_original.so').startswith(b'\x7fELF'))
            self.assertIn(b'scale=',apk.read('lib/arm64-v8a/libframe_settings.so'))

if __name__=='__main__':unittest.main()
