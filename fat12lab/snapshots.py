"""Immutable recovery points with bounded metadata and verified payloads."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import uuid

from .storage import check_version, digest, image_lock

MAX_BYTES = 16 * 1024 * 1024


class SnapshotError(OSError):
    pass


def folder_for(image: Path) -> Path:
    return image.with_name(image.name + '.snapshots')


def checked_folder(image: Path) -> Path:
    folder = folder_for(image.resolve())
    try:
        if folder.resolve() != folder:
            raise SnapshotError('快照目录不能通过链接指向其他位置')
    except (OSError, RuntimeError) as exc:
        raise SnapshotError('快照目录路径校验失败') from exc
    return folder


def paths_for(image: Path, identifier: str) -> tuple[Path, Path]:
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise SnapshotError('快照编号无效')
    folder = checked_folder(image)
    paths = tuple(folder / (identifier + suffix) for suffix in ('.img', '.json'))
    if any(not path.resolve().is_relative_to(folder) for path in paths):
        raise SnapshotError('快照路径越界')
    return paths


def metadata_for(image: Path, identifier: str) -> dict:
    _, metadata_path = paths_for(image, identifier)
    try:
        if metadata_path.stat().st_size > 4096:
            raise ValueError('metadata too large')
        item = json.loads(metadata_path.read_text(encoding='utf-8'))
        if (not isinstance(item, dict) or item.get('version') != 1 or item.get('id') != identifier
                or type(item.get('image_bytes')) is not int or not 512 <= item['image_bytes'] <= MAX_BYTES
                or not isinstance(item.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', item['sha256'])
                or not isinstance(item.get('label'), str) or len(item['label']) > 80
                or type(item.get('restorable', True)) is not bool
                or not isinstance(item.get('created_at'), str)
                or datetime.fromisoformat(item['created_at']).tzinfo is None):
            raise ValueError('invalid metadata')
        return item
    except (OSError, ValueError, TypeError) as exc:
        raise SnapshotError('快照元数据缺失或校验失败') from exc


def create(image: Path, content: bytes, expected: str | None, label: str = '', *, restorable: bool = True) -> dict:
    if not isinstance(label, str) or len(label) > 80:
        raise SnapshotError('快照名称最多 80 个字符')
    identifier = uuid.uuid4().hex
    item = {'version':1,'id':identifier,'label':label,
            'created_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'image_bytes':len(content),'sha256':digest(content),'restorable':restorable}
    payload, metadata = paths_for(image, identifier)
    with image_lock(image):
        check_version(image, expected)
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload_created = metadata_created = False
        try:
            with payload.open('xb') as stream:
                payload_created = True
                stream.write(content)
                stream.flush(); os.fsync(stream.fileno())
            # Metadata is the publication marker; incomplete payloads are not listed.
            with metadata.open('x', encoding='utf-8') as stream:
                metadata_created = True
                json.dump(item, stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
        except Exception:
            if payload_created:payload.unlink(missing_ok=True)
            if metadata_created:metadata.unlink(missing_ok=True)
            raise
    return item


def listing(image: Path) -> list[dict]:
    items = []
    for path in checked_folder(image).glob('*.json'):
        if not re.fullmatch('[a-f0-9]{32}', path.stem):
            continue
        try:
            items.append(metadata_for(image, path.stem))
        except SnapshotError as exc:
            items.append({'id':path.stem,'label':'快照不可读取','created_at':'',
                          'image_bytes':0,'sha256':'','error':str(exc)})
    return sorted(items, key=lambda item:item['created_at'], reverse=True)


def read(image: Path, identifier: str) -> bytes:
    item = metadata_for(image, identifier)
    if not item.get('restorable', True):
        raise SnapshotError('此保护点保留受损镜像原始字节，仅供分析，不能直接恢复')
    payload, _ = paths_for(image, identifier)
    if payload.stat().st_size != item['image_bytes']:
        raise SnapshotError('快照大小校验失败')
    content = payload.read_bytes()
    if digest(content) != item['sha256']:
        raise SnapshotError('快照 SHA256 校验失败，拒绝恢复')
    return content
