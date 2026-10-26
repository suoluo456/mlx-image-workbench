"""Minimal Comfy-compatible transport for ST's native %char_avatar% substitution.

Only our single MLXAvatarTurbo node is accepted; this does not run Comfy graphs.
"""
import copy
import json
from pathlib import Path

import reference_images
import portrait_reference
import comic_storyboard
import tavern_render_options
from sillytavern_api import MODEL

WORKFLOW = 'MLX_Workbench_0.1.0.json'


def object_info():
    return {
        'KSampler': {'input': {'required': {'sampler_name': [['Euler']], 'scheduler': [['Automatic']]}}},
        'CheckpointLoaderSimple': {'input': {'required': {'ckpt_name': [[MODEL+'.safetensors']]}}},
        'UNETLoader': {'input': {'required': {'unet_name': [[]]}}},
        'VAELoader': {'input': {'required': {'vae_name': [['Automatic']]}}},
        'MLXAvatarTurbo': {'input': {'required': {'prompt': ['STRING'], 'avatar': ['STRING']}}},
    }


def ids(engine):
    if not hasattr(engine, 'comfy_avatar_ids'):
        engine.comfy_avatar_ids = []
        for path in sorted(engine.GROUPS.glob('*.json'), key=lambda p: p.stat().st_mtime)[-64:]:
            try:
                if json.loads(path.read_text()).get('options', {}).get('integration') == 'comfy_avatar':
                    engine.comfy_avatar_ids.append(path.stem)
            except (OSError, ValueError):
                pass
        engine.comfy_avatar_ids = engine.comfy_avatar_ids[-8:]
    return engine.comfy_avatar_ids


def submit(data, engine):
    graph = data.get('prompt') if isinstance(data, dict) else None
    if not isinstance(graph, dict) or len(graph) != 1:
        raise ValueError('请选择 MLX Workbench 工作流')
    node = next(iter(graph.values()))
    if not isinstance(node, dict) or node.get('class_type') != 'MLXAvatarTurbo':
        raise ValueError('此接口仅支持 MLX Workbench 工作流')
    values = node.get('inputs', {})
    if not isinstance(values, dict):
        raise ValueError('工作流参数无效')
    request = request_for_values(values, engine)
    with engine.job_lock:
        if not engine.start_job(request):
            return dict(error='工作台正在生成，请完成后再试'), 409
        identifier = engine.job['id']
        known = ids(engine)
        if identifier not in known:
            known.append(identifier)
        engine.comfy_avatar_ids = known[-8:]
    return dict(prompt_id=identifier, number=0, node_errors={}), 200


