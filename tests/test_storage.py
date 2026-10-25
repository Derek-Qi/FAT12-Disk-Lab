import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fat12lab import FAT12, FATError


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'shared.img'
        self.fs=FAT12.create(self.path)

    def tearDown(self):self.folder.cleanup()

    def test_stale_writer_cannot_overwrite_newer_image(self):
        stale=FAT12.open(self.path)
        self.fs.write_file('/FIRST.TXT',b'newer state')
        before=self.path.read_bytes();memory=bytes(stale.data)
        with self.assertRaises(OSError):stale.write_file('/LOST.TXT',b'stale write')
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(bytes(stale.data),memory)
        self.assertEqual(FAT12.open(self.path).read_file('/FIRST.TXT'),b'newer state')

    def test_create_never_overwrites_existing_image_by_default(self):
        self.fs.write_file('/A.TXT',b'preserved')
        before=self.path.read_bytes()
        with self.assertRaises(FATError):FAT12.create(self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_readonly_rejects_mutation_and_save(self):
        fs=FAT12.open(self.path,read_only=True);before=self.path.read_bytes()
        for operation in (lambda:fs.write_file('/NO.TXT',b'no'),fs.reformat,fs.save):
            with self.assertRaises(FATError):operation()
        self.assertTrue(fs.info()['read_only'])
        self.assertEqual(self.path.read_bytes(),before)

    def test_reload_reads_new_state_and_allows_next_write(self):
        stale=FAT12.open(self.path)
        self.fs.write_file('/FIRST.TXT',b'first')
        stale.reload()
        self.assertEqual(stale.read_file('/FIRST.TXT'),b'first')
        stale.write_file('/NEXT.TXT',b'next')
        self.assertEqual(FAT12.open(self.path).read_file('/NEXT.TXT'),b'next')

    def test_invalid_reload_keeps_previous_memory(self):
        before=bytes(self.fs.data)
        self.path.write_bytes(b'not a disk')
        with self.assertRaises(FATError):self.fs.reload()
        self.assertEqual(bytes(self.fs.data),before)

    def test_reload_exposes_bpb_valid_damage_for_diagnosis_and_recovery(self):
        healthy=bytes(self.fs.data);item=self.fs.create_snapshot('healthy')
        damaged=bytearray(healthy);damaged[self.fs.layout.reserved*512+3]^=1
        self.path.write_bytes(damaged)
        self.fs.reload()
        self.assertEqual(bytes(self.fs.data),damaged)
        self.assertFalse(self.fs.check()['ok'])
        with self.assertRaises(FATError):self.fs.write_file('/NO.TXT',b'no')
        self.fs.restore_snapshot(item['id'])
        self.assertEqual(self.path.read_bytes(),healthy)

    def test_lock_is_released_when_writer_process_dies(self):
        code='from fat12lab.storage import image_lock; import sys;\nwith image_lock(sys.argv[1]):\n print("locked",flush=True)\n sys.stdin.readline()'
        process=subprocess.Popen([sys.executable,'-u','-c',code,str(self.path)],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'locked')
            before=self.path.read_bytes()
            with self.assertRaises(OSError):self.fs.write_file('/BLOCK.TXT',b'blocked')
            self.assertEqual(self.path.read_bytes(),before)
            process.kill();process.wait(timeout=10)
            self.fs.write_file('/AFTER.TXT',b'released')
            self.assertEqual(FAT12.open(self.path).read_file('/AFTER.TXT'),b'released')
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=10)
            for stream in (process.stdin,process.stdout,process.stderr):stream.close()

    def exercise_terminated_commit(self, boundary):
        before=self.path.read_bytes()
        marker=Path(self.folder.name)/'checkpoint'
        code='''from pathlib import Path
import sys,time
from fat12lab import FAT12
from fat12lab import storage
original=storage.os.replace
def replace(source,target):
    if sys.argv[2]=='after': original(source,target)
    Path(sys.argv[3]).write_text('ready',encoding='ascii')
    time.sleep(30)
    if sys.argv[2]=='before': original(source,target)
storage.os.replace=replace
FAT12.open(sys.argv[1]).write_file('/COMMIT.TXT',b'committed payload')
'''
        child=subprocess.Popen([sys.executable,'-c',code,str(self.path),boundary,str(marker)],
                               stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+10
            while not marker.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(marker.exists(),'Child did not reach replacement boundary')
            child.kill();child.wait(timeout=10)
            reopened=FAT12.open(self.path)
            self.assertTrue(reopened.check()['ok'])
            if boundary=='before':self.assertEqual(self.path.read_bytes(),before)
            else:self.assertEqual(reopened.read_file('/COMMIT.TXT'),b'committed payload')
            reopened.write_file('/AFTER.TXT',b'lock released')
            self.assertEqual(FAT12.open(self.path).read_file('/AFTER.TXT'),b'lock released')
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=10)
            child.stderr.close()

    def test_process_termination_before_replace_preserves_previous_image(self):
        self.exercise_terminated_commit('before')

    def test_process_termination_after_replace_leaves_complete_new_image(self):
        self.exercise_terminated_commit('after')
