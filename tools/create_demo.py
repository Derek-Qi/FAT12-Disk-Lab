"""Create a reproducible example disk with nested directories and fragmentation."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fat12lab import FAT12
from fat12lab.filesystem import Layout


def populate(fs):
    fs.mkdir("/DOCS")
    fs.mkdir("/LAB")
    fs.write_file("/README.TXT", "欢迎使用 FAT12 磁盘实验台。\n命令行输入 help。图形界面可查看簇链和扇区。\n本镜像使用 ASCII 8.3 文件名，文件内容支持 UTF-8 中文。\n".encode())
    fs.write_file("/DOCS/NOTES.TXT", "FAT12 实验笔记\n\n扇区大小：512 字节\n数据区起始：LBA 33\n簇 2 对应 LBA 33\n\n写入文件时分配簇，再更新 FAT 和目录项。\n删除文件时释放簇，并将目录项首字节置为 E5。\n".encode())
    fs.write_file("/LAB/GAP.BIN", b"G" * 1024)
    fs.write_file("/LAB/KEEP.TXT", b"This allocated cluster keeps the example fragmented.\n")
    fs.remove("/LAB/GAP.BIN")
    text = "FAT12 cluster chain experiment\n" + "0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ\n" * 50
    fs.write_file("/LAB/CHAIN.TXT", text.encode())
    fs.write_file("/LAB/EMPTY.TXT", b"")
    fs.write_file("/LAB/BYTES.BIN", bytes(range(256)) * 8 + b"binary-round-trip")
    return fs


def create720(target, *, overwrite=False):
    """Our own clean 720 KiB fixture; no inherited course content is copied."""
    fs = FAT12.create(target,'LAB720',Layout(1440,2,1,3,112,0xF9,9,2),overwrite=overwrite)
    fs.mkdir('/LAB')
    fs.write_file('/README.TXT','720 KiB FAT12\n每扇区 512 字节，每簇 2 扇区，数据区 LBA 14。\n'.encode())
    fs.write_file('/LAB/PROBE.BIN',bytes(range(256))*9)
    return fs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', nargs='?', type=Path)
    parser.add_argument('--720', dest='small_disk', action='store_true', help='Create the 720 KiB example')
    parser.add_argument('--replace', action='store_true', help='Explicitly replace an existing demo')
    options = parser.parse_args()
    target = options.image or Path('data/demo720.img' if options.small_disk else 'data/demo.img')
    if target.exists() and not options.replace:
        raise SystemExit('Target exists. Use --replace explicitly to regenerate the demo.')
    fs = create720(target,overwrite=options.replace) if options.small_disk else populate(FAT12.create(target, 'OSLAB',overwrite=options.replace))
    print(fs.check())
    if not options.small_disk:
        print('CHAIN.TXT:', fs.chain(fs.stat('/LAB/CHAIN.TXT').cluster))
