# Portfolio and CV facts

**FAT12 Disk Lab — Python, React, TypeScript, filesystem images**

Built an AI-assisted, byte-level FAT12 workbench with BPB-derived geometry, fragmented file I/O, hierarchical directories and a shared CLI/HTTP engine. Added allocation analysis and deterministic compaction with source-bound previews, metadata/content preservation checks and snapshot protection.

Implemented guarded persistence using OS process locks, SHA256 version checks, rollback and atomic image replacement. Validated behavior with standard-library regression/model tests, real process-termination checks, independent FAT interoperability, browser flows and clean-environment package installation.

中文：实现基于镜像字节的 FAT12 文件系统工作台，支持动态 BPB 布局、碎片簇链、多级目录及共享命令行/HTTP 内核；增加空间分析和可预览整理，校验活动内容与元数据保持一致，并在整理前保存保护点。

中文：通过进程锁、内容版本检测、失败回滚和原子替换保护写盘；使用模型测试、真实子进程终止检查、独立 FAT 实现互通、浏览器操作及干净环境安装验证。

Use current receipts and actual Actions results for counts/environments. Do not describe extent reduction as measured disk acceleration, process-kill checks as power-loss recovery, or this educational project as a production driver/research publication. AI assistance is extensive and disclosed in the README. The public repository contains the curated engineering release, not inherited course materials or the local private history.

## Bilingual application material / 中英文申请素材

The following is a project description, not a statement that the applicant personally authored every component. Tailor it to work you actually understand and performed, retain the AI-assistance disclosure, and use the evidence at the cited revision.

**English:** FAT12 Disk Lab is an AI-assisted educational filesystem workbench that manipulates raw FAT12 image structures and exposes a CLI and a browser interface. Its compaction workflow makes preservation and failure boundaries inspectable through a source-bound preview, consistency checks and snapshot protection. Verification includes a finite-value byte-level FAT packing oracle, selected deterministic compaction cases, process-termination tests and interoperability checks with PyFatFS. The documented results are limited to tested cases and do not establish production readiness, power-loss safety or I/O speedup.

**中文：** FAT12 Disk Lab 是一个使用 AI 辅助开发的教学型文件系统工作台，直接处理 FAT12 镜像结构，并提供命令行和浏览器界面。整理流程通过绑定原镜像的预览、一致性检查和快照保护，使数据保持与失败边界可以被观察和检验。项目验证包括有限值域下的 FAT 原始字节参照测试、选定的确定性整理样例、进程终止测试，以及与 PyFatFS 的互操作检查。结论仅适用于已测试的场景，不能据此宣称生产级可靠性、断电安全或磁盘加速。

For an application or interview, describe your actual contribution and decisions in your own words; do not claim unaided authorship or independent replication unless those claims are true. See [the bilingual evidence matrix and limitations](experiments.md#research-style-evidence-matrix-english).

申请或面试中，请依据本人实际参与和理解的部分描述贡献；不要将大量 AI 辅助开发说成完全独立编写，也不要声称他人已完成独立复现。证据和局限见[中英文实验说明](experiments.md#学术证据与复现说明中文)。
