# SPDX-License-Identifier: GPL-3.0-only
"""Detached Steam-library update worker; survives closing the app's Steam scope."""
from pathlib import Path
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import time
from core import APP, DATA, INSTALLS, SHARED, atomic_text, write_json
from steam_shortcuts import decode, encode, upsert, app_id

def command(args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=60)

def sync(register_app=False):
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / 'steam-library.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pending = list((DATA / 'pending').glob('*.json'))
        entries = [json.loads(p.read_text()) for p in pending]
        if register_app:
            exe = '"' + str(APP / 'launch.sh') + '"'
            entries.append({'exe':exe, 'title':'quest2frame', 'directory':str(APP), 'appid':app_id(exe,'quest2frame'),
                            'openvr':0, 'icon':str(APP/'static/icon.svg'), 'art':{}})
        if not entries: return
        userdata = Path.home() / '.local/share/Steam/userdata'
        users = [p for p in userdata.iterdir() if p.name.isdigit() and p.name != '0']
        if len(users) != 1: raise RuntimeError('Expected one Steam account. No library changes made.')
        config = users[0] / 'config'; path = config / 'shortcuts.vdf'; grid = config / 'grid'
        service = command(['systemctl','--user','is-active','steam.service'],False).returncode == 0
        write_json(DATA/'library-sync.json', {'status':'running','message':'Updating Steam library…'})
        try:
            if service: command(['systemctl','--user','stop','steam.service'])
            else: command(['steam','-shutdown'],False)
            for _ in range(40):
                if command(['pgrep','-x','steam'],False).returncode: break
                time.sleep(.5)
            else: raise RuntimeError('Steam did not close. Library not modified.')
            original = path.read_bytes() if path.exists() else b''
            updated = original
            for entry in entries:
                updated, ident = upsert(updated, entry['exe'], entry['title'], entry['directory'], entry.get('icon',''))
                if ident != entry['appid']: raise ValueError('Existing shortcut ID differs from the launcher. No changes made.')
                tree = decode(updated)
                for shortcut in tree['shortcuts'].values():
                    if shortcut['appid'] == ident: shortcut['OpenVR'] = int(entry.get('openvr',1))
                updated = encode(tree)
            stamp = time.strftime('%Y%m%d-%H%M%S'); config.mkdir(parents=True,exist_ok=True); grid.mkdir(exist_ok=True)
            if original: shutil.copy2(path, path.with_name('shortcuts.vdf.backup-q2f-'+stamp))
            for entry in entries:
                for kind, source in entry.get('art',{}).items():
                    suffix = {'portrait':'p','landscape':'','hero':'_hero','logo':'_logo','icon':'_icon'}[kind]
                    source = Path(source)
                    if not source.resolve().is_relative_to(INSTALLS.resolve()): raise ValueError('Artwork outside installation directory')
                    target = grid / (str(entry['appid']) + suffix + source.suffix)
                    if target.exists(): shutil.copy2(target, target.with_name(target.name+'.backup-q2f-'+stamp))
                    tmp = target.with_suffix(target.suffix+'.tmp'); shutil.copy2(source,tmp); tmp.replace(target)
            tmp = path.with_suffix('.q2f.tmp'); tmp.write_bytes(updated); tmp.replace(path)
            for file in pending: file.unlink()
            write_json(DATA/'library-sync.json', {'status':'complete','message':f'Updated {len(entries)} Steam entries.'})
        except Exception as exc:
            write_json(DATA/'library-sync.json', {'status':'error','message':str(exc)})
            raise
        finally:
            if service: command(['systemctl','--user','start','steam.service'],False)
            else: command(['systemd-run','--user','--collect','/usr/bin/steam'],False)

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--register-app',action='store_true');args=parser.parse_args()
    sync(args.register_app)
