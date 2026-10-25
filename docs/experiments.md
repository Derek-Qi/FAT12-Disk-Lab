# Reproducing the compaction experiment

```sh
python tools/compaction_experiment.py
```

The script creates three in-memory volumes using seed **20261025**. It writes out-of-order files, nested directories, binary contents and an empty file, deletes selected files, and overwrites others to produce fragmentation. It never mutates the shipped demo or an inherited image.

| Case | Image bytes | Cluster bytes | File extents before → after | File contents + metadata |
| --- | ---: | ---: | ---: | --- |
| 1.44MB floppy (1440KiB) | 1,474,560 | 512 | 33 → 23 | matching SHA256 |
| 720KiB floppy | 737,280 | 1,024 | 33 → 23 | matching SHA256 |
| Interleaved bad cluster | 1,474,560 | 512 | 34 → 23 | matching SHA256 |

Every case checks that preview leaves the source byte-identical, application passes consistency checks, and planning the compacted image again moves zero clusters. Inventory hashing covers paths, object types, active file bytes, attributes, timestamps, sizes and other directory metadata, excluding the first-cluster pointer that relocation intentionally changes. Dot-reference consistency is checked separately by the engine and regression tests.

See [the actual receipt](../artifacts/compaction-results.json). File timestamps are generated during a run, so inventory hashes may differ across reruns; before and after must match within each run. Geometry, fixed-seed file contents and the reported extent counts are reproducible.

The recorded times cover only the Python in-memory planning/application functions. They do not include physical-device latency, persistent snapshots, fsync or real storage throughput. No disk-speed improvement is inferred from these timings or extent counts.

Bad clusters remain unavailable, with their marker and bytes preserved. Sorted-path packing can still split an object around a bad cluster in other layouts. It is not claimed to be optimal. Relocation does not change file slack or create additional usable clusters.

For cross-implementation validation, `tools/check_interop.py` lets PyFatFS read every file/directory after compaction and write another file, which is then reopened with this engine. This checks real interoperability rather than relying only on the project's own reader.
