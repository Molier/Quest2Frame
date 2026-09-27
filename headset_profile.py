# SPDX-License-Identifier: GPL-3.0-only
"""Version-checked, build-time identity overrides. Never patch shared downloads."""
import hashlib
import re
import struct

PROFILES = ('Default', 'Quest 2', 'Quest 3')
OVR_HASH = '7fdf5cebc25956a5456637261e660de177c1daaa97413602c653ccb42326765b'
# Model UUIDs used by the pinned OVRPlugin's headset-type lookup (9 and 11).
QUEST2_ID = struct.pack('<8H', 25648, 14834, 60693, 8775, 22950, 41310, 55532, 49817)
QUEST3_ID = struct.pack('<8H', 9992, 47686, 29088, 63308, 34703, 57018, 52828, 52803)

def headset_value(value='Default'):
    if value not in PROFILES:
        raise ValueError('Reported headset must be Default, Quest 2, or Quest 3')
    return value

def patch_runtime(data, profile):
    """Accept only the pinned runtime, including its SONAME-only passthrough variant."""
    headset_value(profile)
    if profile == 'Default': return data
    normalized = data
    if hashlib.sha256(normalized).hexdigest() != OVR_HASH:
        # Normalize the exact same-size SONAME substitution, then verify the
        # entire library hash, not just a byte pattern or its version string.
        normalized = data.replace(b'libq2f_original.so\0\0', b'libopenxr_loader.so\0')
    if hashlib.sha256(normalized).hexdigest() != OVR_HASH:
        raise ValueError('Unsupported OVR Port runtime; identity override refused')
    if data.count(QUEST2_ID) != 1 or data.count(b'Oculus Quest2\0') != 1:
        raise ValueError('Unexpected headset identity layout; refusing to patch')
    if profile == 'Quest 2': return data
    return data.replace(QUEST2_ID, QUEST3_ID).replace(b'Oculus Quest2\0', b'Meta Quest 3\0\0')

def patch_unreal_smali(text):
    # Limit changes to the two UE GameActivity classes, selected by the caller.
    # OVR Port replaces Build.MODEL reads with this exact constant.
    return re.sub(r'(\bconst-string(?:/jumbo)?\s+[vp]\d+,\s*)"Quest 2"',
                  r'\1"Quest 3"', text)
