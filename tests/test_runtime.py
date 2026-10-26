"""Public-release runtime checks. No model loading or user data required."""
import base64
import copy
import http.client
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import model_integrity
import model_registry
import reference_images
import tavern_prompt_rules
import workbench_paths
import web_ui as web
from PIL import Image


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mlx-workbench-runtime-')
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'
        self.output = self.data / 'output'
        self.groups = self.output / 'groups'
        self.logs = self.data / 'logs'
        self.groups.mkdir(parents=True)
        self.logs.mkdir()
        self.patches = [patch.object(web, 'DATA_DIR', self.data), patch.object(web, 'OUTPUT', self.output),
            patch.object(web, 'GROUPS', self.groups), patch.object(web, 'LOGS', self.logs),
            patch.object(web, 'PROMPT_FILE', self.data / 'prompt.txt'),
            patch.object(workbench_paths, 'SETTINGS_FILE', self.data / 'settings.json'),
            patch.object(reference_images, 'DIRECTORY', self.data / 'references'),
            patch.object(tavern_prompt_rules, 'DATA_DIR', self.data)]
        for context in self.patches:
            context.start()
        self.old_job = copy.deepcopy(web.job)
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server_thread.join(timeout=3)
        web.job.clear()
        web.job.update(self.old_job)
        if hasattr(web, 'comfy_avatar_ids'):
            del web.comfy_avatar_ids
        for context in reversed(self.patches):
            context.stop()
        self.temp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        if self.server is None:
            self.server = web.ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        body = json.dumps(data) if data is not None else None
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        payload = response.read()
        result = (response.status, dict(response.getheaders()), json.loads(payload) if payload else None)
        connection.close()
        return result

    def valid(self, **overrides):
        request = dict(prompt='A fox in the snow', width=512, height=512, count=1,
                       seed=42, models=[dict(id='zimage', steps=9)])
        request.update(overrides)
        with patch.object(web, 'ready', return_value=True):
            return web.validate_request(request)

    def test_public_catalog_and_empty_start(self):
        self.assertEqual({m['id'] for m in model_registry.catalog()}, {'zimage', 'qwen21_turbo'})
        self.assertEqual(web.default_prompt(), web.DEFAULT_PROMPT)
        self.assertFalse(workbench_paths.tavern_enabled())
        self.assertEqual(tavern_prompt_rules.character_prompts(), {})
        code, _, config = self.request('/api/config')
        self.assertEqual(code, 200)
        self.assertNotIn('loras', config)
        self.assertFalse(config['tavern']['enabled'])
        code, _, history = self.request('/api/history')
        self.assertEqual(code, 200)
        self.assertEqual(history['total'], 0)

    def test_health_and_local_origin_only(self):
        code, headers, health = self.request('/api/health', headers={'Origin': 'http://localhost:8027'})
        self.assertEqual(code, 200)
        self.assertEqual(health['app'], 'mlx-image-workbench')
        self.assertEqual(health['service'], health['app'])
        self.assertEqual(health['data_dir'], str(self.data))
        self.assertEqual(health['model_dir'], str(web.MODEL_DIR))
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'http://localhost:8027')
        self.assertEqual(self.request('/api/health', headers={'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.request('/api/health', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.request('/api/history', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.request('/api/generate', 'POST', {'loras': []})[0], 400)

    def test_tavern_disabled_and_explicit_enable(self):
        for path in ('/system_stats', '/object_info', '/history/job', '/api/tavern/diagnostics', '/sdapi/v1/options'):
            self.assertEqual(self.request(path)[0], 403)
        (self.data / 'settings.json').write_text('{"tavern_enabled":true}')
        self.assertEqual(self.request('/api/health')[2]['tavern_enabled'], True)
        self.assertEqual(self.request('/object_info')[0], 200)
        self.assertEqual(self.request('/history/unknown')[2], {})
        self.assertEqual(self.request('/api/tavern/diagnostics', 'OPTIONS', headers={
            'Origin': 'http://127.0.0.1:8123', 'Access-Control-Request-Method': 'POST'})[0], 204)
        self.assertEqual(self.request('/api/tavern/diagnostics', 'OPTIONS', headers={
            'Origin': 'https://example.com', 'Access-Control-Request-Method': 'POST'})[0], 403)

    def test_adapter_parameters_and_old_model_rejected(self):
        with self.assertRaisesRegex(ValueError, 'LoRA'):
            self.valid(loras=[])
        with self.assertRaisesRegex(ValueError, 'LoRA'):
            self.valid(models=[dict(id='zimage', steps=9, loras=[])])
        with self.assertRaisesRegex(ValueError, '模型不存在'):
            self.valid(models=[dict(id='qwen21', steps=40)])
        with self.assertRaisesRegex(ValueError, '8 步'):
            self.valid(models=[dict(id='qwen21_turbo', steps=9)])

    def test_commands_use_public_paths(self):
        request = self.valid()
        item = dict(model='zimage', effective_prompt='A fox', steps=9, seed=42, filename='test.png')
        with patch.object(web, 'MODEL_DIR', self.root / 'models space'):
            command = web.command_for(item, request)
        self.assertIn(str(self.root / 'models space/z-image-turbo-mflux-q8'), command)
        self.assertEqual(command[-1], str(self.output / 'test.png'))
        self.assertFalse(any('lora' in value.lower() for value in command))
        self.assertTrue(command[0].startswith(str(ROOT)))

    def test_seeded_batches_and_saved_history_without_adapters(self):
        request = self.valid(count=2, models=[dict(id='zimage', steps=9),dict(id='qwen21_turbo', steps=8)])
        with patch.object(web.threading, 'Thread'):
            self.assertTrue(web.start_job(request))
        self.assertEqual(len(web.job['items']), 4)
        self.assertEqual([i['seed'] for i in web.job['items'][:2]], [i['seed'] for i in web.job['items'][2:]])
        self.assertEqual(len(web.batch_items(0)), 2)
        self.assertNotIn('loras', web.job['items'][0])
        self.assertEqual(len(list(self.groups.glob('*.json'))), 1)

    def test_reference_upload_and_character_rules_are_local(self):
        image = Image.new('RGB', (80, 80), '#6699aa')
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        record = reference_images.upload({'image': base64.b64encode(buffer.getvalue()).decode()})
        self.assertTrue(reference_images.resolve(record['id']).is_relative_to(self.data))
        with self.assertRaises(ValueError):
            reference_images.resolve('../image.png')
        (self.data / 'character-prompts.json').write_text(json.dumps({'Example': 'A green scarf', 'Invalid': 3}))
        self.assertEqual(tavern_prompt_rules.character_prompts(), {'Example': 'A green scarf'})

    def test_ready_manifest_is_nonempty_and_scoped(self):
        model_root = self.root / 'models'
        folder = model_root / model_registry.MODELS['qwen21_turbo']['folder']
        folder.mkdir(parents=True)
        marker = folder / '.ready.json'
        with patch.object(model_registry, 'MODEL_DIR', model_root):
            marker.write_text('[]')
            self.assertFalse(model_registry.ready('qwen21_turbo'))
            marker.write_text('{"files":{}}')
            self.assertFalse(model_registry.ready('qwen21_turbo'))
            marker.write_text('{"files":{"../../secret":1}}')
            self.assertFalse(model_registry.ready('qwen21_turbo'))
            (folder / 'weights').write_bytes(b'123')
            marker.write_text('{"files":{"weights":3}}')
            self.assertTrue(model_registry.ready('qwen21_turbo'))
            marker.write_text('{"files":{"weights":4}}')
            self.assertFalse(model_registry.ready('qwen21_turbo'))

    def test_transformer_index_checks_payload_without_original_model(self):
        folder = self.root / 'transformer'
        folder.mkdir()
        (folder / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'weight': '0.safetensors'}}))
        header = json.dumps({'weight': {'dtype':'U8', 'shape':[2], 'data_offsets':[0,2]}}).encode()
        (folder / '0.safetensors').write_bytes(struct.pack('<Q',len(header))+header+b'12')
        self.assertTrue(model_integrity.validate_transformer_index(self.root))
        (folder / '0.safetensors').write_bytes(struct.pack('<Q',len(header))+header+b'1')
        with self.assertRaisesRegex(ValueError, '不完整'):
            model_integrity.validate_transformer_index(self.root)

    def test_relative_override_is_resolved_from_checkout(self):
        environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
            MLX_WORKBENCH_DATA_DIR='relative-data', MLX_WORKBENCH_MODEL_DIR='relative-models')
        result = subprocess.check_output([sys.executable, '-B', '-c',
            'import workbench_paths as p; print(p.DATA_DIR); print(p.MODEL_DIR)'],
            env=environment, cwd=self.root, text=True).splitlines()
        self.assertEqual(result, [str(ROOT / 'relative-data'), str(ROOT / 'relative-models')])


if __name__ == '__main__':
    unittest.main()
