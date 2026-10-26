#!/usr/bin/env python3
"""Local sequential MLX image comparison UI."""
import copy
import json
import math
import os
import random
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs
import psutil
from history_store import query_history, load_group, mutate_history, annotations
from model_registry import ROOT, MODELS, catalog, ready
from workbench_paths import DATA_DIR, MODEL_DIR, OUTPUT_DIR, LOG_DIR, tavern_enabled, is_local_origin
import sillytavern_api
import reference_images
import tavern_avatar_api
import tavern_prompt_rules
import tavern_diagnostics
import history_replay

OUTPUT = OUTPUT_DIR
GROUPS = OUTPUT / 'groups'
LOGS = LOG_DIR
PROMPT_FILE = DATA_DIR / 'prompt.txt'
DEFAULT_PROMPT = '一只赤狐站在雪地中，柔和的晨光，清晰的细节。'
HOST, PORT = '127.0.0.1', int(os.environ.get('MLX_WEB_PORT', '7866'))
job_lock = threading.RLock()
stop_event = threading.Event()
active_process = None
job = dict(state='idle', progress=0, elapsed=0, items=[], id=None, pid=None, mlx_peak_gb=None,
           swap_start_used=None, swap_start_out=None, swap_end_used=None, swap_end_out=None)


def memory_snapshot(state):
    physical, swap = psutil.virtual_memory(), psutil.swap_memory()
    rss = None
    if state.get('pid'):
        try:
            process = psutil.Process(state['pid'])
            rss = sum(p.memory_info().rss for p in [process, *process.children(recursive=True)])
        except psutil.Error:
            pass
    start_used, start_out = state.get('swap_start_used'), state.get('swap_start_out')
    used = state.get('swap_end_used') if state.get('swap_end_used') is not None else swap.used
    sout = state.get('swap_end_out') if state.get('swap_end_out') is not None else swap.sout
    return dict(total=physical.total, used=physical.total-physical.available, available=physical.available,
                process_rss=rss, swap_used=swap.used,
                swap_used_change=None if start_used is None else used-start_used,
                swap_written=None if start_out is None else max(0, sout-start_out))


def public_state():
    with job_lock:
        state = copy.deepcopy(job)
    if state['state'] == 'running':
        state['elapsed'] = round(time.monotonic()-state['started'], 1)
        for item in state['items']:
            if item['state'] == 'running':
                item['elapsed'] = round(time.monotonic()-item['started'], 1)
    records, photos = annotations(OUTPUT)
    state.update(records.get(state.get('id'), {}))
    for item in state['items']:
        item['liked'] = photos.get(item.get('filename'), False)
    state['memory'] = memory_snapshot(state)
    for key in ('pid', 'started', 'swap_start_used', 'swap_start_out', 'swap_end_used', 'swap_end_out'):
        state.pop(key, None)
    for item in state['items']:
        item.pop('started', None)
    return state


def persist():
    state = public_state()
    if not state.get('id'):
        return
    GROUPS.mkdir(parents=True, exist_ok=True)
    dest = GROUPS / (state['id']+'.json')
    temp = dest.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    temp.replace(dest)


def prompt_parts(template, name):
    """Parse non-nested {first|second} choices; line breaks around | are allowed."""
    if not isinstance(template, str) or len(template.strip()) > 30_000:
        raise ValueError(f'{name}模板最多 30000 字')
    parts = []
    offset = 0
    while offset < len(template):
        opening = template.find('{', offset)
        closing = template.find('}', offset)
        if closing >= 0 and (opening < 0 or closing < opening):
            raise ValueError(f'{name}大括号没有配对')
        if opening < 0:
            parts.append(template[offset:])
            break
        if opening > offset:
            parts.append(template[offset:opening])
        closing = template.find('}', opening + 1)
        if closing < 0 or '{' in template[opening + 1:closing]:
            raise ValueError(f'{name}大括号没有配对或存在嵌套')
        content = template[opening + 1:closing]
        if '|' in content:
            choices = tuple(value.strip() for value in content.split('|'))
            if any(not value for value in choices):
                raise ValueError(f'{name}随机选项不能为空')
            parts.append(choices)
        else:
            parts.append(template[opening:closing + 1])
        offset = closing + 1
    if sum(max(map(len, part)) if isinstance(part, tuple) else len(part)
           for part in parts) > 5000:
        raise ValueError(f'{name}单张展开后最多 5000 字')
    return parts


