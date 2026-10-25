from pathlib import Path
import tempfile
import unittest


class PublicReleaseTests(unittest.TestCase):
    def test_only_authored_source_and_selected_evidence_are_published(self):
        from tools.public_release import public_files
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            allowed=('README.md','fat12lab/filesystem.py','web/src/App.tsx','tests/test_storage.py',
                     'docs/architecture.md','artifacts/test-results.json','data/demo.img','tools/evidence.py')
            excluded=('.env','data/work.img','docs/技术报告.md','docs/superpowers/private.md',
                      'tools/build_report.py','artifacts/qa/private.txt','web/node_modules/private.js',
                      'fat12lab/__pycache__/private.pyc','artifacts/course-image-results.json',
                      'fat12lab/.env','fat12lab/notes.txt','web/src/.env','tests/private.txt')
            for name in allowed+excluded:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('example',encoding='utf-8')
            found={p.relative_to(root).as_posix() for p in public_files(root)}
            self.assertEqual(found,set(allowed))

    def test_a_secret_in_an_allowed_file_blocks_export(self):
        from tools.public_release import public_files
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'README.md').write_text('ghp_'+'A'*36,encoding='utf-8')
            with self.assertRaises(ValueError):public_files(root)

    def test_machine_specific_home_path_in_an_allowed_file_blocks_export(self):
        from tools.public_release import public_files
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'README.md').write_text('C:'+'/Users/'+'PrivateName/file',encoding='utf-8')
            with self.assertRaises(ValueError):public_files(root)
