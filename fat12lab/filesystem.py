"""Direct byte-level access to FAT12 floppy images with BPB-derived geometry.

No host directory is used as a substitute for the disk. All names, directory
entries, file contents and allocation chains live inside the image itself.
Only short ASCII 8.3 filenames, 512-byte sectors and two FATs are supported.
"""

from __future__ import annotations

import functools
import math
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .storage import digest, file_digest, write_image
from . import snapshots

SECTOR_SIZE = 512
TOTAL_SECTORS = 2880
IMAGE_SIZE = SECTOR_SIZE * TOTAL_SECTORS
FAT_SECTORS = 9
FAT_SIZE = FAT_SECTORS * SECTOR_SIZE
ROOT_ENTRIES = 224
ROOT_SECTOR = 19
DATA_SECTOR = 33
CLUSTER_COUNT = TOTAL_SECTORS - DATA_SECTOR
LAST_CLUSTER = CLUSTER_COUNT + 1
MAX_IMAGE_SIZE = 16 * 1024 * 1024
EOC = 0xFFF
ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$%'-_@~`!(){}^#&")


class FATError(ValueError):
    """An expected filesystem or image validation error."""


@dataclass(frozen=True)
class Layout:
    total_sectors: int = 2880
    sectors_per_cluster: int = 1
    reserved: int = 1
    fat_sectors: int = 9
    root_entries: int = 224
    media: int = 0xF0
    sectors_per_track: int = 18
    heads: int = 2

    @property
    def root_sector(self): return self.reserved + 2 * self.fat_sectors
    @property
    def root_sectors(self): return (self.root_entries * 32 + 511) // 512
    @property
    def data_sector(self): return self.root_sector + self.root_sectors
    @property
    def cluster_bytes(self): return 512 * self.sectors_per_cluster
    @property
    def cluster_count(self): return (self.total_sectors - self.data_sector) // self.sectors_per_cluster
    @property
    def last_cluster(self): return self.cluster_count + 1
    @property
    def image_bytes(self): return 512 * self.total_sectors

    @classmethod
    def parse(cls, data):
        if len(data) < 512 or len(data) > MAX_IMAGE_SIZE or data[510:512] != b'\x55\xAA':
            raise FATError('无效镜像大小或引导扇区签名')
        bps, spc, reserved, copies, root, total16, media, spf, track, heads, hidden, total32 = struct.unpack_from('<HBHBHHBHHHII', data, 11)
        if bps != 512 or copies != 2 or reserved < 1 or root < 1 or spf < 1:
            raise FATError('仅支持 512 字节扇区、两份 FAT 和非空固定根目录的 FAT12 卷')
        if spc not in (1, 2, 4, 8, 16, 32, 64, 128) or hidden != 0:
            raise FATError('无效每簇扇区数或包含分区偏移；请使用裸卷镜像')
        if (total16 == 0) == (total32 == 0) or not (media == 0xF0 or 0xF8 <= media <= 0xFF):
            raise FATError('无效总扇区字段或介质标识')
        result = cls(total16 or total32, spc, reserved, spf, root, media, track, heads)
        if result.image_bytes != len(data):
            raise FATError(f'BPB 声明 {result.image_bytes:,} 字节，实际 {len(data):,} 字节；拒绝截断或忽略尾部数据')
        if not 1 <= result.cluster_count < 4085 or result.last_cluster >= 0xFF0:
            raise FATError('数据区为空、不是 FAT12，或簇号进入保留值范围')
        if (result.cluster_count + 2) * 3 + 1 > spf * 512 * 2:
            raise FATError('FAT 太小，无法保存全部数据簇的 12 位表项')
        return result


def atomic(method: Callable) -> Callable:
    """Rollback the entire in-memory image on failure, then persist atomically.

Nested operations (copy calling write_file, for example) share one transaction.
Persistence uses a process lock and a version check; this is not a journal.
"""
    @functools.wraps(method)
    def wrapper(self: FAT12, *args, **kwargs):
        if self.read_only:
            raise FATError('镜像处于只读模式，不能修改')
        if self._depth:
            return method(self, *args, **kwargs)
        old = self.data[:]
        old_layout = self.layout
        old_digest = self._disk_digest
        self._depth = 1
        try:
            if method.__name__ not in ("reformat", "restore_snapshot"):
                issues = self.check()["errors"]
                if issues:
                    raise FATError("镜像存在错误，拒绝修改：" + issues[0])
            result = method(self, *args, **kwargs)
            self.validate()
            issues = self.check()["errors"]
            if issues:
                raise FATError("操作后校验失败：" + issues[0])
            if self.path:
                self.save()
            return result
        except Exception:
            self.data = old
            self.layout = old_layout
            self._disk_digest = old_digest
            raise
        finally:
            self._depth = 0
    return wrapper


