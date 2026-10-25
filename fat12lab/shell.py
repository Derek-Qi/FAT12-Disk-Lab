"""Command interpreter shared by the CLI and the browser terminal."""

from __future__ import annotations

import json
from pathlib import Path

from .filesystem import FAT12, FATError

HELP = """FAT12 命令（路径为镜像内部路径，短文件名 8.3）
format [卷标]               格式化当前镜像，清空全部内容
dir [路径] / tree [路径]     列出目录 / 显示目录树
cd 路径 / pwd               切换目录 / 显示当前位置
mkdir 路径 / rmdir 路径      创建目录 / 删除空目录
type 文件                    以 UTF-8 显示文本内容
write 文件 \"文本\"           写入或覆盖文件
append 文件 \"文本\"          追加文本（文件必须存在）
touch 文件                   创建空文件（已存在则保持内容）
del 文件                     删除文件并释放簇
copy 源文件 目标文件          复制文件，目标不可存在
ren 路径 新名字              在原目录重命名
move 源路径 目标路径          移动文件或目录，目标不可存在
stat 文件或目录              显示目录项和簇链
fat [起始簇] [数量]          显示 FAT 项，单次最多 128 项
sector 扇区号                查看 512 字节十六进制数据
info / fsck                  磁盘信息 / 只读一致性检查
bpb / inspect 路径           查看 BPB 字段 / 原始目录项与时间解码
import 本机文件 镜像路径      导入二进制文件（仅 CLI）
export 镜像路径 本机文件      导出二进制文件（仅 CLI）
help / exit                  显示帮助 / 退出 CLI
snapshot [名称] / snapshots   创建快照 / 列出快照
restore 快照编号 / reload     恢复快照 / 重新读取当前磁盘
analyze                      只读分析空间、碎片和连续空闲区
defrag --dry-run              预览整理计划，不修改镜像
defrag 预览SHA256             应用匹配当前内容的整理计划
文本含空格时使用双引号；write 不解释反斜杠转义。
"""


def split_command(command: str) -> list[str]:
    """Quote-aware words without treating Windows backslashes as POSIX escapes.

    Only a backslash before the active quote escapes it. Other backslashes,
    including doubled ones in file content, are literal.
    """
    words, current = [], []
    quote, started, index = None, False, 0
    while index < len(command):
        char = command[index]
        if quote:
            if char == '\\' and index + 1 < len(command) and command[index + 1] == quote:
                current.append(quote); index += 1
            elif char == quote:
                quote = None
            else:
                current.append(char)
        elif char.isspace():
            if started:
                words.append(''.join(current)); current = []; started = False
        elif char in ('"', "'") and not started:
            quote, started = char, True
        else:
            current.append(char); started = True
        index += 1
    if quote:
        raise FATError('命令引号不完整')
    if started:
        words.append(''.join(current))
    return words


