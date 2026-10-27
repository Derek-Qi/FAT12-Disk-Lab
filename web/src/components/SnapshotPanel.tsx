import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useDialogFocus } from '../lib/useDialogFocus'
import type { Disk, Snapshot } from '../types'

type Props = { disk:Disk; busy:boolean; mutate:(route:string,body:object,display:string)=>Promise<boolean|undefined> }

export function SnapshotPanel({disk,busy,mutate}:Props) {
  const [items,setItems]=useState<Snapshot[]>([])
  const [label,setLabel]=useState('')
  const [error,setError]=useState('')
  const [pending,setPending]=useState<Snapshot|null>(null)
  const dialogRef=useDialogFocus<HTMLFormElement>(!!pending)
  useEffect(()=>{
    if(!pending)return
    const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!busy)setPending(null)}
    window.addEventListener('keydown',close)
    return()=>window.removeEventListener('keydown',close)
  },[pending,busy])
  useEffect(()=>{
    let active=true
    api<{snapshots:Snapshot[]}>('/api/snapshots').then(result=>{if(active){setItems(result.snapshots);setError('')}}).catch(e=>{if(active)setError(e.message)})
    return()=>{active=false}
  },[disk])
  return <div className="education-panel snapshot-panel">
    <h3>保存与恢复磁盘状态</h3>
    <p>快照保存完整镜像及 SHA256 校验值。恢复前会自动保存当前状态；受损状态保留为仅供分析的原始保护点。</p>
    <form className="snapshot-create" onSubmit={e=>{e.preventDefault();void mutate('/api/snapshot',{label},'创建快照')}}>
      <label>快照名称<input value={label} maxLength={80} disabled={busy||disk.info.read_only} onChange={e=>setLabel(e.target.value)} placeholder="例如：完成目录实验"/></label>
      <button className="button primary" disabled={busy||disk.info.read_only}>创建快照</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {!items.length?<p>暂无快照。保存一个检查点后，可以继续修改文件，再恢复对比。</p>:<div className="table-scroll"><table className="evidence-table"><thead><tr><th>名称</th><th>创建时间</th><th>镜像大小</th><th>操作</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td><b>{item.label||'未命名快照'}</b><small className="snapshot-id">{item.id}</small>{item.error&&<small>{item.error}</small>}{item.restorable===false&&<small>受损状态原始副本，仅供分析</small>}</td><td>{item.created_at?new Date(item.created_at).toLocaleString():'不可读取'}</td><td>{(item.image_bytes/1024).toLocaleString()} KiB</td><td><button className="button" disabled={busy||disk.info.read_only||!!item.error||item.restorable===false} onClick={()=>setPending(item)}>恢复此快照</button></td></tr>)}</tbody></table></div>}
    <p className="technical-note">快照保存在当前镜像旁。恢复时校验大小、SHA256 和文件系统一致性；每份快照保持原始内容。请定期将重要快照复制到其他位置。</p>
    {pending&&<div className="modal-backdrop"><form ref={dialogRef} tabIndex={-1} className="modal" role="dialog" aria-modal="true" aria-labelledby="restore-title" onSubmit={e=>{e.preventDefault();void mutate('/api/restore',{id:pending.id},'恢复快照').then(ok=>{if(ok)setPending(null)})}}><h2 id="restore-title">确认恢复快照</h2><p>恢复“{pending.label||'未命名快照'}”。当前磁盘会先保存为一个自动保护点。</p><div className="modal-actions"><button type="button" className="button" disabled={busy} onClick={()=>setPending(null)}>取消</button><button className="button primary" disabled={busy}>确认恢复</button></div></form></div>}
  </div>
}
