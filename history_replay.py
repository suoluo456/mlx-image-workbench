"""Restore reference jobs from saved records without dropping per-person data."""
import base64
import copy

import reference_images
import tavern_avatar_api
from history_store import load_group


def prepare(data, engine):
    identifier = data.get('history_replay_id')
    if not isinstance(identifier, str):
        raise ValueError('历史重跑记录无效')
    group = load_group(engine.GROUPS, engine.OUTPUT, identifier, engine.job.get('id'))
    saved = group.get('replay') if group else None
    if not isinstance(saved, dict) or saved.get('mode') != 'reference':
        raise ValueError('找不到原来的参考图生成设置，请重新选择历史记录')
    saved = copy.deepcopy(saved)
    references = saved.get('original_references') or saved.get('references') or [saved.get('reference')]
    if not isinstance(references, list) or not 1 <= len(references) <= 3:
        raise ValueError('原记录的参考图信息不完整')
    paths = [reference_images.resolve(identifier) for identifier in references]
    # These are the controls the workbench exposes. Identity, roles, panels,
    # gaze and style are always recovered from the record, never from the UI.
    for key in ('prompt', 'width', 'height', 'seed'):
        if key in data:
            saved[key] = data[key]
    if saved.get('source') == 'sillytavern':
        seed = saved.get('seed')
        if seed in ('', None):
            seed = -1
        elif isinstance(seed, str) and seed.isdecimal():
            seed = int(seed)
        values = {key:saved[key] for key in (
            'prompt','width','height','render_style','composition','protagonist','protagonist_present',
            'scene_type','panels','expression_mode','sequence_mode','gaze_mode') if key in saved}
        values.update(avatars=[base64.b64encode(path.read_bytes()).decode('ascii') for path in paths],
            characters=saved.get('reference_characters', []),
            reference_roles=saved.get('reference_roles', ['character'] * len(paths)),
            render_mode='reference', seed=seed)
        if saved.get('composition') == 'comic':
            # In replay mode the visible prompt is the common scene, while
            # the original panel actions and independent identities stay saved.
            values['scene_context'] = data.get('prompt', saved.get('scene_context', saved.get('prompt', '')))
        result = tavern_avatar_api.request_for_values(values, engine)
    else:
        saved.update(reference=references[0], references=references)
        result = engine.validate_request(saved)
    result['replay_of'] = identifier
    return result
