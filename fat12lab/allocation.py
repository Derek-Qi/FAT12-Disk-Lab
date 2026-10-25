"""Read-only allocation measurements and deterministic FAT12 relocation.

Compaction preserves active files and metadata, not deleted/free-cluster bytes.
The caller owns snapshots, transaction rollback and persistent version checks.
"""
from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from .storage import digest

if TYPE_CHECKING:
    from .filesystem import FAT12


def extents(chain: list[int]) -> int:
    return int(bool(chain)) + sum(right != left + 1 for left, right in zip(chain, chain[1:]))


def free_runs(fs: FAT12) -> list[int]:
    runs=[]
    length=0
    for cluster in range(2, fs.layout.last_cluster+1):
        if fs.fat_get(cluster)==0:
            length+=1
        elif length:
            runs.append(length);length=0
    if length:runs.append(length)
    return runs


def analyze(fs: FAT12) -> dict:
    check=fs.check()
    result={'schema_version':1,'image_sha256':digest(fs.data),'check':check,
            'cluster_bytes':fs.layout.cluster_bytes,'summary':None,'objects':[]}
    if not check['ok']:
        return result
    objects=[]
    pending=['/']
    while pending:
        directory=pending.pop()
        for entry in fs.list_dir(directory):
            path=directory.rstrip('/')+'/'+entry.name
            chain=fs.chain(entry.cluster)
            allocated=len(chain)*fs.layout.cluster_bytes
            objects.append({'path':path,'is_dir':entry.is_dir,'chain':chain,
                            'logical_bytes':entry.size,'allocated_bytes':allocated,
                            'slack_bytes':0 if entry.is_dir else allocated-entry.size,
                            'extents':extents(chain)})
            if entry.is_dir:pending.append(path)
    objects.sort(key=lambda item:item['path'])
    files=[item for item in objects if not item['is_dir']]
    runs=free_runs(fs)
    bad=sum(fs.fat_get(c)==0xFF7 for c in range(2,fs.layout.last_cluster+1))
    result.update(objects=objects,summary={
        'files':len(files),'directories':len(objects)-len(files),
        'logical_bytes':sum(item['logical_bytes'] for item in files),
        'file_allocated_bytes':sum(item['allocated_bytes'] for item in files),
        'directory_allocated_bytes':sum(item['allocated_bytes'] for item in objects if item['is_dir']),
        'slack_bytes':sum(item['slack_bytes'] for item in files),
        'fragmented_files':sum(item['extents']>1 for item in files),
        'fragmented_directories':sum(item['extents']>1 for item in objects if item['is_dir']),
        'file_extents':sum(item['extents'] for item in files),
        'free_clusters':sum(runs),'free_runs':len(runs),'largest_free_run':max(runs,default=0),
        'bad_clusters':bad})
    return result


def prepare_compaction(fs: FAT12) -> tuple[bytearray, dict]:
    """Build a validated candidate without mutating the source or its disk."""
    from .filesystem import FAT12, FATError, EOC

    before=analyze(fs)
    if not before['check']['ok']:
        raise FATError('镜像存在错误，不能规划整理：'+before['check']['errors'][0])
    ordered=[cluster for item in before['objects'] for cluster in item['chain']]
    available=[c for c in range(2,fs.layout.last_cluster+1) if fs.fat_get(c)!=0xFF7]
    mapping=dict(zip(ordered,available))
    candidate=FAT12(bytes(fs.data))
    width=fs.layout.cluster_bytes
    for cluster in available:
        candidate._fat_set(cluster,0)
        offset=fs.cluster_offset(cluster)
        candidate.data[offset:offset+width]=bytes(width)
    for old,new in mapping.items():
        source,target=fs.cluster_offset(old),fs.cluster_offset(new)
        candidate.data[target:target+width]=fs.data[source:source+width]
    for item in before['objects']:
        chain=[mapping[c] for c in item['chain']]
        for index,cluster in enumerate(chain):
            candidate._fat_set(cluster,chain[index+1] if index+1<len(chain) else EOC)

    data_start=fs.layout.data_sector*512
    def relocated_offset(offset: int) -> int:
        if offset<data_start:return offset
        cluster,within=divmod(offset-data_start,width)
        return fs.cluster_offset(mapping[cluster+2])+within

    directories=[0]+[item['chain'][0] for item in before['objects'] if item['is_dir']]
    for directory in directories:
        for entry in fs._entries(directory,include_dots=True):
            struct.pack_into('<H',candidate.data,relocated_offset(entry.offset)+26,
                             mapping.get(entry.cluster,0))
    after=analyze(candidate)
    if not after['check']['ok']:
        raise FATError('整理候选校验失败：'+after['check']['errors'][0])
    plan={'schema_version':1,'image_sha256':before['image_sha256'],
          'moved_clusters':sum(old!=new for old,new in mapping.items()),
          'mapping':[{'from':old,'to':new} for old,new in mapping.items()],
          'before':before['summary'],'after':after['summary']}
    return candidate.data,plan