@dataclass(frozen=True)
class Entry:
    name: str
    attr: int
    cluster: int
    size: int
    offset: int
    modified: str

    @property
    def is_dir(self) -> bool:
        return bool(self.attr & 0x10)

    def to_dict(self) -> dict:
        return {"name": self.name, "is_dir": self.is_dir, "size": self.size,
                "cluster": self.cluster, "attr": self.attr,
                "offset": self.offset, "modified": self.modified}


def encode_name(name: str) -> bytes:
    if not name.isascii():
        raise FATError('文件名必须为 ASCII 8.3 短文件名')
    upper = name.upper()
    parts = upper.split(".")
    if (len(parts) > 2 or not 1 <= len(parts[0]) <= 8
            or (len(parts) == 2 and not 1 <= len(parts[1]) <= 3)
            or any(c not in ALLOWED for part in parts for c in part)):
        raise FATError("文件名必须为 ASCII 8.3 短文件名，例如 HELLO.TXT 或 DOCS")
    return (parts[0].ljust(8) + (parts[1] if len(parts) == 2 else "").ljust(3)).encode("ascii")


def decode_name(raw: bytes) -> str:
    base = raw[:8].decode("ascii", errors="replace").rstrip()
    ext = raw[8:11].decode("ascii", errors="replace").rstrip()
    return base + ("." + ext if ext else "")


