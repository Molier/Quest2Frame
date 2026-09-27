# SPDX-License-Identifier: GPL-3.0-only
"""Constrained Frame-side uninstall helper. Only managed package directories."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

def checked(path):
    path=Path(path)
    if path.resolve()!=path or path.is_symlink():raise ValueError('Symlinked installation paths are not supported')
    return path

def inspect_game(home, package, mounts):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+',package):raise ValueError('Invalid package')
    anchor=checked(Path(home)/'Applications/quest-frame'/package)
    metadata=checked(anchor/'deployment.json')
    game=json.loads(metadata.read_text())
    if game.get('package')!=package or not isinstance(game.get('appid'),int):raise ValueError('Invalid deployment marker')
    storage_uuid=game.get('storage_uuid','')
    base=anchor
    if storage_uuid:
        matches=[m for m in mounts if m.get('uuid')==storage_uuid]
        if len(matches)!=1:raise ValueError('Required SD/removable storage unavailable')
        mount=checked(matches[0]['mount'])
        if not os.path.ismount(mount):raise ValueError('Card is not mounted')
        actual=json.loads(subprocess.check_output(['findmnt','-J','-M',str(mount),'-o','UUID'],text=True))['filesystems'][0]['uuid']
        if actual!=storage_uuid:raise ValueError('Mounted storage identity changed')
        base=checked(mount/'Applications/quest-frame'/package)
    checked(base/'lepton-app');checked(base/'lepton-data')
    if not (base/'lepton-app/game.apk').is_file():raise ValueError('Managed game APK missing')
    launcher=checked(anchor/'launch.sh')
    text=launcher.read_text()
    if 'STEAM_COMPAT_INSTALL_PATH' not in text or 'lepton-app' not in text:raise ValueError('Unrecognized launcher')
    return dict(package=package,appid=game['appid'],anchor=str(anchor),base=str(base),storage_uuid=storage_uuid)

def inventory(home,mounts):
    root=checked(Path(home)/'Applications/quest-frame');result=[]
    if not root.is_dir():return result
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith('.'):continue
        try:result.append(dict(inspect_game(home,path.name,mounts),error=''))
        except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
            if (path/'deployment.json').is_file():result.append(dict(package=path.name,error=str(exc)))
    return result

def delete_game(home,package,mounts,expected,keep_saves):
    game=inspect_game(home,package,mounts)
    if game!=expected:raise ValueError('Installation changed; refresh before uninstalling')
    running=subprocess.check_output(['podman','ps','--format','{{.Names}}'],text=True).splitlines()
    if 'lepton-steamlaunch-'+str(game['appid']) in running:raise ValueError('Close the game before uninstalling')
    base=Path(game['base']);anchor=Path(game['anchor']);token=uuid.uuid4().hex
    # Renaming isolates the validated game directory. No broad/glob removal.
    staged=base.with_name('.quest2frame-uninstall-'+package+'-'+token)
    staged_anchor=anchor.with_name('.quest2frame-uninstall-'+package+'-'+token)
    base.rename(staged)
    try:
        if anchor!=base:anchor.rename(staged_anchor)
    except Exception:
        staged.rename(base);raise
    saved=None
    try:
        if keep_saves:
            names=[p.name for p in staged.iterdir() if p.name=='lepton-data' or p.name.startswith('previous-baked-')]
            if names:
                saved=checked(base.parent/('.quest2frame-saves-'+package+'-'+token));saved.mkdir()
                for name in names:(staged/name).rename(saved/name)
        # Reject nested mounts, even inside an otherwise legitimate installation.
        directories=[staged]+([staged_anchor] if anchor!=base else [])
        for directory in directories:
            for root,dirs,files in os.walk(directory,followlinks=False):
                if any(os.path.ismount(Path(root)/d) for d in dirs):raise ValueError('Nested mount found; files retained in '+str(directory))
        for directory in directories:shutil.rmtree(directory)
    except Exception as exc:
        raise RuntimeError(f'Uninstall cleanup incomplete. Recovery directories: {staged}, {staged_anchor}; saves: {saved}. {exc}') from exc
    return dict(removed=game,saves=str(saved) if saved else None)

def main(request):
    home=str(Path.home())
    if request['action']=='list':result=inventory(home,request['mounts'])
    elif request['action']=='check':result=inspect_game(home,request['package'],request['mounts'])
    elif request['action']=='delete':result=delete_game(home,request['package'],request['mounts'],request['expected'],request['keep_saves'])
    else:raise ValueError('Unknown action')
    print(json.dumps(result))
