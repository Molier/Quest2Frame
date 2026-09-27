# SPDX-License-Identifier: GPL-3.0-only
"""Deploy source + locally built adapter over verified SSH. Password is prompted."""
from pathlib import Path
import argparse
import getpass
import os
import posixpath
import shlex
import sys
import paramiko

APP=Path(__file__).resolve().parent

def deploy(host, username, password, known_hosts):
    client=paramiko.SSHClient();client.load_host_keys(str(known_hosts));client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(host,username=username,password=password,look_for_keys=False,allow_agent=False,timeout=15)
    def run(command):
        _,out,err=client.exec_command(command);text=out.read().decode()+err.read().decode()
        if out.channel.recv_exit_status():raise RuntimeError(text)
        return text.strip()
    if run('uname -m')!='aarch64':raise RuntimeError('Target is not Linux ARM64')
    home=run('printf %s "$HOME"');dest=home+'/Applications/quest2frame'
    adapter=APP.parent/'quest-frame-app/native/libopenxr_loader_generic.so'
    if not adapter.is_file():raise RuntimeError('Run quest-frame-app/build-native.ps1 before deploying.')
    files={str(f.relative_to(APP)).replace('\\','/'):f for f in APP.rglob('*') if f.is_file() and f.suffix in ('.py','.json','.sh','.html','.css','.js','.svg','.md') and '__pycache__' not in f.parts and '.local' not in f.parts}
    for name in ('steam_shortcuts.py','launcher.sh'):files['shared/'+name]=APP.parent/'quest-frame-app'/name
    files['native/libopenxr_loader_generic.so']=adapter
    files['native/frame_bridge.c']=APP.parent/'quest-frame-app/native/frame_bridge.c'
    files['LICENSE']=APP.parent/'LICENSE'
    files['ROOT_THIRD_PARTY_NOTICES.md']=APP.parent/'THIRD_PARTY_NOTICES.md'
    for file in (APP.parent/'LICENSES').glob('*'):files['LICENSES/'+file.name]=file
    with client.open_sftp() as sftp:
        for relative,source in files.items():
            target=dest+'/'+relative;run('mkdir -p '+shlex.quote(posixpath.dirname(target)))
            sftp.put(str(source),target+'.upload');sftp.posix_rename(target+'.upload',target)
    run('chmod 755 '+shlex.quote(dest+'/launch.sh'))
    print('Deployed to '+dest)
    print(run('python3 '+shlex.quote(dest+'/bootstrap.py')))
    print(run('systemd-run --user --collect --unit=quest2frame-register /usr/bin/python3 '+shlex.quote(dest+'/steam_sync.py')+' --register-app'))
    client.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',default='frame');p.add_argument('--user',default='steamos');p.add_argument('--known-hosts',type=Path,default=APP.parent/'quest-frame-app/known_hosts');args=p.parse_args()
    deploy(args.host,args.user,getpass.getpass('Frame SSH password: '),args.known_hosts)