class FAT12:
    def __init__(self, data: bytes | bytearray, path: str | Path | None = None, *, read_only: bool = False):
        self.data = bytearray(data)
        self.path = Path(path).resolve() if path is not None else None
        self._depth = 0
        self.read_only = read_only
        self._disk_digest = digest(data) if self.path and self.path.exists() else None
        self.validate()

    @classmethod
    def create(cls, path: str | Path | None = None, label: str = "FAT12LAB", layout: Layout | None = None, *, overwrite: bool = False) -> FAT12:
        fs = cls.__new__(cls)
        geometry = layout or Layout()
        if not 512 <= geometry.image_bytes <= MAX_IMAGE_SIZE:
            raise FATError('镜像大小超出支持范围')
        fs.data = bytearray(geometry.image_bytes)
        fs.path = Path(path).resolve() if path is not None else None
        if fs.path and fs.path.exists() and not overwrite:
            raise FATError('目标镜像已存在，拒绝覆盖；需要重新格式化时请打开镜像后执行 format')
        fs.read_only = False
        fs._disk_digest = file_digest(fs.path) if fs.path and fs.path.exists() else None
        fs._depth = 0
        fs.layout = geometry
        fs.reformat(label)
        return fs

    @classmethod
    def open(cls, path: str | Path, *, read_only: bool = False) -> FAT12:
        target = Path(path)
        if not 512 <= target.stat().st_size <= MAX_IMAGE_SIZE:
            raise FATError('镜像大小超出 512 字节至 16 MiB 的支持范围')
        return cls(target.read_bytes(), target, read_only=read_only)

    def reload(self) -> None:
        if not self.path:
            raise FATError('内存镜像没有可重新读取的文件')
        candidate = self.open(self.path, read_only=self.read_only)
        # A valid BPB is enough to load for diagnosis. Ordinary writes still
        # require a healthy filesystem; restore validates its replacement.
        self.data, self.layout, self._disk_digest = candidate.data, candidate.layout, candidate._disk_digest

    def create_snapshot(self, label: str = '') -> dict:
        if self.read_only:
            raise FATError('只读模式不能创建快照')
        if not self.path:
            raise FATError('内存镜像没有快照保存位置')
        issues = self.check()['errors']
        if issues:
            raise FATError('镜像校验失败：' + issues[0])
        return snapshots.create(self.path, bytes(self.data), self._disk_digest, label)

    def list_snapshots(self) -> list[dict]:
        return snapshots.listing(self.path) if self.path else []

    def analyze(self) -> dict:
        from .allocation import analyze
        return analyze(self)

    def plan_defragmentation(self) -> dict:
        from .allocation import prepare_compaction
        return prepare_compaction(self)[1]

    @atomic
    def defragment(self, expected_sha256: str) -> dict:
        from .allocation import prepare_compaction
        if expected_sha256 != digest(self.data):
            raise FATError('镜像已变化，整理预览已过期，请重新预览')
        candidate,plan = prepare_compaction(self)
        if not plan['moved_clusters']:
            raise FATError('镜像已是规划布局，无需整理')
        if self.path:
            self.create_snapshot('磁盘整理前自动保护点')
        self.data = candidate
        return plan

    @atomic
    def restore_snapshot(self, identifier: str) -> None:
        if not self.path:
            raise FATError('内存镜像没有快照保存位置')
        candidate = FAT12(snapshots.read(self.path, identifier))
        issues = candidate.check()['errors']
        if issues:
            raise FATError('快照文件系统校验失败：' + issues[0])
        healthy = self.check()['ok']
        snapshots.create(self.path, bytes(self.data), self._disk_digest,
                         '恢复前自动保护点' if healthy else '恢复前原始保护点（仅供分析）',
                         restorable=healthy)
        self.data, self.layout = candidate.data, candidate.layout

    def validate(self) -> None:
        self.layout = Layout.parse(self.data)

    @atomic
    def reformat(self, label: str = "FAT12LAB") -> None:
        if not label.isascii():
            raise FATError('卷标必须为 ASCII 字符')
        label = label.upper()
        if not label.isascii() or not 1 <= len(label) <= 11 or any(c not in ALLOWED and c != " " for c in label) or not label.strip():
            raise FATError("卷标应为 1 至 11 个 ASCII 字符")
        if self.path and self._disk_digest is not None and self.check()['ok']:
            self.create_snapshot('格式化前自动保护点')
        g = self.layout
        self.data = bytearray(g.image_bytes)
        self.data[:3] = b"\xEB\x3C\x90"
        self.data[3:11] = b"F12LAB  "
        struct.pack_into("<HBHBHHBHHHII", self.data, 11,
                         512, g.sectors_per_cluster, g.reserved, 2, g.root_entries,
                         g.total_sectors if g.total_sectors < 65536 else 0, g.media,
                         g.fat_sectors, g.sectors_per_track, g.heads, 0,
                         0 if g.total_sectors < 65536 else g.total_sectors)
        self.data[36:39] = b"\x00\x00\x29"
        struct.pack_into("<I", self.data, 39, 0x1234ABCD)
        self.data[43:54] = label.ljust(11).encode("ascii")
        self.data[54:62] = b"FAT12   "
        # Minimal x86 halt loop. This is a data disk, not a bootable OS.
        self.data[62:66] = b"\xFA\xF4\xEB\xFD"
        self.data[510:512] = b"\x55\xAA"
        for sector in (g.reserved, g.reserved + g.fat_sectors):
            self.data[sector * 512:sector * 512 + 3] = bytes((g.media, 0xFF, 0xFF))
        self.data[g.root_sector * 512:g.root_sector * 512 + 32] = self._pack_entry(label.ljust(11).encode(), 0x08, 0, 0)

    def save(self, path: str | Path | None = None) -> None:
        if self.read_only:
            raise FATError('镜像处于只读模式，不能保存')
        target = Path(path).resolve() if path is not None else self.path
        if target is None:
            raise FATError("没有指定镜像保存路径")
        if not self._depth:
            self.validate()
            issues = self.check()['errors']
            if issues:
                raise FATError('镜像校验失败，拒绝保存：' + issues[0])
        expected = self._disk_digest if target == self.path else None
        next_digest = write_image(target, self.data, expected)
        if target == self.path:
            self._disk_digest = next_digest

    def fat_get(self, cluster: int, copy: int = 0) -> int:
        if not 0 <= cluster <= self.layout.last_cluster or copy not in (0, 1):
            raise FATError("FAT 索引越界")
        offset = (self.layout.reserved + copy * self.layout.fat_sectors) * 512 + cluster * 3 // 2
        pair = self.data[offset] | self.data[offset + 1] << 8
        return (pair >> 4 if cluster & 1 else pair) & 0xFFF

    def _fat_set(self, cluster: int, value: int) -> None:
        if not 2 <= cluster <= self.layout.last_cluster or not 0 <= value <= 0xFFF:
            raise FATError("无效 FAT 写入")
        for copy in (0, 1):
            offset = (self.layout.reserved + copy * self.layout.fat_sectors) * 512 + cluster * 3 // 2
            pair = self.data[offset] | self.data[offset + 1] << 8
            pair = ((pair & 0x000F) | (value << 4)) if cluster & 1 else ((pair & 0xF000) | value)
            struct.pack_into("<H", self.data, offset, pair)

    def cluster_offset(self, cluster: int) -> int:
        if not 2 <= cluster <= self.layout.last_cluster:
            raise FATError(f"数据簇越界：{cluster}")
        return (self.layout.data_sector + (cluster - 2) * self.layout.sectors_per_cluster) * 512

    def chain(self, start: int) -> list[int]:
        if start == 0:
            return []
        result, seen = [], set()
        current = start
        while True:
            if not 2 <= current <= self.layout.last_cluster:
                raise FATError(f"簇链包含无效簇号 {current}")
            if current in seen:
                raise FATError(f"簇链在 {current} 处形成循环")
            seen.add(current)
            result.append(current)
            value = self.fat_get(current)
            if value >= 0xFF8:
                return result
            if value == 0 or 0xFF0 <= value <= 0xFF7 or value == 1:
                raise FATError(f"簇 {current} 指向空闲、保留或坏簇 0x{value:03X}")
            current = value

    def _allocate(self, count: int) -> list[int]:
        free = [c for c in range(2, self.layout.last_cluster + 1) if self.fat_get(c) == 0]
        if len(free) < count:
            raise FATError(f"磁盘空间不足：需要 {count} 个簇，可用 {len(free)} 个")
        chain = free[:count]
        for i, cluster in enumerate(chain):
            self._fat_set(cluster, chain[i + 1] if i + 1 < len(chain) else EOC)
            offset = self.cluster_offset(cluster)
            self.data[offset:offset + self.layout.cluster_bytes] = bytes(self.layout.cluster_bytes)
        return chain

    def _free(self, start: int) -> None:
        for cluster in self.chain(start):
            self._fat_set(cluster, 0)
            offset = self.cluster_offset(cluster)
            self.data[offset:offset + self.layout.cluster_bytes] = bytes(self.layout.cluster_bytes)

    def _slots(self, directory: int) -> list[int]:
        if directory == 0:
            return [self.layout.root_sector * 512 + i * 32 for i in range(self.layout.root_entries)]
        return [self.cluster_offset(c) + i * 32 for c in self.chain(directory) for i in range(self.layout.cluster_bytes // 32)]

    def _entries(self, directory: int, include_dots: bool = False) -> list[Entry]:
        entries = []
        for offset in self._slots(directory):
            raw = self.data[offset:offset + 32]
            if raw[0] == 0:
                break
            if raw[0] == 0xE5 or raw[11] == 0x0F or raw[11] & 0x08:
                continue
            name = decode_name(raw[:11])
            if name in (".", "..") and not include_dots:
                continue
            time, date, cluster, size = struct.unpack_from("<HHHI", raw, 22)
            try:
                stamp = datetime(1980 + (date >> 9), (date >> 5) & 15, date & 31,
                                 time >> 11, (time >> 5) & 63, (time & 31) * 2).isoformat(" ")
            except ValueError:
                stamp = "未知时间"
            entries.append(Entry(name, raw[11], cluster, size, offset, stamp))
        return entries

    def _find(self, directory: int, name: str) -> Entry:
        for entry in self._entries(directory):
            if entry.name == name.upper():
                return entry
        raise FATError(f"路径不存在：{name}")

    @staticmethod
    def normalize(path: str, cwd: str = "/") -> str:
        if not path:
            path = "."
        if "\x00" in path:
            raise FATError("路径不能含 NUL 字符")
        path = path.replace("\\", "/")
        parts = [] if path.startswith("/") else [p for p in cwd.split("/") if p]
        for part in path.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
            else:
                encode_name(part)
                parts.append(part.upper())
        return "/" + "/".join(parts)

    def resolve_dir(self, path: str) -> int:
        current = 0
        for part in self.normalize(path).strip("/").split("/"):
            if not part:
                continue
            entry = self._find(current, part)
            if not entry.is_dir:
                raise FATError(f"{part} 不是目录")
            current = entry.cluster
        return current

    def _parent(self, path: str) -> tuple[int, str]:
        normalized = self.normalize(path)
        if normalized == "/":
            raise FATError("不能对根目录执行此操作")
        parent, name = normalized.rsplit("/", 1)
        return self.resolve_dir(parent or "/"), name

    def stat(self, path: str) -> Entry:
        parent, name = self._parent(path)
        return self._find(parent, name)

    def list_dir(self, path: str = "/") -> list[Entry]:
        return self._entries(self.resolve_dir(path))

    def read_file(self, path: str) -> bytes:
        entry = self.stat(path)
        if entry.is_dir:
            raise FATError("目录不能作为文件读取")
        chain = self.chain(entry.cluster)
        if len(chain) * self.layout.cluster_bytes < entry.size:
            raise FATError("文件大小超过簇链容量")
        return b"".join(self.data[self.cluster_offset(c):self.cluster_offset(c) + self.layout.cluster_bytes] for c in chain)[:entry.size]

    @staticmethod
    def _pack_entry(name: bytes, attr: int, cluster: int, size: int) -> bytes:
        raw = bytearray(32)
        raw[:11], raw[11] = name, attr
        now = datetime.now()
        year = max(1980, min(2107, now.year))
        date = ((year - 1980) << 9) | (now.month << 5) | now.day
        time = (now.hour << 11) | (now.minute << 5) | (now.second // 2)
        struct.pack_into("<HHH", raw, 14, time, date, date)
        struct.pack_into("<HHHI", raw, 22, time, date, cluster, size)
        return bytes(raw)

    def _empty_slot(self, directory: int) -> int:
        slots = self._slots(directory)
        for index, offset in enumerate(slots):
            if self.data[offset] == 0:
                # Bytes after 0x00 are unspecified on imported FAT volumes.
                # Advance the terminator along the logical chain, which need
                # not be physically contiguous. A full directory has no marker.
                if index + 1 < len(slots):
                    self.data[slots[index + 1]] = 0
                return offset
            if self.data[offset] == 0xE5:
                return offset
        if directory == 0:
            raise FATError(f"根目录项已满（容量 {self.layout.root_entries} 项，卷标也占一项）")
        chain = self.chain(directory)
        new = self._allocate(1)[0]
        self._fat_set(chain[-1], new)
        return self.cluster_offset(new)

    @atomic
    def write_file(self, path: str, content: bytes, overwrite: bool = True) -> None:
        parent, name = self._parent(path)
        encoded = encode_name(name)
        existing = next((e for e in self._entries(parent) if e.name == name), None)
        if existing and (existing.is_dir or not overwrite):
            raise FATError("目标已存在或目标是目录")
        if existing and existing.attr & 1:
            raise FATError("目标文件为只读")
        if len(content) > self.layout.cluster_count * self.layout.cluster_bytes:
            raise FATError("文件大于磁盘数据区")
        if existing:
            self._free(existing.cluster)
        chain = self._allocate(math.ceil(len(content) / self.layout.cluster_bytes))
        for i, cluster in enumerate(chain):
            block = content[i * self.layout.cluster_bytes:(i + 1) * self.layout.cluster_bytes]
            offset = self.cluster_offset(cluster)
            self.data[offset:offset + len(block)] = block
        offset = existing.offset if existing else self._empty_slot(parent)
        raw = bytearray(self._pack_entry(encoded, (existing.attr if existing else 0) | 0x20,
                                         chain[0] if chain else 0, len(content)))
        if existing:
            raw[13:20] = self.data[offset + 13:offset + 20]
        self.data[offset:offset + 32] = raw

    @atomic
    def mkdir(self, path: str) -> None:
        parent, name = self._parent(path)
        if any(e.name == name for e in self._entries(parent)):
            raise FATError("目标已存在")
        slot = self._empty_slot(parent)
        cluster = self._allocate(1)[0]
        offset = self.cluster_offset(cluster)
        self.data[offset:offset + 32] = self._pack_entry(b".          ", 0x10, cluster, 0)
        self.data[offset + 32:offset + 64] = self._pack_entry(b"..         ", 0x10, parent, 0)
        self.data[slot:slot + 32] = self._pack_entry(encode_name(name), 0x10, cluster, 0)

    @atomic
    def remove(self, path: str, directory: bool = False) -> None:
        entry = self.stat(path)
        if entry.is_dir != directory:
            raise FATError("删除目录请使用 rmdir，删除文件请使用 del")
        if entry.attr & 1:
            raise FATError("目标为只读")
        if directory and self._entries(entry.cluster):
            raise FATError("目录非空，请先删除其内容")
        self._free(entry.cluster)
        self.data[entry.offset] = 0xE5

    @atomic
    def copy(self, source: str, target: str) -> None:
        self.write_file(target, self.read_file(source), overwrite=False)

    @atomic
    def move(self, source: str, target: str) -> None:
        source, target = self.normalize(source), self.normalize(target)
        entry = self.stat(source)
        parent, name = self._parent(target)
        if entry.attr & 1:
            raise FATError("目标为只读")
        if target == source or any(e.name == name for e in self._entries(parent)):
            raise FATError("目标已存在")
        if entry.is_dir and target.startswith(source + "/"):
            raise FATError("不能把目录移动到自身的子目录中")
        source_parent, _ = self._parent(source)
        slot = entry.offset if source_parent == parent else self._empty_slot(parent)
        raw = self.data[entry.offset:entry.offset + 32]
        raw[:11] = encode_name(name)
        self.data[slot:slot + 32] = raw
        if slot != entry.offset:
            self.data[entry.offset] = 0xE5
        if entry.is_dir:
            struct.pack_into("<H", self.data, self.cluster_offset(entry.cluster) + 32 + 26, parent)

    def info(self) -> dict:
        g = self.layout
        free = sum(self.fat_get(c) == 0 for c in range(2, g.last_cluster + 1))
        return {"label": self.data[43:54].decode("ascii", "replace").rstrip(),
                'read_only':self.read_only,
                "image_bytes": len(self.data), "sector_size": 512, "total_sectors": g.total_sectors,
                "sectors_per_cluster": g.sectors_per_cluster, "reserved_sectors": g.reserved,
                "cluster_bytes": g.cluster_bytes, "total_clusters": g.cluster_count,
                "free_clusters": free, "used_clusters": g.cluster_count - free,
                "free_bytes": free * g.cluster_bytes, "data_sector": g.data_sector,
                "root_sector": g.root_sector, "fat_sectors": g.fat_sectors,
                "root_capacity": g.root_entries, "fat_type": "FAT12"}

    def check(self) -> dict:
        """Read-only consistency scan: mirrors, loops, sizes and ownership."""
        errors, owners = [], {}
        g = self.layout
        first, size = g.reserved * 512, g.fat_sectors * 512
        if self.data[first:first + size] != self.data[first + size:first + 2 * size]:
            errors.append("两份 FAT 副本不一致")
        if self.fat_get(0) != (0xF00 | g.media) or self.fat_get(1) < 0xFF8:
            errors.append("FAT 保留项或介质标识错误")
        stack, visited, files, directories = [(0, "/", 0)], set(), 0, 0
        while stack:
            directory, path, parent = stack.pop()
            if directory in visited:
                errors.append(f"{path} 目录重复引用或循环")
                continue
            visited.add(directory)
            try:
                slots = self._slots(directory)
                for offset in slots:
                    if self.data[offset] == 0:
                        break
                    if self.data[offset] != 0xE5 and self.data[offset + 11] == 0x0F:
                        errors.append(f"{path} 含长文件名目录项，本程序仅支持 8.3")
                entries = self._entries(directory, include_dots=True)
                if directory:
                    dot_entries = [e for e in entries if e.name in ('.', '..')]
                    dots = {e.name: e for e in dot_entries}
                    first_offset = self.cluster_offset(directory)
                    if ("." not in dots or ".." not in dots
                            or len(dot_entries) != 2
                            or dots["."].cluster != directory or dots[".."].cluster != parent
                            or dots['.'].offset != first_offset or dots['..'].offset != first_offset + 32
                            or any(e.size != 0 or struct.unpack_from('<H', self.data, e.offset + 20)[0] != 0 for e in dot_entries)
                            or not dots["."].is_dir or not dots[".."].is_dir):
                        errors.append(f"{path} 的 . 或 .. 目录项错误")
                names = set()
                for entry in entries:
                    if entry.name in (".", ".."):
                        continue
                    full = path.rstrip("/") + "/" + entry.name
                    if entry.name in names:
                        errors.append(f"{full} 文件名重复")
                    names.add(entry.name)
                    try:
                        encode_name(entry.name)
                        if struct.unpack_from("<H", self.data, entry.offset + 20)[0] != 0:
                            errors.append(f"{full} FAT12 高簇号应为零")
                        chain = self.chain(entry.cluster)
                        if entry.is_dir:
                            directories += 1
                            if not chain or entry.size != 0:
                                errors.append(f"{full} 目录首簇或大小错误")
                            else:
                                stack.append((entry.cluster, full, directory))
                        else:
                            files += 1
                            if len(chain) != math.ceil(entry.size / g.cluster_bytes):
                                errors.append(f"{full} 文件大小与簇链长度不匹配")
                        for cluster in chain:
                            if cluster in owners:
                                errors.append(f"簇 {cluster} 被 {owners[cluster]} 与 {full} 交叉引用")
                            owners[cluster] = full
                    except FATError as exc:
                        errors.append(f"{full}: {exc}")
            except FATError as exc:
                errors.append(f"{path}: {exc}")
        for cluster in range(2, g.last_cluster + 1):
            value = self.fat_get(cluster)
            if value != 0 and value != 0xFF7 and cluster not in owners:
                errors.append(f"孤立簇 {cluster}，FAT 值 0x{value:03X}")
        return {"ok": not errors, "errors": errors, "files": files,
                "directories": directories, "referenced_clusters": len(owners)}

    def sector(self, index: int) -> bytes:
        if not 0 <= index < self.layout.total_sectors:
            raise FATError(f"扇区号应为 0 至 {self.layout.total_sectors - 1}")
        return bytes(self.data[index * 512:(index + 1) * 512])

    def inspect_bpb(self) -> list[dict]:
        fields = ((11,2,'每扇区字节数'),(13,1,'每簇扇区数'),(14,2,'保留扇区数'),
                  (16,1,'FAT 副本数'),(17,2,'根目录项数'),(19,2,'总扇区数 16'),
                  (21,1,'介质标识'),(22,2,'每 FAT 扇区数'),(24,2,'每磁道扇区数'),
                  (26,2,'磁头数'),(28,4,'隐藏扇区数'),(32,4,'总扇区数 32'),
                  (39,4,'卷序列号'))
        return [{'offset':offset,'length':length,'field':name,
                 'raw':self.data[offset:offset+length].hex(' ').upper(),
                 'value':int.from_bytes(self.data[offset:offset+length],'little')}
                for offset,length,name in fields]

    def inspect_entry(self, path: str) -> dict:
        entry = self.stat(path)
        raw = self.data[entry.offset:entry.offset + 32]
        time, date = struct.unpack_from('<HH', raw, 22)
        flags = ((1,'只读'),(2,'隐藏'),(4,'系统'),(8,'卷标'),(16,'目录'),(32,'归档'))
        return {'offset':entry.offset,'raw':raw.hex(' ').upper(),
                'name_bytes':raw[:11].decode('ascii','replace'),
                'attributes':[name for bit,name in flags if entry.attr & bit],
                'attr_hex':f'{entry.attr:02X}', 'cluster':entry.cluster,'size':entry.size,
                'time_word':f'{time:04X}','date_word':f'{date:04X}',
                'decoded_time':{'year':1980+(date>>9),'month':(date>>5)&15,'day':date&31,
                                'hour':time>>11,'minute':(time>>5)&63,'second':(time&31)*2},
                'modified':entry.modified}

    def inspect_fat(self, cluster: int) -> dict:
        value = self.fat_get(cluster)
        offset = self.layout.reserved * 512 + cluster * 3 // 2
        raw = self.data[offset:offset+2]
        return {'cluster':cluster,'value':value,'offset':offset,'raw':raw.hex(' ').upper(),
                'word':int.from_bytes(raw,'little'),'odd':bool(cluster & 1),
                'formula':'(word >> 4) & 0xFFF' if cluster & 1 else 'word & 0xFFF',
                'data_sector':self.cluster_offset(cluster)//512 if cluster >= 2 else None}
