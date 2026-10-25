import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from fat12lab import FAT12, FATError
from fat12lab.filesystem import Layout
from fat12lab.shell import Shell


LAYOUTS=(Layout(),Layout(total_sectors=1440,sectors_per_cluster=2,fat_sectors=3,
                        root_entries=112,media=0xF9,sectors_per_track=9))


def populate(fs):
    fs.mkdir('/BOX');fs.mkdir('/BOX/NEST')
    fs.write_file('/GAP.BIN',b'g'*fs.layout.cluster_bytes)
    fs.write_file('/KEEP.BIN',b'keep')
    fs.write_file('/BOX/NEST/A.BIN',bytes(range(256))*9)
    fs.remove('/GAP.BIN')
    fs.write_file('/BOX/NEST/A.BIN',bytes(range(256))*13)
    fs.write_file('/EMPTY.TXT',b'')


def contents_and_metadata(fs):
    result={};pending=['/']
    while pending:
        path=pending.pop()
        for entry in fs.list_dir(path):
            full=path.rstrip('/')+'/'+entry.name
            raw=bytes(fs.data[entry.offset:entry.offset+32])
            result[full]=(entry.is_dir,raw[:26]+raw[28:],
                          None if entry.is_dir else hashlib.sha256(fs.read_file(full)).hexdigest())
            if entry.is_dir:pending.append(full)
    return result


