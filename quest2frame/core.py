# SPDX-License-Identifier: GPL-3.0-only
"""Local-only Quest -> Frame workflow. All mutation is scoped to user directories."""
from pathlib import Path
import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from bootstrap import APP, DATA, environment, setup, sha256, tools

SHARED = APP / 'shared' if (APP / 'shared').exists() else APP.parent / 'quest-frame-app'
sys.path.insert(0, str(SHARED))
from steam_shortcuts import app_id

VERSION = '3.4.3-23204ea'
INSTALLS = Path.home() / 'Applications/quest-frame'
LEPTON = Path.home() / '.local/share/Steam/steamapps/common/Lepton/lepton'
KNOWN_TITLES = {'com.enhanceexperience.tetriseffect': ('Tetris Effect: Connected', '1003590'),
                'com.Armature.VR4': ('Resident Evil 4', ''),
                'com.beatgames.beatsaber': ('Beat Saber', '620980'),
                'com.superhot.vr': ('SUPERHOT VR', '617830')}

def package_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', value):
        raise ValueError('Invalid Android package name')
    return value

def options(value):
    scale = float(value.get('scale', 100))
    if not 50 <= scale <= 200: raise ValueError('Resolution must be between 50 and 200%.')
    title = str(value.get('title', '')).strip()
    if len(title) > 150 or '\0' in title: raise ValueError('Invalid game title')
    steam_id = str(value.get('steam_id', '')).strip()
    if steam_id and not re.fullmatch(r'[0-9]{1,10}', steam_id): raise ValueError('Steam App ID must be numeric')
    result = {'scale': scale, 'title': title, 'steam_id': steam_id}
    for key in ('controllers', 'foveation', 'add_steam', 'auto_art'):
        item = value.get(key, True)
        if not isinstance(item, bool): raise ValueError('Invalid option: ' + key)
        result[key] = item
    return result

def config_text(opts):
    return f"scale={opts['scale']/100:.3f}\ncontroller_fix={int(opts['controllers'])}\nfoveation_fix={int(opts['foveation'])}\n"

def atomic_text(path, text):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(text, encoding='utf-8'); tmp.replace(path)

def write_json(path, value): atomic_text(path, json.dumps(value, indent=2))

def pretty_title(package):
    if package in KNOWN_TITLES: return KNOWN_TITLES[package][0]
    name = package.rsplit('.', 1)[-1].replace('_', ' ')
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name).strip().title()

def normalized(title): return re.sub(r'[^a-z0-9]', '', title.casefold().replace('vr', ''))

def artwork_candidates(title):
    url = 'https://store.steampowered.com/api/storesearch/?' + urllib.parse.urlencode({'term': title, 'l': 'english', 'cc': 'US'})
    req = urllib.request.Request(url, headers={'User-Agent': 'quest2frame/1.0'})
    with urllib.request.urlopen(req, timeout=20) as response: items = json.load(response).get('items', [])
    result = []
    for item in items[:12]:
        score = difflib.SequenceMatcher(None, normalized(title), normalized(item['name'])).ratio()
        result.append({'id': str(item['id']), 'title': item['name'], 'score': round(score, 3)})
    return sorted(result, key=lambda x: x['score'], reverse=True)

