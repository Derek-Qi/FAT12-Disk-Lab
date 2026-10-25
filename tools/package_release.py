"""Create and verify a source release with its wheel and factual QA receipts."""
from evidence import metadata, project_version
import hashlib
import json
import os
from pathlib import Path
import zipfile
from public_release import public_files

ROOT=Path(__file__).resolve().parent.parent


def files():
    return public_files(ROOT,include_wheel=True)


def main():
    for name in ('test-results','interop-results','browser-results','distribution-results'):
        assert json.loads((ROOT/f'artifacts/{name}.json').read_text(encoding='utf-8'))['ok'],name
    distribution=json.loads((ROOT/'artifacts/distribution-results.json').read_text(encoding='utf-8'))
    wheel=ROOT/'artifacts/releases'/distribution['wheel']
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()==distribution['wheel_sha256'],'untested wheel'
    selected=files()
    for path in selected:
        assert path.is_file() and path.resolve().is_relative_to(ROOT.resolve()),path
    manifest={path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in selected}
    output=ROOT/'artifacts/releases'/f'FAT12Lab-v{project_version()}.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in selected:archive.write(path,'FAT12Lab/'+path.relative_to(ROOT).as_posix())
        archive.writestr('FAT12Lab/SHA256SUMS.txt','\n'.join(value+'  '+name for name,value in manifest.items())+'\n')
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name,value in manifest.items():assert hashlib.sha256(archive.read('FAT12Lab/'+name)).hexdigest()==value
        assert not any('work.img' in name or 'node_modules' in name or '/qa/' in name for name in archive.namelist())
    receipt={**metadata(),'files':len(selected),
             'zip_bytes':output.stat().st_size,'zip_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'ok':True}
    (ROOT/'artifacts/release-results.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
