from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .filesystem import FAT12, FATError
from .shell import Shell, split_command
from . import __version__


def main() -> int:
    parser = argparse.ArgumentParser(description="FAT12 磁盘实验台")
    parser.add_argument('--version', action='version', version=f'FAT12 Lab {__version__}')
    parser.add_argument("--image", default="data/work.img", help="软盘镜像路径")
    parser.add_argument("--create", action="store_true", help="镜像不存在时创建，不覆盖已有镜像")
    parser.add_argument("--command", "-c", action="append", help="执行命令，可重复指定")
    parser.add_argument("--script", help="执行 UTF-8 命令脚本，错误立即退出")
    parser.add_argument("--web", action="store_true", help="启动图形界面服务")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="启动服务后不自动打开浏览器")
    parser.add_argument('--read-only', action='store_true', help='只读查看镜像，拒绝所有写入')
    options = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        image = Path(options.image)
        if options.read_only and options.create and not image.exists():
            raise FATError('只读模式不能创建镜像')
        fs = FAT12.open(image, read_only=options.read_only) if image.exists() else FAT12.create(image) if options.create else None
        if fs is None:
            raise FATError("镜像不存在，请先使用 --create 参数创建")
        if options.web:
            from .server import serve
            serve(fs, options.port, not options.no_browser)
            return 0
        shell = Shell(fs)
        commands = list(options.command or [])
        if options.script is not None:
            try:
                source = Path(options.script).read_text(encoding="utf-8-sig")
            except UnicodeDecodeError as exc:
                raise FATError('命令脚本必须使用 UTF-8 编码，请转换编码后重试') from exc
            commands += [line.strip() for line in source.splitlines()
                         if line.strip() and not line.lstrip().startswith("#")]
        if options.command is not None or options.script is not None:
            for command in commands:
                print(f"A:{shell.cwd}> {command}")
                print(shell.execute(command))
                if [word.lower() for word in split_command(command)] == ['exit']:
                    break
            return 0
        print("FAT12 磁盘实验台。输入 help 查看命令，exit 退出。")
        while True:
            try:
                command = input(f"A:{shell.cwd}> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                print(shell.execute(command))
                if [word.lower() for word in split_command(command)] == ['exit']:
                    break
            except (FATError, OSError) as exc:
                print(f"错误：{exc}")
        return 0
    except (FATError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