class Shell:
    def __init__(self, fs: FAT12, allow_host_io: bool = True):
        self.fs, self.cwd, self.allow_host_io = fs, "/", allow_host_io

    def path(self, value: str) -> str:
        return self.fs.normalize(value, self.cwd)

    def execute(self, command: str) -> str:
        tokens = split_command(command)
        if not tokens:
            return ""
        cmd, args = tokens[0].lower(), tokens[1:]

        def arity(minimum: int, maximum: int | None = None):
            if not minimum <= len(args) <= (minimum if maximum is None else maximum):
                raise FATError(f"{cmd} 参数数量错误，输入 help 查看用法")

        if cmd == "help":
            arity(0)
            return HELP
        if cmd == "exit":
            arity(0)
            return "再见"
        if cmd == 'analyze':
            arity(0)
            return json.dumps(self.fs.analyze(),ensure_ascii=False,indent=2)
        if cmd == 'defrag':
            arity(1)
            result = self.fs.plan_defragmentation() if args[0]=='--dry-run' else self.fs.defragment(args[0])
            return json.dumps(result,ensure_ascii=False,indent=2)
        if cmd == 'snapshot':
            arity(0, 1)
            return json.dumps(self.fs.create_snapshot(args[0] if args else ''), ensure_ascii=False, indent=2)
        if cmd == 'snapshots':
            arity(0)
            return json.dumps(self.fs.list_snapshots(), ensure_ascii=False, indent=2)
        if cmd == 'restore':
            arity(1)
            self.fs.restore_snapshot(args[0]);self.cwd = '/'
            return '快照已恢复；恢复前的内容已另存保护点'
        if cmd == 'reload':
            arity(0)
            self.fs.reload();self.cwd = '/'
            return '已重新读取当前磁盘'
        if cmd == "format":
            arity(0, 1)
            self.fs.reformat(args[0] if args else "FAT12LAB")
            self.cwd = "/"
            info = self.fs.info()
            return f"格式化完成：{info['image_bytes']:,} 字节，FAT12，两份 FAT，{info['total_clusters']:,} 个数据簇（保留当前几何参数）"
        if cmd == 'bpb':
            arity(0)
            return json.dumps(self.fs.inspect_bpb(), ensure_ascii=False, indent=2)
        if cmd == 'inspect':
            arity(1)
            return json.dumps(self.fs.inspect_entry(self.path(args[0])), ensure_ascii=False, indent=2)
        if cmd in ("info", "fsck", "pwd"):
            arity(0)
            if cmd == "pwd":
                return self.cwd
            if cmd == "info":
                return json.dumps(self.fs.info(), ensure_ascii=False, indent=2)
            result = self.fs.check()
            if result["ok"]:
                return f"FSCK OK：{result['files']} 个文件，{result['directories']} 个目录，{result['referenced_clusters']} 个引用簇"
            return "FSCK FAILED：\n" + "\n".join(result["errors"])
        if cmd in ("dir", "tree"):
            arity(0, 1)
            path = self.path(args[0] if args else ".")
            if cmd == "dir":
                entries = self.fs.list_dir(path)
                lines = [f"目录 {path}", "名称          类型     字节        首簇  修改时间"]
                lines += [f"{e.name:12} {'<DIR>' if e.is_dir else 'FILE ':5} {e.size:9} {e.cluster:6}  {e.modified}" for e in entries]
                lines.append(f"共 {len(entries)} 项，可用 {self.fs.info()['free_bytes']:,} 字节")
                return "\n".join(lines)
            lines, stack, seen = [path], [(path, 1)], set()
            while stack:
                current, depth = stack.pop()
                cluster = self.fs.resolve_dir(current)
                if cluster in seen:
                    raise FATError("目录树存在循环")
                seen.add(cluster)
                entries = self.fs.list_dir(current)
                for entry in entries:
                    lines.append("  " * depth + entry.name + ("/" if entry.is_dir else f" ({entry.size} B)"))
                stack.extend((current.rstrip("/") + "/" + e.name, depth + 1) for e in reversed(entries) if e.is_dir)
            return "\n".join(lines)
        if cmd == "cd":
            arity(1)
            path = self.path(args[0])
            self.fs.resolve_dir(path)
            self.cwd = path
            return self.cwd
        if cmd in ("mkdir", "rmdir", "del", "touch", "type", "stat"):
            arity(1)
            path = self.path(args[0])
            if cmd == "mkdir":
                self.fs.mkdir(path)
            elif cmd in ("rmdir", "del"):
                if cmd == "rmdir" and (self.cwd == path or self.cwd.startswith(path + "/")):
                    raise FATError("不能删除当前目录或其祖先")
                self.fs.remove(path, directory=cmd == "rmdir")
            elif cmd == "touch":
                parent, name = self.fs._parent(path)
                existing = next((e for e in self.fs._entries(parent) if e.name == name), None)
                if existing and existing.is_dir:
                    raise FATError("目标为目录")
                if not existing:
                    self.fs.write_file(path, b"", overwrite=False)
            elif cmd == "type":
                data = self.fs.read_file(path)
                try:
                    return data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise FATError("文件不是 UTF-8 文本，请使用 export 或 GUI 下载") from exc
            elif cmd == "stat":
                entry = self.fs.stat(path)
                value = entry.to_dict()
                value["chain"] = self.fs.chain(entry.cluster)
                value["allocated_bytes"] = len(value["chain"]) * self.fs.layout.cluster_bytes
                return json.dumps(value, ensure_ascii=False, indent=2)
            return f"{cmd} 完成：{path}"
        if cmd in ("write", "append", "copy", "ren", "move"):
            arity(2)
            source = self.path(args[0])
            if cmd in ("write", "append"):
                data = args[1].encode("utf-8")
                if cmd == "append":
                    data = self.fs.read_file(source) + data
                self.fs.write_file(source, data)
                return f"写入 {len(data)} 字节：{source}"
            target = self.path(args[1])
            if cmd == "ren":
                if "/" in args[1] or "\\" in args[1]:
                    raise FATError("ren 的第二个参数应为新名字，移动请用 move")
                target = source.rsplit("/", 1)[0] + "/" + args[1].upper()
            if cmd == "copy":
                self.fs.copy(source, target)
            else:
                self.fs.move(source, target)
                if self.cwd == source or self.cwd.startswith(source + "/"):
                    self.cwd = target + self.cwd[len(source):]
            return f"{cmd} 完成：{source} -> {target}"
        if cmd == "fat":
            arity(0, 2)
            try:
                start, count = int(args[0]) if args else 0, int(args[1]) if len(args) == 2 else 16
            except ValueError as exc:
                raise FATError("簇号和数量应为整数") from exc
            if count < 1 or count > 128 or start < 0 or start + count > self.fs.layout.last_cluster + 1:
                raise FATError(f"FAT 范围错误，数量为 1 至 128，索引为 0 至 {self.fs.layout.last_cluster}")
            return "\n".join(f"{c:4}  0x{self.fs.fat_get(c):03X}" for c in range(start, start + count))
        if cmd == "sector":
            arity(1)
            try:
                index = int(args[0])
            except ValueError as exc:
                raise FATError("扇区号应为整数") from exc
            data = self.fs.sector(index)
            return "\n".join(f"{index * 512 + i:06X}  " + " ".join(f"{b:02X}" for b in data[i:i + 16]) for i in range(0, 512, 16))
        if cmd in ("import", "export"):
            arity(2)
            if not self.allow_host_io:
                raise FATError("网页中请使用上传文件或下载文件按钮")
            if cmd == "import":
                host = Path(args[0])
                if host.stat().st_size > self.fs.layout.cluster_count * self.fs.layout.cluster_bytes:
                    raise FATError("文件大于磁盘数据区")
                self.fs.write_file(self.path(args[1]), host.read_bytes(), overwrite=False)
            else:
                target = Path(args[1])
                if target.exists():
                    raise FATError("本机目标已存在，请使用新的导出文件名")
                content = self.fs.read_file(self.path(args[0]))
                with target.open("xb") as stream:
                    stream.write(content)
            return f"{cmd} 完成"
        raise FATError(f"未知命令：{cmd}，输入 help 查看帮助")
