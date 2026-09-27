# SPDX-License-Identifier: GPL-3.0-only
"""Loopback-only UI server with per-session capability and strict request checks."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import hmac
import json
import mimetypes
import os
import secrets
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from core import APP, DATA, INSTALLS, Engine, options, package_name

engine = Engine()
TOKEN = secrets.token_urlsafe(32)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # Never write capability URLs into logs.

    def send(self, code, content, content_type='application/json'):
        if isinstance(content, (dict,list)): content=json.dumps(content).encode()
        elif isinstance(content,str): content=content.encode()
        self.send_response(code)
        self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(content)

    def authorized(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected: return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + expected: return False
        return hmac.compare_digest(self.headers.get('X-Quest2Frame-Token',''),TOKEN)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}': return self.send(403,{'error':'Invalid host'})
        if path == '/api/state':
            if not self.authorized(): return self.send(403,{'error':'Unauthorized'})
            return self.send(200,engine.snapshot())
        if path.startswith('/art/'):
            try:
                _,_,package,kind = path.split('/')
                package_name(package)
                name = {'portrait':'library_600x900.jpg','landscape':'header.jpg','hero':'library_hero.jpg','logo':'logo.png'}[kind]
                file = INSTALLS/package/'artwork'/name
                return self.send(200,file.read_bytes(),mimetypes.guess_type(name)[0])
            except (ValueError,KeyError,OSError): return self.send(404,b'')
        allowed={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/icon.svg':'icon.svg'}
        if path not in allowed:return self.send(404,{'error':'Not found'})
        file=APP/'static'/allowed[path]
        self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'text/plain')

    def do_POST(self):
        if not self.authorized():return self.send(403,{'error':'Unauthorized'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 16384:raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(size)); path=urllib.parse.urlsplit(self.path).path
            if not isinstance(body,dict):raise ValueError('Object required')
            if path=='/api/setup':engine.start('setup',engine.setup)
            elif path=='/api/scan':engine.start('scan',lambda:engine.scan(str(body.get('serial',''))))
            elif path=='/api/transfer':
                package=package_name(body['package']);opts=options(body);serial=str(body['serial'])
                engine.start('backup',lambda:engine.transfer(serial,package,opts))
            elif path=='/api/settings':
                package=package_name(body['package']);opts=options(body)
                engine.start('settings',lambda:engine.settings(package,opts))
            elif path=='/api/artwork/search':
                title=str(body['title'])[:150];engine.start('artwork',lambda:engine.search_art(title))
            elif path=='/api/artwork/repair':
                package=package_name(body['package']);opts=options(body)
                engine.start('artwork',lambda:engine.repair_art(package,opts))
            elif path=='/api/resume':
                package=package_name(body['package']);engine.start('install',lambda:engine.resume(package))
            elif path=='/api/sync':
                if engine.state['busy']:raise ValueError('Wait for the current operation to finish.')
                if body.get('confirm') is not True:raise ValueError('Steam restart confirmation required')
                subprocess.run(['systemd-run','--user','--collect','--unit=quest2frame-sync-'+str(int(time.time())),
                                '/usr/bin/python3',str(APP/'steam_sync.py')],check=True,capture_output=True)
            else:return self.send(404,{'error':'Unknown action'})
            self.send(202,{'ok':True})
        except (ValueError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:self.send(400,{'error':str(exc)})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    # Only one mutating app process, including one launched outside Steam.
    if os.name=='posix':
        import fcntl
        lock=(DATA/'app.lock').open('w')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('quest2frame is already running. Return to its open window.')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    url=f'http://127.0.0.1:{server.server_port}/#'+TOKEN
    # Owner-readable file is used only by local launch/test tools; never committed.
    session=DATA/'session.json';session.write_text(json.dumps({'url':url,'port':server.server_port}));session.chmod(0o600)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        if args.no_browser:thread.join()
        else:
            profile=Path.home()/'.var/app/com.google.Chrome/config/quest2frame'
            process=subprocess.Popen(['flatpak','run','com.google.Chrome','--user-data-dir='+str(profile),
                                      '--no-first-run','--no-default-browser-check','--window-size=1440,1000','--app='+url])
            process.wait()
            # A transfer must survive accidental closing of the browser window.
            if engine.thread and engine.thread.is_alive():engine.thread.join()
    finally:server.shutdown();session.unlink(missing_ok=True)

if __name__=='__main__':main()
