"""Small AUTOMATIC1111-compatible surface for SillyTavern's built-in image source.

Generation stays in the workbench queue, so Tavern and the workbench cannot load
two models at once. This adapter deliberately exposes only the installed Turbo.
"""
import base64
import copy
import json
import secrets
import time

MODEL = 'Qwen-Image-2.1 Turbo MLX 8bit'


def get(path, engine):
    if path == '/sdapi/v1/options':
        return dict(sd_model_checkpoint=MODEL, sd_vae='Automatic', CLIP_stop_at_last_layers=1)
    if path == '/sdapi/v1/sd-models':
        return [dict(title=MODEL, model_name=MODEL, filename='Qwen-Image-2.1-Turbo-MLX-8bit')]
    if path == '/sdapi/v1/samplers':
        return [dict(name='Euler', aliases=['euler'], options={})]
    if path == '/sdapi/v1/schedulers':
        return [dict(name='Automatic', label='Turbo 8 steps')]
    if path in ('/sdapi/v1/sd-vae', '/sdapi/v1/sd-modules', '/sdapi/v1/latent-upscale-modes', '/sdapi/v1/loras'):
        return []
    if path == '/sdapi/v1/upscalers':
        return [dict(name='None')]
    if path == '/sdapi/v1/progress':
        with engine.job_lock:
            running = engine.job['state'] == 'running'
            return dict(progress=engine.job['progress']/100 if running else 0,
                        eta_relative=0, state=dict(job_count=int(running)))
    return None


def translate(data, engine):
    if not isinstance(data, dict):
        raise ValueError('请求格式不正确')
    engine.reject_adapters(data)
    if data.get('enable_hr') or data.get('init_images'):
        raise ValueError('酒馆入口暂只支持文生图，请关闭高清修复和参考图')
    if data.get('restore_faces') or data.get('alwayson_scripts'):
        raise ValueError('此 MLX 接口未接入面部修复或 ADetailer，请关闭这些选项')
    if data.get('batch_size', 1) != 1 or data.get('n_iter', 1) != 1:
        raise ValueError('酒馆入口每次生成一张')
    seed = data.get('seed', -1)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < -1:
        raise ValueError('种子需为 -1 或非负整数')
    seed = secrets.randbelow(1_000_000_000) if seed == -1 else seed % 1_000_000_000
    request = engine.validate_request(dict(prompt=data.get('prompt', ''),
        width=data.get('width', 768), height=data.get('height', 1024),
        count=1, seed=seed, models=[dict(id='qwen21_turbo', steps=8)]))
    request['source'] = 'sillytavern'
    return request


def generate(data, engine, timeout=900):
    request = translate(data, engine)
    with engine.job_lock:
        if not engine.start_job(request):
            return dict(error='工作台正在生成，请完成后再试'), 409
        group_id = engine.job['id']
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.job_lock:
            state = copy.deepcopy(engine.job) if engine.job['id'] == group_id else None
        if state is None:
            state = json.loads((engine.GROUPS / (group_id + '.json')).read_text())
        if state['state'] != 'running':
            break
        time.sleep(.25)
    else:
        with engine.job_lock:
            if engine.job['id'] == group_id:
                engine.cancel_job()
        return dict(error='生成超时，已停止此任务'), 504
    item = state['items'][0]
    if item['state'] != 'done':
        return dict(error=item.get('error') or '生成已停止'), 500
    image = (engine.OUTPUT / item['filename']).read_bytes()
    info = dict(prompt=item['effective_prompt'], negative_prompt='', seed=item['seed'],
                all_seeds=[item['seed']], width=request['width'], height=request['height'],
                steps=8, cfg_scale=1, sampler_name='Euler', sd_model_name=MODEL,
                group_id=group_id, backend='mlx', elapsed=item['elapsed'])
    return dict(images=[base64.b64encode(image).decode()], parameters=info,
                info=json.dumps(info, ensure_ascii=False)), 200
