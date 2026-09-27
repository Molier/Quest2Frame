# SPDX-License-Identifier: GPL-3.0-only
"""User-local, hash-pinned ARM64 tools. Never invokes a package manager or sudo."""
from pathlib import Path
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

APP = Path(__file__).resolve().parent
DATA = Path(os.environ.get('QUEST2FRAME_DATA', Path.home() / '.local/share/quest2frame'))
RUNTIME = DATA / 'runtime'

def sha256(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def download(asset, cache, report=print):
    target = cache / asset['sha256']
    if target.exists() and sha256(target) == asset['sha256']: return target
    report('Downloading ' + asset['url'].rsplit('/', 1)[-1])
    request = urllib.request.Request(asset['url'], headers={'User-Agent': 'quest2frame/1.0'})
    temporary = target.with_suffix('.part')
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as out:
        shutil.copyfileobj(response, out)
    if sha256(temporary) != asset['sha256']: raise RuntimeError('Download checksum mismatch; refusing to execute it.')
    temporary.replace(target)
    return target

def deb_data(path):
    with path.open('rb') as f:
        if f.read(8) != b'!<arch>\n': raise ValueError('Invalid Debian archive')
        while header := f.read(60):
            if len(header) != 60: raise ValueError('Truncated Debian archive')
            size = int(header[48:58]); name = header[:16].decode().strip().rstrip('/')
            data = f.read(size)
            if size % 2: f.read(1)
            if name.startswith('data.tar'): return data
    raise ValueError('No data archive in package')

def environment():
    env = os.environ.copy()
    root = RUNTIME / 'debian'
    paths = [root / 'usr/lib/aarch64-linux-gnu/android', root / 'usr/lib/aarch64-linux-gnu', root / 'lib/aarch64-linux-gnu', root / 'usr/lib/p7zip', root / 'usr/lib']
    env['LD_LIBRARY_PATH'] = ':'.join(map(str, paths))
    env['ADB_SERVER_PORT'] = '5038'  # Do not interfere with Lepton/developer ADB servers.
    return env

def tools():
    root = RUNTIME / 'debian'
    def find(pattern):
        paths = sorted(root.glob(pattern))
        if not paths: raise RuntimeError('Tools not set up. Open Tools and choose Set up tools.')
        return paths[0].resolve()
    java = next((RUNTIME / 'java').glob('*/bin/java'), None)
    jars = list((RUNTIME / 'ovrport').rglob('overportcli-*-all.jar'))
    if not java or not jars: raise RuntimeError('Java / OVR Port is not installed yet.')
    return {'adb': find('usr/bin/adb'), 'aapt': find('usr/bin/aapt'),
            'zipalign': find('usr/bin/zipalign'), 'signer': find('usr/share/java/apksigner.jar'),
            'java': java, 'ovrport': jars[0]}

def setup(report=print):
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        raise RuntimeError('Tool setup requires Linux ARM64 (Steam Frame).')
    lock = json.loads((APP / 'tools.lock.json').read_text())
    cache = DATA / 'downloads'; cache.mkdir(parents=True, exist_ok=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for asset in lock['debian']:
        mark = RUNTIME / ('installed-' + asset['sha256'])
        if mark.exists(): continue
        archive = download(asset, cache, report)
        root = RUNTIME / 'debian'; root.mkdir(exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(deb_data(archive))) as tar:
            tar.extractall(root, filter='data')
        mark.touch()
    for kind in ('java', 'ovrport'):
        asset = lock[kind]; mark = RUNTIME / ('installed-' + asset['sha256'])
        if mark.exists(): continue
        archive = download(asset, cache, report); target = RUNTIME / kind; target.mkdir(exist_ok=True)
        if kind == 'java':
            with tarfile.open(archive) as tar: tar.extractall(target, filter='data')
        else:
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    if not (target / name).resolve().is_relative_to(target.resolve()): raise ValueError('Unsafe ZIP path')
                z.extractall(target)
        mark.touch()
    resolved = tools()
    for command in ([resolved['adb'], 'version'], [resolved['aapt'], 'version'], [resolved['java'], '-version'], [resolved['java'], '-jar', resolved['signer'], 'version']):
        p = subprocess.run(command, env=environment(), capture_output=True, text=True, timeout=20)
        if p.returncode: raise RuntimeError((p.stdout + p.stderr)[-2000:])
        report((p.stdout + p.stderr).strip())
    check = subprocess.run([resolved['zipalign']], env=environment(), capture_output=True, text=True, timeout=20)
    if 'Usage' not in check.stdout + check.stderr: raise RuntimeError('zipalign cannot run: ' + check.stderr)
    report('ARM64 tools ready. Connect Quest and allow USB debugging.')
    return resolved

if __name__ == '__main__': setup()