def choose_prompt(parts, rng=None):
    rng = rng or secrets.SystemRandom()
    return ''.join(rng.choice(part) if isinstance(part, tuple) else part
                   for part in parts).strip()


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError('请求格式不正确')
    reject_adapters(data)
    prompt = data.get('prompt', '')
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('提示词不能为空')
    prompt_parts(prompt, '提示词')
    negative_prompt = data.get('negative_prompt', '')
    prompt_parts(negative_prompt, '负向提示词')
    negative_guidance = data.get('negative_guidance', 2.0) if negative_prompt.strip() else 2.0
    if (isinstance(negative_guidance, bool) or not isinstance(negative_guidance, (int, float))
            or not math.isfinite(negative_guidance) or not 1.01 <= negative_guidance <= 10.0):
        raise ValueError('负向引导值需为 1.01～10')
    def integer(value, name, low, high):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'{name}需为 {low}～{high} 的整数')
        return value
    width = integer(data.get('width'), '宽度', 256, 2560)
    height = integer(data.get('height'), '高度', 256, 2560)
    if width % 16 or height % 16:
        raise ValueError('宽高需为 16 的倍数')
    count = integer(data.get('count', 1), '每模型张数', 1, 100)
    seed = data.get('seed')
    if seed in ('', None):
        seed = secrets.randbelow(1_000_000_000)
    elif isinstance(seed, str) and seed.isdecimal():
        seed = int(seed)
    seed = integer(seed, '种子', 0, 999_999_999)
    reference = data.get('reference')
    mode = data.get('mode', 'text')
    if mode not in ('text', 'reference'):
        raise ValueError('生成方式不正确')
    preserve_identity = data.get('preserve_identity', True)
    if not isinstance(preserve_identity, bool):
        raise ValueError('保留人物外貌设置不正确')
    if mode == 'reference':
        references = data.get('references', [reference])
        if (not isinstance(references, list) or not 1 <= len(references) <= 3
                or any(not isinstance(i, str) for i in references) or len(set(references)) != len(references)):
            raise ValueError('请为最多三名人物分别提供不同的参考图')
        for identifier in references:
            reference_images.resolve(identifier)
        reference = references[0]
        if width % 32 or height % 32:
            raise ValueError('参考图模式的宽高需为 32 的倍数')
        if count != 1:
            raise ValueError('参考图试用模式每次生成一张')
    elif reference:
        raise ValueError('请切换到人物参考模式')
    models = data.get('models')
    if mode == 'reference' and (not isinstance(models, list) or len(models) != 1
            or not isinstance(models[0], dict) or models[0].get('id') != 'qwen21_turbo_ref'):
        raise ValueError('参考图模式使用 Qwen Turbo · 人物参考')
    if mode == 'text' and isinstance(models, list) and any(
            isinstance(m, dict) and m.get('id') == 'qwen21_turbo_ref' for m in models):
        raise ValueError('人物参考模型需要参考图模式')
    if not isinstance(models, list) or not 1 <= len(models) <= len(MODELS):
        raise ValueError(f'请选择 1～{len(MODELS)} 个模型')
    seen, selected = set(), []
    for entry in models:
        if not isinstance(entry, dict) or entry.get('id') not in MODELS:
            raise ValueError('模型不存在')
        reject_adapters(entry)
        key = entry['id']
        if key in seen:
            raise ValueError('模型不能重复选择')
        seen.add(key)
        steps = integer(entry.get('steps'), '步数', 1, 80)
        if MODELS[key].get('fixed_steps') and steps != MODELS[key]['steps']:
            raise ValueError(MODELS[key]['name'] + ' 固定使用 8 步')
        limit = MODELS[key].get('max_dimension', 2560)
        if max(width, height) > limit:
            raise ValueError(MODELS[key]['name'] + f' 宽高最多 {limit}，建议先用 1024×1024')
        if not ready(key):
            raise ValueError(MODELS[key]['name']+' 尚未下载完整')
        selected.append(dict(id=key, steps=steps))
    result = dict(prompt=prompt.strip(), negative_prompt=negative_prompt.strip(),
                negative_guidance=float(negative_guidance), width=width, height=height,
                count=count, seed=seed, seed_input=data.get('seed') if data.get('seed') not in ('',None) else '', models=selected)
    if mode == 'reference':
        result.update(mode=mode, reference=reference, preserve_identity=preserve_identity)
        if len(references) > 1:
            result['references'] = references
        characters = data.get('reference_characters')
        if characters is not None:
            if (not isinstance(characters, list) or len(characters) != len(references)
                    or any(not isinstance(name, str) or not name.strip() or len(name) > 100 for name in characters)):
                raise ValueError('参考图与人物名称需要逐一对应')
            result['reference_characters'] = characters
    return result


