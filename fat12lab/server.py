"""Loopback-only HTTP adapter for the React interface, using the standard library."""

from __future__ import annotations

import base64
import binascii
import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .filesystem import FAT12, FATError, Layout, MAX_IMAGE_SIZE
from .shell import Shell
from .storage import ConcurrentWriteError

WEB_DIST = Path(__file__).resolve().parent / 'static'


def disk_changes(before: bytes, fs: FAT12) -> dict:
    """Exact byte/sector counts with bounded raw samples, for classroom evidence."""
    previous = Layout.parse(before)
    allocation_fields = ('total_sectors', 'sectors_per_cluster', 'reserved', 'fat_sectors', 'root_entries')
    reason = 'capacity' if len(before) != len(fs.data) else 'layout'
    if any(getattr(previous, field) != getattr(fs.layout, field) for field in allocation_fields):
        return {'replaced':True,'before_bytes':len(before),'after_bytes':len(fs.data),
                'reason':reason,'changed_bytes':None,'sectors':[],'regions':{},'samples':[]}
    if before == fs.data:
        return {'replaced':False,'changed_bytes':0,'changed_sector_count':0,
                'sectors':[],'regions':{},'samples':[]}
    g = fs.layout
    bounds = ((g.reserved*512,'引导与保留区'),
              ((g.reserved+g.fat_sectors)*512,'FAT 1'),
              (g.root_sector*512,'FAT 2'),(g.data_sector*512,'根目录'),
              (len(fs.data),'数据区'))
    count, sectors, regions, samples = 0, set(), {}, []
    run = None
    for index,(old,new) in enumerate(zip(before,fs.data)):
        if old == new:
            run = None
            continue
        count += 1
        sectors.add(index//512)
        region = next(name for end,name in bounds if index < end)
        regions[region] = regions.get(region,0)+1
        if run is not None and run['offset']+len(run['before']) == index and len(run['before'])<16:
            run['before'].append(old);run['after'].append(new)
        elif len(samples)<16:
            run={'offset':index,'before':[old],'after':[new]};samples.append(run)
        else:
            run=None
    for sample in samples:
        sample['before'] = bytes(sample['before']).hex(' ').upper()
        sample['after'] = bytes(sample['after']).hex(' ').upper()
    return {'replaced':False,'changed_bytes':count,'changed_sector_count':len(sectors),
            'sectors':sorted(sectors)[:64],'regions':regions,'samples':samples}


def snapshot(fs: FAT12, path: str = "/") -> dict:
    path = fs.normalize(path)
    return {"info": fs.info(), "path": path,
            "entries": [e.to_dict() for e in fs.list_dir(path)],
            "fat": [fs.fat_get(c) for c in range(fs.layout.last_cluster + 1)], "check": fs.check(),
            "bpb": fs.inspect_bpb()}


def make_handler(fs: FAT12, port: int):
    lock = threading.RLock()
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{host}" for host in hosts}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(WEB_DIST), **kwargs)

        def _guard(self):
            if self.headers.get("Host") not in hosts:
                self.send_error(403, "Loopback Host required")
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                self.send_error(403, "Same origin required")
                return False
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_error(403, "Cross-site request denied")
                return False
            return True

        def end_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
            super().end_headers()

        def _json(self, payload, status=200):
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _binary(self, data, filename):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._guard():
                return
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query)
            try:
                with lock:
                    path = params.get("path", ["/"])[0]
                    if parsed.path == "/api/state":
                        self._json(snapshot(fs, path))
                    elif parsed.path == '/api/snapshots':
                        self._json({'snapshots':fs.list_snapshots()})
                    elif parsed.path == '/api/analysis':
                        self._json(fs.analyze())
                    elif parsed.path == '/api/defrag-plan':
                        self._json(fs.plan_defragmentation())
                    elif parsed.path == "/api/file":
                        data, entry = fs.read_file(path), fs.stat(path)
                        try:
                            content, text = data.decode("utf-8"), True
                        except UnicodeDecodeError:
                            content, text = "", False
                        self._json({"entry": entry.to_dict(), "chain": fs.chain(entry.cluster),
                                    "content": content, "is_text": text, "raw_entry": fs.inspect_entry(path)})
                    elif parsed.path == '/api/fat-entry':
                        self._json(fs.inspect_fat(int(params.get('cluster', ['2'])[0])))
                    elif parsed.path == "/api/download":
                        self._binary(fs.read_file(path), fs.stat(path).name)
                    elif parsed.path == "/api/image":
                        self._binary(bytes(fs.data), "fat12lab.img")
                    elif parsed.path == "/api/sector":
                        index = int(params.get("index", ["0"])[0])
                        self._json({"index": index, "bytes": list(fs.sector(index))})
                    elif parsed.path.startswith("/api/"):
                        self._json({"error": "接口不存在"}, 404)
                    else:
                        # Only bundled static assets are exposed, never workspace sources.
                        requested = (WEB_DIST / parsed.path.lstrip("/")).resolve()
                        if not requested.is_relative_to(WEB_DIST.resolve()) or not requested.exists():
                            self.send_error(404)
                        else:
                            super().do_GET()
            except (FATError, ValueError, OSError) as exc:
                self._json({"error": str(exc)}, 400)

        def do_POST(self):
            if not self._guard():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_IMAGE_SIZE * 4 // 3 + 4096:
                    raise FATError("请求大小超限或为空")
                # Consume a bounded body before rejecting its media type. Closing
                # a socket with unread bytes can reset the Windows connection
                # before the client receives the otherwise valid error response.
                raw = self.rfile.read(length)
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise FATError("请求必须为 application/json")
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise FATError("请求应为 JSON 对象")
                route = urlsplit(self.path).path
                with lock:
                    before = bytes(fs.data)
                    cwd = fs.normalize(str(body.get("cwd", "/")))
                    output = ""
                    if route == "/api/command":
                        shell = Shell(fs, allow_host_io=False)
                        shell.cwd = cwd
                        fs.resolve_dir(cwd)
                        output = shell.execute(str(body["command"]))
                        cwd = shell.cwd
                    elif route == "/api/write":
                        fs.write_file(str(body["path"]), str(body["content"]).encode("utf-8"))
                        output = "文件已保存"
                    elif route == "/api/upload":
                        data = base64.b64decode(body["data"], validate=True)
                        fs.write_file(str(body["path"]), data, overwrite=False)
                        output = f"已导入 {len(data)} 字节"
                    elif route == "/api/mount":
                        data = base64.b64decode(body["data"], validate=True)
                        candidate = FAT12(data)
                        report = candidate.check()
                        if not report["ok"]:
                            raise FATError("镜像校验失败：" + report["errors"][0])
                        fs.create_snapshot('加载镜像前自动保护点')
                        old, old_layout = fs.data, fs.layout
                        fs.data = candidate.data
                        fs.layout = candidate.layout
                        try:
                            fs.save()
                        except Exception:
                            fs.data = old
                            fs.layout = old_layout
                            raise
                        cwd, output = "/", "已加载镜像"
                    elif route == '/api/snapshot':
                        item = fs.create_snapshot(str(body.get('label', '')))
                        output = '快照已创建：' + item['id']
                    elif route == '/api/restore':
                        fs.restore_snapshot(str(body['id']))
                        cwd, output = '/', '快照已恢复，原内容已保存为保护点'
                    elif route == '/api/reload':
                        fs.reload()
                        cwd, output = '/', '已重新读取当前磁盘'
                    elif route == '/api/defragment':
                        plan = fs.defragment(str(body['expected_sha256']))
                        cwd, output = '/', f"磁盘整理完成：移动 {plan['moved_clusters']} 个簇；整理前状态已保存为保护点"
                    else:
                        self._json({"error": "接口不存在"}, 404)
                        return
                    # The directory may have been moved or removed by an explicit command.
                    try:
                        fs.resolve_dir(cwd)
                    except FATError:
                        cwd = "/"
                    self._json({"output": output, "state": snapshot(fs, cwd),
                                "changes":disk_changes(before, fs)})
            except ConcurrentWriteError as exc:
                self._json({'error':str(exc)}, 409)
            except (FATError, ValueError, OSError, KeyError, TypeError, binascii.Error) as exc:
                self._json({"error": str(exc)}, 400)

        def log_message(self, fmt, *args):
            # Keep terminal output readable during a classroom demonstration.
            if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
                super().log_message(fmt, *args)

    return Handler


def serve(fs: FAT12, port: int = 8765, open_browser: bool = True):
    if not (WEB_DIST / "index.html").exists():
        raise FATError("缺少前端构建产物，请进入 web 执行 npm ci 和 npm run build")
    if not 1024 <= port <= 65535:
        raise FATError("端口应为 1024 至 65535")
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(fs, port))
    server.daemon_threads = True
    print(f"图形界面：http://127.0.0.1:{port}，镜像：{fs.path}。按 Ctrl+C 停止。", flush=True)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
