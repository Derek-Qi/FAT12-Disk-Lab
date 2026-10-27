import unittest

from fat12lab import FAT12
from fat12lab.filesystem import encode_name


class DirectoryMarkerTests(unittest.TestCase):
    @staticmethod
    def ghost():
        return b'GHOST   TXT'+b'\x20'+bytes(20)

    def test_new_entries_do_not_activate_data_after_directory_end(self):
        for operation in ('write','mkdir','move'):
            with self.subTest(operation=operation):
                fs=FAT12.create();root=fs.layout.root_sector*512
                end=root+32
                if operation=='move':
                    fs.mkdir('/SOURCE');fs.write_file('/SOURCE/A.TXT',b'a');end+=32
                fs.data[end+32:end+64]=self.ghost()
                self.assertTrue(fs.check()['ok'])
                if operation=='write':fs.write_file('/NEW.TXT',b'new')
                elif operation=='mkdir':fs.mkdir('/NEW')
                else:fs.move('/SOURCE/A.TXT','/NEW.TXT')
                self.assertNotIn('GHOST.TXT',[entry.name for entry in fs.list_dir()])
                self.assertEqual(fs.data[end+32],0)
                self.assertTrue(fs.check()['ok'])

    def test_end_marker_follows_logical_directory_chain_across_clusters(self):
        fs=FAT12.create();fs.mkdir('/DIR');fs.write_file('/BLOCK.BIN',b'keep this data')
        for index in range(15):fs.write_file(f'/DIR/F{index}.TXT',b'')
        fs.remove('/DIR/F13.TXT');fs.remove('/DIR/F14.TXT')
        cluster=fs.stat('/DIR').cluster;slots=fs._slots(cluster)
        self.assertNotEqual(slots[16],slots[15]+32)
        fs.data[slots[15]]=0;fs.data[slots[16]:slots[16]+32]=self.ghost()
        self.assertTrue(fs.check()['ok'])
        fs.write_file('/DIR/NEW.TXT',b'')
        self.assertEqual(len(fs.list_dir('/DIR')),14)
        self.assertEqual(fs.data[slots[16]],0)
        self.assertEqual(fs.read_file('/BLOCK.BIN'),b'keep this data')
        self.assertTrue(fs.check()['ok'])

    def test_reusing_deleted_slot_preserves_following_active_entries(self):
        fs=FAT12.create();fs.write_file('/FIRST.TXT',b'one');fs.write_file('/LAST.TXT',b'two')
        fs.remove('/FIRST.TXT');fs.write_file('/NEW.TXT',b'new')
        self.assertEqual({entry.name for entry in fs.list_dir()},{'NEW.TXT','LAST.TXT'})
        self.assertEqual(fs.read_file('/LAST.TXT'),b'two')

    def test_last_root_slot_does_not_overwrite_the_data_region(self):
        fs=FAT12.create();fs.write_file('/KEEP.BIN',b'keep data')
        start=fs.layout.root_sector*512
        for index in range(2,fs.layout.root_entries-1):
            offset=start+index*32
            fs.data[offset:offset+32]=fs._pack_entry(encode_name(f'F{index}.TXT'),0x20,0,0)
        fs.write_file('/LAST.TXT',b'')
        self.assertEqual(len(fs.list_dir()),fs.layout.root_entries-1)
        self.assertEqual(fs.read_file('/KEEP.BIN'),b'keep data')
        self.assertTrue(fs.check()['ok'])
