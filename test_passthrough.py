# SPDX-License-Identifier: GPL-3.0-only
import struct
import unittest

from build_passthrough import rename_soname


class SonameTests(unittest.TestCase):
    def library(self):
        data = bytearray(512)
        data[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HH', data, 54, 56, 2)
        struct.pack_into('<IIQQQQQQ', data, 64, 1, 4, 0, 0x1000, 0, 512, 512, 16)
        struct.pack_into('<IIQQQQQQ', data, 120, 2, 4, 192, 0x10c0, 0, 48, 48, 16)
        struct.pack_into('<QQQQQQ', data, 192, 5, 0x1100, 14, 16, 0, 0)
        data[272:292] = b'libopenxr_loader.so\0'
        # Another occurrence must not be changed (e.g. a dependency or diagnostic string).
        data[320:340] = b'libopenxr_loader.so\0'
        return bytes(data)

    def test_only_soname_changed_and_size_preserved(self):
        original = self.library()
        patched = rename_soname(original)
        self.assertEqual(len(original), len(patched))
        self.assertEqual(patched[272:292], b'libq2f_original.so\0\0')
        self.assertEqual(patched[320:340], b'libopenxr_loader.so\0')
        self.assertEqual(patched[:272], original[:272])
        self.assertEqual(patched[292:], original[292:])

    def test_reject_already_patched(self):
        with self.assertRaises(ValueError):
            rename_soname(rename_soname(self.library()))

    def test_reject_wrong_elf(self):
        with self.assertRaises(ValueError):
            rename_soname(b'not an ELF')

    def test_reject_long_name(self):
        with self.assertRaises(ValueError):
            rename_soname(self.library(), replacement=b'x'*40)


if __name__ == '__main__':
    unittest.main()
