"""Verify archive hashes, then run its extracted source outside the repository."""
import argparse
from evidence import metadata
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--course',action='store_true',help='Verify the coursework archive instead of the public source release')
    options=parser.parse_args()
    source=options.archive.resolve()
    prefix='FAT12大作业一/' if options.course else 'FAT12Lab/'
    with tempfile.TemporaryDirectory(prefix='fat12-release-') as temporary:
        stage=Path(temporary).resolve()
        assert stage.name.startswith('fat12-release-')
        with zipfile.ZipFile(source) as archive:
            names=archive.namelist()
            assert len(names)==len(set(names)) and archive.testzip() is None
            assert sum(item.file_size for item in archive.infolist())<=64*1024*1024
            for item in archive.infolist():
                assert item.filename.startswith(prefix)
                assert (stage/item.filename).resolve().is_relative_to(stage)
                assert not stat.S_ISLNK(item.external_attr>>16)
            manifest={}
            for line in archive.read(prefix+'SHA256SUMS.txt').decode().splitlines():
                value,name=line.split('  ',1)
                assert re.fullmatch('[a-f0-9]{64}',value) and name not in manifest
                manifest[name]=value
            assert set(names)=={prefix+'SHA256SUMS.txt'}|{prefix+name for name in manifest}
            for name,value in manifest.items():
                assert hashlib.sha256(archive.read(prefix+name)).hexdigest()==value,name
            if options.course:
                assert {'pyproject.toml','README.zh-CN.md','docs/提交前检查.md',
                        'artifacts/技术报告.pdf','artifacts/课堂演示.pptx'}<=set(manifest)
            archive.extractall(stage)
        extracted=stage/prefix.rstrip('/')
        env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],
                              cwd=extracted,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
        count=int(re.search(r'Ran (\d+) tests',result.stderr)[1])
        expected=json.loads((extracted/'artifacts/test-results.json').read_text(encoding='utf-8'))['tests_run']
        assert count==expected and 'OK' in result.stderr
        command=subprocess.run([sys.executable,'-m','fat12lab','--image','data/demo.img','--read-only','-c','fsck'],
                               cwd=extracted,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
        assert any(line.startswith('FSCK OK') for line in command.stdout.splitlines()),command.stdout
    receipt={**metadata(),'files':len(manifest),
             'zip_bytes':source.stat().st_size,'zip_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'extracted_source_tests':count,'python':sys.version.split()[0],
             'checks':['CRC and all manifest SHA256 values','extracted source unittest suite',
                       'extracted read-only CLI and demo image'],'ok':True}
    receipt_name='submission-results.json' if options.course else 'release-results.json'
    (ROOT/'artifacts'/receipt_name).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
