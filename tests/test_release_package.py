import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_release import audit
from build_release import add_file


class ReleasePackageTests(unittest.TestCase):
    def test_command_keeps_executable_bits_and_unicode_name(self):
        with tempfile.TemporaryDirectory(prefix='mlx-zip-test-') as temp:
            root = Path(temp)
            command = root / '启动.command'
            command.write_text('#!/bin/bash\ntrue\n')
            target = root / 'release.zip'
            with zipfile.ZipFile(target, 'w') as archive:
                add_file(archive, command, '工作台/启动.command')
            with zipfile.ZipFile(target) as archive:
                info = archive.getinfo('工作台/启动.command')
                self.assertEqual(info.create_system, 3)
                mode = info.external_attr >> 16
                self.assertEqual(stat.S_IMODE(mode), 0o755)
                self.assertTrue(stat.S_ISREG(mode))
                self.assertEqual(archive.read(info), command.read_bytes())

    def test_runtime_data_is_rejected_even_if_manifest_lists_it(self):
        with tempfile.TemporaryDirectory(prefix='mlx-audit-test-') as temp:
            root = Path(temp)
            (root / 'release-files.json').write_text(json.dumps({'files': ['data/history.json']}))
            files, problems = audit(root)
            self.assertEqual(len(problems), 1)
            self.assertIn('不允许的路径', problems[0])

    def test_symlinks_cannot_smuggle_user_files(self):
        with tempfile.TemporaryDirectory(prefix='mlx-audit-test-') as temp:
            root = Path(temp)
            (root / 'private.txt').write_text('private')
            (root / 'README.md').symlink_to(root / 'private.txt')
            (root / 'release-files.json').write_text(json.dumps({'files': ['README.md']}))
            self.assertTrue(audit(root)[1])

    def test_audit_reports_location_without_echoing_secrets(self):
        with tempfile.TemporaryDirectory(prefix='mlx-audit-test-') as temp:
            root = Path(temp)
            fake = 'hf_' + 'a' * 30
            (root / 'README.md').write_text(fake)
            (root / 'release-files.json').write_text(json.dumps({'files': ['README.md']}))
            problems = audit(root)[1]
            self.assertEqual(len(problems), 1)
            self.assertNotIn(fake, problems[0])
            self.assertIn('README.md:1', problems[0])


if __name__ == '__main__':
    unittest.main()
