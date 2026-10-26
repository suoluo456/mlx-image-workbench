"""Offline tests with tiny synthetic files; never reads or downloads model weights."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
try:
    import requests
except ImportError:
    class RequestException(Exception):
        pass
    requests = types.SimpleNamespace(RequestException=RequestException, get=None)
    sys.modules['requests'] = requests
spec = importlib.util.spec_from_file_location('model_manager_under_test', ROOT / 'scripts/manage_models.py')
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class Response:
    def __init__(self, content, status=200, content_range=None):
        self.content, self.status_code = content, status
        self.headers = {'Content-Range': content_range} if content_range else {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def raise_for_status(self):
        pass
    def iter_content(self, size):
        yield self.content


class ModelManagerTest(unittest.TestCase):
    def setUp(self):
        tests = ROOT / '.tools/test-model-manager'
        tests.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=tests)
        self.root = Path(self.temp.name)
        self.model_dir = self.root / 'models'
        self.model_dir.mkdir()
        self.directory = self.model_dir / 'fixture'
        self.directory.mkdir()
        self.content = b'five!'
        self.entry = dict(path='weights.bin', remote_path='weights.bin', repo='public/fixture',
                          revision='a' * 40, size=5, sha256=hashlib.sha256(self.content).hexdigest())
        self.manifest = {'zimage': dict(name='fixture', folder='fixture', files=[self.entry])}
        self.patches = [patch.object(manager, 'MODEL_DIR', self.model_dir),
                        patch.object(manager, 'MANIFEST', self.manifest),
                        patch.object(manager.time, 'sleep'), patch('sys.stdout', new_callable=io.StringIO)]
        for p in self.patches:
            p.start()
    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_resume_checks_range_and_sha(self):
        (self.directory / 'weights.bin.part').write_bytes(self.content[:2])
        with patch.object(requests, 'get', return_value=Response(self.content[2:], 206, 'bytes 2-4/5')) as get:
            result = manager.download(self.directory, self.entry)
        self.assertEqual(get.call_args.kwargs['headers']['Range'], 'bytes=2-')
        self.assertEqual(result.read_bytes(), self.content)
        self.assertFalse((self.directory / 'weights.bin.part').exists())

    def test_server_without_range_safely_restarts(self):
        (self.directory / 'weights.bin.part').write_bytes(b'xx')
        with patch.object(requests, 'get', return_value=Response(self.content)):
            result = manager.download(self.directory, self.entry)
        self.assertEqual(result.read_bytes(), self.content)

    def test_corrupt_file_same_size_is_repaired(self):
        (self.directory / 'weights.bin').write_bytes(b'wrong')
        with patch.object(requests, 'get', return_value=Response(self.content)):
            result = manager.download(self.directory, self.entry)
        self.assertEqual(result.read_bytes(), self.content)

    def test_bad_sha_never_becomes_installed(self):
        with patch.object(requests, 'get', return_value=Response(b'wrong')):
            with self.assertRaisesRegex(ValueError, '下载未完成'):
                manager.download(self.directory, self.entry)
        self.assertFalse((self.directory / 'weights.bin').exists())
        self.assertFalse((self.directory / '.ready.json').exists())

    def test_verified_file_does_not_redownload(self):
        (self.directory / 'weights.bin').write_bytes(self.content)
        with patch.object(requests, 'get') as get:
            manager.download(self.directory, self.entry)
        get.assert_not_called()

    def test_path_escape_and_symlink_are_rejected(self):
        with self.assertRaises(ValueError):
            manager.safe_target(self.directory, '../../history.json')
        (self.directory / 'link').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            manager.safe_target(self.directory, 'link/history.json')

    def test_unowned_directory_is_not_adopted(self):
        (self.directory / 'keep.txt').write_text('personal')
        with self.assertRaisesRegex(ValueError, '已有不属于'):
            manager.install('zimage', set())
        self.assertEqual((self.directory / 'keep.txt').read_text(), 'personal')

    def test_low_disk_stops_before_download(self):
        with patch.object(manager.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=1)):
            with self.assertRaisesRegex(ValueError, '磁盘空间不足'):
                manager.check_space(self.manifest['zimage'], self.directory)

    def test_same_size_bad_file_still_reserves_replacement_space(self):
        (self.directory / 'weights.bin').write_bytes(b'wrong')
        with patch.object(manager.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=manager.RESERVE_BYTES + 4)):
            with self.assertRaisesRegex(ValueError, '磁盘空间不足'):
                manager.check_space(self.manifest['zimage'], self.directory)

    def test_remove_keeps_history_and_unrelated_files(self):
        history = self.root / 'history.json'
        history.write_text('keep')
        manager.write_json(self.directory / '.workbench-model.json', dict(app=manager.APP, model_id='zimage'))
        manager.remove('zimage', True)
        self.assertFalse(self.directory.exists())
        self.assertEqual(history.read_text(), 'keep')

    def test_remove_without_ownership_refused(self):
        with self.assertRaisesRegex(ValueError, '不是本安装器'):
            manager.remove('zimage', True)
        self.assertTrue(self.directory.exists())

    def test_remove_dependency_refused(self):
        manager.write_json(self.directory / '.workbench-model.json', dict(app=manager.APP, model_id='zimage'))
        self.manifest['dependent'] = dict(name='reference', folder='dependent', files=[], requires=['zimage'])
        (self.model_dir / 'dependent').mkdir()
        with self.assertRaisesRegex(ValueError, '先移除依赖'):
            manager.remove('zimage', True)

    def test_invalid_model_list_does_not_touch_disk(self):
        with patch.object(sys, 'argv', ['manage_models.py', 'remove', '../data', '--yes']), patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                manager.main()
        self.assertTrue(self.directory.exists())

    def test_verify_rejects_same_size_corruption(self):
        (self.directory / 'weights.bin').write_bytes(b'wrong')
        manager.write_json(self.directory / '.ready.json', dict(files={'weights.bin': 5},
                            sha256={'weights.bin': self.entry['sha256']}))
        with self.assertRaisesRegex(ValueError, '校验失败'):
            manager.verify('zimage')

    def test_verify_rejects_tampered_record_hash(self):
        (self.directory / 'weights.bin').write_bytes(self.content)
        manager.write_json(self.directory / '.ready.json', dict(files={'weights.bin': 5},
                            sha256={'weights.bin': '0' * 64}))
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            manager.verify('zimage')

    def test_reference_schedule_same_length_tamper_is_rejected(self):
        header = json.dumps({'weight': {'dtype': 'U8', 'shape': [1], 'data_offsets': [0, 1]}}).encode()
        transformer = self.directory / 'transformer'
        transformer.mkdir()
        target = transformer / '0.safetensors'
        target.write_bytes(struct.pack('<Q', len(header)) + header + b'x')
        manager.write_json(transformer / 'model.safetensors.index.json', manager.transformer_index(target))
        self.manifest['qwen21_turbo'] = dict(transformer=dict(size=target.stat().st_size, sha256=manager.digest(target)))
        self.manifest['qwen21_turbo_ref'] = dict(name='fixture reference', folder='fixture', files=[])
        index = self.directory / 'model_index.json'
        manager.write_json(index, dict(_class_name='QwenImage21Pipeline',
                           sample_sigmas=[1.0, .978453, .95418, .926626, .89508, .845148, .704534, .414568]))
        names = ['transformer/0.safetensors', 'transformer/model.safetensors.index.json', 'model_index.json']
        manager.write_json(self.directory / '.ready.json',
                           dict(files={n: (self.directory / n).stat().st_size for n in names},
                                sha256={n: manager.digest(self.directory / n) for n in names}))
        manager.verify('qwen21_turbo_ref')
        original_size = index.stat().st_size
        index.write_text(index.read_text().replace('1.0,', '1.1,'))
        self.assertEqual(index.stat().st_size, original_size)
        with self.assertRaisesRegex(ValueError, '时间表不匹配'):
            manager.verify('qwen21_turbo_ref')

    def test_repack_uses_download_revision_and_preserves_tensor_bytes(self):
        original_header = {'modulation.1.weight': {'dtype': 'U8', 'shape': [3], 'data_offsets': [0, 3]}}
        original_json = json.dumps(original_header).encode()
        download = self.directory / 'downloads/source.safetensors'
        download.parent.mkdir()
        download.write_bytes(struct.pack('<Q', len(original_json)) + original_json + b'abc')
        source_spec = dict(repo='public/turbo', revision='5' * 40, path='downloads/source.safetensors')
        expected_header = {'modulation.layers.1.weight': original_header['modulation.1.weight'],
                           '__metadata__': dict(quantization_level='8', mflux_version='0.20.0',
                                                source_repo='public/turbo', source_revision='5' * 40)}
        body = json.dumps(expected_header, separators=(',', ':')).encode()
        body += b' ' * (-len(body) % 8)
        expected = struct.pack('<Q', len(body)) + body + b'abc'
        transform_spec = dict(path='transformer/0.safetensors', size=len(expected),
                              sha256=hashlib.sha256(expected).hexdigest())
        with patch.object(manager, 'download', return_value=download):
            manager.repack_transformer(self.directory, dict(transformer=transform_spec, transformer_source=source_spec))
        self.assertEqual((self.directory / 'transformer/0.safetensors').read_bytes(), expected)
        index = json.loads((self.directory / 'transformer/model.safetensors.index.json').read_text())
        self.assertEqual(index['metadata']['source_revision'], '5' * 40)
        self.assertEqual(index['weight_map'], {'modulation.layers.1.weight': '0.safetensors'})


if __name__ == '__main__':
    unittest.main()
