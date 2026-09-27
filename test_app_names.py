# SPDX-License-Identifier: GPL-3.0-only
import unittest
from pathlib import Path
from unittest.mock import patch
from bridge import Bridge
import test_app


class NameLookupTests(unittest.TestCase):
    def test_names_sorted_and_unknown_package_retained(self):
        b=Bridge(lambda _:None)
        with patch.object(b,'packages',return_value=['com.z.game','com.a.game']), \
             patch.object(b,'label_helper',return_value=Path('classes.dex')),patch.object(b,'adb_run'), \
             patch.object(b,'shell',return_value='noise\nQ2F_LABELS={"com.z.game":"A Friendly Name"}') as shell:
            self.assertEqual(b.installed_apps('quest'),[
                dict(package='com.z.game',title='A Friendly Name'),dict(package='com.a.game',title='com.a.game')])
            self.assertEqual(shell.call_args.args[1:3],('rm','-f'))

    def test_lookup_failure_falls_back_without_losing_apps(self):
        b=Bridge(lambda _:None)
        with patch.object(b,'packages',return_value=['com.test.game']), \
             patch.object(b,'label_helper',side_effect=RuntimeError('SDK missing')),patch.object(b,'shell'):
            self.assertEqual(b.installed_apps('quest'),[dict(package='com.test.game',title='com.test.game')])


class NameUITests(unittest.TestCase):
    setUp=test_app.ArtworkUITests.setUp
    tearDown=test_app.ArtworkUITests.tearDown

    def test_filter_and_selection_keep_real_package(self):
        self.app.auto_art.set(False)
        self.app.package_list=['com.one.game','com.two.game']
        self.app.package_names={'com.one.game':'Same Name','com.two.game':'Same Name'}
        self.app.vars['filter'].set('two')
        self.assertEqual(self.app.listbox.size(),1)
        self.app.listbox.selection_set(0);self.app.select_game()
        self.assertEqual(self.app.package,'com.two.game')
        self.assertEqual(self.app.vars['title'].get(),'Same Name')
        self.app.vars['filter'].set('same name')
        self.assertEqual(self.app.listbox.size(),2)

    def test_multi_select_passes_package_ids(self):
        self.app.package_list=['com.one.game','com.two.game']
        self.app.package_names={'com.one.game':'One','com.two.game':'Two'}
        self.app.filter_packages();self.app.listbox.selection_set(0,'end')
        with patch.object(self.app,'show_batch') as show:
            self.app.select_game()
            show.assert_called_once_with(['com.one.game','com.two.game'])
