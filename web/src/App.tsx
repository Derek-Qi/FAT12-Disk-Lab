import { useEffect, useRef, useState, type FormEvent, type ChangeEvent } from 'react'
import type { Entry, Disk, OpenFile, FatDetail, Changes, Log, Dialog } from './types'
import { api } from './lib/api'
import { SnapshotPanel } from './components/SnapshotPanel'
import { AnalysisPanel } from './components/AnalysisPanel'

const bytes = (n:number) => n === 0 ? '0 B' : n >= 1024 ? `${(n/1024).toFixed(1)} KiB` : `${n} B`
const q = (s:string) => `"${s.replaceAll('"', '\\"')}"`
const join = (base:string, name:string) => `${base === '/' ? '' : base}/${name}`

function Icon({name, size=18}:{name:string; size?:number}) {
  const paths:Record<string,string> = {disk:'M4 3h13l4 4v14H3V3h1 M7 3v6h10V3 M7 21v-7h10v7',folder:'M3 6h7l2 2h9v12H3Z M3 6V4h7l2 2',file:'M5 3h9l5 5v13H5Z M14 3v6h5 M8 13h8 M8 17h6',terminal:'M4 7l5 5-5 5 M12 17h8',grid:'M3 3h7v7H3Z M14 3h7v7h-7Z M3 14h7v7H3Z M14 14h7v7h-7Z',sector:'M4 4h16v16H4Z M4 10h16 M10 4v16 M4 15h16',plus:'M12 5v14 M5 12h14',up:'M12 16V4 M7 9l5-5 5 5 M4 17v4h16v-4',down:'M12 3v13 M7 11l5 5 5-5 M4 17v4h16v-4',check:'M4 12l5 5L20 6',arrow:'M5 12h14 M13 6l6 6-6 6',refresh:'M20 7v5h-5 M4 17v-5h5 M5 7a8 8 0 0114-1 M19 17A8 8 0 015 18',trash:'M4 6h16 M9 6V3h6v3 M6 6l1 15h10l1-15 M10 10v7 M14 10v7',edit:'M4 20l4-1L20 7l-3-3L5 16Z M14 7l3 3',close:'M6 6l12 12 M6 18L18 6',home:'M3 10l9-7 9 7 M5 9v12h14V9 M9 21v-8h6v8'}
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.file}/></svg>
}


