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

## Research-style evidence matrix (English)

This is an educational engineering investigation, not a claim of a novel algorithm, a peer-reviewed publication, or a formal proof. The question is: **for the supported FAT12 image subset, can relocation reduce fragmentation in selected constructed examples while preserving active contents and filesystem structure?** The evidence below is intentionally narrower than universal filesystem correctness.

| Claim | Method and observable evidence | Boundary / alternative explanation |
| --- | --- | --- |
| 12-bit entry packing respects adjacent bits in the tested cases | `python -m unittest tests.test_fat12_oracle -v`: a separate 24-bit little-endian pair model checks raw bytes, both FAT copies, reader values and neighbouring guard bytes for all 4,096 target values, both parities, pair positions 2/3 and 340/341, and three adjacent values. Entry 341 crosses a 512-byte sector boundary. | 49,152 combinations, not all cluster positions or all 4,096 neighbour values; this tests packing, not allocation semantics or arbitrary damaged volumes. The oracle and implementation could still share a misunderstanding of the format. |
| Selected compactions preserve active inventory and reduce file extents | `python tools/compaction_experiment.py`; inspect `artifacts/compaction-results.json`: the script checks image equality after preview, hashes before/after inventory, consistency and zero moves in a second plan. | Three constructed cases from one seed; hashes depend on generated timestamps. There is no random-population estimate, significance test, hardware measurement, or claim that extent reduction makes I/O faster. |
| A distinct implementation can interpret selected resulting images | `python tools/check_interop.py`, after the pinned optional installation in [testing.md](testing.md); it enumerates and reads compacted files with PyFatFS and tests a write-back round trip. | One third-party implementation and specific images do not establish universal interoperability, standards conformance, or independent human replication. PyFatFS and this code may share assumptions. |
| A terminated writer leaves an old or complete new image at the observed commit boundaries | `python -m unittest tests.test_storage -v`; examine the process-termination tests and actual platform results. | Process termination and OS-mediated replacement do not simulate sudden power loss, storage-controller caches, filesystem bugs or non-cooperating writers. |

The format oracle is grounded in [Microsoft FAT Specification 1.03, section on FAT12 FAT entries](https://www.pcjs.org/documents/papers/microsoft/MS_FAT_OVERVIEW_103-2000-12-06.pdf). Two adjacent 12-bit entries occupy three bytes: interpret those bytes as a little-endian 24-bit integer `p`, then the even entry is `p & 0xFFF` and the odd entry is `(p >> 12) & 0xFFF`. The test constructs the expected three bytes from those two values and inspects surrounding bytes; it does not use the production setter to construct the expected result.

### Protocol and interpretation

1. Record the repository commit (`git rev-parse HEAD`), operating system and Python version (`python --version`). Run from a clean checkout; do not overwrite valuable images. The experiment uses in-memory images and writes only its receipt.
2. Run the packing test above, the complete unittest command in [testing.md](testing.md), then the compaction experiment. Preserve the console output and generated receipt with the exact revision and environment.
3. For each case compare extent counts and the two inventory hashes **within that run**. The `before` and `after` counts report layout; the hashes provide a practical collision-resistant check, not a mathematical proof of equality. Per-run time values are diagnostic and have no statistical interpretation.
4. Optionally run PyFatFS checks in an isolated environment; record its exact version and dependency installation. Check the CI run for the particular commit before saying a platform passed. A fresh result is not automatically established by an older receipt.
5. An independent person should follow the protocol on a separately prepared environment and report deviations. This repository supplies a rerun procedure; it does **not** claim such an independent replication has already occurred.

Planned stronger evidence, not completed results: more workload seeds and geometries, mutation/fault injection with recorded seeds, another independent FAT implementation, and realistic storage benchmarks with repeated trials and an explicit baseline. A human replication report would strengthen a graduate application; a theoretical guarantee would require a separate proof and precise assumptions.

## 学术证据与复现说明（中文）

本项目属于教学与工程实践，不宣称提出新算法、发表论文或完成形式化证明。要检验的问题是：**在本项目支持的 FAT12 镜像范围内，针对选定的构造样例，整理能否减少碎片连续段，同时保持活动内容与文件系统结构？**

| 可陈述的结论 | 证据与运行方式 | 不能由此推出 |
| --- | --- | --- |
| 在选定位置和相邻值下，FAT12 表项的 12 位写入与读取符合独立的三字节参照模型 | `python -m unittest tests.test_fat12_oracle -v`：覆盖全部 4096 个目标值、奇偶表项、普通与跨扇区位置、三种相邻值和两份 FAT，检查原始字节及前后保护字节。 | 共 49152 组输入，并非穷尽所有位置和所有相邻值；不证明整个文件系统正确。参照模型也可能与实现共享规范理解错误。 |
| 对三个固定种子构造样例，整理前后活动内容和纳入清单的元数据哈希一致，且所报告的文件连续段减少 | `python tools/compaction_experiment.py`；核对 `artifacts/compaction-results.json` 内同一次运行的前后结果、预览不变及再次规划零迁移。 | 三个样例不能代表所有工作负载；没有真实磁盘测速、统计显著性或性能提升结论。哈希比较是实用验证而非数学证明。 |
| 一种独立 FAT 实现可读取选定整理结果并完成写回 | 按 [验证指南](testing.md) 安装指定 PyFatFS 版本后运行 `python tools/check_interop.py`。 | 不等于通过所有 FAT 工具、全部标准一致性测试或其他研究者的独立复现。 |
| 指定提交点附近终止进程后，测试观察到旧镜像或完整新镜像 | `python -m unittest tests.test_storage -v`，结合具体平台的实际测试记录。 | 不能等同于突然断电、控制器缓存、文件系统故障或不遵守锁的外部写入者。 |

复现时记录源码提交号、操作系统和 Python 版本；在干净副本中依次运行完整测试、整理实验和可选互通测试，保存终端输出与 JSON 记录。比较的是**同一次运行**的整理前后哈希；生成的时间戳会使不同运行的哈希不同。报告现有版本的云端结果时，应核对对应提交的实际 CI 记录，不能用旧结果代替新版本的验证。

进一步工作包括更多随机种子与布局、可重放的故障注入、第二种独立 FAT 实现以及带重复试验和基线的真实存储测试。这些均为后续建议，不是已经完成的成果。邀请他人在独立环境复现并记录差异，会比增加无法验证的宣传用语更有说服力。
