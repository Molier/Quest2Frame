# SPDX-License-Identifier: GPL-3.0-only
"""Build an opt-in experimental passthrough APK. Does not deploy or alter inputs."""
import argparse
from pathlib import Path
import re
import struct
import zipfile

from bridge import Bridge, ROOT, valid_package


def rename_soname(data, expected=b'libopenxr_loader.so', replacement=b'libq2f_original.so'):
    """Rename only DT_SONAME in an ELF64 LE library, without relocating sections."""
    if data[:6] != b'\x7fELF\x02\x01' or len(replacement) > len(expected):
        raise ValueError('Expected ELF64 little-endian and a non-growing SONAME')
    data = bytearray(data)
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    segments = [struct.unpack_from('<IIQQQQQQ', data, offset+i*size) for i in range(count)]
    dynamic = next(p for p in segments if p[0] == 2)
    tags = {}
    for pos in range(dynamic[2], dynamic[2]+dynamic[5], 16):
        tag, value = struct.unpack_from('<QQ', data, pos)
        if not tag:
            break
        tags[tag] = value
    address = tags[5]+tags[14]
    segment = next(p for p in segments if p[0] == 1 and p[3] <= address < p[3]+p[5])
    start = segment[2]+address-segment[3]
    end = data.index(0, start)
    if data[start:end] != expected:
        raise ValueError('Unexpected original SONAME; refusing to patch')
    data[start:end+1] = replacement + b'\0'*(end-start+1-len(replacement))
    return bytes(data)


def build(apk, output, bridge=None):
    apk = Path(apk).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    bridge = bridge or Bridge()
    java, _, tools, clang = bridge.toolchain()
    if not clang:
        raise RuntimeError('Android NDK is required')
    badging = bridge.run([tools/'aapt.exe', 'dump', 'badging', apk])
    package = valid_package(re.search(r"package: name='([^']+)'", badging)[1])
    prefix = 'lib/arm64-v8a/'
    with zipfile.ZipFile(apk) as archive:
        if prefix+'libq2f_original.so' in archive.namelist():
            raise ValueError('Input already contains the experimental adapter')
        (output/'libq2f_original.so').write_bytes(rename_soname(archive.read(prefix+'libopenxr_loader.so')))
    adapter = output/'libopenxr_loader.so'
    bridge.run([clang, '--target=aarch64-linux-android29',
                f'--sysroot={clang.parent.parent / "sysroot"}', '-shared', '-fPIC', '-O2',
                '-Wall', '-Wextra', '-Werror', '-Wl,-Bsymbolic', '-Wl,-z,max-page-size=16384',
                '-Wl,-soname,libopenxr_loader.so', '-I', ROOT/'native/include',
                ROOT/'native/passthrough_bridge.c', '-Wl,--no-as-needed',
                output/'libq2f_original.so', '-ldl', '-llog', '-o', adapter])
    with zipfile.ZipFile(apk) as src, zipfile.ZipFile(output/'unsigned.apk', 'w', zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename.startswith('META-INF/') or item.filename == prefix+'libopenxr_loader.so':
                continue
            dst.writestr(item, src.read(item.filename))
        dst.write(adapter, prefix+adapter.name)
        dst.write(output/'libq2f_original.so', prefix+'libq2f_original.so')
    bridge.run([tools/'zipalign.exe', '-f', '-P', '16', '4', output/'unsigned.apk', output/'aligned.apk'])
    key = ROOT/'tools/ovrport-workspace/signatures'/f'{package}.keystore'
    bridge.run([java, '-jar', tools/'lib/apksigner.jar', 'sign', '--ks', key,
                '--ks-pass', 'pass:password', '--out', output/'game.apk', output/'aligned.apk'])
    bridge.run([java, '-jar', tools/'lib/apksigner.jar', 'verify', '--verbose', output/'game.apk'])
    print(f'Experimental APK: {output / "game.apk"}. Original APK unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('output', type=Path, help='New directory; must not exist')
    args = parser.parse_args()
    build(args.apk, args.output)
