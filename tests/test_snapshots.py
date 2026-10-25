import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import uuid

from fat12lab import FAT12, FATError
from fat12lab.shell import Shell


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'disk.img';self.fs=FAT12.create(self.path)
        self.fs.write_file('/A.TXT',b'original')

    def tearDown(self):self.folder.cleanup()

    def test_restore_exact_bytes_and_creates_recovery_point(self):
        before=bytes(self.fs.data);item=self.fs.create_snapshot('中文 checkpoint')
        self.fs.write_file('/A.TXT',b'changed');changed=bytes(self.fs.data)
        self.fs.restore_snapshot(item['id'])
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.fs.read_file('/A.TXT'),b'original')
        remaining=[s for s in self.fs.list_snapshots() if s['id']!=item['id']]
        self.assertEqual(len(remaining),1)
        self.fs.restore_snapshot(remaining[0]['id'])
        self.assertEqual(self.path.read_bytes(),changed)

    def test_corrupt_payload_does_not_change_working_image(self):
        item=self.fs.create_snapshot('good')
        target=self.path.with_name('disk.img.snapshots')/(item['id']+'.img')
        data=bytearray(target.read_bytes());data[-1]^=1;target.write_bytes(data)
        before=self.path.read_bytes()
        with self.assertRaises((FATError,OSError)):self.fs.restore_snapshot(item['id'])
        self.assertEqual(self.path.read_bytes(),before)

    def test_traversal_identifier_is_rejected(self):
        before=self.path.read_bytes()
        for value in ('../disk','..\\disk','/disk','', 'a'*33):
            with self.subTest(value=value),self.assertRaises((FATError,OSError)):
                self.fs.restore_snapshot(value)
        self.assertEqual(self.path.read_bytes(),before)

    def test_metadata_validation_rejects_inconsistent_size(self):
        item=self.fs.create_snapshot('good')
        target=self.path.with_name('disk.img.snapshots')/(item['id']+'.json')
        metadata=json.loads(target.read_text(encoding='utf-8'));metadata['image_bytes']=1
        target.write_text(json.dumps(metadata),encoding='utf-8')
        with self.assertRaises((FATError,OSError)):self.fs.restore_snapshot(item['id'])

    def test_restore_save_failure_rolls_back_memory(self):
        item=self.fs.create_snapshot();self.fs.write_file('/A.TXT',b'current')
        before=bytes(self.fs.data)
        with patch('fat12lab.storage.os.replace',side_effect=OSError('replace failed')):
            with self.assertRaises(OSError):self.fs.restore_snapshot(item['id'])
        self.assertEqual(bytes(self.fs.data),before)
        self.assertEqual(self.path.read_bytes(),before)
        self.fs.write_file('/NEXT.TXT',b'next')

    def test_readonly_can_list_but_cannot_create_or_restore(self):
        item=self.fs.create_snapshot()
        readonly=FAT12.open(self.path,read_only=True)
        self.assertEqual(readonly.list_snapshots()[0]['id'],item['id'])
        with self.assertRaises(FATError):readonly.create_snapshot()
        with self.assertRaises(FATError):readonly.restore_snapshot(item['id'])

    def test_stale_snapshot_is_refused(self):
        other=FAT12.open(self.path);self.fs.write_file('/NEW.TXT',b'new')
        with self.assertRaises(OSError):other.create_snapshot()
        self.assertEqual(other.list_snapshots(),[])

    def test_snapshot_shell_commands(self):
        shell=Shell(self.fs);item=json.loads(shell.execute('snapshot "checkpoint"'))
        self.fs.remove('/A.TXT')
        shell.execute('restore '+item['id'])
        self.assertEqual(shell.execute('type A.TXT'),'original')
        self.assertIn('checkpoint',shell.execute('snapshots'))

    def test_identifier_collision_preserves_existing_snapshot(self):
        item=self.fs.create_snapshot('original checkpoint')
        with patch('fat12lab.snapshots.uuid.uuid4',return_value=uuid.UUID(item['id'])):
            with self.assertRaises(OSError):self.fs.create_snapshot('collision')
        self.fs.write_file('/A.TXT',b'changed')
        self.fs.restore_snapshot(item['id'])
        self.assertEqual(self.fs.read_file('/A.TXT'),b'original')

    def test_format_creates_recovery_point_for_healthy_disk(self):
        before=bytes(self.fs.data)
        self.fs.reformat('EMPTY')
        items=self.fs.list_snapshots()
        self.assertEqual(len(items),1)
        self.assertEqual(self.fs.list_dir(),[])
        self.fs.restore_snapshot(items[0]['id'])
        self.assertEqual(self.path.read_bytes(),before)

    def test_restore_repairs_damaged_fat_and_preserves_raw_protection_point(self):
        healthy=bytes(self.fs.data);item=self.fs.create_snapshot('healthy')
        damaged=bytearray(healthy);damaged[self.fs.layout.reserved*512+3]^=1
        self.path.write_bytes(damaged)
        broken=FAT12.open(self.path)
        self.assertFalse(broken.check()['ok'])
        broken.restore_snapshot(item['id'])
        self.assertEqual(self.path.read_bytes(),healthy)
        self.assertTrue(broken.check()['ok'])
        protection=next(s for s in broken.list_snapshots() if s['id']!=item['id'])
        self.assertFalse(protection['restorable'])
        raw=self.path.with_name('disk.img.snapshots')/(protection['id']+'.img')
        self.assertEqual(raw.read_bytes(),damaged)
        with self.assertRaises((FATError,OSError)):broken.restore_snapshot(protection['id'])
        self.assertEqual(self.path.read_bytes(),healthy)

    def test_snapshot_root_link_is_rejected_before_writing_or_listing(self):
        outside=Path(self.folder.name)/'outside';outside.mkdir()
        link=self.path.with_name('disk.img.snapshots')
        if os.name=='nt':
            result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],
                                  capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode,0,result.stderr)
        else:
            link.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError):self.fs.create_snapshot('must stay beside image')
        with self.assertRaises(OSError):self.fs.list_snapshots()
        self.assertEqual(list(outside.iterdir()),[])

    def test_metadata_rejects_non_boolean_restorable_flag(self):
        item=self.fs.create_snapshot('good')
        target=self.path.with_name('disk.img.snapshots')/(item['id']+'.json')
        metadata=json.loads(target.read_text(encoding='utf-8'));metadata['restorable']='false'
        target.write_text(json.dumps(metadata),encoding='utf-8')
        with self.assertRaises(OSError):self.fs.restore_snapshot(item['id'])