class AllocationTests(unittest.TestCase):
    def test_shared_shell_analysis_preview_and_apply(self):
        fs=FAT12.create();populate(fs);shell=Shell(fs);before=bytes(fs.data)
        analysis=json.loads(shell.execute('analyze'))
        plan=json.loads(shell.execute('defrag --dry-run'))
        self.assertTrue(analysis['check']['ok']);self.assertEqual(bytes(fs.data),before)
        result=json.loads(shell.execute('defrag '+plan['image_sha256']))
        self.assertEqual(result['after']['fragmented_files'],0)
        self.assertTrue(fs.check()['ok'])

    def test_analysis_is_readonly_and_reports_fragmentation_and_slack(self):
        fs=FAT12.create();populate(fs);before=bytes(fs.data)
        report=fs.analyze()
        row=next(item for item in report['objects'] if item['path']=='/BOX/NEST/A.BIN')
        self.assertTrue(report['check']['ok'])
        self.assertEqual(row['extents'],2)
        self.assertEqual(row['logical_bytes'],3328)
        self.assertEqual(row['slack_bytes'],256)
        self.assertEqual(report['summary']['logical_bytes'],3332)
        self.assertEqual(report['summary']['slack_bytes'],764)
        self.assertEqual(report['summary']['fragmented_files'],1)
        self.assertEqual(report['image_sha256'],hashlib.sha256(before).hexdigest())
        self.assertEqual(bytes(fs.data),before)

    def test_compaction_preserves_contents_metadata_and_geometry_for_both_layouts(self):
        for layout in LAYOUTS:
            with self.subTest(cluster_bytes=layout.cluster_bytes):
                fs=FAT12.create(layout=layout);populate(fs)
                entry=fs.stat('/KEEP.BIN');fs.data[entry.offset+11]=0x27
                expected=contents_and_metadata(fs);boot=bytes(fs.data[:layout.reserved*512])
                before=bytes(fs.data);plan=fs.plan_defragmentation()
                self.assertGreater(plan['moved_clusters'],0)
                self.assertEqual(plan,fs.plan_defragmentation())
                self.assertEqual(bytes(fs.data),before)
                result=fs.defragment(plan['image_sha256'])
                self.assertEqual(result['after']['fragmented_files'],0)
                self.assertEqual(contents_and_metadata(fs),expected)
                self.assertEqual(fs.layout,layout)
                self.assertEqual(bytes(fs.data[:layout.reserved*512]),boot)
                self.assertTrue(fs.check()['ok'],fs.check())
                self.assertEqual(fs.plan_defragmentation()['moved_clusters'],0)
                after=bytes(fs.data)
                with self.assertRaises(FATError):fs.defragment(hashlib.sha256(after).hexdigest())
                self.assertEqual(bytes(fs.data),after)

    def test_expanded_nested_directory_dot_references_are_relocated(self):
        fs=FAT12.create();fs.write_file('/HOLE.BIN',b'hole')
        fs.mkdir('/TREE');fs.mkdir('/TREE/CHILD')
        for index in range(40):
            fs.write_file(f'/TREE/E{index}.BIN',bytes([index])*513)
        fs.remove('/HOLE.BIN');expected=contents_and_metadata(fs)
        self.assertGreater(len(fs.chain(fs.stat('/TREE').cluster)),1)
        plan=fs.plan_defragmentation();fs.defragment(plan['image_sha256'])
        self.assertEqual(contents_and_metadata(fs),expected)
        self.assertTrue(fs.check()['ok'],fs.check())
        tree=fs.stat('/TREE').cluster;child=fs.stat('/TREE/CHILD').cluster
        dots={e.name:e.cluster for e in fs._entries(child,include_dots=True)}
        self.assertEqual(dots,{'.':child,'..':tree})

    def test_bad_cluster_marker_and_bytes_are_preserved(self):
        fs=FAT12.create();fs._fat_set(3,0xFF7)
        offset=fs.cluster_offset(3);bad_bytes=b'x'*fs.layout.cluster_bytes
        fs.data[offset:offset+len(bad_bytes)]=bad_bytes
        fs.write_file('/Z.BIN',b'z'*1024);fs.write_file('/A.BIN',b'a'*1024)
        expected=contents_and_metadata(fs);plan=fs.plan_defragmentation()
        self.assertFalse(any(row['to']==3 for row in plan['mapping']))
        fs.defragment(plan['image_sha256'])
        self.assertEqual(fs.fat_get(3),0xFF7);self.assertEqual(fs.fat_get(3,1),0xFF7)
        self.assertEqual(bytes(fs.data[offset:offset+len(bad_bytes)]),bad_bytes)
        self.assertEqual(contents_and_metadata(fs),expected)
        self.assertEqual(fs.analyze()['summary']['bad_clusters'],1)
        self.assertEqual(fs.analyze()['summary'],plan['after'])

    def test_plan_with_no_allocations_is_noop_and_creates_no_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            fs=FAT12.create(Path(folder)/'empty.img');before=bytes(fs.data)
            plan=fs.plan_defragmentation()
            self.assertEqual(plan['moved_clusters'],0)
            self.assertEqual(plan['before']['largest_free_run'],fs.layout.cluster_count)
            with self.assertRaises(FATError):fs.defragment(plan['image_sha256'])
            self.assertEqual(fs.list_snapshots(),[])
            self.assertEqual(bytes(fs.data),before)

    def test_stale_preview_is_rejected_without_mutation(self):
        fs=FAT12.create();populate(fs);plan=fs.plan_defragmentation()
        fs.write_file('/NEXT.TXT',b'new state');before=bytes(fs.data)
        with self.assertRaises(FATError):fs.defragment(plan['image_sha256'])
        self.assertEqual(bytes(fs.data),before)

    def test_readonly_allows_analysis_and_preview_but_refuses_apply(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'read.img';fs=FAT12.create(path);populate(fs)
            fs=FAT12.open(path,read_only=True);before=path.read_bytes()
            self.assertTrue(fs.analyze()['check']['ok'])
            plan=fs.plan_defragmentation()
            with self.assertRaises(FATError):fs.defragment(plan['image_sha256'])
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(fs.list_snapshots(),[])

    def test_corruption_is_reported_and_compaction_is_refused(self):
        fs=FAT12.create();populate(fs);fs.data[fs.layout.reserved*512+3]^=1
        before=bytes(fs.data)
        self.assertFalse(fs.analyze()['check']['ok'])
        with self.assertRaises(FATError):fs.plan_defragmentation()
        with self.assertRaises(FATError):fs.defragment(hashlib.sha256(before).hexdigest())
        self.assertEqual(bytes(fs.data),before)

    def test_persisted_compaction_has_an_exact_restorable_protection_point(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'disk.img';fs=FAT12.create(path);populate(fs)
            before=path.read_bytes();expected=contents_and_metadata(fs)
            fs.defragment(fs.plan_defragmentation()['image_sha256'])
            self.assertEqual(contents_and_metadata(FAT12.open(path)),expected)
            snapshots=fs.list_snapshots();self.assertEqual(len(snapshots),1)
            fs.restore_snapshot(snapshots[0]['id'])
            self.assertEqual(path.read_bytes(),before)

    def test_compaction_save_failure_rolls_back_memory_and_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'disk.img';fs=FAT12.create(path);populate(fs)
            before=path.read_bytes();plan=fs.plan_defragmentation()
            with patch('fat12lab.storage.os.replace',side_effect=OSError('injected save failure')):
                with self.assertRaises(OSError):fs.defragment(plan['image_sha256'])
            self.assertEqual(bytes(fs.data),before);self.assertEqual(path.read_bytes(),before)
            self.assertEqual(len(fs.list_snapshots()),1)
            fs.defragment(plan['image_sha256'])
            self.assertTrue(FAT12.open(path).check()['ok'])

    def test_competing_writer_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'shared.img';fs=FAT12.create(path);populate(fs)
            stale=FAT12.open(path);plan=stale.plan_defragmentation();old=bytes(stale.data)
            fs.write_file('/LATEST.TXT',b'newer');latest=path.read_bytes()
            with self.assertRaises(OSError):stale.defragment(plan['image_sha256'])
            self.assertEqual(path.read_bytes(),latest);self.assertEqual(bytes(stale.data),old)
            self.assertEqual(fs.list_snapshots(),[])

    def test_seeded_preservation_and_idempotence_across_layouts(self):
        for layout in LAYOUTS:
            for seed in (12,91):
                with self.subTest(layout=layout.cluster_bytes,seed=seed):
                    rng=random.Random(seed);fs=FAT12.create(layout=layout);fs.mkdir('/FILES')
                    for i in range(22):fs.write_file(f'/FILES/F{i}.BIN',rng.randbytes(rng.randrange(0,3100)))
                    for i in range(0,22,3):fs.remove(f'/FILES/F{i}.BIN')
                    for i in range(1,22,4):
                        if i%3:fs.write_file(f'/FILES/F{i}.BIN',rng.randbytes(4100))
                    expected=contents_and_metadata(fs);plan=fs.plan_defragmentation()
                    self.assertGreater(plan['moved_clusters'],0)
                    fs.defragment(plan['image_sha256'])
                    self.assertEqual(contents_and_metadata(fs),expected)
                    self.assertEqual(fs.plan_defragmentation()['moved_clusters'],0)
                    self.assertTrue(fs.check()['ok'])
