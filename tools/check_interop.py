"""Optional independent verification. Runtime does not depend on pyfatfs.

Install into an isolated environment: pip install pyfatfs==1.1.0 'setuptools<81'
"""
from evidence import metadata

from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
vendor=ROOT/'artifacts/qa/vendor'
if vendor.exists():
    sys.path.insert(0,str(vendor))

from fat12lab import FAT12
from pyfatfs.PyFatFS import PyFatFS


def main():
    checks=[]
    image=ROOT/'data/demo.img'
    own=FAT12.open(image)
    with PyFatFS(str(image),read_only=True) as other:
        for directory in ('/','/DOCS','/LAB'):
            assert set(other.listdir(directory))=={e.name for e in own.list_dir(directory)}
            for entry in own.list_dir(directory):
                if not entry.is_dir:
                    path=directory.rstrip('/')+'/'+entry.name
                    assert other.readbytes(path)==own.read_file(path),path
                    checks.append(f'pyfatfs reads {path}: byte-identical')
    target=ROOT/'artifacts/qa/external.img'
    target.parent.mkdir(parents=True,exist_ok=True)
    # Start with the default 1.44 MB layout.
    # Start with our image, then use a completely separate FAT implementation
    # to allocate directories and file chains in it.
    target.write_bytes(image.read_bytes())
    payload=bytes(range(256))*7+b'from-independent-writer'
    with PyFatFS(str(target)) as other:
        other.makedir('/EXTERNAL')
        other.writebytes('/EXTERNAL/DATA.BIN',payload)
    imported=FAT12.open(target)
    assert imported.check()['ok'],imported.check()
    assert imported.read_file('/EXTERNAL/DATA.BIN')==payload
    checks.append('Own reader reads directory and binary file created by pyfatfs')
    imported.write_file('/EXTERNAL/OURS.TXT','双向互通\n'.encode())
    with PyFatFS(str(target),read_only=True) as other:
        assert other.readbytes('/EXTERNAL/OURS.TXT')=='双向互通\n'.encode()
    checks.append('pyfatfs reads our file written into its disk')
    target720=ROOT/'artifacts/qa/external720.img'
    target720.write_bytes((ROOT/'data/demo720.img').read_bytes())
    with PyFatFS(str(target720)) as other:
        assert other.readbytes('/LAB/PROBE.BIN')==bytes(range(256))*9
        other.writebytes('/OTHER.BIN',payload)
    imported720=FAT12.open(target720)
    assert imported720.read_file('/OTHER.BIN')==payload
    assert imported720.check()['ok'],imported720.check()
    imported720.write_file('/RETURN.TXT','720KB 双向互通'.encode())
    with PyFatFS(str(target720),read_only=True) as other:
        assert other.readbytes('/RETURN.TXT')=='720KB 双向互通'.encode()
    checks.append('720 KiB / 1024-byte clusters: independent reader and writer roundtrip passed')
    for path in (target,target720):
        compacted=FAT12.open(path)
        plan=compacted.plan_defragmentation()
        assert plan['moved_clusters']>0
        compacted.defragment(plan['image_sha256'])
        with PyFatFS(str(path),read_only=True) as other:
            pending=['/']
            while pending:
                directory=pending.pop()
                entries=compacted.list_dir(directory)
                assert set(other.listdir(directory))=={item.name for item in entries}
                for item in entries:
                    name=directory.rstrip('/')+'/'+item.name
                    if item.is_dir:pending.append(name)
                    else:assert other.readbytes(name)==compacted.read_file(name),name
        with PyFatFS(str(path)) as other:other.writebytes('/AFTER.TXT',b'independent post-compaction write')
        assert FAT12.open(path).read_file('/AFTER.TXT')==b'independent post-compaction write'
        checks.append(f'{compacted.layout.image_bytes} bytes: independent reader checks every compacted file; post-compaction writer roundtrip passed')
    result={**metadata(),'library':'pyfatfs 1.1.0','ok':True,'checks':checks}
    (ROOT/'artifacts/interop-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
