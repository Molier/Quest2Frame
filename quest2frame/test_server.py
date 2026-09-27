# SPDX-License-Identifier: GPL-3.0-only
import json
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import server

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.thread.join()
    def request(self,path,body=None,token=True,origin=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Quest2Frame-Token']=server.TOKEN
        if origin:headers['Origin']=origin
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,e.read()
    def test_auth_required(self):self.assertEqual(self.request('/api/state',token=False)[0],403)
    def test_state_authorized(self):self.assertEqual(self.request('/api/state')[0],200)
    def test_origin_rejected(self):self.assertEqual(self.request('/api/setup',{},origin='https://evil.example')[0],403)
    def test_steam_restart_requires_confirmation(self):
        with patch('server.subprocess.run') as run:
            self.assertEqual(self.request('/api/sync',{'confirm':False})[0],400);run.assert_not_called()
    def test_invalid_scale_rejected_before_job(self):
        with patch.object(server.engine,'start') as start:
            self.assertEqual(self.request('/api/settings',{'package':'com.example.game','scale':201})[0],400);start.assert_not_called()
    def test_file_paths_not_exposed(self):self.assertEqual(self.request('/../../LICENSE')[0],404)
    def test_unknown_actions_rejected(self):self.assertEqual(self.request('/api/shell',{'command':'id'})[0],404)

if __name__=='__main__':unittest.main()
