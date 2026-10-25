"""Run the standard-library suite and retain factual, machine-readable evidence."""
from evidence import metadata

from pathlib import Path
from contextlib import redirect_stderr
import io
import json
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from fat12lab import FAT12


def main():
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    start=time.perf_counter()
    with redirect_stderr(stream):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    duration=time.perf_counter()-start
    output=ROOT/'artifacts'
    output.mkdir(exist_ok=True)
    (output/'test-output.txt').write_text(stream.getvalue(),encoding='utf-8')
    if not result.wasSuccessful():
        sys.stderr.write(stream.getvalue())
    fs=FAT12.open(ROOT/'data/demo.img')
    report={**metadata(),
            'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'skipped':len(result.skipped),'ok':result.wasSuccessful(),'seconds':round(duration,3),
            'demo_image_bytes':len(fs.data),'demo_check':fs.check(),
            'fragmented_file':{'path':'/LAB/CHAIN.TXT','bytes':fs.stat('/LAB/CHAIN.TXT').size,
                               'chain':fs.chain(fs.stat('/LAB/CHAIN.TXT').cluster)}}
    (output/'test-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