def request_for_values(values, engine):
    if not isinstance(values, dict):
        raise ValueError('工作流参数无效')
    engine.reject_adapters(values)
    render_style = tavern_render_options.checked_style(values.get('render_style', 'default'))
    avatars, names = values.get('avatars'), values.get('characters')
    render_mode = values.get('render_mode', 'reference')
    if render_mode not in ('reference', 'text'):
        raise ValueError('生成方式无效')
    if (not isinstance(avatars, list) or not isinstance(names, list) or len(names) != len(avatars)
            or (render_mode == 'reference' and not 1 <= len(avatars) <= 3)
            or (render_mode == 'text' and len(avatars) != 0)):
        raise ValueError('人物参考最多两位聊天人物加主角头像；无头像时须使用文生图方式')
    roles = values.get('reference_roles', ['character'] * len(names))
    if (not isinstance(roles, list) or len(roles) != len(names)
            or any(role not in ('character', 'protagonist') for role in roles)
            or roles.count('character') > 2 or roles.count('protagonist') > 1
            or any(not isinstance(name, str) or not name.strip() or len(name) > 100 for name in names)
            or len(set(names)) != len(names)):
        raise ValueError('头像角色与姓名需逐一对应，最多两位聊天人物和一位主角')
    women = [name for name, role in zip(names, roles) if role == 'character']
    composition = values.get('composition', 'default')
    protagonist = values.get('protagonist', '')
    if (composition not in ('default', 'interaction', 'dialogue_pov', 'comic') or not isinstance(protagonist, str)
            or len(protagonist) > 100 or (composition in ('interaction', 'dialogue_pov') and (len(women) != 1 or not protagonist.strip()))):
        raise ValueError('互动构图需一位人物头像和明确的主角名称')
    main = next((i for i, role in enumerate(roles) if role == 'protagonist'), None)
    if main is not None and (names[main] != protagonist.strip() or
            not (values.get('protagonist_present') is True or composition == 'interaction')):
        raise ValueError('主角头像必须对应本次实际入镜的主角')
    # A persona without an avatar remains drawable from the story text. Never
    # substitute another character's face for the protagonist.
    comic = comic_storyboard.validate(values, women, protagonist) if composition == 'comic' else {}
    if composition == 'comic' and 'scene_context' in values:
        context = values['scene_context']
        if not isinstance(context, str) or not context.strip() or len(context) > 3000:
            raise ValueError('漫画共同场景无效')
        comic['scene_context'] = context.strip()
    references = [reference_images.upload(dict(image=image)) for image in avatars]
    if any(min(r['width'], r['height']) < 64 for r in references):
        raise ValueError('人物头像不可用，请先为该人物设置清晰头像')
    original_references = [r['id'] for r in references]
    if composition in ('dialogue_pov', 'comic') or main is not None:
        references = [portrait_reference.prepare(r) for r in references]
    width, height = values.get('width', 1024), values.get('height', 576)
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 256 or n > 2560 for n in (width, height)):
        raise ValueError('画布宽高需在 256～2560 内')
    # Tavern offers some sizes that are 16-aligned. Preserve their intent while
    # satisfying the edit model's 32-pixel constraint.
    width, height = (max(256, round(n/32)*32) for n in (width, height))
    seed = values.get('seed', -1)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < -1:
        raise ValueError('种子需为 -1 或非负整数')
    render_width, render_height = tavern_render_options.reference_size(width, height) if references else (width, height)
    arguments = dict(prompt=values.get('prompt', ''), width=render_width, height=render_height,
        count=1, seed='' if seed == -1 else seed % 1_000_000_000,
        models=[dict(id='qwen21_turbo_ref' if references else 'qwen21_turbo', steps=8)])
    if references:
        arguments.update(mode='reference', references=[r['id'] for r in references],
                         reference_characters=names, preserve_identity=True)
    request = engine.validate_request(arguments)
    request.update(source='sillytavern', integration='comfy_avatar', width=width, height=height,
                   render_style=render_style, reference_characters=names,
                   reference_roles=roles, composition=composition, protagonist=protagonist.strip(), **comic)
    if references and composition != 'comic' and (render_width, render_height) != (width, height):
        request['reference_render_size'] = [render_width, render_height]
    if main is not None:
        request['protagonist_reference_index'] = main + 1
    if [r['id'] for r in references] != original_references:
        request['original_references'] = original_references
    return request


def history(engine):
    result = {}
    for identifier in ids(engine):
        with engine.job_lock:
            group = copy.deepcopy(engine.job) if engine.job.get('id') == identifier else None
        if group is None:
            group = engine.load_group(engine.GROUPS, engine.OUTPUT, identifier, engine.job.get('id'))
        if not group or group['state'] == 'running':
            continue
        item = group['items'][0]
        ok = item['state'] == 'done'
        error = item.get('error') or '生成已停止'
        result[identifier] = dict(outputs={'1': dict(images=[dict(filename=item['filename'],
            subfolder='', type='output')])} if ok else {},
            status=dict(status_str='success' if ok else 'error', completed=True,
                messages=[] if ok else [['execution_error', dict(node_type='MLXAvatarTurbo', node_id='1',
                    exception_type='GenerationError', exception_message=error)]]))
    return result


def workflow():
    return {'1': dict(class_type='MLXAvatarTurbo', inputs=dict(prompt='%prompt%', avatars=[], characters=[], render_mode='text',
                    width='%width%', height='%height%', seed='%seed%'))}
