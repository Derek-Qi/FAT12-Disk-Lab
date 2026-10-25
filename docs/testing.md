# Verification guide

## Standard-library tests

```sh
python -m unittest discover -s tests -v
python tools/verify_project.py
```

Coverage includes FAT packing and neighbor preservation, allocation/freeing, directory growth and dot references, model-based mutations, invalid geometry, Windows command paths, HTTP guards, real process locks, snapshots, stale previews, compaction preservation and rollback.

Two child-process tests pause a real writer immediately before or after `os.replace`, kill it, and reopen the image. Before replacement the previous image must be byte-identical; after replacement the complete new file must be readable. A subsequent write proves the OS lock was released. These are process-crash observations, not abrupt-power-loss guarantees.

Receipts include Python, OS, a UTC timestamp and the client date in Asia/Shanghai. A local Windows receipt does not prove Linux or other Python versions passed; the Actions job results provide that evidence.

## Browser and dependency checks

```sh
cd web
npm ci
npm run build
npm audit
cd ..
python tools/check_browser.py
```

The optional `agent-browser` CLI and its browser must be installed separately. The script owns a random-port server and disposable image. It checks read-only analysis/preview, snapshot creation/restore, FAT-to-sector links, dirty-editor navigation, narrow layout, damaged FAT recovery, raw protection-point refusal, preview invalidation, confirmed compaction and read-only refusal. Actual screenshots are kept in `artifacts/screenshots/`.

## Independent FAT implementation

In an isolated development environment:

```sh
python -m pip install pyfatfs==1.1.0 "setuptools<81"
python tools/check_interop.py
```

PyFatFS is an optional oracle; it is not a runtime dependency. The check uses disposable image copies and covers both floppy layouts and post-compaction read/write interoperability. Its older dependency stack may emit a deprecation notice.

## Distribution and public-source checks

```sh
python -m pip install "setuptools>=68" wheel
python tools/build_wheel.py
python tools/check_distribution.py artifacts/releases/fat12_disk_lab-1.2.0-py3-none-any.whl
python tools/public_release.py
python tools/package_release.py
python tools/check_release.py artifacts/releases/FAT12Lab-v1.2.0.zip
```

A fresh staging directory prevents obsolete assets entering a wheel. The clean venv check verifies the installed console entry, snapshots, compaction, read-only HTTP and referenced assets. The source-archive check verifies CRC/all SHA256 entries, extracts outside the repository, runs the full suite and exercises the bundled read-only demo.

The public allowlist excludes course references, old reports, private disks, local execution ledgers and credentials. It scans selected text for common secret/home-path patterns. This is a useful publication guard, not a proof that arbitrary content contains no sensitive information.
