"""Build from a fresh staging directory to exclude stale setuptools assets."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from evidence import project_version

ROOT=Path(__file__).resolve().parent.parent


def main():
    output=ROOT/'artifacts/releases';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fat12-build-') as temporary:
        stage=Path(temporary).resolve()
        assert stage.name.startswith('fat12-build-')
        for name in ('pyproject.toml','README.md'):shutil.copyfile(ROOT/name,stage/name)
        shutil.copytree(ROOT/'fat12lab',stage/'fat12lab',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        subprocess.run([sys.executable,'-m','pip','wheel','.', '--no-deps','--no-build-isolation',
                        '--wheel-dir',str(output)],cwd=stage,check=True)
    wheel=output/f'fat12_disk_lab-{project_version()}-py3-none-any.whl'
    # Ensure source modules and frontend files match the exact release payload,
    # with no obsolete compiled JS from a previous incremental build.
    expected={p.relative_to(ROOT).as_posix():p for p in (ROOT/'fat12lab').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    with zipfile.ZipFile(wheel) as archive:
        actual={name for name in archive.namelist() if name.startswith('fat12lab/')}
        assert actual==expected.keys(),(actual-expected.keys(),expected.keys()-actual)
        for name,path in expected.items():assert archive.read(name)==path.read_bytes(),name
    print(f'Verified wheel: {wheel.name}; SHA256 {hashlib.sha256(wheel.read_bytes()).hexdigest()}')


if __name__=='__main__':main()
