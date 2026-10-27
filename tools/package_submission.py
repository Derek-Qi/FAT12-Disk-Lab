"""Build a portable submission without caches, dependencies or working disks."""
from pathlib import Path
import hashlib
import json
import os
import sys
import zipfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from tools.public_release import public_files
from tools.evidence import metadata


def sources():
    root=ROOT.resolve()
    files=public_files(root)
    extras=('docs/技术报告.md','docs/演示与答辩.md','docs/提交前检查.md','docs/资料筛选与教师评审.md','demo/commands.txt',
            'tools/build_report.py','tools/build_deck.mjs','tools/record_demo.py','tools/check_course_images.py',
            'artifacts/技术报告.pdf','artifacts/课堂演示.pptx','artifacts/course-image-results.json',
            'artifacts/demo-transcript.txt','artifacts/delivery-checks.json')
    extras+=tuple('artifacts/screenshots/'+name+'.png' for name in ('files','fat','changes'))
    for name in extras:
        file=root/name
        if file.is_file():
            if file.resolve()!=file or not file.resolve().is_relative_to(root):
                raise ValueError('Linked or escaped submission source: '+name)
            files.append(file)
    return sorted(set(files),key=lambda p:p.relative_to(root).as_posix())


def build():
    from pypdf import PdfReader  # Authoring/check dependency only, not runtime.
    tests=json.loads((ROOT/'artifacts/test-results.json').read_text(encoding='utf-8'))
    interop=json.loads((ROOT/'artifacts/interop-results.json').read_text(encoding='utf-8'))
    browser=json.loads((ROOT/'artifacts/browser-results.json').read_text(encoding='utf-8'))
    course=json.loads((ROOT/'artifacts/course-image-results.json').read_text(encoding='utf-8'))
    assert tests['ok'] and interop['ok'] and browser['ok']
    version=metadata()['version']
    assert all(item['version']==version for item in (tests,interop,browser)), 'Receipts must match the current release'
    assert course['source_files_unchanged']
    with zipfile.ZipFile(ROOT/'artifacts/课堂演示.pptx') as deck:
        slide_count=sum(name.startswith('ppt/slides/slide') and name.endswith('.xml') for name in deck.namelist())
        note_count=sum(name.startswith('ppt/notesSlides/notesSlide') and name.endswith('.xml') for name in deck.namelist())
    check={**metadata(),'unit_tests':tests['tests_run'],'unit_tests_ok':tests['ok'],
           'interop_ok':interop['ok'],'report_pages':len(PdfReader(ROOT/'artifacts/技术报告.pdf').pages),
           'presentation_slides':slide_count,'speaker_notes':note_count,
           'course_images':{'date':course['date'],'historical_record':True,
                            'entries':course['images_checked'],'unique':course['unique_images'],
                            'accepted':course['accepted'],'rejected':course['rejected'],
                            'source_files_unchanged':course['source_files_unchanged']},
           'browser':{'ok':browser['ok'],'checks':browser['checks'],'date':browser['date']},
           'runtime_dependencies':'Python 3.11+ standard library; prebuilt React assets included'}
    (ROOT/'artifacts/delivery-checks.json').write_text(json.dumps(check,ensure_ascii=False,indent=2),encoding='utf-8')
    files=sources()
    required={'pyproject.toml','README.zh-CN.md','fat12lab/static/index.html',
              'artifacts/技术报告.pdf','artifacts/课堂演示.pptx','docs/提交前检查.md'}
    assert required<={file.relative_to(ROOT).as_posix() for file in files}, 'Submission is incomplete'
    for file in files:
        assert file.exists(),file
        assert file.resolve().is_relative_to(ROOT.resolve()),file
    manifest='\n'.join(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.relative_to(ROOT).as_posix() for file in files)+'\n'
    (ROOT/'artifacts/SHA256SUMS.txt').write_text(manifest,encoding='utf-8')
    target=ROOT/'artifacts'/f'FAT12大作业一-v{version}.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for file in files:
            archive.write(file,'FAT12大作业一/'+file.relative_to(ROOT).as_posix())
        archive.writestr('FAT12大作业一/SHA256SUMS.txt',manifest)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert not any('node_modules' in n or 'work.img' in n for n in archive.namelist())
    print(json.dumps({'zip':str(target),'files':len(files),'bytes':target.stat().st_size,'checks':check},ensure_ascii=False,indent=2))


if __name__=='__main__':
    build()
