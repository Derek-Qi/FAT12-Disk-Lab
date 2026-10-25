"""Install a wheel into a clean venv and exercise its CLI and bundled HTTP UI."""
import argparse
from evidence import metadata, project_version
import json
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import venv

ROOT=Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel',type=Path)
    wheel=parser.parse_args().wheel.resolve()
    if not wheel.is_file():raise SystemExit('Wheel does not exist; build it first.')
    with tempfile.TemporaryDirectory(prefix='fat12-install-') as temporary:
        destination=Path(temporary).resolve()
        assert destination.name.startswith('fat12-install-')
        environment=destination/'venv';venv.EnvBuilder(with_pip=True).create(environment)
        python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
        def run(*args):
            result=subprocess.run([str(python),*args],cwd=destination,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
            return result.stdout
        run('-m','pip','install','--no-index','--no-deps',str(wheel))
        entry=environment/('Scripts/fat12lab.exe' if os.name=='nt' else 'bin/fat12lab')
        version=subprocess.run([str(entry),'--version'],cwd=destination,env=env,
                               capture_output=True,text=True,check=True).stdout
        assert project_version() in version
        run('-c',"import fat12lab; from fat12lab import FAT12; from fat12lab.server import WEB_DIST; from pathlib import Path; assert 'site-packages' in fat12lab.__file__; assert (WEB_DIST/'index.html').is_file(); f=FAT12.create('disk.img'); f.write_file('/A.TXT',b'original'); s=f.create_snapshot('installed'); f.write_file('/A.TXT',b'changed'); f.restore_snapshot(s['id']); assert f.read_file('/A.TXT')==b'original'; assert f.check()['ok']")
        run('-c',"from fat12lab import FAT12; f=FAT12.open('disk.img'); f.write_file('/Z.BIN',b'z'*1100); f.write_file('/B.BIN',b'b'*700); p=f.plan_defragmentation(); assert p['moved_clusters']>0; f.defragment(p['image_sha256']); assert f.read_file('/Z.BIN')==b'z'*1100; assert f.read_file('/B.BIN')==b'b'*700; assert f.plan_defragmentation()['moved_clusters']==0")
        output=run('-m','fat12lab','--image','disk.img','-c','type A.TXT')
        assert 'original' in output
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        server=subprocess.Popen([str(python),'-m','fat12lab','--image','disk.img','--read-only','--web','--port',str(port),'--no-browser'],cwd=destination,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    html=urllib.request.urlopen(url+'/',timeout=1).read().decode();break
                except OSError:time.sleep(.05)
            else:raise AssertionError('Installed server failed to start')
            import re
            assets=re.findall(r'(?:src|href)="(/assets/[^"]+)"',html)
            assert len(assets)>=2
            for asset in assets:assert urllib.request.urlopen(url+asset,timeout=2).status==200
            state=json.load(urllib.request.urlopen(url+'/api/state',timeout=2))
            assert state['info']['read_only'] and state['check']['ok']
        finally:server.terminate();server.wait(timeout=10)
    receipt={**metadata(),'wheel':wheel.name,
             'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'ok':True,
             'checks':['clean venv installation without runtime dependencies','installed console entry and snapshot roundtrip','installed allocation analysis and compaction',
                       'installed HTTP state in read-only mode','all referenced frontend assets served']}
    (ROOT/'artifacts/distribution-results.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
