import struct
import tempfile
import unittest
from pathlib import Path

from fat12lab import FAT12, FATError
from fat12lab.filesystem import Layout
from fat12lab.server import disk_changes
from fat12lab.shell import Shell


class RegressionTests(unittest.TestCase):
    def test_unquoted_windows_image_path(self):
        fs=FAT12.create();fs.mkdir('/D');fs.write_file('/D/A.TXT',b'content')
        self.assertEqual(Shell(fs).execute(r'type D\A.TXT'),'content')

    def test_literal_backslashes_and_escaped_quotes_in_text(self):
        fs=FAT12.create();shell=Shell(fs)
        shell.execute(r'write A.TXT "one\\two and \"quote\""')
        self.assertEqual(fs.read_file('/A.TXT'),b'one\\\\two and "quote"')
        shell.execute('write EMPTY.TXT ""')
        self.assertEqual(fs.read_file('/EMPTY.TXT'),b'')

    def test_unquoted_host_path_import(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.bin';source.write_bytes(b'host data')
            fs=FAT12.create()
            Shell(fs).execute(f'import {source} DATA.BIN')
            self.assertEqual(fs.read_file('/DATA.BIN'),b'host data')

    def test_dot_entries_must_be_first_and_unique(self):
        for defect in ('misplaced','duplicate','size','high_cluster'):
            with self.subTest(defect=defect):
                fs=FAT12.create();fs.mkdir('/D')
                offset=fs.cluster_offset(fs.stat('/D').cluster)
                if defect=='misplaced':
                    fs.data[offset+64:offset+96]=fs.data[offset+32:offset+64]
                    fs.data[offset+32]=0xE5
                elif defect=='duplicate':
                    fs.data[offset+64:offset+96]=fs.data[offset:offset+32]
                elif defect=='size':struct.pack_into('<I',fs.data,offset+28,123)
                else:struct.pack_into('<H',fs.data,offset+20,1)
                self.assertFalse(fs.check()['ok'])
                before=bytes(fs.data)
                with self.assertRaises(FATError):fs.write_file('/A.TXT',b'refuse corrupt disk')
                self.assertEqual(bytes(fs.data),before)

    def test_same_size_layout_replacement_is_explicit(self):
        old=FAT12.create();new=FAT12.create(layout=Layout(sectors_per_cluster=2,fat_sectors=5))
        result=disk_changes(bytes(old.data),new)
        self.assertTrue(result['replaced'])
        self.assertEqual(result['reason'],'layout')
        self.assertEqual(result['regions'],{})

    def test_720kb_fat_range_prompt_matches_actual_layout(self):
        fs=FAT12.create(layout=Layout(1440,2,1,3,112,0xF9,9,2))
        with self.assertRaises(FATError) as caught:Shell(fs).execute('fat 715 1')
        self.assertIn('714',str(caught.exception))
        self.assertNotIn('2848',str(caught.exception))
