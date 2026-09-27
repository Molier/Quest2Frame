# SPDX-License-Identifier: GPL-3.0-only
"""Read-only storage discovery executed on Frame; never mounts/formats devices."""
PROBE = r'''
import json, os, pathlib, subprocess
home=os.path.expanduser('~')
def free(path):
    s=os.statvfs(path);return s.f_bavail*s.f_frsize
result=[dict(id='internal',label='Internal storage',mount=home,free=free(home),uuid='')]
tree=json.loads(subprocess.check_output(['lsblk','-J','-o','NAME,PATH,TYPE,TRAN,RM,FSTYPE,UUID,MOUNTPOINTS'],text=True))
def walk(node,external=False,sd=False):
    try:card_type=pathlib.Path('/sys/class/block',node['name'],'device/type').read_text().strip()
    except OSError:card_type=''
    sd=sd or card_type=='SD'
    external=external or sd or node.get('rm') in (True,1,'1') or node.get('tran')=='usb'
    if external and node.get('uuid') and node.get('fstype') in ('ext4','btrfs'):
        for mount in node.get('mountpoints') or []:
            if not mount or mount in ('/','/home','/var','/boot','/efi'):continue
            try:
                info=json.loads(subprocess.check_output(['findmnt','-J','-M',mount,'-o','OPTIONS'],text=True))['filesystems'][0]
                flags=info['options'].split(',')
                if 'rw' not in flags or 'noexec' in flags or not os.access(mount,os.W_OK|os.X_OK):continue
                ident='uuid:'+node['uuid']
                if any(x['id']==ident for x in result):continue
                result.append(dict(id=ident,uuid=node['uuid'],mount=mount,free=free(mount),label=('SD card' if sd else 'Removable storage')))
            except (OSError,subprocess.SubprocessError,KeyError,ValueError):continue
    for child in node.get('children',[]):walk(child,external,sd)
for node in tree['blockdevices']:walk(node)
print(json.dumps(result))
'''

def select_storage(choices, ident):
    matches=[item for item in choices if item['id']==ident]
    if len(matches)!=1:raise RuntimeError('Selected storage is missing or not writable. Insert/mount the card and refresh storage; no internal fallback was used.')
    return matches[0]

def card_launcher(uuid, package):
    import shlex
    q=shlex.quote
    code="import json,subprocess; mounts=json.loads(subprocess.check_output(['findmnt','-J','-S',"+repr('UUID='+uuid)+",'-o','TARGET'],text=True))['filesystems']; assert len(mounts)==1, 'Storage mount is ambiguous'; print(mounts[0]['target'])"
    return ('storage_mount=$(python3 -c '+q(code)+')\n'
            'if [[ -z "$storage_mount" ]] || ! mountpoint -q -- "$storage_mount"; then\n'
            '  echo "Quest2Frame: required SD/removable storage is not mounted." >&2; exit 1\nfi\n'
            'app_dir="$storage_mount"/'+q('Applications/quest-frame/'+package)+'\n'
            'test -f "$app_dir/lepton-app/game.apk" || { echo "Game missing on selected storage" >&2; exit 1; }\n')
