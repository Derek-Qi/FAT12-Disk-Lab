"""Shared dates and environment facts for reproducible verification receipts."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import platform
import sys
import tomllib

ROOT=Path(__file__).resolve().parent.parent


def project_version() -> str:
    return tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def metadata(now: datetime | None = None) -> dict:
    instant=now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('Evidence timestamps must include a timezone')
    return {'date':instant.astimezone(timezone(timedelta(hours=8))).date().isoformat(),
            'date_timezone':'Asia/Shanghai',
            'generated_at_utc':instant.astimezone(timezone.utc).isoformat(timespec='seconds'),
            'version':project_version(),'python':sys.version.split()[0],'system':platform.system()}
