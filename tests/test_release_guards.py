import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import package_release


class ReleaseGuardTests(unittest.TestCase):
    def fixture(self,root,receipt_version,wheel_name):
        (root/'artifacts/releases').mkdir(parents=True)
        (root/'pyproject.toml').write_text('[project]\nversion="9.9.9"\n',encoding='utf-8')
        for name in ('test-results','interop-results','browser-results','distribution-results'):
            data={'ok':True,'version':receipt_version}
            if name=='distribution-results':
                wheel=root/'artifacts/releases'/wheel_name;wheel.write_bytes(b'tested wheel')
                data.update(wheel=wheel_name,wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest())
            (root/f'artifacts/{name}.json').write_text(json.dumps(data),encoding='utf-8')

    def test_release_rejects_successful_receipts_from_another_version(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            self.fixture(root,'9.9.8','fat12_disk_lab-9.9.8-py3-none-any.whl')
            with patch.object(package_release,'ROOT',root),patch.object(package_release,'project_version',return_value='9.9.9'):
                with self.assertRaisesRegex(AssertionError,'version'):
                    package_release.main()
            self.assertFalse((root/'artifacts/releases/FAT12Lab-v9.9.9.zip').exists())

    def test_release_requires_the_current_versions_wheel(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            self.fixture(root,'9.9.9','fat12_disk_lab-9.9.8-py3-none-any.whl')
            with patch.object(package_release,'ROOT',root),patch.object(package_release,'project_version',return_value='9.9.9'):
                with self.assertRaisesRegex(AssertionError,'wheel'):
                    package_release.main()
            self.assertFalse((root/'artifacts/releases/FAT12Lab-v9.9.9.zip').exists())
