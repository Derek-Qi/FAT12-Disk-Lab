"""Resolve native Windows browser tooling without cmd.exe argument evaluation."""
import os
from pathlib import Path
import platform
import re
import shutil


def browser_executable(command: str | None = None, *, windows: bool | None = None) -> str:
    command=command or os.environ.get('FAT12_BROWSER_CLI') or shutil.which('agent-browser')
    if not command:raise RuntimeError('Install the optional agent-browser CLI and browser first.')
    path=Path(command)
    if not (os.name=='nt' if windows is None else windows) or path.suffix.lower()=='.exe':
        return str(path)
    if path.suffix.lower() in ('.cmd','.bat'):
        wrapper=path.read_text(encoding='utf-8',errors='replace')
        literal=re.search(r'^\s*"([^"\r\n]*agent-browser-win32-(?:x64|arm64)\.exe)"\s+%\*\s*$',wrapper,re.MULTILINE)
        if literal and Path(literal[1]).is_file():return str(Path(literal[1]))
        architecture='arm64' if platform.machine().lower()=='arm64' else 'x64'
        candidate=path.parent/'node_modules/agent-browser/bin'/f'agent-browser-win32-{architecture}.exe'
        if candidate.is_file():return str(candidate)
    raise RuntimeError('Set FAT12_BROWSER_CLI to the native agent-browser executable; Windows shell launchers are unsupported.')