def reject_adapters(data):
    if any(str(key).lower().startswith('lora') for key in data):
        raise ValueError('本公开版不支持 LoRA 参数')


def command_for(item, request):
    model = MODELS[item['model']]
    if item['model'] == 'qwen21_turbo_ref':
        render_width, render_height = request.get('reference_render_size', [request['width'], request['height']])
        return [str(ROOT/'.venv-reference/bin/python'), str(ROOT/'qwen21_reference_cli.py'),
                '--prompt', item['effective_prompt'], '--width', str(render_width),
                '--height', str(render_height), '--seed', str(item['seed']),
                '--reference', *[str(reference_images.resolve(i)) for i in request.get('references', [request['reference']])],
                *(['--comic-spec', json.dumps(request, ensure_ascii=False)]
                  if request.get('source') == 'sillytavern' and request.get('composition') == 'comic' else []),
                *(['--output-width', str(request['width']), '--output-height', str(request['height'])]
                  if 'reference_render_size' in request else []),
                '--output', str(OUTPUT/item['filename'])]
    program = ([str(ROOT / '.venv/bin/python'), str(ROOT / model['cli'])]
               if model['cli'].endswith('.py') else
               [str(ROOT / '.venv/bin' / model['cli'])])
    prompt = item.get('effective_prompt') or request['prompt']
    negative = (item.get('negative_prompt', request.get('negative_prompt', ''))
                if model['supports_negative'] else '')
    guidance = request.get('negative_guidance', 2.0) if negative else 1.0
    return [*program, '--model', str(MODEL_DIR / model['folder']),
            '--base-model', 'qwen-image-2.1' if item['model'] == 'qwen21_turbo' else model['base'],
            '--prompt', prompt, '--width', str(request['width']),
            '--height', str(request['height']), '--steps', str(item['steps']), '--seed', str(item['seed']),
            *(['--guidance', str(guidance)] if item['model'] != 'zimage' else []),
            *(['--negative-prompt', negative] if negative else []),
            '--low-ram',
            '--metadata', '--output', str(OUTPUT / item['filename'])]


def consume_line(line, item, index, total):
    match = re.search(r'(\d+)%', line)
    shot = re.fullmatch(r'Comic shot (\d+)/(\d+)', line.strip())
    peak = re.search(r'Peak MLX memory:\s*([\d.]+)\s*GB', line)
    with job_lock:
        if shot:
            item['comic_panel'], item['comic_panel_count'] = map(int, shot.groups())
        if match:
            percent = int(match.group(1))
            if item.get('comic_panel_count'):
                percent = round((item['comic_panel'] - 1 + percent / 100) / item['comic_panel_count'] * 100)
            item['progress'] = min(99, percent)
            job['progress'] = round((index+item['progress']/100)/total*100)
        if peak:
            item['mlx_peak_gb'] = float(peak.group(1))
            job['mlx_peak_gb'] = max(job['mlx_peak_gb'] or 0, item['mlx_peak_gb'])


