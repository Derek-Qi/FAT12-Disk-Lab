# Security and data boundaries

FAT12 Disk Lab is a local, single-user educational tool. It is not intended to be exposed as a hosted Internet service. The HTTP adapter binds to loopback, validates Host/Origin, limits body sizes, and exposes only bundled assets and the selected image. Host-file import/export is unavailable through the web command interpreter.

Use read-only mode for unknown or reference images. Writable operations require a healthy supported layout and filesystem; snapshots and compaction plans are not an authenticity mechanism. Snapshot paths reject directory-link escape, but the tool does not claim to resist a malicious local process racing filesystem changes.

Image writes use cooperating OS locks, SHA256 version checks, a synchronized temporary file and atomic replacement. This is command-level atomicity; it is not a power-loss journal. Snapshot pairs are not automatically pruned. Uncooperative external writers and cloud-sync software should be used separately from an active write session.

For security vulnerabilities, use [GitHub private vulnerability reporting](https://github.com/Derek-Qi/FAT12-Disk-Lab/security/advisories/new). For other bugs, open a [GitHub issue](https://github.com/Derek-Qi/FAT12-Disk-Lab/issues). Provide the affected version and a minimal synthetic image or reproduction. Do not include real disk contents, credentials or private user files. Review dependencies with `npm audit` and rebuild compiled assets after development-tool updates.
