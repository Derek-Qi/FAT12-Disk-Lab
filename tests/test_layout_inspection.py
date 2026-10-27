import base64
import struct
import unittest
from unittest.mock import patch
from fat12lab import FAT12, FATError
from fat12lab.server import disk_changes
from fat12lab.shell import Shell


def disk720():
    # Independent fixture: construct BPB and two reserved FAT entries directly.
    raw=bytearray(737280)
    raw[510:512]=b'\x55\xAA'
    struct.pack_into('<HBHBHHBHHHII',raw,11,512,2,1,2,112,1440,0xF9,3,9,2,0,0)
    raw[43:54]=b'TEST720    '
    for start in (512,2048):raw[start:start+3]=b'\xF9\xFF\xFF'
    return FAT12(raw)


class LayoutInspectionTests(unittest.TestCase):
    def test_720kb_cross_cluster_io_and_directory_extension(self):
        fs=disk720()
        self.assertEqual((fs.layout.root_sector,fs.layout.data_sector,fs.layout.cluster_count),(7,14,713))
        fs.mkdir('/SUB')
        content=bytes(range(256))*9
        fs.write_file('/SUB/A.BIN',content)
        self.assertEqual(len(fs.chain(fs.stat('/SUB/A.BIN').cluster)),3)
        for i in range(35):fs.write_file(f'/SUB/F{i}.TXT',b'')
        self.assertEqual(len(fs.chain(fs.stat('/SUB').cluster)),2)
        reopened=FAT12(bytes(fs.data))
        self.assertEqual(reopened.read_file('/SUB/A.BIN'),content)
        self.assertTrue(reopened.check()['ok'],reopened.check())

    def test_format_preserves_loaded_geometry_and_media(self):
        fs=disk720();fs.write_file('/A.TXT',b'old')
        Shell(fs).execute('format CLASS')
        self.assertEqual(len(fs.data),737280)
        self.assertEqual(fs.layout.cluster_bytes,1024)
        self.assertEqual(fs.fat_get(0),0xFF9)
        self.assertEqual(fs.list_dir(),[])
        self.assertEqual(fs.layout.root_entries,112)
        self.assertTrue(fs.check()['ok'])

    def test_geometry_corruption_and_length_mismatch(self):
        raw=disk720().data
        for size in (737279,1228800,1474560):
            bad=(raw+bytes(1474560))[:size]
            with self.assertRaisesRegex(FATError,'BPB 声明'):FAT12(bad)
        for offset,fmt,value in ((13,'B',3),(22,'H',1),(17,'H',0),(19,'H',0),(32,'I',1440),(28,'I',1)):
            bad=raw[:];struct.pack_into('<'+fmt,bad,offset,value)
            with self.assertRaises(FATError,msg=str(offset)):FAT12(bad)

    def test_exact_directory_and_fat_decode(self):
        fs=disk720();fs.write_file('/A.TXT',b'x'*1025)
        e=fs.stat('/A.TXT');details=fs.inspect_entry('/A.TXT')
        self.assertEqual(len(bytes.fromhex(details['raw'])),32)
        self.assertEqual(details['name_bytes'],'A       TXT')
        self.assertEqual(details['decoded_time']['second']%2,0)
        self.assertEqual(details['cluster'],2)
        self.assertEqual(fs.inspect_fat(2)['value'],3)
        self.assertEqual(fs.inspect_fat(3)['value'],0xFFF)
        self.assertEqual(fs.inspect_fat(3)['data_sector'],16)
        self.assertEqual(fs.inspect_bpb()[1]['raw'],'02')
        self.assertIn('每簇扇区数',Shell(fs).execute('bpb'))
        self.assertIn('A       TXT',Shell(fs).execute('inspect A.TXT'))

    def test_diff_counts_match_independent_byte_comparison(self):
        fs=FAT12.create();before=bytes(fs.data)
        fs.write_file('/A.TXT',b'hello')
        change=disk_changes(before,fs)
        indices=[i for i in range(len(before)) if before[i]!=fs.data[i]]
        self.assertEqual(change['changed_bytes'],len(indices))
        self.assertEqual(change['changed_sector_count'],len({i//512 for i in indices}))
        self.assertEqual(set(change['regions']),{'FAT 1','FAT 2','根目录','数据区'})
        for sample in change['samples']:
            offset=sample['offset'];old=bytes.fromhex(sample['before']);new=bytes.fromhex(sample['after'])
            self.assertEqual(old,before[offset:offset+len(old)])
            self.assertEqual(new,fs.data[offset:offset+len(new)])
        fs.remove('/A.TXT')
        self.assertEqual(fs.data[fs.layout.root_sector*512+32],0xE5)
        self.assertTrue(fs.check()['ok'])

    def test_geometry_and_bytes_survive_failed_write(self):
        fs=disk720();fs.write_file('/A.TXT',b'original')
        before=bytes(fs.data);layout=fs.layout
        with patch.object(fs,'save',side_effect=OSError('disk failure')):
            fs.path='placeholder.img'
            with self.assertRaises(OSError):fs.write_file('/A.TXT',b'new')
        self.assertEqual(bytes(fs.data),before)
        self.assertEqual(fs.layout,layout)
        self.assertEqual(fs.read_file('/A.TXT'),b'original')

    def test_diff_samples_cross_sector_boundaries_and_remain_bounded(self):
        fs=FAT12.create();before=bytes(fs.data);start=fs.layout.data_sector*512
        changed=list(range(start+510,start+530))+[start+1024+2*i for i in range(30)]
        for offset in changed:fs.data[offset]=0xAA
        result=disk_changes(before,fs)
        self.assertEqual(result['changed_bytes'],50)
        self.assertEqual(result['changed_sector_count'],3)
        self.assertEqual(result['regions'],{'数据区':50})
        self.assertEqual(len(result['samples']),16)
        self.assertEqual(result['samples'][0],{'offset':start+510,'before':('00 '*16).strip(),'after':('AA '*16).strip()})
        self.assertEqual(result['samples'][1],{'offset':start+526,'before':'00 00 00 00','after':'AA AA AA AA'})


if __name__=='__main__':unittest.main()
