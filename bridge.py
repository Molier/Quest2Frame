# SPDX-License-Identifier: GPL-3.0-only
"""Quest backup, OVR Port conversion and per-game Lepton deployment."""
from pathlib import Path, PurePosixPath
import base64
import difflib
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import zipfile
import paramiko
from steam_shortcuts import upsert, app_id
from storage import PROBE, select_storage, card_launcher

APP = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
ROOT = APP
ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
LIB_VERSION = '3.4.3-23204ea'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

def artwork_query(title):
    return re.sub(r'\s*\(Quest\)\s*$', '', title, flags=re.I).strip()

def suggested_title(package):
    known = {'com.enhanceexperience.tetriseffect':'Tetris Effect: Connected',
             'com.beatgames.beatsaber':'Beat Saber', 'com.Armature.VR4':'Resident Evil 4'}
    if package in known: return known[package]
    name = package.rsplit('.', 1)[-1].replace('_', ' ')
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name).strip()

def artwork_candidates(title):
    """Return suggestions only; the user must confirm the correct Steam edition."""
    query = artwork_query(title)[:150]
    if not query: return []
    url = 'https://store.steampowered.com/api/storesearch/?' + urllib.parse.urlencode(
        {'term':query, 'l':'english', 'cc':'US'})
    request = urllib.request.Request(url, headers={'User-Agent':'Quest2Frame/1.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
    def normalized(text): return re.sub(r'[^a-z0-9]', '', text.casefold())
    candidates = []; seen = set()
    for item in payload.get('items', [])[:30]:
        ident = str(item.get('id', '')); name = item.get('name')
        if not ident.isdigit() or not isinstance(name, str) or ident in seen: continue
        seen.add(ident)
        score = difflib.SequenceMatcher(None, normalized(query), normalized(name)).ratio()
        candidates.append({'id':ident, 'title':name, 'score':score})
    return sorted(candidates, key=lambda item:item['score'], reverse=True)[:10]

def valid_package(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', value):
        raise ValueError('Invalid Android package name')
    return value

def settings_text(scale=100, controllers=True, foveation=True):
    if not 50 <= float(scale) <= 200: raise ValueError('Resolution must be 50–200%')
    return f'scale={float(scale)/100:.3f}\ncontroller_fix={int(controllers)}\nfoveation_fix={int(foveation)}\n'

def digest(path):
    with open(path, 'rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()

def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)

def launcher_text(base, ident, lepton, storage_setup=''):
    return (ASSETS / 'launcher.sh').read_text(encoding='utf-8').replace('@APP_DIR@', shlex.quote(base)).replace('@APP_ID@', str(int(ident))).replace('@LEPTON@', shlex.quote(lepton)).replace('@STORAGE_SETUP@',storage_setup)

class Bridge:
    def __init__(self, log=print):
        self.log = log
        self.adb = shutil.which('adb') or str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Android/Sdk/platform-tools/adb.exe')

    def run(self, args, check=True):
        p = subprocess.Popen([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding='utf-8', errors='replace', creationflags=NO_WINDOW)
        lines = []; previous = None
        for line in p.stdout:
            lines.append(line)
            clean = re.sub(r'^[|/\\-] +(?:\[[^\]]*\] +)?', '', line.strip())
            if clean and clean != previous: self.log(clean)
            previous = clean
        p.wait(); output = ''.join(lines)
        if check and p.returncode: raise RuntimeError(f'Command failed ({Path(str(args[0])).name}):\n{output[-2500:]}')
        return output

    def adb_run(self, serial, *args, check=True):
        return self.run([self.adb, '-s', serial, *args], check)

    def shell(self, serial, *args, check=True):
        return self.adb_run(serial, 'shell', shlex.join(str(a) for a in args), check=check)

    def devices(self):
        text = self.run([self.adb, 'devices'])
        return [line.split()[0] for line in text.splitlines() if len(line.split()) == 2 and line.split()[1] == 'device']

    def quests(self):
        result = []
        for serial in self.devices():
            model = self.shell(serial, 'getprop', 'ro.product.model', check=False).strip()
            maker = self.shell(serial, 'getprop', 'ro.product.manufacturer', check=False).strip()
            if 'quest' in model.lower() or maker.lower() in ('oculus', 'meta'):
                result.append((serial, model))
        return result

    def packages(self, serial):
        return sorted(x[8:].strip() for x in self.shell(serial, 'pm', 'list', 'packages', '-3').splitlines() if x.startswith('package:'))

    def backup(self, serial, package):
        valid_package(package)
        paths = [x[8:] for x in self.shell(serial, 'pm', 'path', package).splitlines() if x.startswith('package:')]
        if not paths: raise RuntimeError('Package disappeared or Quest is disconnected')
        if len(paths) != 1: raise RuntimeError('This game uses split APKs. This version supports single-APK games only; nothing was changed.')
        folder = ROOT / 'games' / package / time.strftime('backup-%Y%m%d-%H%M%S')
        folder.mkdir(parents=True, exist_ok=False)
        self.log('Backing up APK. Keep the Quest connected until conversion finishes.')
        self.adb_run(serial, 'pull', paths[0], folder / 'base.apk')
        warnings = []
        for kind in ('obb', 'data'):
            remote = f'/sdcard/Android/{kind}/{package}'
            exists = self.shell(serial, 'sh', '-c', f'test -d {shlex.quote(remote)} && echo PRESENT', check=False)
            if 'PRESENT' not in exists: continue
            target = folder / kind; target.mkdir()
            result = self.adb_run(serial, 'pull', remote + '/.', target, check=False)
            if 'error:' in result.lower() or 'permission denied' in result.lower():
                if kind == 'obb': raise RuntimeError(f'OBB backup incomplete. Retry with Quest unlocked. Partial backup: {folder}')
                warnings.append('Some external save/cache files were inaccessible. Private Android app data is not backed up.')
        write_json(folder / 'backup.json', {'package': package, 'apk_sha256': digest(folder / 'base.apk'), 'warnings': warnings})
        for warning in warnings: self.log('WARNING: ' + warning)
        return folder

    def toolchain(self):
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT') or Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk')
        def pick(pattern):
            found = sorted(sdk.glob(pattern), reverse=True)
            if not found: raise RuntimeError(f'Android SDK tool missing: {sdk / pattern}')
            return found[0]
        java = next((ROOT / 'tools/java21').glob('*/bin/java.exe'), None)
        jar = ROOT / 'tools/ovrport-cli/overportcli-1.2.3-all.jar'
        if not java or not jar.exists(): raise RuntimeError('Keep this app beside the existing tools folder (Java 21 and OVR Port CLI).')
        clangs = sorted(sdk.glob('ndk/*/toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe'), reverse=True)
        return java, jar, pick('build-tools/*/aapt.exe').parent, clangs[0] if clangs else None

    def convert(self, backup, title, scale=100, controllers=True, foveation=True, steam_id=''):
        backup = Path(backup)
        java, jar, build, clang = self.toolchain()
        source_apk = backup / 'base.apk'
        if not source_apk.exists(): source_apk = backup / 'apk/base.apk'
        badging = self.run([build / 'aapt.exe', 'dump', 'badging', source_apk])
        package = valid_package(re.search(r"package: name='([^']+)'", badging)[1])
        with zipfile.ZipFile(source_apk) as apk:
            if not any(n.startswith('lib/arm64-v8a/') for n in apk.namelist()):
                raise RuntimeError('Game has no ARM64 libraries; this conversion profile does not support it.')
        if steam_id and not str(steam_id).isdigit(): raise ValueError('Steam artwork App ID must contain digits only')
        folder = ROOT / 'games' / package / time.strftime('build-%Y%m%d-%H%M%S')
        folder.mkdir(parents=True, exist_ok=False)
        workspace = ROOT / 'tools/ovrport-workspace'
        self.log('Converting with pinned OVR Port ' + LIB_VERSION)
        self.run([java, '-jar', jar, 'patch', f'--input={source_apk}', f'--output={folder}',
                  '--output-name=ovrport.apk', f'--workspace={workspace}', f'--version={LIB_VERSION}'])
        self.log('Building Frame compatibility adapter and resolution control…')
        library = folder / 'libopenxr_loader_generic.so'
        prebuilt = ASSETS / 'native/libopenxr_loader_generic.so'
        if prebuilt.exists(): shutil.copy2(prebuilt, library)
        else:
            if not clang: raise RuntimeError('Missing bundled adapter and Android NDK compiler')
            include = ASSETS / 'native/include'
            if not (include / 'openxr/openxr.h').exists():
                raise RuntimeError('Run build-native.ps1 to obtain verified OpenXR headers and build the adapter.')
            self.run([clang, '--target=aarch64-linux-android29', f'--sysroot={clang.parent.parent / "sysroot"}',
                      '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror', '-Wl,-Bsymbolic',
                      '-Wl,-soname,libopenxr_loader_generic.so', '-I', include,
                      ASSETS / 'native/frame_bridge.c', '-ldl', '-llog', '-o', library])
        prefix = 'lib/arm64-v8a/'
        original = prefix + 'libopenxr_loader_generic.so'
        with zipfile.ZipFile(folder / 'ovrport.apk') as src, zipfile.ZipFile(folder / 'unsigned.apk', 'w', zipfile.ZIP_DEFLATED) as dst:
            if original not in src.namelist(): raise RuntimeError('OVR Port output has no generic loader; incompatible game/profile')
            for item in src.infolist():
                if item.filename == original or item.filename.startswith('META-INF/'): continue
                dst.writestr(item, src.read(item.filename))
            dst.writestr(prefix + 'libopenxr_loader_original.so', src.read(original))
            dst.write(library, original)
            dst.writestr(prefix + 'libframe_settings.so', settings_text(scale, controllers, foveation))
        self.run([build / 'zipalign.exe', '-f', '-P', '16', '4', folder / 'unsigned.apk', folder / 'aligned.apk'])
        key = workspace / 'signatures' / (package + '.keystore')
        self.run([java, '-jar', build / 'lib/apksigner.jar', 'sign', '--ks', key, '--ks-pass', 'pass:password', '--out', folder / 'game.apk', folder / 'aligned.apk'])
        self.run([java, '-jar', build / 'lib/apksigner.jar', 'verify', '--verbose', folder / 'game.apk'])
        label = re.search(r"application-label:'([^']+)'", badging)
        manifest = {'package': package, 'title': title.strip() or (label[1] if label else package),
                    'backup': str(backup.resolve()), 'scale': float(scale), 'controllers': controllers,
                    'foveation': foveation, 'steam_id': str(steam_id), 'ovrport': LIB_VERSION,
                    'sha256': digest(folder / 'game.apk')}
        write_json(folder / 'game.json', manifest)
        self.log('Conversion complete. Unplug Quest, plug in Frame, then press Install.')
        return folder

    def connect(self, host, username, password, port=22):
        """Trust an SSH key only after comparing it to the physically connected Frame."""
        if not host.strip() or not username.strip(): raise ValueError('Enter the Frame SSH host and username')
        client = paramiko.SSHClient()
        known = APP / 'known_hosts'
        if known.exists(): client.load_host_keys(str(known))
        key_host = host if int(port) == 22 else f'[{host}]:{port}'
        if not client.get_host_keys().lookup(key_host):
            if 'frame' not in self.devices():
                raise RuntimeError('First SSH connection: plug in Frame by USB so its host key can be verified securely.')
            key = self.shell('frame', 'cat', '/etc/ssh/ssh_host_ed25519_key.pub').strip().split()
            if len(key) < 2 or key[0] != 'ssh-ed25519': raise RuntimeError('Could not read Frame SSH host key')
            client.get_host_keys().add(key_host, key[0], paramiko.Ed25519Key(data=base64.b64decode(key[1])))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(host.strip(), port=int(port), username=username.strip(), password=password,
                       look_for_keys=False, allow_agent=False, timeout=10, auth_timeout=15)
        client.save_host_keys(str(known))
        self.log('SSH identity and authentication verified.')
        return client

    def remote(self, client, command, check=True):
        _, out, err = client.exec_command(command, timeout=60)
        output = out.read().decode('utf-8', 'replace') + err.read().decode('utf-8', 'replace')
        code = out.channel.recv_exit_status()
        if output.strip(): self.log(output.strip())
        if check and code: raise RuntimeError(f'Frame command failed ({code}): {output[-2000:]}')
        return output.strip()

    def put_text(self, client, remote, text):
        with client.open_sftp() as sftp:
            with sftp.file(remote + '.tmp', 'w') as f: f.write(text.encode('utf-8'))
            sftp.posix_rename(remote + '.tmp', remote)

    def artwork(self, steam_id, folder):
        if not str(steam_id).isdigit(): raise ValueError('Steam App ID must be numeric')
        folder = Path(folder); folder.mkdir(exist_ok=True)
        assets = {'portrait': 'library_600x900.jpg', 'landscape': 'header.jpg', 'hero': 'library_hero.jpg', 'logo': 'logo.png'}
        result = {}
        for kind, filename in assets.items():
            path = folder / filename
            try:
                url = f'https://cdn.akamai.steamstatic.com/steam/apps/{steam_id}/{filename}'
                with urllib.request.urlopen(url, timeout=30) as response: data = response.read()
                if not (data.startswith(b'\x89PNG') or data.startswith(b'\xff\xd8')): raise ValueError('Not an image')
                path.write_bytes(data); result[kind] = path
            except Exception as exc: self.log(f'Artwork {kind} unavailable: {exc}')
        return result

    def storage_locations(self, client):
        return json.loads(self.remote(client,'python3 -c '+shlex.quote(PROBE)))

    def deployment_base(self, client, deployment):
        uuid=deployment.get('storage_uuid','')
        if not uuid:return deployment['remote']
        choice=select_storage(self.storage_locations(client),'uuid:'+uuid)
        return choice['mount']+'/Applications/quest-frame/'+valid_package(deployment['package'])

    def install(self, folder, client, add_steam=True, artwork_id=None, storage_id='internal'):
        folder = Path(folder); game = json.loads((folder / 'game.json').read_text())
        package = valid_package(game['package']); backup = Path(game['backup'])
        obb_source = backup / 'obb'
        data_source = backup / 'data'
        if not obb_source.exists(): obb_source = backup / 'Android/obb' / package
        if not data_source.exists(): data_source = backup / 'Android/data' / package
        if digest(folder / 'game.apk') != game['sha256']: raise RuntimeError('APK checksum differs from build manifest')
        if 'frame' not in self.devices(): raise RuntimeError('Plug in Frame by USB and enable USB debugging first.')
        # Verify SSH and USB point to the same physical device, not two different Frames.
        usb_key = self.shell('frame', 'cat', '/etc/machine-id').strip()
        ssh_key = self.remote(client, 'cat /etc/machine-id')
        if usb_key != ssh_key: raise RuntimeError('USB Frame and SSH Frame do not match')
        home = self.remote(client, 'printf %s "$HOME"')
        storage=select_storage(self.storage_locations(client),storage_id)
        anchor=home+'/Applications/quest-frame/'+package
        base = storage['mount'] + '/Applications/quest-frame/' + package
        q = shlex.quote
        launcher = anchor + '/launch.sh'; exe = '"' + launcher + '"'
        ident = app_id(exe, game['title'])
        # Existing IDs must survive title changes; use the previous deployment metadata.
        old = self.remote(client, f'cat {q(anchor + "/deployment.json")}', check=False)
        try: old_deployment=json.loads(old)
        except ValueError: old_deployment={}
        if old_deployment and old_deployment.get('storage_uuid','')!=storage['uuid']:
            raise RuntimeError('Game already installed on a different storage device. Choose its existing location; moving existing games/saves is not supported automatically.')
        if old_deployment.get('appid'):ident=int(old_deployment['appid'])
        if storage['uuid'] and not old_deployment:
            if self.remote(client,'test -d '+q(anchor+'/lepton-app')+' && echo EXISTS',check=False):
                raise RuntimeError('Existing internal game found. Select internal storage to preserve its saves.')
        running = self.remote(client, f'podman ps --format "{{{{.Names}}}}"', check=False)
        if f'lepton-steamlaunch-{ident}' in running.splitlines():
            raise RuntimeError('Close this game on Frame before updating it. Other games will not be stopped.')
        lepton = home + '/.local/share/Steam/steamapps/common/Lepton/lepton'
        self.remote(client, f'test -x {q(lepton)}')
        required = (folder / 'game.apk').stat().st_size + sum(p.stat().st_size for p in obb_source.rglob('*') if p.is_file())
        required += sum(p.stat().st_size for p in data_source.rglob('*') if p.is_file())
        if storage['free'] < required*2 + 512*1024**2: raise RuntimeError('Not enough free space on selected storage for safe staged deployment')
        stamp = time.strftime('%Y%m%d-%H%M%S')
        stage = base + '/staging-' + stamp
        if storage['uuid']:
            self.remote(client,'mountpoint -q -- '+q(storage['mount']))
        self.remote(client, f'mkdir -p {q(anchor)} {q(stage + "/obb")} {q(base + "/lepton-data/external/Android/data/" + package + "/files")}')
        self.log('Installing over USB ADB (APK + expansion data). Keep Frame connected…')
        self.adb_run('frame', 'push', '-Z', folder / 'game.apk', stage + '/game.apk')
        for file in obb_source.rglob('*'):
            if file.is_file():
                relative = file.relative_to(obb_source).as_posix()
                dest = stage + '/obb/' + relative
                self.remote(client, 'mkdir -p ' + q(str(PurePosixPath(dest).parent)))
                self.adb_run('frame', 'push', '-Z', file, dest)
                actual = self.remote(client, 'sha256sum ' + q(dest)).split()[0]
                if actual != digest(file): raise RuntimeError('OBB verification failed; previous installation untouched')
        if self.remote(client, 'sha256sum ' + q(stage + '/game.apk')).split()[0] != game['sha256']:
            raise RuntimeError('APK transfer verification failed; previous installation untouched')
        # Never overwrite Frame progress with an older Quest save on a repeat install.
        data_root = base + '/lepton-data/external/Android/data/' + package
        for file in data_source.rglob('*'):
            if not file.is_file(): continue
            relative = file.relative_to(data_source).as_posix()
            if relative == 'files/framebridge.conf': continue
            destination = data_root + '/' + relative
            exists = self.remote(client, f'if test -e {q(destination)}; then echo EXISTS; fi')
            if exists: continue
            self.remote(client, 'mkdir -p ' + q(str(PurePosixPath(destination).parent)))
            self.adb_run('frame', 'push', file, destination)
        self.put_text(client, data_root + '/files/framebridge.conf', settings_text(game['scale'], game['controllers'], game['foveation']))
        self.put_text(client, base + '/settings.conf', settings_text(game['scale'], game['controllers'], game['foveation']))
        # Preserve all prior application and baked private data on updates.
        self.remote(client, f'if test -d {q(base + "/lepton-app")}; then mv {q(base + "/lepton-app")} {q(base + "/previous-app-" + stamp)}; fi; mv {q(stage)} {q(base + "/lepton-app")}')
        self.remote(client, f'if test -d {q(base + "/lepton-data/baked")}; then cp -a --reflink=auto {q(base + "/lepton-data/baked")} {q(base + "/previous-baked-" + stamp)}; fi')
        script = launcher_text(base, ident, lepton,card_launcher(storage['uuid'],package) if storage['uuid'] else '')
        self.put_text(client, launcher, script)
        self.remote(client, 'chmod 755 ' + q(launcher))
        deployment={'remote':base,'anchor':anchor,'appid':ident,'package':package,'storage_uuid':storage['uuid']}
        write_json(folder / 'deployment.json',deployment)
        self.put_text(client, anchor + '/deployment.json', json.dumps(deployment))
        if add_steam:
            arts = self.artwork(artwork_id or game['steam_id'], folder / 'artwork') if (artwork_id or game['steam_id']) else {}
            self.add_shortcut(client, anchor, game['title'], ident, arts)
        self.log('Installed. Launch from Steam; Lepton initializes the dedicated Android container on first launch.')
        return base, ident

    def add_shortcut(self, client, base, title, expected_id, arts):
        q = shlex.quote
        home = self.remote(client, 'printf %s "$HOME"')
        steam = home + '/.local/share/Steam'
        with client.open_sftp() as sftp:
            users = [n for n in sftp.listdir(steam + '/userdata') if n != '0' and n.isdigit()]
            if len(users) != 1: raise RuntimeError('Multiple/no Steam users found; game installed, but select a Steam account manually before adding its shortcut.')
        config = steam + '/userdata/' + users[0] + '/config'
        self.log('Closing Steam briefly to update its library safely. It will restart afterward.')
        service = self.remote(client, 'systemctl --user is-active steam.service', check=False) == 'active'
        if service: self.remote(client, 'systemctl --user stop steam.service')
        else: self.remote(client, 'steam -shutdown >/dev/null 2>&1', check=False)
        for _ in range(40):
            if not self.remote(client, 'pgrep -x steam', check=False): break
            time.sleep(1)
        else:
            if service: self.remote(client, 'systemctl --user start steam.service', check=False)
            raise RuntimeError('Steam did not close; library not modified. Close it and retry.')
        try:
            self.remote(client, 'mkdir -p ' + q(config + '/grid'))
            with client.open_sftp() as sftp:
                path = config + '/shortcuts.vdf'
                try:
                    with sftp.file(path, 'rb') as f: original = f.read()
                except FileNotFoundError: original = b''
                icon = base + '/artwork/' + arts.get('logo', arts.get('landscape', Path(''))).name if arts else ''
                updated, ident = upsert(original, '"' + base + '/launch.sh"', title, base, icon)
                if ident != expected_id: raise RuntimeError('Existing Steam shortcut ID differs from launcher; library not modified')
                if original:
                    with sftp.file(path + '.backup-' + time.strftime('%Y%m%d-%H%M%S'), 'wb') as f: f.write(original)
                with sftp.file(path + '.quest-frame.tmp', 'wb') as f: f.write(updated)
                sftp.posix_rename(path + '.quest-frame.tmp', path)
                self.remote(client, 'mkdir -p ' + q(base + '/artwork'))
                suffixes = {'portrait': 'p', 'landscape': '', 'hero': '_hero', 'logo': '_logo'}
                for kind, local in arts.items():
                    dest = config + '/grid/' + str(ident) + suffixes[kind] + local.suffix
                    try: sftp.stat(dest)
                    except FileNotFoundError: pass
                    else: sftp.posix_rename(dest, dest + '.backup-' + time.strftime('%Y%m%d-%H%M%S'))
                    sftp.put(str(local), dest)
                    sftp.put(str(local), base + '/artwork/' + local.name)
            self.log(f'Steam VR shortcut added: {title} ({ident}); {len(arts)} artwork assets.')
        finally:
            if service: self.remote(client, 'systemctl --user start steam.service', check=False)
            else: self.remote(client, 'systemd-run --user --collect --unit=quest-frame-steam-' + str(int(time.time())) + ' /usr/bin/steam', check=False)

    def update_settings(self, folder, client, scale, controllers, foveation):
        folder = Path(folder)
        deployment = json.loads((folder / 'deployment.json').read_text())
        package = valid_package(deployment['package'])
        base=self.deployment_base(client,deployment)
        path = base + '/lepton-data/external/Android/data/' + package + '/files/framebridge.conf'
        self.put_text(client, path, settings_text(scale, controllers, foveation))
        self.put_text(client, base + '/settings.conf', settings_text(scale, controllers, foveation))
        game = json.loads((folder / 'game.json').read_text())
        game.update(scale=float(scale), controllers=bool(controllers), foveation=bool(foveation))
        write_json(folder / 'game.json', game)
        self.log('Resolution/settings saved. Restart the game to apply. No APK rebuild is needed.')
