from pathlib import Path
import tempfile
import unittest


class BrowserCliTests(unittest.TestCase):
    def test_windows_literal_wrapper_resolves_to_native_executable(self):
        from tools.browser_cli import browser_executable
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);native=root/'folder with & spaces'/'agent-browser-win32-x64.exe'
            native.parent.mkdir();native.write_bytes(b'native fixture')
            wrapper=root/'agent-browser.cmd';wrapper.write_text(f'@echo off\n"{native}" %*\n',encoding='utf-8')
            self.assertEqual(browser_executable(str(wrapper),windows=True),str(native))

    def test_windows_unknown_shell_wrapper_is_refused(self):
        from tools.browser_cli import browser_executable
        with tempfile.TemporaryDirectory() as folder:
            wrapper=Path(folder)/'agent-browser.cmd';wrapper.write_text('@echo unsafe wrapper',encoding='utf-8')
            with self.assertRaises(RuntimeError):browser_executable(str(wrapper),windows=True)
