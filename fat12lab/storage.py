"""Cross-process persistence primitives, independent of FAT directory logic."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile


class ConcurrentWriteError(OSError):
    """A cooperative writer is active or this instance has an outdated image."""


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


@contextmanager
def image_lock(path: Path | str):
    """Nonblocking OS lock on a stable sidecar; never unlink its inode.

    Locking the image itself would conflict with atomic replacement on Windows.
    OS locks are released when the process exits, including abnormal exits.
    """
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.with_name(target.name + '.fat12.lock').open('a+b') as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b'\0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ConcurrentWriteError('另一个进程正在写入镜像，请稍后重试') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def check_version(target: Path, expected: str | None) -> None:
    if expected is None:
        if target.exists():
            raise ConcurrentWriteError('目标镜像已存在，拒绝覆盖')
    elif not target.is_file() or file_digest(target) != expected:
        raise ConcurrentWriteError('镜像已被其他进程修改，请重新读取磁盘后再操作')


def write_image(path: Path, data: bytes | bytearray, expected: str | None) -> str:
    content = bytes(data)
    next_digest = digest(content)
    with image_lock(path):
        check_version(path, expected)
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return next_digest
