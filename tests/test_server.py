import base64
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fat12lab import FAT12
from fat12lab.server import make_handler
from test_layout_inspection import disk720


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.fs=FAT12.create(Path(cls.temp.name)/'api.img')
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(cls.fs,0))
        cls.port=cls.server.server_address[1]
        cls.server.RequestHandlerClass=make_handler(cls.fs,cls.port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self,route,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        actual_headers={'Content-Type':'application/json'}
        actual_headers.update(headers or {})
        connection.request('POST' if body is not None else 'GET',route,json.dumps(body) if body is not None else None,actual_headers)
        response=connection.getresponse()
        result=(response.status,response.read(),dict(response.getheaders()))
        connection.close()
        return result

    def test_command_write_read_download_and_persistence(self):
        status,data,_=self.request('/api/command',{'command':'write API.TXT "你好 API"','cwd':'/'})
        self.assertEqual(status,200,data)
        status,data,_=self.request('/api/file?path=/API.TXT')
        self.assertEqual(json.loads(data)['content'],'你好 API')
        status,data,headers=self.request('/api/download?path=/API.TXT')
        self.assertEqual(data,'你好 API'.encode())
        self.assertIn('attachment',headers['Content-Disposition'])
        self.assertEqual(FAT12.open(self.fs.path).read_file('/API.TXT'),data)

    def test_binary_upload_and_sector(self):
        value=bytes(range(256))*3
        status,data,_=self.request('/api/upload',{'path':'/UPLOAD.BIN','data':base64.b64encode(value).decode()})
        self.assertEqual(status,200,data)
        self.assertEqual(self.request('/api/download?path=/UPLOAD.BIN')[1],value)
        status,data,_=self.request('/api/sector?index=0')
        self.assertEqual(json.loads(data)['bytes'][-2:],[85,170])

    def test_mount_invalid_is_transactional(self):
        before=bytes(self.fs.data)
        status,_,_=self.request('/api/mount',{'data':base64.b64encode(b'bad').decode()})
        self.assertEqual(status,400)
        self.assertEqual(before,self.fs.data)

    def test_origin_host_content_type_and_invalid_requests(self):
        self.assertEqual(self.request('/api/state',headers={'Origin':'https://example.com'})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'example.com'})[0],403)
        before=bytes(self.fs.data)
        status,data,_=self.request('/api/command',{'command':'help'},headers={'Content-Type':'text/plain'})
        self.assertEqual(status,400)
        self.assertEqual(json.loads(data)['error'],'请求必须为 application/json')
        self.assertEqual(bytes(self.fs.data),before)
        self.assertEqual(self.request('/api/missing')[0],404)
        self.assertEqual(self.request('/api/sector?index=9999')[0],400)
        self.assertEqual(self.request('/api/command',{'command':'export A.TXT C:/TEMP.TXT'})[0],400)

    def test_parallel_mutations_are_serialized(self):
        results=[]
        def write(index):
            results.append(self.request('/api/command',{'command':f'write T{index}.TXT "thread {index}"'})[0])
        threads=[threading.Thread(target=write,args=(i,)) for i in range(8)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(results,[200]*8)
        self.assertTrue(self.fs.check()['ok'])
        for i in range(8):self.assertEqual(self.fs.read_file(f'/T{i}.TXT'),f'thread {i}'.encode())

    def test_mount_720kb_updates_geometry_and_persisted_image(self):
        old=bytes(self.fs.data)
        try:
            encoded=base64.b64encode(disk720().data).decode()
            status,data,_=self.request('/api/mount',{'data':encoded})
            self.assertEqual(status,200,data)
            result=json.loads(data)
            self.assertEqual(result['state']['info']['cluster_bytes'],1024)
            self.assertEqual(len(result['state']['fat']),715)
            self.assertTrue(result['changes']['replaced'])
            self.assertEqual(FAT12.open(self.fs.path).layout.data_sector,14)
            status,data,_=self.request('/api/command',{'command':'write ROUND.TXT "roundtrip"'})
            self.assertEqual(status,200,data)
            self.assertEqual(FAT12.open(self.fs.path).read_file('/ROUND.TXT'),b'roundtrip')
        finally:
            self.request('/api/mount',{'data':base64.b64encode(old).decode()})

    def test_mount_save_failure_restores_geometry_and_image(self):
        before=bytes(self.fs.data);layout=self.fs.layout
        with patch.object(self.fs,'save',side_effect=OSError('test failure')):
            status,_,_=self.request('/api/mount',{'data':base64.b64encode(disk720().data).decode()})
        self.assertEqual(status,400)
        self.assertEqual(bytes(self.fs.data),before)
        self.assertEqual(self.fs.layout,layout)

    def test_decoded_entry_fat_and_readonly_byte_diff(self):
        status,data,_=self.request('/api/command',{'command':'write DECODE.TXT "bytes"'})
        self.assertEqual(status,200,data)
        changes=json.loads(data)['changes']
        self.assertIn('FAT 1',changes['regions']);self.assertIn('FAT 2',changes['regions'])
        status,data,_=self.request('/api/file?path=/DECODE.TXT')
        entry=json.loads(data)
        self.assertEqual(len(bytes.fromhex(entry['raw_entry']['raw'])),32)
        status,data,_=self.request(f"/api/fat-entry?cluster={entry['entry']['cluster']}")
        self.assertEqual(json.loads(data)['value'],0xFFF)
        status,data,_=self.request('/api/command',{'command':'dir'})
        self.assertEqual(json.loads(data)['changes']['changed_bytes'],0)

    def test_snapshot_and_restore_http_roundtrip(self):
        self.request('/api/write',{'path':'/SNAP.TXT','content':'original'})
        status,data,_=self.request('/api/snapshot',{'label':'HTTP checkpoint'})
        self.assertEqual(status,200,data)
        status,data,_=self.request('/api/snapshots')
        item=next(s for s in json.loads(data)['snapshots'] if s['label']=='HTTP checkpoint')
        self.request('/api/write',{'path':'/SNAP.TXT','content':'changed'})
        status,data,_=self.request('/api/restore',{'id':item['id']})
        self.assertEqual(status,200,data)
        self.assertEqual(self.fs.read_file('/SNAP.TXT'),b'original')

    def test_allocation_preview_apply_and_stale_plan_http(self):
        self.fs.write_file('/ZFRAG.BIN',b'z'*1025)
        self.fs.write_file('/AFRAG.BIN',b'a')
        before=bytes(self.fs.data)
        status,data,_=self.request('/api/analysis')
        self.assertEqual(status,200,data)
        self.assertTrue(json.loads(data)['check']['ok'])
        status,data,_=self.request('/api/defrag-plan')
        self.assertEqual(status,200,data)
        plan=json.loads(data);self.assertEqual(bytes(self.fs.data),before)
        self.assertGreater(plan['moved_clusters'],0)
        self.fs.write_file('/ANEW.TXT',b'new')
        latest=bytes(self.fs.data)
        status,data,_=self.request('/api/defragment',{'expected_sha256':plan['image_sha256']})
        self.assertEqual(status,400,data);self.assertEqual(bytes(self.fs.data),latest)
        status,data,_=self.request('/api/defrag-plan');plan=json.loads(data)
        status,data,_=self.request('/api/defragment',{'expected_sha256':plan['image_sha256']})
        self.assertEqual(status,200,data)
        self.assertTrue(json.loads(data)['state']['check']['ok'])
        self.assertEqual(self.fs.read_file('/ZFRAG.BIN'),b'z'*1025)

    def test_readonly_http_allocation_preview_and_apply_refusal(self):
        before=bytes(self.fs.data);self.fs.read_only=True
        try:
            status,data,_=self.request('/api/analysis');self.assertEqual(status,200,data)
            status,data,_=self.request('/api/defrag-plan');self.assertEqual(status,200,data)
            plan=json.loads(data)
            status,data,_=self.request('/api/defragment',{'expected_sha256':plan['image_sha256']})
            self.assertEqual(status,400,data);self.assertEqual(bytes(self.fs.data),before)
        finally:self.fs.read_only=False

    def test_reload_resolves_external_write_conflict(self):
        other=FAT12.open(self.fs.path);other.write_file('/OUTSIDE.TXT',b'outside')
        status,_,_=self.request('/api/write',{'path':'/STALE.TXT','content':'stale'})
        self.assertEqual(status,409)
        status,data,_=self.request('/api/reload',{})
        self.assertEqual(status,200,data)
        self.assertEqual(self.fs.read_file('/OUTSIDE.TXT'),b'outside')

    def test_readonly_http_state_and_mutation_refusal(self):
        before=bytes(self.fs.data);self.fs.read_only=True
        try:
            status,data,_=self.request('/api/state')
            self.assertTrue(json.loads(data)['info']['read_only'])
            for route,body in (('/api/write',{'path':'/NO.TXT','content':'no'}),('/api/snapshot',{})):
                self.assertEqual(self.request(route,body)[0],400)
            self.assertEqual(bytes(self.fs.data),before)
        finally:self.fs.read_only=False


if __name__=='__main__':
    unittest.main()