def batch_items(index):
    """Only consecutive images with the same model can share weights."""
    first = job['items'][index]
    if first['model'] == 'qwen21_turbo_ref':
        return []
    items = []
    for item in job['items'][index:]:
        if item['model'] != first['model']:
            break
        items.append(item)
    return items if len(items) > 1 else []


def run_model_batch(items, request, offset):
    global active_process
    spec_path = LOGS / (items[0]['filename'] + '.batch.json')
    spec_path.write_text(json.dumps(dict(model=items[0]['model'],
        command=command_for(items[0], request),
        items=[dict(item, output=str(OUTPUT / item['filename'])) for item in items])))
    env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONUNBUFFERED='1')
    current = items[0]
    recent = ''
    try:
        with (LOGS / (items[0]['filename']+'.log')).open('w') as log:
            with subprocess.Popen([str(ROOT / '.venv/bin/python'), str(ROOT / 'batch_generate.py'),
                                   str(spec_path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1, start_new_session=True, env=env) as proc:
                with job_lock:
                    active_process = proc
                    job['pid'] = proc.pid
                    current.update(state='running', started=time.monotonic())
                    if stop_event.is_set():
                        proc.terminate()
                persist()
                line = ''
                while (char := proc.stdout.read(1)):
                    log.write(char)
                    if char not in '\r\n':
                        line += char
                        continue
                    if line.startswith('MLX_BATCH_EVENT '):
                        event = json.loads(line[len('MLX_BATCH_EVENT '):])
                        current = items[event['index']]
                        with job_lock:
                            if event['event'] == 'start':
                                current.update(state='running')
                                current.setdefault('started', time.monotonic())
                            elif event['event'] == 'done':
                                if not (OUTPUT / current['filename']).is_file():
                                    raise RuntimeError('批量生成未保存图片')
                                current.update(state='done', progress=100, image=current['filename'],
                                               mlx_peak_gb=event['peak_gb'])
                                # Include model loading in the first image's elapsed time.
                                current['elapsed'] = round(time.monotonic()-current['started'], 1)
                                job['progress'] = round((offset+event['index']+1)/len(job['items'])*100)
                            elif event['event'] == 'error':
                                current.update(state='error', error=event['error'])
                        persist()
                    else:
                        consume_line(line, current, offset+items.index(current), len(job['items']))
                        recent = (recent+line+'\n')[-4000:]
                    line = ''
                    log.flush()
                result = proc.wait()
                if result and not stop_event.is_set():
                    recent = recent[-1200:] or f'退出码 {result}'
    except Exception as exc:
        recent = str(exc)
    finally:
        with job_lock:
            for item in items:
                if item['state'] == 'running' or (stop_event.is_set() and item['state'] == 'queued'):
                    item.update(state='cancelled' if stop_event.is_set() else 'error',
                                error=None if stop_event.is_set() else recent or '批量生成提前结束')
                    if item.get('started'):
                        item['elapsed'] = round(time.monotonic()-item['started'], 1)
            active_process = None
            job['pid'] = None
        spec_path.unlink(missing_ok=True)
        persist()


def run_queue(request):
    global active_process
    try:
        completed_batch = set()
        for index, item in enumerate(job['items']):
            if index in completed_batch:
                continue
            if stop_event.is_set():
                break
            shared = batch_items(index)
            if shared:
                run_model_batch(shared, request, index)
                completed_batch.update(index+n for n, entry in enumerate(shared)
                                       if entry['state'] != 'queued')
                continue
            with job_lock:
                item.update(state='running', started=time.monotonic())
            persist()
            recent = ''
            try:
                env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONUNBUFFERED='1')
                with (LOGS / (item['filename']+'.log')).open('w') as log:
                    with subprocess.Popen(command_for(item, request), stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT, text=True, bufsize=1,
                                          start_new_session=True, env=env) as proc:
                        with job_lock:
                            active_process = proc
                            job['pid'] = proc.pid
                            if stop_event.is_set():
                                proc.terminate()
                        line = ''
                        while (char := proc.stdout.read(1)):
                            log.write(char)
                            if char in '\r\n':
                                consume_line(line, item, index, len(job['items']))
                                recent = (recent+line+'\n')[-4000:]
                                line = ''
                                log.flush()
                            else:
                                line += char
                        if line:
                            consume_line(line, item, index, len(job['items']))
                            recent += line
                        result = proc.wait()
                with job_lock:
                    if stop_event.is_set():
                        item.update(state='cancelled')
                    elif result == 0 and (OUTPUT / item['filename']).is_file():
                        item.update(state='done', progress=100, image=item['filename'])
                    else:
                        item.update(state='error', error=recent[-1200:] or f'退出码 {result}')
            except Exception as exc:
                with job_lock:
                    item.update(state='error', error=str(exc))
            finally:
                with job_lock:
                    active_process = None
                    job['pid'] = None
                    item['elapsed'] = round(time.monotonic()-item['started'], 1)
                    job['progress'] = round((index+1)/len(job['items'])*100)
                persist()
    finally:
        with job_lock:
            for item in job['items']:
                if item['state'] == 'queued':
                    item['state'] = 'cancelled'
            failures = sum(i['state'] == 'error' for i in job['items'])
            job['state'] = 'cancelled' if stop_event.is_set() else ('partial' if failures else 'done')
            job['elapsed'] = round(time.monotonic()-job['started'], 1)
            swap = psutil.swap_memory()
            job.update(pid=None, swap_end_used=swap.used, swap_end_out=swap.sout)
            # Persist while locked so a new job cannot replace this finished group.
            persist()


def start_job(request):
    with job_lock:
        if job['state'] == 'running':
            return False
        stop_event.clear()
        group_id = time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
        positive_parts = prompt_parts(request['prompt'], '提示词')
        negative_parts = prompt_parts(request.get('negative_prompt', ''), '负向提示词')
        # Keep the entered seed for image one; draw the remaining seeds randomly.
        # A fixed seed reproduces the batch, and model comparisons share its seeds.
        seed_rng = random.Random(request['seed'])
        image_seeds = [request['seed']]
        while len(image_seeds) < request['count']:
            candidate = seed_rng.randrange(1_000_000_000)
            if candidate not in image_seeds:
                image_seeds.append(candidate)
        selected_prompts = []
        for n in range(request['count']):
            rng = random.Random(image_seeds[n])
            selected_prompts.append((choose_prompt(positive_parts, rng),
                                     choose_prompt(negative_parts, rng)))
        items = []
        for model in request['models']:
            for n in range(request['count']):
                filename = f'{group_id}-{model["id"]}-{n+1}.png'
                positive, negative = selected_prompts[n]
                if model['id'] == 'qwen21_turbo_ref' and request.get('preserve_identity', True):
                    references = request.get('references', [request['reference']])
                    if len(references) > 1:
                        names = request.get('reference_characters', [f'人物{i+1}' for i in range(len(references))])
                        mapping = '，'.join(f'参考图{i+1}对应{name}' for i, name in enumerate(names))
                        positive = (mapping + f'，是{len(references)}位不同人物。'
                                    '分别保留各自的脸型、五官和可辨识特征，不要混用、融合或交换各人的面部。'+positive)
                    elif request.get('source') == 'sillytavern' and request.get('reference_characters'):
                        positive = (f'参考图1只约束{request["reference_characters"][0]}的外貌，保留其脸型、五官和可辨识特征。'
                                    '人物姿态、场景和镜头构图采用当前描述。'+positive)
                    else:
                        positive = ('以参考图中的人物为同一位主角，保留其面部轮廓、五官比例、眼睛、鼻子、嘴和可辨识特征，'
                                    '不要更换人物身份。根据以下要求改变画面：'+positive)
                    positive += '\n\n' + tavern_prompt_rules.REFERENCE_IDENTITY_RULE
                positive = tavern_prompt_rules.append(positive, request)
                items.append(dict(model=model['id'], name=MODELS[model['id']]['name'], steps=model['steps'],
                                  effective_prompt=positive,
                                  requested_negative_prompt=negative,
                                  negative_prompt=negative if MODELS[model['id']]['supports_negative'] else '',
                                  guidance=(0.0 if model['id'] == 'zimage' else 1.0
                                            if model['id'] in ('qwen21_turbo', 'qwen21_turbo_ref') else
                                            request.get('negative_guidance', 2.0)
                                            if negative else 1.0),
                                  seed=image_seeds[n], filename=filename, image=None,
                                  state='queued', progress=0, elapsed=0, error=None, mlx_peak_gb=None))
                if (model['id'] == 'qwen21_turbo_ref' and request.get('source') == 'sillytavern'
                        and request.get('composition') == 'comic'):
                    import comic_render
                    shots = comic_render.shot_jobs(request, request.get('references', [request['reference']]))
                    items[-1]['comic_render_mode'] = 'isolated_panels'
                    items[-1]['effective_prompt'] = '\n\n'.join(
                        f'第{shot["index"] + 1}格（独立绘制，参考人物：' +
                        ('、'.join(shot['reference_characters']) or '无面部参考') + '）：\n' + shot['prompt']
                        for shot in shots)
        swap = psutil.swap_memory()
        job.clear()
        job.update(state='running', id=group_id, created_at=time.time(), started=time.monotonic(), progress=0, elapsed=0,
                   prompt=request['prompt'], negative_prompt=request.get('negative_prompt', ''),
                   width=request['width'], height=request['height'], items=items, options=copy.deepcopy(request),
                   pid=None, mlx_peak_gb=None, swap_start_used=swap.used, swap_start_out=swap.sout,
                   swap_end_used=None, swap_end_out=None)
        persist()
        threading.Thread(target=run_queue, args=(request,), daemon=True).start()
    return True


def cancel_job():
    with job_lock:
        if job['state'] != 'running':
            return
        stop_event.set()
        proc = active_process
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        def ensure_stopped():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        threading.Thread(target=ensure_stopped, daemon=True).start()


def default_prompt():
    try:
        return PROMPT_FILE.read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError):
        return DEFAULT_PROMPT