class Engine:
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock(); self.proc = None; self.thread = None
        self.state = {'busy': False, 'phase': 'idle', 'progress': 0, 'message': 'Connect your Quest to get started.',
                      'error': '', 'devices': [], 'packages': [], 'logs': [], 'selected_device': '',
                      'tool_ready': False, 'candidates': [], 'result': None}
        try: tools(); self.state['tool_ready'] = True
        except RuntimeError: pass
        self.refresh_installed()

    def snapshot(self):
        with self.lock:
            state = json.loads(json.dumps(self.state))
        state['free_gb'] = round(shutil.disk_usage(DATA).free / 1024**3, 1)
        state['pending'] = len(list((DATA / 'pending').glob('*.json')))
        state['library_sync'] = json.loads((DATA / 'library-sync.json').read_text()) if (DATA / 'library-sync.json').exists() else None
        return state

    def update(self, **values):
        with self.lock: self.state.update(values)

    def log(self, line):
        line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', str(line)).strip()
        if not line: return
        with self.lock:
            self.state['logs'].append(line[-1600:]); self.state['logs'] = self.state['logs'][-160:]
        with (DATA / 'session.log').open('a', encoding='utf-8') as f: f.write(line + '\n')

    def start(self, name, fn):
        with self.lock:
            if self.state['busy']: raise ValueError('Another operation is running. Wait for it to finish.')
            self.state.update(busy=True, error='', result=None, phase=name, progress=0, message=name)
        def job():
            try:
                result = fn()
                self.update(result=result, progress=100)
            except Exception as exc:
                self.log(str(exc)); self.update(error=str(exc), message='Needs attention', phase='error')
            finally:
                self.refresh_installed(); self.update(busy=False)
        self.thread = threading.Thread(target=job, daemon=True); self.thread.start()

    def run(self, args, check=True, timeout=1800, quiet=False, env=None):
        p = subprocess.Popen([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors='replace', env=env or environment())
        self.proc = p; output = []
        def reader():
            previous = None
            for line in p.stdout:
                output.append(line)
                clean = re.sub(r'^[|/\\-] +(?:\[[^\]]*\] +)?', '', line.strip())
                if clean and clean != previous and not quiet: self.log(clean)
                previous = clean
        thread = threading.Thread(target=reader, daemon=True); thread.start()
        try: p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
            raise RuntimeError('Operation timed out. Partial backups are retained; reconnect and retry.')
        finally: thread.join(timeout=5); self.proc = None
        text = ''.join(output)
        if check and p.returncode: raise RuntimeError(f'{Path(str(args[0])).name} failed:\n{text[-1800:]}')
        return text

    def adb(self, serial, *args, **kwargs):
        command = [tools()['adb'], '-P', '5038']
        if serial: command += ['-s', serial]
        return self.run(command + list(args), **kwargs)

    def shell(self, serial, *args, **kwargs):
        return self.adb(serial, 'shell', shlex.join(str(a) for a in args), **kwargs)

    def setup(self):
        self.update(message='Fetching verified ARM64 tools…')
        setup(self.log); self.update(tool_ready=True, phase='ready', message='Tools ready. Connect Quest.')

    def scan(self, requested=''):
        self.update(message='Looking for your Quest…', phase='scan', packages=[])
        output = self.adb(None, 'devices', '-l', timeout=25)
        devices = []
        for line in output.splitlines():
            fields = line.split()
            if len(fields) < 2 or fields[0] == 'List' or line.startswith('*'): continue
            serial, status = fields[:2]
            if serial.startswith('emulator-') or ':' in serial: continue
            if status in ('unauthorized', 'offline'):
                devices.append({'serial': serial, 'state': status, 'model': 'USB device'}); continue
            if status == 'no':
                devices.append({'serial': serial, 'state': 'no permissions', 'model': 'USB device'}); continue
            if status != 'device': continue
            model = self.shell(serial, 'getprop', 'ro.product.model', timeout=15, quiet=True).strip()
            maker = self.shell(serial, 'getprop', 'ro.product.manufacturer', timeout=15, quiet=True).strip()
            if 'quest' in model.lower() or maker.lower() in ('meta', 'oculus'):
                devices.append({'serial': serial, 'state': 'ready', 'model': model})
        self.update(devices=devices)
        ready = [d for d in devices if d['state'] == 'ready']
        if requested: ready = [d for d in ready if d['serial'] == requested]
        if len(ready) > 1: raise RuntimeError('More than one Quest is connected. Select a device and rescan.')
        if not ready:
            message = 'Connect Quest directly with a data-capable USB-C cable, unlock it, then scan again.'
            if any(d['state'] == 'unauthorized' for d in devices): message = 'Allow USB debugging inside your Quest, then scan again.'
            if any(d['state'] == 'no permissions' for d in devices): message = 'USB permissions denied. See the USB troubleshooting section; no root changes were made.'
            self.update(selected_device='', message=message, phase='waiting'); return []
        serial = ready[0]['serial']
        output = self.shell(serial, 'pm', 'list', 'packages', '-3', timeout=30)
        packages = sorted(package_name(x[8:].strip()) for x in output.splitlines() if x.startswith('package:'))
        items = [{'package': p, 'title': pretty_title(p), 'steam_id': KNOWN_TITLES.get(p, ('', ''))[1]} for p in packages]
        self.update(packages=items, selected_device=serial, phase='ready', message=f'{len(items)} apps found on {ready[0]["model"]}.')
        return items

    def refresh_installed(self):
        installed = []
        for path in INSTALLS.glob('*/deployment.json'):
            try:
                d = json.loads(path.read_text()); package = package_name(d['package'])
                opts = options(d.get('options', {}))
                # Also discover games deployed with the original desktop application.
                conf = path.parent / 'settings.conf'
                if conf.exists():
                    values = dict(x.split('=', 1) for x in conf.read_text().splitlines() if '=' in x)
                    opts.update(scale=float(values.get('scale', 1))*100,
                                controllers=values.get('controller_fix', '1') != '0', foveation=values.get('foveation_fix', '1') != '0')
                installed.append({'package': package, 'title': d.get('title', pretty_title(package)),
                                  'appid': d['appid'], 'options': opts, 'art': f'/art/{package}/portrait'})
            except (OSError, ValueError, KeyError): continue
        self.update(installed=installed)

    def search_art(self, title):
        self.update(message='Finding matching Steam artwork…')
        candidates = artwork_candidates(title)
        self.update(candidates=candidates, phase='ready', message='Artwork matches ready.' if candidates else 'No confident artwork match. You can enter a Steam App ID.')
        return candidates

    def transfer(self, serial, package, opts):
        package_name(package); opts = options(opts)
        with self.lock:
            if serial != self.state['selected_device'] or package not in [p['package'] for p in self.state['packages']]:
                raise ValueError('Scan and select an installed Quest app before transferring.')
        paths = [line[8:].strip() for line in self.shell(serial, 'pm', 'path', package).splitlines() if line.startswith('package:')]
        if len(paths) != 1: raise ValueError('Split APK games are not supported. Nothing has been changed on Quest.')
        if shutil.disk_usage(DATA).free < 3*1024**3: raise RuntimeError('Keep at least 3 GB free before starting a transfer.')
        backup = DATA / 'games' / package / ('backup-' + time.strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True, exist_ok=False)
        self.update(phase='backup', progress=8, message='Copying the original APK from Quest…')
        self.adb(serial, 'pull', paths[0], backup / 'base.apk')
        for kind in ('obb', 'data'):
            remote = f'/sdcard/Android/{kind}/{package}'
            found = self.shell(serial, 'sh', '-c', f'if test -d {shlex.quote(remote)}; then echo PRESENT; fi', quiet=True)
            if 'PRESENT' not in found: continue
            target = backup / kind; target.mkdir()
            self.update(message='Copying expansion data…' if kind == 'obb' else 'Copying accessible saves…', progress=15 if kind == 'obb' else 28)
            output = self.adb(serial, 'pull', remote + '/.', target, check=kind == 'obb')
            if 'permission denied' in output.lower() or 'error:' in output.lower():
                if kind == 'obb': raise RuntimeError('Expansion data could not be fully copied. Reconnect Quest and retry.')
                self.log('WARNING: Some save/cache files are protected and could not be backed up.')
        write_json(backup / 'backup.json', {'package': package, 'sha256': sha256(backup / 'base.apk')})
        return self.convert_install(backup, package, opts)

    def convert_install(self, backup, package, opts, install=True):
        """Separate entry point for offline conversion tests and resumable local backups."""
        backup = Path(backup); package_name(package); opts = options(opts); t = tools()
        adapter = APP / 'native/libopenxr_loader_generic.so'
        if not adapter.exists(): raise RuntimeError('Frame adapter is missing. Redeploy using deploy.py after build-native.ps1.')
        badging = self.run([t['aapt'], 'dump', 'badging', backup / 'base.apk'], quiet=True)
        match = re.search(r"package: name='([^']+)'", badging)
        if not match or match[1] != package: raise RuntimeError('APK package does not match the selected game.')
        label = re.search(r"application-label:'([^']+)'", badging)
        if not opts['title'] or opts['title'] == pretty_title(package):
            opts['title'] = KNOWN_TITLES.get(package, (label[1] if label else pretty_title(package), ''))[0]
        with zipfile.ZipFile(backup / 'base.apk') as z:
            if not any(n.startswith('lib/arm64-v8a/') for n in z.namelist()): raise RuntimeError('This app has no ARM64 native libraries.')
        build = backup.parent / ('build-' + time.strftime('%Y%m%d-%H%M%S')); build.mkdir(exist_ok=False)
        workspace = DATA / 'ovrport-workspace'
        self.update(phase='convert', progress=35, message='Converting locally with OVR Port…')
        self.run([t['java'], '-Xmx1536m', '-jar', t['ovrport'], 'patch', f'--input={backup / "base.apk"}',
                  f'--output={build}', '--output-name=ovrport.apk', f'--workspace={workspace}', f'--version={VERSION}'])
        self.update(phase='configure', progress=65, message='Applying Frame compatibility and resolution settings…')
        prefix = 'lib/arm64-v8a/'
        with zipfile.ZipFile(build / 'ovrport.apk') as src, zipfile.ZipFile(build / 'unsigned.apk', 'w', zipfile.ZIP_DEFLATED) as dst:
            if prefix + 'libopenxr_loader_generic.so' not in src.namelist(): raise RuntimeError('OVR Port did not supply a generic loader for this app.')
            for item in src.infolist():
                if item.filename == prefix + 'libopenxr_loader_generic.so' or item.filename.startswith('META-INF/'): continue
                # Compress native libs so this old, portable zipalign never needs 16K ELF page alignment.
                if item.filename.startswith('lib/') and item.filename.endswith('.so'): item.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(item, src.read(item.filename))
            dst.writestr(prefix + 'libopenxr_loader_original.so', src.read(prefix + 'libopenxr_loader_generic.so'))
            dst.write(adapter, prefix + 'libopenxr_loader_generic.so')
            dst.writestr(prefix + 'libframe_settings.so', config_text(opts))
        self.run([t['zipalign'], '-f', '4', build / 'unsigned.apk', build / 'aligned.apk'])
        self.run([t['java'], '-jar', t['signer'], 'sign', '--ks', workspace / 'signatures' / (package + '.keystore'),
                  '--ks-pass', 'pass:password', '--out', build / 'game.apk', build / 'aligned.apk'])
        self.run([t['java'], '-jar', t['signer'], 'verify', '--verbose', build / 'game.apk'])
        game = {'package': package, 'title': opts['title'], 'options': opts, 'backup': str(backup), 'sha256': sha256(build / 'game.apk')}
        write_json(build / 'game.json', game)
        if install: return self.install(build, game)
        return str(build)

    def install(self, build, game):
        package = package_name(game['package']); opts = options(game['options']); backup = Path(game['backup'])
        if not LEPTON.is_file(): raise RuntimeError('Install Lepton through Steam first.')
        base = INSTALLS / package; base.mkdir(parents=True, exist_ok=True)
        exe = '"' + str(base / 'launch.sh') + '"'; ident = app_id(exe, game['title'])
        if (base / 'deployment.json').exists(): ident = int(json.loads((base / 'deployment.json').read_text())['appid'])
        live = self.run(['podman', 'ps', '--format', '{{.Names}}'], quiet=True)
        if f'lepton-steamlaunch-{ident}' in live.splitlines(): raise RuntimeError('Close this game on Frame before updating it. The converted build is saved for retry.')
        required = sum(p.stat().st_size for p in backup.rglob('*') if p.is_file()) + (build / 'game.apk').stat().st_size
        if shutil.disk_usage(base).free < required*2 + 512*1024**2: raise RuntimeError('Not enough free space for safe staging and backups. Converted build retained.')
        self.update(phase='install', progress=78, message='Installing into a dedicated Lepton container…')
        stamp = time.strftime('%Y%m%d-%H%M%S'); stage = base / ('staging-' + uuid.uuid4().hex); stage.mkdir()
        shutil.copy2(build / 'game.apk', stage / 'game.apk')
        if sha256(stage / 'game.apk') != game['sha256']: raise RuntimeError('APK verification failed. Previous installation untouched.')
        if (backup / 'obb').exists():
            shutil.copytree(backup / 'obb', stage / 'obb')
            for file in (backup / 'obb').rglob('*'):
                if file.is_file() and sha256(file) != sha256(stage / 'obb' / file.relative_to(backup / 'obb')):
                    raise RuntimeError('Expansion data verification failed. Previous installation untouched.')
        data = base / 'lepton-data/external/Android/data' / package
        for file in (backup / 'data').rglob('*'):
            if not file.is_file() or file.is_symlink(): continue
            relative = file.relative_to(backup / 'data'); dest = data / relative
            if relative.as_posix() == 'files/framebridge.conf' or dest.exists(): continue
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(file, dest)
        baked = base / 'lepton-data/baked'
        if baked.exists(): self.run(['cp', '-a', '--reflink=auto', baked, base / ('previous-baked-' + stamp)])
        old = base / 'lepton-app'
        previous = base / ('previous-app-' + stamp)
        if old.exists(): old.rename(previous)
        try: stage.rename(old)
        except Exception:
            if previous.exists(): previous.rename(old)
            raise
        atomic_text(base / 'settings.conf', config_text(opts))
        atomic_text(data / 'files/framebridge.conf', config_text(opts))
        template = (SHARED / 'launcher.sh').read_text()
        script = template.replace('@APP_DIR@', shlex.quote(str(base))).replace('@APP_ID@', str(ident)).replace('@LEPTON@', shlex.quote(str(LEPTON)))
        atomic_text(base / 'launch.sh', script); (base / 'launch.sh').chmod(0o755)
        self.update(phase='artwork', progress=90, message='Finding artwork for your Steam library…')
        art = self.fetch_art(package, opts, base)
        deployment = {'package': package, 'title': game['title'], 'appid': ident, 'options': opts, 'build': str(build)}
        write_json(base / 'deployment.json', deployment)
        if opts['add_steam']:
            write_json(DATA / 'pending' / (package + '.json'), {'exe': exe, 'title': game['title'], 'directory': str(base),
                       'appid': ident, 'openvr': 1, 'art': art, 'icon': art.get('logo', art.get('icon', ''))})
        self.update(phase='complete', progress=100, message='Installed. Apply Steam library updates when you’re ready.' if opts['add_steam'] else 'Installed. Your game is ready.')
        return deployment

    def fetch_art(self, package, opts, base):
        art = {}; steam_id = opts['steam_id']; folder = base / 'artwork'; folder.mkdir(exist_ok=True)
        if not steam_id and opts['auto_art']:
            if package in KNOWN_TITLES: steam_id = KNOWN_TITLES[package][1]
            else:
                try:
                    candidates = artwork_candidates(opts['title'])
                    self.update(candidates=candidates)
                    # Avoid confidently putting another game's cover in the user's library.
                    if candidates and candidates[0]['score'] >= .9 and (len(candidates) == 1 or candidates[0]['score'] - candidates[1]['score'] >= .08): steam_id = candidates[0]['id']
                except Exception as exc: self.log('Artwork lookup unavailable: ' + str(exc))
        if steam_id:
            for kind, filename in {'portrait':'library_600x900.jpg', 'landscape':'header.jpg', 'hero':'library_hero.jpg', 'logo':'logo.png'}.items():
                try:
                    with urllib.request.urlopen(f'https://cdn.akamai.steamstatic.com/steam/apps/{steam_id}/{filename}', timeout=20) as response: content = response.read(8*1024**2)
                    if not (content.startswith(b'\x89PNG') or content.startswith(b'\xff\xd8')): raise ValueError('Not an image')
                    target = folder / filename; target.write_bytes(content); art[kind] = str(target)
                except Exception as exc: self.log(f'{kind} artwork unavailable: {exc}')
        if not art: self.log('No confident artwork found. Installation succeeded; choose a Steam App ID later.')
        return art

    def settings(self, package, value):
        package_name(package); opts = options(value); base = INSTALLS / package
        path = base / 'deployment.json'
        if not path.is_file(): raise ValueError('Game is not installed')
        record = json.loads(path.read_text()); opts['title'] = opts['title'] or record.get('title', pretty_title(package))
        atomic_text(base / 'settings.conf', config_text(opts))
        atomic_text(base / 'lepton-data/external/Android/data' / package / 'files/framebridge.conf', config_text(opts))
        record['options'] = opts; write_json(path, record)
        self.update(phase='complete', message='Settings saved. Restart the game to apply them.')

    def repair_art(self, package, value):
        package_name(package); opts = options(value); base = INSTALLS / package
        record = json.loads((base / 'deployment.json').read_text())
        opts['title'] = opts['title'] or record.get('title', pretty_title(package))
        art = self.fetch_art(package, opts, base)
        write_json(DATA / 'pending' / (package + '.json'), {'exe':'"'+str(base/'launch.sh')+'"', 'title':record.get('title',opts['title']),
                   'directory':str(base), 'appid':record['appid'], 'openvr':1, 'art':art, 'icon':art.get('logo','')})
        self.update(phase='complete', message='Artwork ready. Apply Steam library updates to finish.')

    def resume(self, package):
        package_name(package)
        manifests = sorted((DATA / 'games' / package).glob('build-*/game.json'))
        if not manifests: raise ValueError('No completed conversion is available to retry.')
        build = manifests[-1].parent; game = json.loads(manifests[-1].read_text())
        if sha256(build / 'game.apk') != game['sha256']: raise ValueError('Converted APK hash mismatch')
        return self.install(build, game)
