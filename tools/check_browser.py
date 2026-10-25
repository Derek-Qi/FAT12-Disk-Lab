"""Reproducible UI checks using agent-browser against disposable local disks.

Requires the optional agent-browser CLI and an installed browser. Runtime does
not depend on it. Run after building the frontend.
"""
from evidence import metadata
from browser_cli import browser_executable
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parent.parent


def main():
    try:cli=browser_executable()
    except RuntimeError as exc:raise SystemExit(str(exc)) from exc
    env={**os.environ,'AGENT_BROWSER_SESSION':'fat12-test-'+uuid.uuid4().hex[:12],
         'AGENT_BROWSER_DEFAULT_TIMEOUT':'8000'}
    checks=[]
    def browser(*arguments):
        # Windows daemon startup can inherit pipe handles and keep communicate()
        # waiting after the CLI exits. File-backed output has no EOF wait.
        with tempfile.TemporaryFile() as log:
            result=subprocess.run([cli,*arguments],stdout=log,stderr=log,env=env,timeout=40)
            log.seek(0);output=log.read().decode('utf-8',errors='replace')
        if result.returncode:raise AssertionError(output)
        return output
    def click(name):browser('find','role','button','click','--name',name,'--exact')
    def evaluate(script):return browser('eval','-b',base64.b64encode(script.encode()).decode())
    def wait(text):browser('wait','--text',text)
    def command(text):
        browser('fill','#command',text);click('执行命令')
        browser('wait','--fn',"!document.querySelector('#command').disabled")
    with tempfile.TemporaryDirectory(prefix='fat12-ui-') as temporary:
        destination=Path(temporary).resolve()
        assert destination.name.startswith('fat12-ui-')
        image=destination/'ui.img';shutil.copyfile(ROOT/'data/demo.img',image)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        server=subprocess.Popen([sys.executable,'-m','fat12lab','--image',str(image),'--web','--port',str(port),'--no-browser'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            url=f'http://127.0.0.1:{port}/'
            for _ in range(100):
                try:urllib.request.urlopen(url,timeout=1).close();break
                except OSError:time.sleep(.05)
            else:raise AssertionError('Local UI server failed to start')
            browser('set','viewport','1280','900')
            browser('open',url);wait('一致性检查')
            before=image.read_bytes()
            click('磁盘分析');wait('文件尾部空闲')
            click('预览整理');wait('整理预览')
            assert image.read_bytes()==before
            checks.append('allocation analysis and preview leave disk bytes unchanged')
            browser('screenshot',str(ROOT/'artifacts/screenshots/allocation-ui.png'))
            # Missing snapshots UI makes the original course build fail here.
            click('快照恢复');wait('创建快照')
            browser('find','label','快照名称','fill','browser checkpoint')
            click('创建快照');wait('browser checkpoint')
            checks.append('snapshot creation through UI')
            command('write UI.TXT "changed"');wait('写入 7 字节')
            click('恢复此快照');wait('确认恢复快照');click('确认恢复')
            wait('快照已恢复')
            browser('scroll','up','2000')
            browser('screenshot',str(ROOT/'artifacts/screenshots/portfolio-ui.png'))
            click('文件管理')
            assert 'UI.TXT' not in browser('get','text','table')
            checks.append('restore removes subsequent file and creates recovery point')
            click('LAB ›');click('CHAIN.TXT');browser('wait','button[aria-label="查看簇 6 的 FAT 项"]')
            click('查看簇 6 的 FAT 项');wait('FAT 1 原始字节');click('查看所选簇的数据扇区')
            wait('偏移 0x4A00')
            checks.append('fragmented chain links to FAT and data sector 37')
            click('文件管理');click('CHAIN.TXT');wait('UTF-8 文本预览')
            browser('find','label','文件内容','fill','unsaved edit')
            click('快照恢复');wait('有未保存的修改')
            checks.append('dirty editor blocks navigation')
            click('还原');click('快照恢复');browser('set','viewport','680','900')
            assert 'true' in browser('eval','document.documentElement.scrollWidth <= window.innerWidth')
            checks.append('narrow viewport has no page-level horizontal overflow')
            # Simulate an external tool corrupting one FAT while retaining a
            # readable BPB. Refresh must expose the damage and permit recovery.
            damaged=bytearray(image.read_bytes())
            damaged[int.from_bytes(damaged[14:16],'little')*512+3]^=1
            image.write_bytes(damaged)
            click('刷新磁盘');wait('已重新读取当前磁盘')
            browser('wait','--fn',"!!document.querySelector('.unhealthy')")
            wait('browser checkpoint')
            index=int(evaluate("Array.from(document.querySelectorAll('.snapshot-panel tbody tr')).findIndex(row=>row.querySelector('b')?.textContent==='browser checkpoint')").strip())
            assert index>=0
            browser('find','nth',str(index),'.snapshot-panel tbody tr button','click')
            wait('确认恢复快照');click('确认恢复')
            browser('wait','--fn',"!!document.querySelector('.healthy')")
            wait('受损状态原始副本，仅供分析')
            checks.append('external FAT damage is diagnosed and recovered through UI')
            assert 'true' in evaluate("Array.from(document.querySelectorAll('tr')).find(row=>row.textContent.includes('仅供分析'))?.querySelector('button')?.disabled")
            checks.append('raw damaged protection point cannot be restored through UI')
            browser('set','viewport','1280','900');browser('scroll','up','2000')
            browser('screenshot',str(ROOT/'artifacts/screenshots/portfolio-ui.png'))
            click('磁盘分析');wait('文件尾部空闲');click('预览整理');wait('整理预览')
            command('write PLAN.TXT "preview changed"')
            assert 'true' in evaluate("!document.querySelector('.defrag-preview')")
            checks.append('a mutation invalidates the visible compaction preview')
            click('预览整理');wait('整理预览');click('应用整理计划')
            wait('确认磁盘整理');click('确认整理');wait('磁盘整理完成')
            browser('wait','--fn',"!document.querySelector('#command').disabled")
            report=json.load(urllib.request.urlopen(url+'api/analysis'))
            assert report['summary']['fragmented_files']==0 and report['check']['ok']
            checks.append('confirmed UI compaction persists a healthy contiguous layout')
            browser('screenshot',str(ROOT/'artifacts/screenshots/compacted-ui.png'))
            browser('close')
            server.terminate();server.wait(timeout=10)
            server=subprocess.Popen([sys.executable,'-m','fat12lab','--image',str(image),'--read-only','--web','--port',str(port),'--no-browser'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(100):
                try:urllib.request.urlopen(url,timeout=1).close();break
                except OSError:time.sleep(.05)
            browser('open',url);wait('只读查看')
            result=browser('eval',"document.querySelector('button[aria-label=\"新建文件\"]')?.disabled ?? Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='新建文件')?.disabled")
            assert 'true' in result
            checks.append('read-only mode disables creation controls')
            click('磁盘分析');wait('文件尾部空闲');click('预览整理');wait('整理预览')
            assert 'true' in evaluate("Array.from(document.querySelectorAll('button')).find(button=>button.textContent==='应用整理计划')?.disabled")
            checks.append('read-only allocation preview cannot be applied')
        finally:
            try:browser('close')
            finally:
                if server.poll() is None:server.terminate();server.wait(timeout=10)
    output={**metadata(),'ok':True,'checks':checks}
    (ROOT/'artifacts/browser-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
