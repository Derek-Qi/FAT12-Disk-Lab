"""Explicit public-source allowlist; never export the local coursework history."""
from pathlib import Path
import argparse
import os
import re
import shutil
import tomllib

TOP=('.gitignore','.gitattributes','README.md','README.zh-CN.md','pyproject.toml',
     'start.bat','cli.bat','NOTICE.md','CONTRIBUTING.md','SECURITY.md')
DOCS=('architecture.md','experiments.md','testing.md','portfolio.md')
TOOLS=('build_wheel.py','browser_cli.py','check_browser.py','check_distribution.py','check_interop.py',
       'check_release.py','compaction_experiment.py','create_demo.py','evidence.py',
       'package_release.py','package_submission.py','public_release.py','verify_project.py')
RECEIPTS=('test-results.json','test-output.txt','browser-results.json','distribution-results.json',
          'interop-results.json','compaction-results.json','frontend-audit.json')
SENSITIVE=re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|'
                     r'-----BEGIN[ A-Z]*PRIVATE KEY-----|[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+[\\/]+')


def public_files(root: Path, *, include_wheel: bool = False) -> list[Path]:
    root=Path(root).resolve()
    selected=[root/name for name in TOP]
    for folder in ('fat12lab','web/src','tests','.github'):
        start=root/folder
        if start.exists() and start.resolve()!=start:raise ValueError(f'Linked public source: {folder}')
        for directory,children,names in os.walk(start,followlinks=False):
            children[:]=[name for name in children if name not in ('__pycache__','node_modules','dist')]
            for name in names:
                path=Path(directory)/name
                if name.startswith('.'):continue
                if folder=='fat12lab':
                    allowed=path.suffix=='.py' or (path.is_relative_to(root/'fat12lab/static') and path.suffix in ('.html','.js','.css','.txt','.svg','.png','.webp','.woff2'))
                else:
                    extensions={'web/src':('.ts','.tsx','.css','.svg','.png','.webp'),
                                'tests':('.py',),'.github':('.yml','.yaml','.md')}
                    allowed=path.suffix in extensions[folder]
                if allowed:selected.append(path)
    selected.extend(root/'web'/name for name in ('package.json','package-lock.json','index.html',
                    'vite.config.ts','tsconfig.json','tsconfig.app.json','tsconfig.node.json'))
    selected.extend(root/'docs'/name for name in DOCS)
    selected.extend(root/'tools'/name for name in TOOLS)
    selected.extend(root/'data'/name for name in ('demo.img','demo720.img'))
    selected.extend(root/'artifacts'/name for name in RECEIPTS)
    selected.extend(root/'artifacts/screenshots'/name for name in ('allocation-ui.png','compacted-ui.png','portfolio-ui.png'))
    if include_wheel:
        version=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
        selected.append(root/'artifacts/releases'/f'fat12_disk_lab-{version}-py3-none-any.whl')
    result=[]
    for path in sorted(set(selected)):
        if not path.is_file():continue
        if path.resolve()!=path or not path.resolve().is_relative_to(root):
            raise ValueError(f'Linked or escaped public source: {path.name}')
        if path.suffix in ('.py','.ts','.tsx','.js','.css','.json','.md','.txt','.html','.yml','.yaml','.bat'):
            if SENSITIVE.search(path.read_text(encoding='utf-8')):
                raise ValueError(f'Credential or private home path found in {path.relative_to(root)}')
        result.append(path)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parent.parent
    selected=public_files(root)
    required={'README.md','README.zh-CN.md','pyproject.toml','fat12lab/filesystem.py',
              'fat12lab/allocation.py','fat12lab/static/index.html','tools/evidence.py'}
    assert required<={path.relative_to(root).as_posix() for path in selected}
    if args.export:
        destination=args.export.resolve()
        if destination.exists() and any(destination.iterdir()):raise ValueError('Export requires a new empty directory')
        if destination==root:raise ValueError('Cannot export over the source checkout')
        destination.mkdir(parents=True,exist_ok=True)
        for path in selected:
            target=destination/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)
    print(f'Public source validated: {len(selected)} selected files; no coursework history or private runtime data.')


if __name__=='__main__':main()
