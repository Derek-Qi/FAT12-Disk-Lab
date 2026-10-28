"""Exhaustive value-space checks against a 24-bit FAT12 pair oracle."""
import unittest

from fat12lab import FAT12


class Fat12PackingOracleTests(unittest.TestCase):
    def test_every_12_bit_value_and_adjacent_entry(self):
        fs = FAT12.create()
        # Cluster 341 begins at FAT byte 511 and spans a sector boundary.
        for even in (2, 340):
            offset = even * 3 // 2
            for target_is_odd in (False, True):
                target = even + target_is_odd
                neighbour = even + (not target_is_odd)
                for neighbour_value in (0x000, 0x5A3, 0xFFF):
                    for value in range(4096):
                        initial_even = neighbour_value if target_is_odd else 0xA5C
                        initial_odd = 0xA5C if target_is_odd else neighbour_value
                        initial = (initial_even | initial_odd << 12).to_bytes(3, 'little')
                        expected_even = neighbour_value if target_is_odd else value
                        expected_odd = value if target_is_odd else neighbour_value
                        expected = (expected_even | expected_odd << 12).to_bytes(3, 'little')
                        bases = [(fs.layout.reserved + copy * fs.layout.fat_sectors) * 512 + offset
                                 for copy in (0, 1)]
                        for base in bases:
                            fs.data[base-1:base+4] = b'\x96' + initial + b'\x69'
                        fs._fat_set(target, value)
                        for copy, base in enumerate(bases):
                            actual = bytes(fs.data[base-1:base+4])
                            if actual != b'\x96' + expected + b'\x69':
                                self.fail(f'raw FAT mismatch: cluster={target}, value={value:#x}, '
                                          f'neighbour={neighbour_value:#x}, copy={copy}')
                            self.assertEqual(fs.fat_get(target, copy), value)
                            self.assertEqual(fs.fat_get(neighbour, copy), neighbour_value)


if __name__ == '__main__':
    unittest.main()
