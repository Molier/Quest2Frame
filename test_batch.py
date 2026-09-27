# SPDX-License-Identifier: GPL-3.0-only
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from batch import run_batch

def item(package):
    return dict(package=package,options=dict(title='',scale=100,steam_id='',controllers=True,foveation=True),status='Queued',error='',backup='',build='')

class BatchTests(unittest.TestCase):
    def test_partial_failure_continues_and_saved_backup_is_reused(self):
        items=[item('com.test.one'),item('com.test.two')];bridge=MagicMock();save=MagicMock()
        bridge.backup.side_effect=['backup-one','backup-two']
        bridge.convert.side_effect=[RuntimeError('bad APK'),'build-two']
        run_batch(items,'convert',bridge,'quest',{},False,save)
        self.assertEqual([i['status'] for i in items],['Failed','Ready'])
        self.assertEqual(items[0]['backup'],'backup-one')
        bridge.backup.reset_mock();bridge.convert.side_effect=None;bridge.convert.return_value='build-one'
        run_batch(items,'convert',bridge,'quest',{},False,save)
        bridge.backup.assert_not_called()
        self.assertEqual([i['build'] for i in items],['build-one','build-two'])
        self.assertGreater(save.call_count,4)

    def test_install_uses_distinct_options_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            items=[item('com.test.one'),item('com.test.two')]
            for index,entry in enumerate(items):
                folder=Path(tmp)/str(index);folder.mkdir();entry['build']=str(folder)
                (folder/'game.json').write_text(json.dumps({'package':entry['package'],'title':'APK title'}))
                entry['options']['scale']=75+index*50
                entry['options']['steam_id']=str(100+index)
            bridge=MagicMock();bridge.install.side_effect=[RuntimeError('connection lost'),('remote',1)]
            run_batch(items,'install',bridge,None,{'host':'frame'},True,lambda:None)
            self.assertEqual([i['status'] for i in items],['Failed','Installed'])
            self.assertEqual([c.args[3] for c in bridge.install.call_args_list],['100','101'])
            for index,entry in enumerate(items):
                game=json.loads((Path(entry['build'])/'game.json').read_text())
                self.assertEqual(game['scale'],75+index*50)
                self.assertEqual(game['title'],'APK title')

    def test_package_mismatch_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry=item('com.test.one');entry['build']=tmp
            (Path(tmp)/'game.json').write_text(json.dumps({'package':'com.test.other'}))
            bridge=MagicMock();run_batch([entry],'install',bridge,None,{},False,lambda:None)
            bridge.install.assert_not_called();self.assertEqual(entry['status'],'Failed')

    def test_artwork_failure_does_not_fail_conversion(self):
        bridge=MagicMock();bridge.backup.return_value='backup'
        with tempfile.TemporaryDirectory() as tmp:
            bridge.convert.return_value=tmp
            (Path(tmp)/'game.json').write_text(json.dumps({'title':'Test'}))
            entry=item('com.test.one')
            with patch('batch.artwork_candidates',side_effect=TimeoutError()):
                run_batch([entry],'convert',bridge,'quest',{},False,lambda:None,True)
            self.assertEqual(entry['status'],'Ready')