export default function App() {
  const [disk,setDisk] = useState<Disk|null>(null)
  const [tab,setTab] = useState('files')
  const [selected,setSelected] = useState<Entry|null>(null)
  const [opened,setOpened] = useState<OpenFile|null>(null)
  const [editor,setEditor] = useState('')
  const [command,setCommand] = useState('')
  const [logs,setLogs] = useState<Log[]>([{command:'info',output:'FAT12 磁盘实验台已就绪。输入 help 查看全部命令。'}])
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [dialog,setDialog] = useState<Dialog>(null)
  const [name,setName] = useState('')
  const [sector,setSector] = useState(0)
  const [sectorData,setSectorData] = useState<number[]>([])
  const [fatPage,setFatPage] = useState(0)
  const [fatSelected,setFatSelected] = useState(2)
  const [fatDetail,setFatDetail] = useState<FatDetail|null>(null)
  const [changes,setChanges] = useState<Changes|null>(null)
  const [lastOperation,setLastOperation] = useState('')
  const upload = useRef<HTMLInputElement>(null)
  const mount = useRef<HTMLInputElement>(null)
  const terminal = useRef<HTMLDivElement>(null)
  const commandInput = useRef<HTMLInputElement>(null)
  const history = useRef<string[]>([])
  const historyIndex = useRef(0)
  const selectionRequest = useRef(0)

  useEffect(() => { api<Disk>('/api/state').then(setDisk).catch(e=>setError(String(e.message))) }, [])
  useEffect(() => {terminal.current?.scrollTo(0,terminal.current.scrollHeight)}, [logs])
  useEffect(() => {window.scrollTo(0,0)}, [tab])
  useEffect(() => {let active=true;if(tab === 'sector') api<{bytes:number[]}>(`/api/sector?index=${sector}`).then(s=>{if(active)setSectorData(s.bytes)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[tab,sector,disk])
  useEffect(() => {let active=true;setFatDetail(null);if(tab==='fat')api<FatDetail>(`/api/fat-entry?cluster=${fatSelected}`).then(value=>{if(active)setFatDetail(value)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[tab,fatSelected,disk])
  useEffect(() => {if(!dialog)return; const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!busy)setDialog(null)}; window.addEventListener('keydown',escape); return ()=>window.removeEventListener('keydown',escape)},[dialog,busy])

  const clearSelection = () => {selectionRequest.current++;setSelected(null);setOpened(null);setEditor('')}
  async function navigate(path:string) {
    if(busy)return
    setBusy(true);setError('')
    try {setDisk(await api<Disk>(`/api/state?path=${encodeURIComponent(path)}`));clearSelection()} catch(e){setError((e as Error).message)} finally{setBusy(false)}
  }
  async function choose(entry:Entry) {
    if(busy)return
    if(entry.is_dir){await navigate(join(disk!.path,entry.name));return}
    const id=++selectionRequest.current
    setSelected(entry);setOpened(null);setError('')
    try {const file=await api<OpenFile>(`/api/file?path=${encodeURIComponent(join(disk!.path,entry.name))}`);if(id!==selectionRequest.current)return;setOpened(file);setEditor(file.content)} catch(e){if(id===selectionRequest.current)setError((e as Error).message)}
  }
  async function mutate(route:string, body:object, display:string) {
    if(busy)return
    setBusy(true);setError('')
    try {const result=await api<{output:string;state:Disk;changes:Changes}>(route,{...body,cwd:disk!.path});setDisk(result.state);setChanges(result.changes);setLastOperation(display);if(['/api/mount','/api/restore','/api/reload','/api/defragment'].includes(route)){setSector(0);setFatPage(0);setFatSelected(2)}clearSelection();setLogs(l=>[...l.slice(-99),{command:display,output:result.output}]);setDialog(null);return true}
    catch(e){const message=(e as Error).message;setError(message);setLogs(l=>[...l.slice(-99),{command:display,output:message,error:true}]);return false}finally{setBusy(false)}
  }
  async function run(cmd:string) {
    if(!cmd.trim()||busy)return
    if(dirty){setError('有未保存的修改，请先保存文件或点击“还原”');return}
    history.current.push(cmd);historyIndex.current=history.current.length
    await mutate('/api/command',{command:cmd},cmd)
  }
  async function submitDialog(e:FormEvent) {
    e.preventDefault()
    if(dialog==='mount'){setDialog(null);mount.current?.click();return}
    let cmd=''
    if(dialog==='folder')cmd=`mkdir ${q(name)}`
    if(dialog==='file')cmd=`touch ${q(name)}`
    if(dialog==='rename')cmd=`ren ${q(selected!.name)} ${q(name)}`
    if(dialog==='delete')cmd=`${selected!.is_dir?'rmdir':'del'} ${q(selected!.name)}`
    if(dialog==='format')cmd=`format ${q(name)}`
    await run(cmd)
  }
  async function loadLocal(event:ChangeEvent<HTMLInputElement>, image:boolean) {
    const file=event.target.files?.[0];event.target.value=''
    if(!file)return
    if(file.size>(image?16*1024*1024:disk!.info.total_clusters*disk!.info.cluster_bytes)){setError(image?'镜像超过 16 MiB 支持范围':'文件超过当前磁盘数据区容量');return}
    try {
      const buffer=new Uint8Array(await file.arrayBuffer());let binary=''
      for(let i=0;i<buffer.length;i+=8192)binary+=String.fromCharCode(...buffer.subarray(i,i+8192))
      await mutate(image?'/api/mount':'/api/upload',{data:btoa(binary),path:join(disk!.path,file.name)},image?'加载镜像':`上传 ${file.name}`)
    }catch(e){setError((e as Error).message)}
  }
  function openDialog(kind:Dialog, initial=''){setName(initial);setDialog(kind);setError('')}
  const dirty=!!opened&&opened.is_text&&editor!==opened.content
  const confirmNavigation=(action:()=>void)=>{if(dirty){setError('有未保存的修改，请先保存文件或点击“还原”');return}action()}

  return <div className="app">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon"><Icon name="disk" size={27}/></span><div>FAT12<span>DISK LAB</span></div></div>
      <div className="side-label">工作空间</div>
      <nav aria-label="主导航">{[['files','folder','文件管理'],['analysis','grid','磁盘分析'],['fat','grid','FAT 簇图'],['sector','sector','扇区解析'],['bpb','disk','BPB 解码'],['changes','edit','操作变化'],['snapshots','refresh','快照恢复']].map(([id,icon,label])=><button key={id} className={tab===id?'active':''} onClick={()=>confirmNavigation(()=>setTab(id))}><Icon name={icon}/>{label}<span className="nav-dot"/></button>)}</nav>
      <div className="side-label disk-label">当前磁盘</div>
      <div className="disk-card"><Icon name="disk" size={34}/><b>{disk?.info.label||'连接中'}</b><span>BPB 动态解析 · FAT12</span><div className="side-meter"><i style={{width:`${disk?(disk.info.used_clusters/disk.info.total_clusters*100):0}%`}}/></div><small>{disk?.info.used_clusters||0} / {disk?.info.total_clusters.toLocaleString()||0} 个簇已使用</small></div>
      <div className="side-bottom"><span className="online"/>本地镜像模式<small>Python 内核 + React 界面</small></div>
    </aside>
    <main>
      <header><div className="eyebrow">文件系统工程 / FAT12 Lab</div><div className="heading-row"><div><h1>FAT12 磁盘实验台</h1><p>浏览文件，执行命令，观察磁盘上的每一个字节。</p></div><div className="header-actions"><a className="button ghost" href="/api/image"><Icon name="down"/>导出镜像</a><button className="button" disabled={busy||!disk||disk.info.read_only} onClick={()=>confirmNavigation(()=>openDialog('mount'))}><Icon name="up"/>加载镜像</button></div></div></header>
      {error&&<div className="error" role="alert"><span>{error}</span><button aria-label="关闭提示" onClick={()=>setError('')}><Icon name="close"/></button></div>}
      {!disk?<div className="loading">{error?'服务连接失败，请检查本地 Python 服务。':'正在读取软盘镜像…'}</div>:<>
        <section className="metrics" aria-label="磁盘概况"><div><span>磁盘容量</span><strong>{(disk.info.image_bytes/1024).toLocaleString()} <small>KiB</small></strong><em>{disk.info.image_bytes.toLocaleString()} 字节</em></div><div><span>可用空间</span><strong>{(disk.info.free_bytes/1024).toFixed(1)} <small>KiB</small></strong><em>{disk.info.free_clusters.toLocaleString()} 个空闲簇</em></div><div><span>文件与目录</span><strong>{disk.check.files} <small>文件 / {disk.check.directories} 目录</small></strong><em>{disk.info.read_only?'只读查看 · 修改命令不可用':'ASCII 8.3 短文件名'}</em></div><div><span>一致性检查</span><strong className={disk.check.ok?'healthy':'unhealthy'}><Icon name="check" size={23}/>{disk.check.ok?'正常':'异常'}</strong><em>{disk.check.ok?'FAT 副本与簇链检查通过':`${disk.check.errors.length} 个问题`}</em></div></section>
        <section className="workspace">
          <div className="workspace-title"><h2>{{files:'文件管理',analysis:'磁盘分析与整理',fat:'FAT 簇分配图',sector:'扇区数据解析',bpb:'BPB 字段解码',changes:'命令执行后的磁盘变化',snapshots:'快照恢复'}[tab]}</h2><span>{{files:'FILE EXPLORER',analysis:'ALLOCATION ANALYSIS',fat:'ALLOCATION TABLE',sector:'SECTOR INSPECTOR',bpb:'BIOS PARAMETER BLOCK',changes:'BYTE CHANGES',snapshots:'RECOVERY POINTS'}[tab]}</span><button className="icon-button" disabled={busy} aria-label="刷新磁盘" onClick={()=>confirmNavigation(()=>void mutate('/api/reload',{},'重新读取磁盘'))}><Icon name="refresh"/></button></div>
          {tab==='analysis'&&<AnalysisPanel disk={disk} busy={busy} mutate={mutate} locate={cluster=>{setFatSelected(cluster);setFatPage(Math.floor((cluster-2)/256));setTab('fat')}}/>}
          {tab==='files'&&<>
            <div className="file-toolbar"><div className="breadcrumbs"><button aria-label="根目录" disabled={busy} onClick={()=>confirmNavigation(()=>navigate('/'))}><Icon name="home"/></button>{disk.path.split('/').filter(Boolean).map((part,i,all)=><span key={i}>/<button disabled={busy} onClick={()=>confirmNavigation(()=>navigate('/'+all.slice(0,i+1).join('/')))}>{part}</button></span>)}{disk.path==='/'&&<span>/ 根目录</span>}</div><div><button disabled={busy||disk.info.read_only} onClick={()=>confirmNavigation(()=>openDialog('folder'))}><Icon name="plus"/>新建目录</button><button disabled={busy||disk.info.read_only} onClick={()=>confirmNavigation(()=>openDialog('file'))}><Icon name="file"/>新建文件</button><button disabled={busy||disk.info.read_only} onClick={()=>confirmNavigation(()=>upload.current?.click())}><Icon name="up"/>上传文件</button></div></div>
            <div className="file-split"><div className="files"><table><thead><tr><th>名称</th><th>大小</th><th>首簇</th><th>修改时间</th></tr></thead><tbody>{disk.entries.map(entry=><tr key={entry.offset} className={selected?.offset===entry.offset?'selected':''}><td><button className="file-name" disabled={busy} onClick={()=>confirmNavigation(()=>void choose(entry))}><span className={entry.is_dir?'folder-icon':'file-icon'}><Icon name={entry.is_dir?'folder':'file'}/></span>{entry.name}{entry.is_dir&&<span className="enter-folder">›</span>}</button></td><td>{entry.is_dir?'目录':bytes(entry.size)}</td><td className="mono">{entry.cluster||'—'}</td><td className="date">{entry.modified}</td></tr>)}</tbody></table>{!disk.entries.length&&<div className="empty"><Icon name="folder" size={34}/><p>这个目录还是空的</p><small>创建文件或上传本机文件开始实验</small></div>}<div className="file-foot">{disk.entries.length} 个项目<span>目录项为 32 字节 · 每簇 {disk.info.cluster_bytes} 字节</span></div></div>
            <aside className="inspector">{selected?<><div className="inspector-head"><span className="file-icon"><Icon name="file" size={24}/></span><b>{selected.name}</b></div><dl><dt>文件大小</dt><dd>{selected.size} 字节</dd><dt>目录项偏移</dt><dd className="mono">0x{selected.offset.toString(16).toUpperCase()}</dd><dt>占用空间</dt><dd>{opened?opened.chain.length*disk.info.cluster_bytes:'…'} 字节</dd></dl><div className="chain-label">簇链</div><div className="chain">{opened?.chain.length?opened.chain.map((c,i)=><span key={c}><button aria-label={`查看簇 ${c} 的 FAT 项`} onClick={()=>confirmNavigation(()=>{setFatSelected(c);setFatPage(Math.floor((c-2)/256));setTab('fat')})}><b>{c}</b></button>{i<opened.chain.length-1&&<Icon name="arrow" size={13}/>}</span>):<small>{opened?'空文件，无数据簇':'读取中…'}</small>}{!!opened?.chain.length&&<em>EOC</em>}</div>{opened&&<details className="raw-entry"><summary>32 字节目录项解码</summary><code>{opened.raw_entry.raw}</code><p>属性 0x{opened.raw_entry.attr_hex}：{opened.raw_entry.attributes.join("、")||"无"}</p><p>时间字 0x{opened.raw_entry.time_word}，日期字 0x{opened.raw_entry.date_word}</p><p>{opened.raw_entry.modified}（秒精度 2 秒）</p><button onClick={()=>confirmNavigation(()=>{setSector(Math.floor(selected.offset/512));setTab("sector")})}>定位目录项所在扇区</button></details>}<div className="inspector-buttons"><a className="button" href={`/api/download?path=${encodeURIComponent(join(disk.path,selected.name))}`}><Icon name="down"/>下载</a><button className="icon-button" disabled={busy||disk.info.read_only} aria-label="重命名文件" onClick={()=>confirmNavigation(()=>openDialog('rename',selected.name))}><Icon name="edit"/></button><button className="icon-button danger" disabled={busy||disk.info.read_only} aria-label="删除文件" onClick={()=>confirmNavigation(()=>openDialog('delete'))}><Icon name="trash"/></button></div><div className="preview-title">{opened?.is_text?'UTF-8 文本预览':'二进制文件'}{opened?.is_text&&<button disabled={busy} onClick={()=>setEditor(opened.content)}>还原</button>}</div>{opened?.is_text?<><textarea aria-label="文件内容" className="editor" value={editor} disabled={busy||disk.info.read_only} onChange={e=>setEditor(e.target.value)}/><button className="button primary save" disabled={busy||disk.info.read_only||!dirty} onClick={()=>void mutate('/api/write',{path:join(disk.path,selected.name),content:editor},`保存 ${selected.name}`)}>{busy?'保存中…':dirty?'保存修改':'已保存'}</button></>:<p className="binary-note">{opened?'下载后可用二进制工具查看。':'正在读取…'}</p>}</>:<div className="inspect-empty"><Icon name="file" size={38}/><h3>查看文件内部</h3><p>选择一个文件，查看内容、目录项位置和 FAT 簇链。</p><small>点击目录进入下一层</small></div>}</aside></div>
          </>}
          {tab==='fat'&&<div className="fat-panel"><div className="fat-explainer"><div><h3>每个方块代表一个数据簇</h3><p>空闲簇的 FAT 值为 000，文件末簇以 FF8–FFF 结束。</p></div><div className="legend"><span><i className="free"/>空闲</span><span><i className="used"/>已分配</span><span><i className="end"/>链尾</span><span><i className="bad"/>坏簇或保留</span></div></div><div className="cluster-grid">{disk.fat.slice(2+fatPage*256,Math.min(258+fatPage*256,disk.fat.length)).map((value,i)=>{const c=2+fatPage*256+i;return <button key={c} aria-label={`簇 ${c}，FAT 值 ${value.toString(16)}`} title={`簇 ${c} · 0x${value.toString(16).padStart(3,'0').toUpperCase()}`} className={`${value===0?'free':value>=4088?'end':value>=4080?'bad':'used'} ${c===fatSelected?'focus':''}`} onClick={()=>setFatSelected(c)}>{c}</button>})}</div><div className="fat-footer"><div>簇 <b>{fatSelected}</b> 的 FAT 值 <code>0x{(disk.fat[fatSelected]??0).toString(16).padStart(3,'0').toUpperCase()}</code> · 数据扇区 <b>{disk.info.data_sector+(fatSelected-2)*disk.info.sectors_per_cluster}</b></div><div><button disabled={fatPage===0} onClick={()=>setFatPage(p=>p-1)}>上一页</button><span>{fatPage+1} / {Math.ceil(disk.info.total_clusters/256)}</span><button disabled={fatPage>=Math.ceil(disk.info.total_clusters/256)-1} onClick={()=>setFatPage(p=>p+1)}>下一页</button></div></div>{fatDetail&&<div className="decode-note"><b>FAT 1 原始字节</b><code>0x{fatDetail.offset.toString(16).toUpperCase()}: {fatDetail.raw}</code><span>小端字 0x{fatDetail.word.toString(16).toUpperCase()}，{fatDetail.formula} = 0x{fatDetail.value.toString(16).padStart(3,"0").toUpperCase()}</span></div>}<button className="button cluster-locate" onClick={()=>{setSector(disk.info.data_sector+(fatSelected-2)*disk.info.sectors_per_cluster);setTab('sector')}}>查看所选簇的数据扇区</button><p className="technical-note">FAT12 将两个 12 位表项压入三个字节。引导区不属于数据簇，保留表项 0 和 1 不显示在方块中。</p></div>}
          {tab==='sector'&&<div className="sector-panel"><div className="sector-toolbar"><label>扇区号 <input type="number" min={0} max={disk.info.total_sectors-1} value={sector} onChange={e=>setSector(Math.max(0,Math.min(disk.info.total_sectors-1,Number(e.target.value)||0)))}/></label><div>{[['引导区',0],['FAT 1',disk.info.reserved_sectors],['FAT 2',disk.info.reserved_sectors+disk.info.fat_sectors],['根目录',disk.info.root_sector],['数据区',disk.info.data_sector]].map(([label,n])=><button key={label} className={sector===n?'chosen':''} onClick={()=>setSector(Number(n))}>{label}</button>)}</div><span>偏移 0x{(sector*512).toString(16).toUpperCase()}</span></div><div className="hex-scroll"><table className="hex"><thead><tr><th>OFFSET</th>{Array.from({length:16},(_,i)=><th key={i}>{i.toString(16).toUpperCase()}</th>)}<th>ASCII</th></tr></thead><tbody>{Array.from({length:32},(_,row)=><tr key={row}><td>{(sector*512+row*16).toString(16).padStart(6,'0').toUpperCase()}</td>{sectorData.slice(row*16,row*16+16).map((b,i)=><td key={i} className={b?'nonzero':''}>{b.toString(16).padStart(2,'0').toUpperCase()}</td>)}<td>{sectorData.slice(row*16,row*16+16).map(b=>b>=32&&b<=126?String.fromCharCode(b):'.').join('')}</td></tr>)}</tbody></table></div><p className="technical-note">引导扇区末尾为 55 AA。所有区域地址根据当前 BPB 计算，数据区从 LBA {disk.info.data_sector} 开始，每簇 {disk.info.sectors_per_cluster} 个扇区。</p></div>}
          {tab==='bpb'&&<div className="education-panel"><p>从引导扇区读取原始字节，再按小端序解码整数。字段来自当前镜像。</p><div className="table-scroll"><table className="evidence-table"><thead><tr><th>偏移</th><th>字段</th><th>长度</th><th>原始字节</th><th>值</th></tr></thead><tbody>{disk.bpb.map(field=><tr key={field.offset}><td className="mono">0x{field.offset.toString(16).padStart(2,'0').toUpperCase()}</td><td>{field.field}</td><td>{field.length}</td><td className="mono">{field.raw}</td><td>{field.value.toLocaleString()}</td></tr>)}</tbody></table></div><div className="decode-note"><b>从 BPB 推导磁盘布局</b><span>根目录 LBA {disk.info.root_sector}，数据区 LBA {disk.info.data_sector}，每簇 {disk.info.cluster_bytes} 字节</span><code>ClusterLBA(n) = {disk.info.data_sector} + (n - 2) * {disk.info.sectors_per_cluster}</code><span>{disk.info.total_clusters} 个数据簇。FAT 类型依据数据簇数量判断，不能只看 FAT12 字符串。</span></div></div>}
          {tab==='changes'&&<div className="education-panel">{changes?<><h3>最近一次操作：{lastOperation}</h3>{changes.replaced?<p>{changes.reason==='layout'?'磁盘布局已改变：':'加载了不同容量的镜像：'}{changes.before_bytes?.toLocaleString()} 字节改为 {changes.after_bytes?.toLocaleString()} 字节。不同布局不作逐字节区域比较。</p>:<><p>改变 <b>{changes.changed_bytes?.toLocaleString()}</b> 个字节，涉及 <b>{changes.changed_sector_count}</b> 个扇区。只读命令应为 0。</p><p>区域统计：{Object.entries(changes.regions).map(([region,n])=>`${region} ${n} 字节`).join('；')||'没有磁盘变化'}</p><p>扇区 LBA：{changes.sectors.join(', ')||'无'}{(changes.changed_sector_count||0)>64?'（仅列前 64 个）':''}</p><div className="table-scroll"><table className="evidence-table"><thead><tr><th>字节偏移</th><th>操作前</th><th>操作后</th></tr></thead><tbody>{changes.samples.map(sample=><tr key={sample.offset}><td className="mono">0x{sample.offset.toString(16).toUpperCase()}</td><td className="mono">{sample.before}</td><td className="mono">{sample.after}</td></tr>)}</tbody></table></div><p className="technical-note">统计覆盖整张镜像。表格仅显示前 16 段，每段最多 16 个连续变化字节。创建文件应更新两份 FAT、目录项与数据区；空文件无需数据簇。刷新页面后记录清空。</p></>}</>:<p>在下方终端执行 write、mkdir 或 del，再返回这里观察原始字节变化。记录仅保留本次网页会话的最近一次成功操作。</p>}</div>}
          {tab==='snapshots'&&<SnapshotPanel disk={disk} busy={busy} mutate={mutate}/>}
        </section>
        <section className="terminal"><div className="terminal-title"><Icon name="terminal"/><h2>命令终端</h2><span>所有命令直接操作当前镜像</span><button onClick={()=>setLogs([])}>清屏</button><button disabled={busy} onClick={()=>void run('help')}>帮助</button></div><div className="terminal-output" ref={terminal} aria-live="polite">{logs.map((log,i)=><div key={i} className={log.error?'log-error':''}><div className="log-command"><span>A:&gt;</span> {log.command}</div><pre>{log.output}</pre></div>)}</div><form onSubmit={e=>{e.preventDefault();const value=command;setCommand('');void run(value)}}><label htmlFor="command">A:{disk.path}&gt;</label><input id="command" ref={commandInput} autoComplete="off" spellCheck={false} value={command} disabled={busy} placeholder='例如：write HELLO.TXT "Hello FAT12"' onChange={e=>setCommand(e.target.value)} onKeyDown={e=>{if(e.key==='ArrowUp'||e.key==='ArrowDown'){e.preventDefault();historyIndex.current=Math.max(0,Math.min(history.current.length,historyIndex.current+(e.key==='ArrowUp'?-1:1)));setCommand(history.current[historyIndex.current]||'')}}}/><button disabled={busy||!command.trim()} aria-label="执行命令"><Icon name="arrow"/></button></form></section>
        <footer><span>FAT12 实验镜像 · 本地持久化</span><button disabled={busy||disk.info.read_only} onClick={()=>confirmNavigation(()=>openDialog('format','OSLAB'))}>格式化磁盘</button><span>512 B / 扇区 · {disk.info.total_sectors.toLocaleString()} 扇区 · 2 份 FAT</span></footer>
      </>}
    </main>
    <input className="hidden" ref={upload} type="file" onChange={e=>void loadLocal(e,false)}/><input className="hidden" ref={mount} type="file" accept=".img,.ima,.vfd" onChange={e=>void loadLocal(e,true)}/>
    {dialog&&<div className="modal-backdrop"><form className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" onSubmit={submitDialog}><div className="modal-title"><h2 id="modal-title">{{file:'新建文件',folder:'新建目录',rename:'重命名文件',delete:'删除项目',format:'格式化磁盘',mount:'加载软盘镜像'}[dialog]}</h2><button type="button" disabled={busy} aria-label="关闭对话框" onClick={()=>setDialog(null)}><Icon name="close"/></button></div>{dialog==='delete'?<p>删除 {selected?.name} 并释放占用的簇。可从已有快照恢复整张磁盘。</p>:dialog==='mount'?<p>加载 FAT12 裸卷镜像（.img / .vfd），按 BPB 校验容量、簇大小和布局。将替换当前工作镜像，可先导出保存。</p>:<><p>{dialog==='format'?'格式化将清空全部文件和目录，健康磁盘会先自动保存保护点。请输入卷标。':'使用 ASCII 8.3 名称，例如 HELLO.TXT、DOCS。'}</p><label>{dialog==='format'?'卷标':'名称'}<input autoFocus required maxLength={dialog==='format'?11:12} value={name} onChange={e=>setName(e.target.value)}/></label></>}{error&&<p className="modal-error">{error}</p>}<div className="modal-actions"><button type="button" className="button" disabled={busy} onClick={()=>setDialog(null)}>取消</button><button className={`button ${dialog==='delete'||dialog==='format'?'destructive':'primary'}`} disabled={busy}>{busy?'执行中…':dialog==='mount'?'选择镜像文件':'确定'}</button></div></form></div>}
  </div>
}
