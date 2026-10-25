"""Reproduce allocation changes with content/metadata hashes, not I/O speed claims."""
import hashlib
import json
from pathlib import Path
import random
import sys
from time import perf_counter

from evidence import metadata

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from fat12lab import FAT12
from fat12lab.filesystem import Layout


def inventory(fs):
    records=[];pending=['/']
    while pending:
        directory=pending.pop()
        for entry in fs.list_dir(directory):
            path=directory.rstrip('/')+'/'+entry.name
            raw=bytes(fs.data[entry.offset:entry.offset+32])
            records.append({'path':path,'directory':entry.is_dir,
                            'content':None if entry.is_dir else hashlib.sha256(fs.read_file(path)).hexdigest(),
                            'metadata':(raw[:26]+raw[28:]).hex()})
            if entry.is_dir:pending.append(path)
    records.sort(key=lambda item:item['path'])
    return hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()


def run_case(name,layout,bad=False):
    fs=FAT12.create(layout=layout)
    if bad:fs._fat_set(3,0xFF7)
    rng=random.Random(20261025)
    fs.write_file('/ZFIRST.BIN',rng.randbytes(1800));fs.mkdir('/LAB');fs.mkdir('/LAB/NEST')
    for i in range(28):fs.write_file(f'/LAB/NEST/F{i}.BIN',rng.randbytes(rng.randrange(0,4200)))
    for i in range(0,28,4):fs.remove(f'/LAB/NEST/F{i}.BIN')
    for i in range(1,28,5):fs.write_file(f'/LAB/NEST/F{i}.BIN',rng.randbytes(5300))
    fs.write_file('/AEMPTY.TXT',b'')
    original=bytes(fs.data);before_hash=inventory(fs)
    start=perf_counter();plan=fs.plan_defragmentation();planning_ms=(perf_counter()-start)*1000
    assert bytes(fs.data)==original,'Preview mutated the source'
    assert plan['moved_clusters']>0
    start=perf_counter();fs.defragment(plan['image_sha256']);apply_ms=(perf_counter()-start)*1000
    after_hash=inventory(fs)
    assert before_hash==after_hash and fs.check()['ok']
    assert fs.plan_defragmentation()['moved_clusters']==0
    return {'case':name,'seed':20261025,'image_bytes':layout.image_bytes,'cluster_bytes':layout.cluster_bytes,
            'before':plan['before'],'after':plan['after'],'moved_clusters':plan['moved_clusters'],
            'content_and_metadata_sha256_before':before_hash,'content_and_metadata_sha256_after':after_hash,
            'preview_byte_identical':True,'second_plan_moved_clusters':0,
            'in_memory_planning_ms':round(planning_ms,3),'in_memory_apply_ms':round(apply_ms,3)}


def main():
    small=Layout(total_sectors=1440,sectors_per_cluster=2,fat_sectors=3,root_entries=112,media=0xF9,sectors_per_track=9)
    result={**metadata(),'ok':True,'timing_scope':'in-memory Python algorithm; no disk latency or throughput claim',
            'cases':[run_case('1440KiB (1.44MB floppy)',Layout()),run_case('720KiB geometry',small),
                     run_case('bad cluster interleaved',Layout(),bad=True)]}
    output=ROOT/'artifacts/compaction-results.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
