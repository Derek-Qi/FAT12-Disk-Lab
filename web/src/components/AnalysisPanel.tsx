import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { Analysis, CompactionPlan, Disk } from '../types'

type Props = {
  disk:Disk
  busy:boolean
  mutate:(route:string,body:object,display:string)=>Promise<boolean|undefined>
  locate:(cluster:number)=>void
}

const bytes=(value:number)=>`${value.toLocaleString()} B`

export function AnalysisPanel({disk,busy,mutate,locate}:Props) {
  const [report,setReport]=useState<Analysis|null>(null)
  const [plan,setPlan]=useState<CompactionPlan|null>(null)
  const [error,setError]=useState('')
  const [preparing,setPreparing]=useState(false)
  const [confirm,setConfirm]=useState(false)
  const [page,setPage]=useState(0)
  const generation=useRef(0)
  const dialog=useRef<HTMLDivElement>(null)
  const previewButton=useRef<HTMLButtonElement>(null)

  useEffect(()=>{
    const id=++generation.current
    setReport(null);setPlan(null);setConfirm(false);setPreparing(false);setPage(0);setError('')
    api<Analysis>('/api/analysis').then(value=>{
      if(id===generation.current)setReport(value)
    }).catch(e=>{if(id===generation.current)setError(e.message)})
    return()=>{generation.current++}
  },[disk])

  useEffect(()=>{
    if(!confirm)return
    const element=dialog.current
    element?.querySelector<HTMLButtonElement>('button')?.focus()
    const keydown=(event:KeyboardEvent)=>{
      if(event.key==='Escape'&&!busy){setConfirm(false);previewButton.current?.focus()}
      if(event.key==='Tab'){
        const buttons=Array.from(element?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')??[])
        if(!buttons.length)return
        if(event.shiftKey&&document.activeElement===buttons[0]){event.preventDefault();buttons.at(-1)?.focus()}
        if(!event.shiftKey&&document.activeElement===buttons.at(-1)){event.preventDefault();buttons[0].focus()}
      }
    }
    window.addEventListener('keydown',keydown)
    return()=>window.removeEventListener('keydown',keydown)
  },[confirm,busy])

  async function preview() {
    if(preparing||busy||!report?.check.ok)return
    const id=generation.current
    setPreparing(true);setError('')
    try{
      const value=await api<CompactionPlan>('/api/defrag-plan')
      if(id===generation.current){
        if(value.image_sha256!==report.image_sha256){setError('镜像已变化，请刷新磁盘后重新预览');setPlan(null)}
        else setPlan(value)
      }
    }catch(e){if(id===generation.current)setError((e as Error).message)}
    finally{if(id===generation.current)setPreparing(false)}
  }

  const summary=report?.summary
  return <div className="education-panel analysis-panel">
    <div className="analysis-heading"><div><h3>从文件内容到物理簇布局</h3><p>统计直接来自镜像中的目录项和 FAT。预览只读取磁盘；整理会重新安排活动文件和目录的簇位置。</p></div>
      <button ref={previewButton} className="button primary" disabled={busy||preparing||!summary} onClick={()=>void preview()}>{preparing?'正在规划…':'预览整理'}</button>
    </div>
    {error&&<p role="alert" className="analysis-error">{error}</p>}
    {!report?<p role="status">正在分析磁盘布局…</p>:!summary?<div role="alert"><p>镜像存在一致性错误，整理已禁用。请先检查问题或恢复健康快照。</p><ul>{report.check.errors.map((item,index)=><li key={index}>{item}</li>)}</ul></div>:<>
      <div className="analysis-summary">
        <div><span>有效文件内容</span><strong>{bytes(summary.logical_bytes)}</strong><small>{summary.files} 个文件 / {summary.directories} 个目录</small></div>
        <div><span>文件尾部空闲</span><strong>{bytes(summary.slack_bytes)}</strong><small>已分配文件簇中的内部碎片</small></div>
        <div><span>非连续文件</span><strong>{summary.fragmented_files}<small> / {summary.files}</small></strong><small>文件连续段合计 {summary.file_extents}</small></div>
        <div><span>最大连续空闲区</span><strong>{summary.largest_free_run.toLocaleString()}<small> 簇</small></strong><small>{summary.free_runs} 段空闲区 / {summary.bad_clusters} 个坏簇</small></div>
      </div>
      {plan&&<section className="defrag-preview" aria-label="整理预览">
        <div><h3>整理预览</h3><p>需要移动 <b>{plan.moved_clusters}</b> 个簇。文件连续段 {plan.before.file_extents} → {plan.after.file_extents}；非连续文件 {plan.before.fragmented_files} → {plan.after.fragmented_files}。</p>
          <p>最大连续空闲区 {plan.before.largest_free_run} → {plan.after.largest_free_run} 个簇。坏簇保留，文件内容和活动目录项元数据保持一致。</p>
          <details><summary>查看簇迁移与镜像版本</summary><code className="analysis-digest">SHA256 {plan.image_sha256}</code><p>{plan.mapping.filter(item=>item.from!==item.to).slice(0,24).map(item=>`${item.from} → ${item.to}`).join(' · ')||'无需迁移'}{plan.moved_clusters>24?'（仅显示前 24 项）':''}</p></details>
        </div>
        <button className="button" disabled={busy||disk.info.read_only||plan.moved_clusters===0} onClick={()=>setConfirm(true)}>应用整理计划</button>
        {plan.moved_clusters===0&&<p>当前已经是规划布局，无需整理。</p>}
      </section>}
      <div className="table-scroll"><table className="evidence-table allocation-table"><thead><tr><th>镜像路径</th><th>内容大小</th><th>已分配</th><th>尾部空闲</th><th>连续段</th><th>簇链入口</th></tr></thead><tbody>
        {report.objects.slice(page*50,(page+1)*50).map(item=><tr key={item.path}><td className="mono">{item.path}{item.is_dir?' /':''}</td><td>{item.is_dir?'目录':bytes(item.logical_bytes)}</td><td>{bytes(item.allocated_bytes)}</td><td>{item.is_dir?'—':bytes(item.slack_bytes)}</td><td>{item.extents}</td><td>{item.chain.length?<button className="analysis-link" onClick={()=>locate(item.chain[0])}>簇 {item.chain[0]} → FAT</button>:'空文件'}</td></tr>)}
      </tbody></table></div>
      {report.objects.length>50&&<div className="analysis-pagination"><button className="button" disabled={page===0} onClick={()=>setPage(p=>p-1)}>上一页</button><span>{page+1} / {Math.ceil(report.objects.length/50)}</span><button className="button" disabled={(page+1)*50>=report.objects.length} onClick={()=>setPage(p=>p+1)}>下一页</button></div>}
      <p className="technical-note">每簇 {report.cluster_bytes} 字节。连续段衡量簇位置相邻程度，不等于实测磁盘延迟。整理保留活动内容，可能清空空闲簇中的旧字节；取证分析请使用只读模式。整理前自动保存完整保护点。</p>
    </>}
    {confirm&&plan&&<div className="modal-backdrop"><div ref={dialog} className="modal" role="dialog" aria-modal="true" aria-labelledby="compact-title"><h2 id="compact-title">确认磁盘整理</h2><p>将移动 {plan.moved_clusters} 个簇，更新 FAT 和目录引用。活动文件内容保持一致，空闲区中的旧字节可能被清空。当前镜像会先保存为完整保护点。</p><div className="modal-actions"><button className="button" disabled={busy} onClick={()=>{setConfirm(false);previewButton.current?.focus()}}>取消</button><button className="button primary" disabled={busy} onClick={()=>void mutate('/api/defragment',{expected_sha256:plan.image_sha256},'磁盘整理').then(ok=>{setConfirm(false);if(!ok)setPlan(null)})}>确认整理</button></div></div></div>}
  </div>
}