def is_tavern_route(path):
    return (path.startswith('/sdapi/') or path.startswith('/api/tavern/')
            or path.startswith('/history/')
            or path in ('/system_stats', '/object_info', '/history', '/view', '/prompt', '/interrupt'))


class Handler(BaseHTTPRequestHandler):
    def valid_host(self):
        # Binding loopback alone does not prevent browser DNS rebinding.
        host = self.headers.get('Host', '')
        return host in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def log_message(self, _format, *_args):
        pass

    def send_bytes(self, data, content_type, status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        if urlparse(self.path).path in (tavern_diagnostics.ROUTE, '/api/health'):
            origin = self.headers.get('Origin')
            if is_local_origin(origin):
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, value, status=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8', status)

    def do_GET(self):
        if not self.valid_host():
            return self.send_json(dict(error='请求主机不允许'), 403)
        path = urlparse(self.path).path
        if is_tavern_route(path) and not tavern_enabled():
            return self.send_json(dict(error='酒馆支持尚未启用，请重新运行安装器并选择酒馆组件'), 403)
        if path == '/api/health':
            origin = self.headers.get('Origin')
            if origin and not is_local_origin(origin):
                return self.send_json(dict(error='请求来源不允许'), 403)
            return self.send_json(dict(app='mlx-image-workbench', service='mlx-image-workbench',
                version='0.1.0', root=str(ROOT), data_dir=str(DATA_DIR), model_dir=str(MODEL_DIR), port=PORT,
                tavern_enabled=tavern_enabled(), models=catalog(), reference_ready=ready('qwen21_turbo_ref')))
        if path == tavern_diagnostics.ROUTE:
            origin = self.headers.get('Origin')
            if origin and not is_local_origin(origin):
                return self.send_json(dict(error='请求来源不允许'), 403)
            try:
                value = parse_qs(urlparse(self.path).query).get('id', [None])[0]
                return self.send_bytes(tavern_diagnostics.serialize(tavern_diagnostics.read(LOGS/'tavern-plans', value)),
                                       'application/json; charset=utf-8')
            except (ValueError, FileNotFoundError) as exc:
                return self.send_json(dict(error=str(exc)), 404)
        if path == '/system_stats':
            return self.send_json(dict(system=dict(os='darwin', comfyui_version='MLX avatar adapter'), devices=[]))
        if path == '/object_info':
            return self.send_json(tavern_avatar_api.object_info())
        if path == '/history' or path.startswith('/history/'):
            records = tavern_avatar_api.history(sys.modules[__name__])
            if path != '/history':
                identifier = path.removeprefix('/history/')
                records = {identifier: records[identifier]} if identifier in records else {}
            return self.send_json(records)
        if path == '/view':
            name = parse_qs(urlparse(self.path).query).get('filename', [''])[0]
            if Path(name).name != name or not name.endswith('.png') or not (OUTPUT/name).is_file():
                return self.send_json(dict(error='图片不存在'), 404)
            return self.send_bytes((OUTPUT/name).read_bytes(), 'image/png')
        if path.startswith('/sdapi/'):
            result = sillytavern_api.get(path, sys.modules[__name__])
            return self.send_json(result if result is not None else dict(error='接口不存在'),
                                  200 if result is not None else 404)
        if path == '/':
            return self.send_bytes((ROOT/'web_ui.html').read_bytes(), 'text/html; charset=utf-8')
        if path == '/prompt-hover.mjs':
            return self.send_bytes((ROOT/'tavern-extension/prompt-hover.mjs').read_bytes(), 'text/javascript; charset=utf-8')
        if path == '/api/config':
            return self.send_json(dict(prompt=default_prompt(), models=catalog(),
                                       reference=dict(ready=ready('qwen21_turbo_ref'), max_dimension=1536),
                                       tavern=dict(enabled=tavern_enabled(), url=f'http://{HOST}:{PORT}')))
        if path.startswith('/references/'):
            try:
                return self.send_bytes(reference_images.resolve(path[len('/references/'):]).read_bytes(), 'image/png')
            except ValueError as exc:
                return self.send_json(dict(error=str(exc)), 404)
        if path == '/api/status':
            return self.send_json(public_state())
        if path == '/api/history':
            try:
                return self.send_json(query_history(GROUPS, OUTPUT,
                    parse_qs(urlparse(self.path).query), job.get('id')))
            except ValueError as exc:
                return self.send_json(dict(error=str(exc)), 400)
        if path == '/api/history/group':
            group_id = parse_qs(urlparse(self.path).query).get('id', [''])[0]
            group = load_group(GROUPS, OUTPUT, group_id, job.get('id'))
            return self.send_json(group if group else dict(error='记录不存在'), 200 if group else 404)
        if path in ('/history_ui.js', '/history_ui.css', '/reference_ui.js'):
            return self.send_bytes((ROOT/path[1:]).read_bytes(), 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
        if path.startswith('/images/'):
            name = unquote(path[len('/images/'):])
            if Path(name).name != name or not name.endswith('.png'):
                return self.send_json(dict(error='无效图片路径'), 400)
            image = OUTPUT / name
            if not image.is_file():
                return self.send_json(dict(error='图片不存在'), 404)
            return self.send_bytes(image.read_bytes(), 'image/png')
        return self.send_json(dict(error='页面不存在'), 404)

    def do_OPTIONS(self):
        path = urlparse(self.path).path
        if (not self.valid_host() or path not in (tavern_diagnostics.ROUTE, '/api/health')
                or not is_local_origin(self.headers.get('Origin'))
                or (path == tavern_diagnostics.ROUTE and not tavern_enabled())
                or self.headers.get('Access-Control-Request-Method') not in ('POST', 'GET')):
            return self.send_json(dict(error='请求来源或方法不允许'), 403)
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
        self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        # Reject cross-origin browser submissions to the local generation endpoint.
        if not self.valid_host():
            return self.send_json(dict(error='请求主机不允许'), 403)
        path = urlparse(self.path).path
        if is_tavern_route(path) and not tavern_enabled():
            return self.send_json(dict(error='酒馆支持尚未启用，请重新运行安装器并选择酒馆组件'), 403)
        origin = self.headers.get('Origin')
        if path == tavern_diagnostics.ROUTE:
            if origin and not is_local_origin(origin):
                return self.send_json(dict(error='请求来源不允许'), 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= tavern_diagnostics.LIMIT:
                    raise ValueError('分镜诊断大小不正确')
                data = json.loads(self.rfile.read(length))
                return self.send_json(tavern_diagnostics.save(LOGS/'tavern-plans', data))
            except (ValueError, TypeError, OSError) as exc:
                return self.send_json(dict(error=str(exc)), 400)
        if origin and origin not in (f'http://{HOST}:{PORT}', f'http://localhost:{PORT}'):
            return self.send_json(dict(error='请求来源不允许'), 403)
        path = urlparse(self.path).path
        if path in ('/prompt', '/interrupt'):
            try:
                if path == '/interrupt':
                    with job_lock:
                        if job.get('options', {}).get('integration') == 'comfy_avatar':
                            cancel_job()
                    return self.send_json({})
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 43_000_000:
                    raise ValueError('角色头像每张最多 10 MB，最多三张')
                result, status = tavern_avatar_api.submit(json.loads(self.rfile.read(length)), sys.modules[__name__])
                return self.send_json(result, status)
            except (ValueError, TypeError, OSError) as exc:
                return self.send_json(dict(error=str(exc)), 400)
        if path == '/api/reference/upload':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 14_000_000:
                    raise ValueError('参考图最多 10 MB')
                result = reference_images.upload(json.loads(self.rfile.read(length)))
                return self.send_json(result)
            except (ValueError, TypeError, OSError) as exc:
                return self.send_json(dict(error=str(exc)), 400)
        if path.startswith('/sdapi/'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 100_000:
                    raise ValueError('请求大小不正确')
                data = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(data, dict):
                    raise ValueError('请求格式不正确')
                reject_adapters(data)
                if path == '/sdapi/v1/options':
                    if data.get('sd_model_checkpoint', sillytavern_api.MODEL) != sillytavern_api.MODEL:
                        raise ValueError('酒馆入口仅提供 Qwen Turbo MLX')
                    return self.send_json({})
                if path == '/sdapi/v1/interrupt':
                    with job_lock:
                        if job.get('options', {}).get('source') == 'sillytavern':
                            cancel_job()
                    return self.send_json({})
                if path == '/sdapi/v1/txt2img':
                    result, status = sillytavern_api.generate(data, sys.modules[__name__])
                    return self.send_json(result, status)
                return self.send_json(dict(error='接口不存在'), 404)
            except (ValueError, TypeError, OSError) as exc:
                return self.send_json(dict(error=str(exc)), 400)
        if path == '/api/cancel':
            cancel_job()
            return self.send_json(dict(ok=True))
        if path == '/api/history/action':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 10000:
                    raise ValueError('请求大小不正确')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('请求格式不正确')
                with job_lock:
                    active = job.get('id') if job['state']=='running' else None
                    result = mutate_history(GROUPS, OUTPUT, LOGS, data, active)
                    if data.get('action') in ('delete_record','delete_photo') and data.get('id')==job.get('id'):
                        # Prevent status polling from resurrecting a removed photo/record.
                        job.update(state='idle', id=None, items=[], progress=0)
                return self.send_json(result)
            except (ValueError, TypeError, OSError) as exc:
                return self.send_json(dict(error=str(exc)), 400)
        if path != '/api/generate':
            return self.send_json(dict(error='接口不存在'), 404)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 100_000:
                raise ValueError('请求大小不正确')
            data = json.loads(self.rfile.read(length))
            if isinstance(data, dict):
                reject_adapters(data)
            request = (history_replay.prepare(data, sys.modules[__name__])
                       if isinstance(data, dict) and 'history_replay_id' in data else validate_request(data))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            return self.send_json(dict(error=str(exc)), 400)
        if not start_job(request):
            return self.send_json(dict(error='上一组还在生成，请稍候'), 409)
        self.send_json(dict(ok=True, id=job['id']), 202)


if __name__ == '__main__':
    for folder in (OUTPUT, GROUPS, LOGS):
        folder.mkdir(parents=True, exist_ok=True)
    def stop_server(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f'MLX 多模型文生图：http://{HOST}:{PORT}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cancel_job()
        server.server_close()
