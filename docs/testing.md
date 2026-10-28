# Verification guide

## Standard-library tests

```sh
python -m unittest discover -s tests -v
python tools/verify_project.py
```

Coverage includes FAT packing and neighbor preservation, allocation/freeing, directory growth and dot references, model-based mutations, invalid geometry, Windows command paths, HTTP guards, real process locks, snapshots, stale previews, compaction preservation and rollback.

The independent 24-bit FAT-pair oracle in `tests/test_fat12_oracle.py` checks all 4096 target values for two pair positions, both parities and three neighbour values, including the cross-sector entry. Its scope and limitations are specified in [the evidence matrix](experiments.md#research-style-evidence-matrix-english).

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

The v1.2.1 checks also exercise keyboard focus in delete/restore dialogs, unload protection registration, and stale editor saves. A conflicting save must preserve both the newer disk content and the browser draft. Native unload dialogs depend on browser activation rules; registering a handler is not a guarantee against all ways of closing a browser.

The browser CI job uses the Chrome supplied by the pinned Ubuntu 24.04 runner image through `AGENT_BROWSER_EXECUTABLE_PATH`, avoiding a second browser/system-dependency installation. It prints the detected browser version and has a ten-minute job limit. The [runner software inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md#browsers-and-drivers) documents that environment; local checks can still use agent-browser's own installed browser.

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
python tools/check_distribution.py artifacts/releases/fat12_disk_lab-1.2.1-py3-none-any.whl
python tools/public_release.py
python tools/package_release.py
python tools/check_release.py artifacts/releases/FAT12Lab-v1.2.1.zip
```

A fresh staging directory prevents obsolete assets entering a wheel. The clean venv check verifies the installed console entry, snapshots, compaction, read-only HTTP and referenced assets. The source-archive check verifies CRC/all SHA256 entries, extracts outside the repository, runs the full suite and exercises the bundled read-only demo.

Release assembly rejects successful receipts from another version and requires the tested wheel for the current version. In the local coursework checkout, `check_release.py --course <archive>` additionally checks the Chinese instructions, technical report and slides, then runs the extracted tests. Course-only documents are intentionally absent from the public repository.

The public allowlist excludes course references, old reports, private disks, local execution ledgers and credentials. It scans selected text for common secret/home-path patterns. This is a useful publication guard, not a proof that arbitrary content contains no sensitive information.
