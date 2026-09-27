# SPDX-License-Identifier: GPL-3.0-only
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from bridge import Bridge
import test_app


class ProgressTests(unittest.TestCase):
    def test_wifi_byte_progress_and_completion(self):
        events=[];b=Bridge(lambda _:None,lambda *event:events.append(event))
        client=MagicMock()
        def put(local,remote,callback):
            callback(512,1024);callback(1024,1024)
        client.open_sftp.return_value.__enter__.return_value.put.side_effect=put
        b.transfer_file(client,Path('game.apk'),'/remote/game.apk','wifi')
        self.assertTrue(any(percent==50 for _,percent in events))
        self.assertEqual(events[-1],('Installing: game.apk',100))

    def test_failed_transfer_never_reports_complete(self):
        events=[];b=Bridge(lambda _:None,lambda *event:events.append(event))
        client=MagicMock()
        client.open_sftp.return_value.__enter__.return_value.put.side_effect=OSError('offline')
        with self.assertRaises(OSError):b.transfer_file(client,Path('game.apk'),'/remote/game.apk','wifi')
        self.assertFalse(any(percent==100 for _,percent in events))

    def test_adb_reported_percent(self):
        events=[];b=Bridge(lambda _:None,lambda *event:events.append(event))
        b.progress('Backup: APK')
        process=MagicMock(stdout=io.StringIO('[ 25%] file.apk\n[100%] file.apk\n'),returncode=0)
        with patch('bridge.subprocess.Popen',return_value=process):b.adb_run('quest','pull','file.apk','local.apk')
        self.assertEqual(events[-2:],[('Backup: APK',25),('Backup: APK',100)])

    def test_batch_context(self):
        events=[];b=Bridge(lambda _:None,lambda *event:events.append(event))
        b.progress_prefix='Game 2/3: '
        b.progress('Signing')
        self.assertEqual(events,[('Game 2/3: Signing',None)])


class ProgressUITests(unittest.TestCase):
    setUp=test_app.ArtworkUITests.setUp
    tearDown=test_app.ArtworkUITests.tearDown

    def test_modes_and_percent(self):
        self.app.show_progress('Signing',None)
        self.assertEqual(str(self.app.progress['mode']),'indeterminate')
        self.app.show_progress('Uploading',42)
        self.assertEqual(str(self.app.progress['mode']),'determinate')
        self.assertEqual(self.app.progress_value.get(),42)
        self.assertIn('42% of this stage',self.app.progress_text.get())

    def test_worker_events_and_failure(self):
        self.app.events.put(('progress',('Uploading',60)))
        self.app.drain()
        self.assertEqual(self.app.progress_value.get(),60)
        self.app.events.put(('error','Disconnected'))
        with patch('app.messagebox.showerror'):self.app.drain()
        self.assertEqual(self.app.progress_value.get(),0)
        self.assertFalse(self.app.busy)
        self.assertIn('failed',self.app.progress_text.get())
