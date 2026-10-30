# FAT12 Disk Lab 中文使用说明

这是一个直接读写 FAT12 磁盘镜像字节的系统工程项目。1.2 系列在原有文件操作、原始字段解码和快照恢复上，增加空间分析与可预览的磁盘整理。

v1.2.1 完成提交前稳定性检查：修复外部卷目录结束标记、空脚本执行和过期编辑覆盖，补充离页保护与确认框键盘操作，并校验发布包使用当前版本的测试记录。

项目的[中英文实验说明](docs/experiments.md)列出证据、复现方法和局限；[中英文申请素材](docs/portfolio.md)明确说明 AI 辅助与可支持的表述。
## 快速运行

需要 Python 3.11 或更高版本，运行时只使用标准库。前端已经构建，不必先安装 Node.js。

```powershell
python -m fat12lab --image data/demo.img --read-only --web
```

此命令只读观察演示盘。Windows 双击 `start.bat` 会在首次运行时把演示盘复制为 `data/work.img`，后续写入仅保存到工作盘。`cli.bat` 打开命令行。不要把原始课件镜像直接作为可写工作盘。

## 可以完成什么

- format、dir、type、mkdir、创建、覆盖、追加、复制、移动、重命名、删除及簇回收，共32条共享命令。
- 多级目录、目录扩展、碎片簇链、空文件、二进制与 UTF-8 文本。
- 文件管理、编辑、上传下载、镜像加载导出，以及 BPB、目录项、FAT 和扇区原始字节解析。
- 簇链 → FAT 表项 → 数据扇区联动，精确操作字节变化统计。
- 只读分析、版本冲突拒绝、进程锁、失败回滚、校验式快照与受损状态恢复。
- 分析有效内容、分配空间、文件尾部空闲、连续段、连续空闲区和坏簇；先预览，再确认整理。

```text
mkdir TRYOUT
write TRYOUT/HELLO.TXT "Hello FAT12"
dir TRYOUT
type TRYOUT/HELLO.TXT
analyze
defrag --dry-run
snapshot "完成实验"
fsck
```

`defrag --dry-run` 返回绑定当前镜像 SHA256 的计划。正式整理使用 `defrag 预览中的SHA256`，也可以在“磁盘分析”界面确认执行。发生修改后，旧预览会被拒绝，必须重新预览。

整理会迁移文件和目录、修改 FAT 与目录引用，保留活动内容及元数据，并跳过坏簇。正式写盘前自动创建完整保护点。空闲簇中的旧字节可能被清空，因此整理不适合取证保全。

## 验证

```powershell
python -m unittest discover -s tests -v
python tools/verify_project.py
python tools/compaction_experiment.py
python tools/check_browser.py
```

固定种子实验覆盖两种布局及坏簇场景，用内容与元数据哈希验证前后一致，检查重复规划为零迁移。连续段变化用于描述布局，不冒充磁盘实测提速。测试还实际强制结束处于提交前后的写入子进程；这不等于突然断电试验。

完整结果以 `artifacts/` 中的当前 JSON 为准；日期采用 Asia/Shanghai，并另存 UTC 时间戳。独立互通检查需要可选的 `pyfatfs==1.1.0` 和 `setuptools<81`，不参与运行时读写。

## 工程边界

支持无分区偏移的 FAT12 裸卷、ASCII 8.3 短文件名、512字节扇区、两份 FAT 和固定根目录，镜像最大16MiB。没有长文件名、FAT16/32、启动系统、自动修复或完整断电日志。整盘内存事务易于解释和验证，但每次写入有复制和全盘检查成本。

同一个 Python 对象由调用方串行使用，HTTP 已串行化。锁协调本项目写入者；其他工具应轮流操作。快照不自动清理，SHA256 不提供身份认证。严重引导区损坏时，可从健康快照载荷建立新工作副本。

本项目由本人独立完成，过程中部分使用 AI 辅助并复制部分 AI 生成内容；AI 也参与后续优化、测试和文档整理。公开介绍以源码和实际记录为依据。

[英文项目说明](README.md) · [架构与取舍](docs/architecture.md) · [实验复现](docs/experiments.md) · [简历素材](docs/portfolio.md)
