# SPDX-License-Identifier: GPL-3.0-only
import unittest
from unittest.mock import patch
import tkinter as tk
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
