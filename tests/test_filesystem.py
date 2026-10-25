import random
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fat12lab import FAT12, FATError
from fat12lab.filesystem import CLUSTER_COUNT, IMAGE_SIZE, ROOT_SECTOR, encode_name
from fat12lab.shell import Shell


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.fs = FAT12.create()

    def assertHealthy(self):
        report = self.fs.check()
        self.assertTrue(report['ok'], report['errors'])

    def test_format_geometry_and_signature(self):
        data = self.fs.data
        self.assertEqual(len(data), IMAGE_SIZE)
        self.assertEqual(data[510:512], b'\x55\xaa')
        self.assertEqual(struct.unpack_from('<H', data, 11)[0], 512)
        self.assertEqual(data[13], 1)
        self.assertEqual(data[16], 2)
        self.assertEqual(struct.unpack_from('<H', data, 17)[0], 224)
        self.assertEqual(self.fs.info()['free_clusters'], 2847)
        self.assertEqual(data[512:515], b'\xf0\xff\xff')
        self.assertEqual(data[512:5120], data[5120:9728])
        self.assertEqual(data[ROOT_SECTOR * 512 + 11], 8)
        self.assertHealthy()

    def test_fat_packing_preserves_neighbor_and_sector_boundary(self):
        for even in (2, 340, 682, 2846):
            self.fs._fat_set(even, 0xABC)
            self.fs._fat_set(even + 1, 0xDEF)
            self.assertEqual(self.fs.fat_get(even), 0xABC)
            self.assertEqual(self.fs.fat_get(even + 1), 0xDEF)
            self.fs._fat_set(even, 0x123)
            self.assertEqual(self.fs.fat_get(even + 1), 0xDEF)
            self.assertEqual(self.fs.fat_get(even, 1), 0x123)

    def test_empty_file_allocates_no_cluster(self):
        self.fs.write_file('/EMPTY.TXT', b'')
        self.assertEqual(self.fs.stat('/EMPTY.TXT').cluster, 0)
        self.assertEqual(self.fs.read_file('/EMPTY.TXT'), b'')
        self.assertEqual(self.fs.info()['free_clusters'], 2847)

    def test_boundaries_and_binary_round_trip(self):
        for size in (1, 511, 512, 513, 1024, 1025, 4097):
            payload = bytes(i % 256 for i in range(size))
            self.fs.write_file('/BYTES.BIN', payload)
            entry = self.fs.stat('/BYTES.BIN')
            self.assertEqual(entry.size, size)
            self.assertEqual(len(self.fs.chain(entry.cluster)), (size + 511)//512)
            self.assertEqual(self.fs.read_file('/BYTES.BIN'), payload)
            self.assertHealthy()

    def test_utf8_and_case_insensitive_paths(self):
        self.fs.mkdir('/docs')
        content = ('操作系统 FAT12 中文内容\n' * 60).encode('utf-8')
        self.fs.write_file('/docs/hello.txt', content)
        self.assertEqual(self.fs.read_file('/DOCS/HeLLo.TxT'), content)

    def test_deleted_clusters_reused_and_fragmented_read(self):
        self.fs.write_file('/A.BIN', b'a'*1024)
        self.fs.write_file('/B.BIN', b'b'*512)
        self.fs.remove('/A.BIN')
        payload = b'x'*1537
        self.fs.write_file('/C.BIN', payload)
        self.assertEqual(self.fs.chain(self.fs.stat('/C.BIN').cluster), [2, 3, 5, 6])
        self.assertEqual(self.fs.read_file('/C.BIN'), payload)
        self.assertHealthy()

    def test_directory_growth_past_one_cluster(self):
        self.fs.mkdir('/D')
        for i in range(40):
            self.fs.write_file(f'/D/F{i}.TXT', str(i).encode())
        self.assertEqual(len(self.fs.list_dir('/D')), 40)
        self.assertEqual(len(self.fs.chain(self.fs.stat('/D').cluster)), 3)
        self.assertEqual(self.fs.read_file('/D/F39.TXT'), b'39')
        self.assertHealthy()

    def test_nested_directory_dotdot_and_nonempty_delete(self):
        self.fs.mkdir('/A')
        self.fs.mkdir('/A/B')
        self.fs.write_file('/A/B/X.TXT', b'x')
        before = bytes(self.fs.data)
        with self.assertRaises(FATError):
            self.fs.remove('/A', directory=True)
        self.assertEqual(before, self.fs.data)
        self.fs.remove('/A/B/X.TXT')
        self.fs.remove('/A/B', directory=True)
        self.fs.remove('/A', directory=True)
        self.assertEqual(self.fs.info()['free_clusters'], 2847)

    def test_copy_independent_chain_and_duplicate_rejection(self):
        self.fs.write_file('/A.TXT', b'original'*200)
        self.fs.copy('/A.TXT', '/B.TXT')
        a = self.fs.chain(self.fs.stat('/A.TXT').cluster)
        b = self.fs.chain(self.fs.stat('/B.TXT').cluster)
        self.assertFalse(set(a) & set(b))
        self.fs.write_file('/A.TXT', b'changed')
        self.assertEqual(self.fs.read_file('/B.TXT'), b'original'*200)
        with self.assertRaises(FATError):
            self.fs.copy('/A.TXT', '/B.TXT')

    def test_move_directory_updates_parent_and_prevents_cycle(self):
        self.fs.mkdir('/A')
        self.fs.mkdir('/B')
        self.fs.mkdir('/A/C')
        self.fs.write_file('/A/C/X.TXT', b'x')
        self.fs.move('/A/C', '/B/D')
        self.assertEqual(self.fs.read_file('/B/D/X.TXT'), b'x')
        self.assertHealthy()
        before = bytes(self.fs.data)
        with self.assertRaises(FATError):
            self.fs.move('/B', '/B/D/B')
        self.assertEqual(before, self.fs.data)

    def test_rename_uses_same_chain(self):
        self.fs.write_file('/A.TXT', b'abc'*500)
        chain = self.fs.chain(self.fs.stat('/A.TXT').cluster)
        self.fs.move('/A.TXT', '/B.TXT')
        self.assertEqual(self.fs.chain(self.fs.stat('/B.TXT').cluster), chain)
        with self.assertRaises(FATError):
            self.fs.stat('/A.TXT')

    def test_full_disk_and_overwrite_rollback(self):
        self.fs.write_file('/SMALL.BIN', b'old'*171)
        self.fs.write_file('/FULL.BIN', b'f'*(CLUSTER_COUNT-2)*512)
        before = bytes(self.fs.data)
        with self.assertRaises(FATError):
            self.fs.write_file('/SMALL.BIN', b'new'*1000)
        self.assertEqual(self.fs.data, before)
        self.assertEqual(self.fs.read_file('/SMALL.BIN'), b'old'*171)
        self.fs.write_file('/SMALL.BIN', b's'*1024)
        self.assertEqual(self.fs.info()['free_clusters'], 0)
        self.fs.write_file('/ZERO.TXT', b'')
        self.assertHealthy()

    def test_root_full_is_transactional(self):
        for i in range(223):
            self.fs.write_file(f'/F{i}.TXT', b'')
        before = bytes(self.fs.data)
        with self.assertRaises(FATError):
            self.fs.write_file('/FULL.TXT', b'x')
        self.assertEqual(before, self.fs.data)
        self.fs.remove('/F99.TXT')
        self.fs.write_file('/REUSED.TXT', b'x')
        self.assertHealthy()

    def test_invalid_names_and_geometry_rejected(self):
        for name in ('中文.TXT','ß.TXT','ſ.TXT','TOOLONGXX.TXT','A.LONG','A..B','A B.TXT','A.','.'):
            with self.assertRaises(FATError, msg=name):
                encode_name(name)
        for offset in (11,13,16,22,28,510):
            data = self.fs.data[:]
            data[offset] ^= 1
            with self.assertRaises(FATError):
                FAT12(data)
        data = self.fs.data[:]
        struct.pack_into('<H',data,17,0)
        with self.assertRaises(FATError):
            FAT12(data)
        with self.assertRaises(FATError):
            FAT12(bytes(1024))

    def test_advisory_chs_fields_do_not_change_sector_offsets(self):
        self.fs.write_file('/A.TXT',b'logical addressing')
        data=self.fs.data[:]
        struct.pack_into('<HH',data,24,0,0)
        loaded=FAT12(data)
        self.assertEqual(loaded.read_file('/A.TXT'),b'logical addressing')
        self.assertTrue(loaded.check()['ok'])

    def test_mirror_corruption_detected_and_mutation_refused(self):
        self.fs.data[5120 + 4] ^= 1
        self.assertIn('两份 FAT 副本不一致', self.fs.check()['errors'])
        before = bytes(self.fs.data)
        with self.assertRaises(FATError):
            self.fs.write_file('/X.TXT', b'x')
        self.assertEqual(before, self.fs.data)

    def test_cycle_bad_cluster_orphan_and_crosslink_detected(self):
        self.fs.write_file('/A.TXT', b'a'*1024)
        a = self.fs.stat('/A.TXT').cluster
        self.fs._fat_set(a+1,a)
        self.assertTrue(any('循环' in e for e in self.fs.check()['errors']))
        self.fs._fat_set(a+1,0xFF7)
        self.assertTrue(any('坏簇' in e for e in self.fs.check()['errors']))
        self.fs._fat_set(a+1,0xFFF)
        self.fs._fat_set(99,0xFFF)
        self.assertTrue(any('孤立簇 99' in e for e in self.fs.check()['errors']))
        self.fs._fat_set(99,0)
        self.fs.write_file('/B.TXT', b'b'*1024)
        b = self.fs.stat('/B.TXT')
        struct.pack_into('<H',self.fs.data,b.offset+26,a)
        self.assertTrue(any('交叉引用' in e for e in self.fs.check()['errors']))

    def test_persistence_and_save_failure_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'disk.img'
            fs=FAT12.create(path)
            fs.write_file('/PERSIST.TXT', b'persistent')
            reopened=FAT12.open(path)
            self.assertEqual(reopened.read_file('/PERSIST.TXT'),b'persistent')
            before=bytes(fs.data)
            with patch('fat12lab.storage.os.replace',side_effect=OSError('simulated replace failure')):
                with self.assertRaises(OSError):
                    fs.write_file('/PERSIST.TXT',b'lost?')
            self.assertEqual(fs.data,before)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(list(Path(tmp).glob('*.tmp')),[])

    def test_readonly_is_respected(self):
        self.fs.write_file('/R.TXT',b'readonly')
        self.fs.data[self.fs.stat('/R.TXT').offset+11]|=1
        for operation in (lambda:self.fs.remove('/R.TXT'),lambda:self.fs.write_file('/R.TXT',b'x'),lambda:self.fs.move('/R.TXT','/X.TXT')):
            with self.assertRaises(FATError):
                operation()

    def test_deterministic_random_operations_against_memory_model(self):
        rng=random.Random(20261003)
        model={}
        self.fs.mkdir('/DATA')
        for _ in range(180):
            name=f'/DATA/F{rng.randrange(25)}.BIN'
            action=rng.choice(('write','remove','copy','rename'))
            if action=='write':
                value=rng.randbytes(rng.randrange(0,2200))
                self.fs.write_file(name,value)
                model[name]=value
            elif action=='remove' and name in model:
                self.fs.remove(name)
                del model[name]
            elif action in ('copy','rename') and name in model:
                target=f'/DATA/F{rng.randrange(25)}.BIN'
                if target not in model:
                    if action=='copy':
                        self.fs.copy(name,target)
                        model[target]=model[name]
                    else:
                        self.fs.move(name,target)
                        model[target]=model.pop(name)
            self.assertHealthy()
            self.assertEqual({e.name for e in self.fs.list_dir('/DATA')},{p.rsplit('/',1)[-1] for p in model})
            for path,value in model.items():
                self.assertEqual(self.fs.read_file(path),value)


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.shell=Shell(FAT12.create())

    def test_commands_and_relative_paths(self):
        for command in ('mkdir D','cd D','write A.TXT "hello world"','append A.TXT "!"','copy A.TXT B.TXT','ren B.TXT C.TXT','cd ..','move D/C.TXT /C.TXT'):
            self.shell.execute(command)
        self.assertEqual(self.shell.execute('type /C.TXT'),'hello world!')
        self.assertEqual(self.shell.execute('pwd'),'/')
        self.assertIn('FSCK OK',self.shell.execute('fsck'))
        self.assertIn('C.TXT',self.shell.execute('tree'))

    def test_touch_preserves_existing_and_binary_type_rejects(self):
        self.shell.execute('write A.TXT "abc"')
        self.shell.execute('touch A.TXT')
        self.assertEqual(self.shell.execute('type A.TXT'),'abc')
        self.shell.fs.write_file('/BIN.DAT',b'\xff\x00')
        with self.assertRaises(FATError):
            self.shell.execute('type BIN.DAT')

    def test_move_current_directory_and_ancestor_delete(self):
        self.shell.execute('mkdir A')
        self.shell.execute('mkdir A/B')
        self.shell.execute('cd A/B')
        self.shell.execute('move /A /D')
        self.assertEqual(self.shell.cwd,'/D/B')
        with self.assertRaises(FATError):
            self.shell.execute('rmdir /D/B')

    def test_bad_parameters_and_host_io_disabled(self):
        for command in ('mkdir','type','unknown','fat -1 2','fat 0 129','sector 2880','write X.TXT "unterminated'):
            with self.assertRaises(FATError,msg=command):
                self.shell.execute(command)
        shell=Shell(self.shell.fs,allow_host_io=False)
        with self.assertRaises(FATError):
            shell.execute('import secret.txt A.TXT')


if __name__=='__main__':
    unittest.main()
