# SPDX-License-Identifier: GPL-3.0-only
"""Lossless binary Valve KeyValues for Steam shortcuts (unknown types fail closed)."""
import struct
import zlib

def decode(data):
    offset = 0
    def string():
        nonlocal offset
        end = data.index(b'\0', offset)
        result = data[offset:end].decode('utf-8', 'surrogateescape')
        offset = end + 1
        return result
    def obj():
        nonlocal offset
        result = {}
        while True:
            kind = data[offset]; offset += 1
            if kind == 8: return result
            key = string()
            if kind == 0: value = obj()
            elif kind == 1: value = string()
            elif kind == 2:
                value = struct.unpack_from('<I', data, offset)[0]; offset += 4
            else: raise ValueError(f'Unsupported VDF type {kind}; file has not been modified')
            if key in result: raise ValueError('Duplicate VDF keys; refusing lossy rewrite')
            result[key] = value
    result = obj()
    if any(b != 8 for b in data[offset:]): raise ValueError('Unexpected trailing VDF data')
    return result

def encode(obj):
    result = bytearray()
    def string(value): return value.encode('utf-8', 'surrogateescape') + b'\0'
    for key, value in obj.items():
        kind = 0 if isinstance(value, dict) else 1 if isinstance(value, str) else 2
        result.extend(bytes([kind]) + string(key))
        result.extend(encode(value) if kind == 0 else string(value) if kind == 1 else struct.pack('<I', value & 0xffffffff))
    return bytes(result) + b'\x08'

def app_id(exe, title):
    return zlib.crc32((exe + title).encode('utf-8')) | 0x80000000

def upsert(data, exe, title, directory, icon=''):
    root = decode(data) if data else {'shortcuts': {}}
    shortcuts = root.setdefault('shortcuts', {})
    existing = next((v for v in shortcuts.values() if v.get('Exe') == exe), None)
    ident = existing['appid'] if existing else app_id(exe, title)
    if existing is None:
        if any(v.get('appid') == ident for v in shortcuts.values()): raise ValueError('Shortcut ID collision')
        existing = {'appid': ident, 'LastPlayTime': 0, 'tags': {'0': 'Quest → Frame'}}
        index = str(max([int(k) for k in shortcuts] + [-1]) + 1)
        shortcuts[index] = existing
    existing.update(appname=title, Exe=exe, StartDir=directory, icon=icon,
                    ShortcutPath='', LaunchOptions='', IsHidden=0, AllowDesktopConfig=1,
                    AllowOverlay=1, OpenVR=1, Devkit=0, DevkitGameID='',
                    DevkitOverrideAppID=0, FlatpakAppID='')
    return encode(root), ident
