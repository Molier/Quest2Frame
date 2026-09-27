# SPDX-License-Identifier: GPL-3.0-only
import unittest
from unittest.mock import patch
import tkinter as tk
import tempfile
import json
from pathlib import Path
from app import Wizard

class ArtworkUITests(unittest.TestCase):
    def setUp(self):
        try:self.app=Wizard()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.app.withdraw()
        self.app.vars['title'].set('Example Game')
        self.app.run_job=lambda title,fn,done:done(fn())

    def tearDown(self):
        if hasattr(self,'app'):
            for ident in self.app.tk.call('after','info'):self.app.after_cancel(ident)
            self.app.destroy()

    def test_selection_requires_confirmation(self):
        self.app.vars['steam_id'].set('999')
        with patch('app.artwork_candidates',return_value=[{'id':'123','title':'Example Game','score':1}]):
            self.app.search_artwork()
        self.assertEqual(self.app.vars['steam_id'].get(),'999')
        self.app.art_matches.current(0);self.app.choose_artwork()
        self.assertEqual(self.app.vars['steam_id'].get(),'123')

    def test_network_failure_preserves_manual_id(self):
        self.app.vars['steam_id'].set('999')
        with patch('app.artwork_candidates',side_effect=TimeoutError('timeout')):
            self.app.search_artwork()
        self.assertEqual(self.app.vars['steam_id'].get(),'999')
        self.assertIn('unavailable',self.app.art_matches.get())

    def test_stale_search_discarded(self):
        def search(title):
            self.app.vars['title'].set('Different Game')
            return [{'id':'123','title':'Example Game','score':1}]
        with patch('app.artwork_candidates',side_effect=search):self.app.search_artwork()
        self.assertEqual(self.app.art_candidates,[])
        self.assertEqual(self.app.vars['steam_id'].get(),'')

    def test_batch_settings_and_queue_reload(self):
        from batch import BatchWindow
        with tempfile.TemporaryDirectory() as tmp, patch('batch.ROOT',Path(tmp)):
            batch=BatchWindow(self.app,['com.test.one','com.test.two'],'quest')
            batch.tree.selection_set('0');batch.tree.focus('0');batch.selected()
            batch.values['scale'].set('75');batch.values['steam_id'].set('123');batch.save_editor()
            batch.tree.selection_set('1');batch.tree.focus('1');batch.selected()
            self.assertEqual(batch.values['scale'].get(),'100.0')
            batch.values['scale'].set('125');batch.save_editor()
            path=batch.path;batch.close()
            saved=json.loads(path.read_text())
            self.assertNotIn('password',saved)
            reopened=BatchWindow(self.app,path=path)
            self.assertEqual([i['options']['scale'] for i in reopened.items],[75,125])
            self.assertEqual(reopened.items[0]['options']['steam_id'],'123')
            reopened.close()
