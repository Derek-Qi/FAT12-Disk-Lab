from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fat12lab import FAT12


class CliTests(unittest.TestCase):
    def run_script(self, content, *commands, stdin=''):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'cli.img';script=root/'commands.txt'
            FAT12.create(image);script.write_bytes(content)
            args=[sys.executable,'-m','fat12lab','--image',str(image),'--script',str(script)]
            for command in commands:args.extend(['-c',command])
            result=subprocess.run(args,input=stdin,capture_output=True,text=True,encoding='utf-8',timeout=20)
            names=[entry.name for entry in FAT12.open(image).list_dir()]
            return result,names

    def test_empty_script_exits_without_consuming_interactive_input(self):
        result,names=self.run_script(b'# comment only\n',stdin='write WRONG.TXT "unexpected"\nexit\n')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('WRONG.TXT',names)
        self.assertNotIn('输入 help',result.stdout)

    def test_invalid_script_encoding_reports_error_without_traceback(self):
        result,names=self.run_script(b'\xff\xfe\x00')
        self.assertEqual(result.returncode,1)
        self.assertNotIn('Traceback',result.stderr)
        self.assertIn('UTF-8',result.stderr)
        self.assertEqual(names,[])

    def test_quoted_exit_stops_the_script(self):
        for command in (b"'exit'",b'"EXIT"'):
            with self.subTest(command=command):
                result,names=self.run_script(command+b'\nwrite WRONG.TXT x\n')
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(names,[])
