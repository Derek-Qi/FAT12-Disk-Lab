from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import package_submission


class SubmissionTests(unittest.TestCase):
    def fixture(self, root):
        for name in ('README.md','README.zh-CN.md','pyproject.toml','fat12lab/__init__.py',
                     'fat12lab/static/index.html','docs/技术报告.md',
                     'docs/superpowers/private.md','tools/private_helper.py','data/work.img'):
            path=root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('example',encoding='utf-8')

    def test_submission_includes_runtime_metadata_and_chinese_instructions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();self.fixture(root)
            with patch.object(package_submission,'ROOT',root):
                names={p.relative_to(root).as_posix() for p in package_submission.sources()}
            self.assertTrue({'pyproject.toml','README.zh-CN.md','fat12lab/static/index.html'}<=names)

    def test_submission_excludes_execution_notes_and_unselected_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();self.fixture(root)
            with patch.object(package_submission,'ROOT',root):
                names={p.relative_to(root).as_posix() for p in package_submission.sources()}
            self.assertFalse({'docs/superpowers/private.md','tools/private_helper.py','data/work.img'} & names)
