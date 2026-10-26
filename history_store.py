"""Persistent generation history, annotations, filtering and scoped deletion."""
import copy
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from model_registry import MODELS


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)


def annotations(output):
    path = output / 'history.sqlite'
    if not path.exists():
        return {}, {}
    with sqlite3.connect(path) as db:
        groups = {i: dict(title=t, liked=bool(l)) for i,t,l in db.execute('SELECT id,title,liked FROM records')}
        images = {i: bool(l) for i,l in db.execute('SELECT filename,liked FROM photos')}
    return groups, images


def database(output):
    db = sqlite3.connect(output / 'history.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT "", liked INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS photos (filename TEXT PRIMARY KEY, liked INTEGER NOT NULL DEFAULT 0)')
    return db


def timestamp(record, path):
    if isinstance(record.get('created_at'), (float, int)):
        return record['created_at']
    try:
        return datetime.strptime(record['id'][:15], '%Y%m%d-%H%M%S').timestamp()
    except (KeyError, ValueError, TypeError):
        return path.stat().st_mtime


def legacy_group(path):
    meta = read_json(path.with_suffix('.metadata.json')) or {}
    identifier = str(meta.get('base_model', ''))+' '+str(meta.get('model', ''))
    model = meta.get('model_id')
    if model not in MODELS:
        model = next((k for k,v in sorted(MODELS.items(), key=lambda pair: len(pair[1]['base']), reverse=True)
                      if v['base'] in identifier), 'legacy')
    item = dict(model=model, name=MODELS[model]['name'] if model in MODELS else str(meta.get('model') or '旧版图片'),
                steps=meta.get('steps', '—'), seed=meta.get('seed', '—'),
                elapsed=meta.get('generation_time_seconds', 0) or 0,
                image=path.name, filename=path.name, state='done',
                effective_prompt=meta.get('prompt', ''), negative_prompt=meta.get('negative_prompt', ''),
                guidance=meta.get('guidance', 1))
    return dict(id='legacy:'+path.name, created_at=path.stat().st_mtime, state='done',
                prompt=meta.get('prompt') or '', negative_prompt=meta.get('negative_prompt') or '',
                width=meta.get('width', '—'), height=meta.get('height', '—'),
                elapsed=item['elapsed'], items=[item], legacy=True)


def replay_options(group):
    if isinstance(group.get('options'), dict):
        return copy.deepcopy(group['options'])
    chosen = {}
    for item in group['items']:
        key = item.get('model')
        if key in MODELS and key not in chosen:
            chosen[key] = dict(id=key, steps=item.get('steps', MODELS[key]['steps']))
    return dict(prompt=group.get('prompt', ''), negative_prompt=group.get('negative_prompt', ''),
                negative_guidance=next((i.get('guidance') for i in group['items'] if (i.get('guidance') or 0)>1), 2),
                width=group.get('width'), height=group.get('height'),
                count=max([sum(i.get('model')==key for i in group['items']) for key in chosen] or [1]),
                seed=next((i.get('seed') for i in group['items']), ''), models=list(chosen.values()), inferred=True)


def load_group(groups, output, group_id, active_id=None, tags=None):
    if group_id.startswith('legacy:'):
        name = group_id[7:]
        if Path(name).name != name or not name.endswith('.png'):
            return None
        path = output / name
        group = legacy_group(path) if path.is_file() else None
    else:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', group_id):
            return None
        path = groups / (group_id+'.json')
        group = read_json(path)
        if group and isinstance(group.get('items'), list):
            group['created_at'] = timestamp(group, path)
        else:
            return None
    if not group:
        return None
    if group.get('state') == 'running' and group_id != active_id:
        group['state'] = 'interrupted'
        for item in group['items']:
            if item.get('state') in ('queued', 'running'):
                item['state'] = 'cancelled'
    records, photos = annotations(output) if tags is None else tags
    group.update(records.get(group_id, dict(title='', liked=False)))
    for item in group['items']:
        item['liked'] = photos.get(item.get('filename') or item.get('image'), False)
    group['replay'] = replay_options(group)
    return group


def query_history(groups, output, params, active_id=None):
    def number(key, default):
        try:
            return int(params.get(key, [default])[0])
        except (ValueError, TypeError):
            raise ValueError('历史筛选参数无效')
    start, end = number('start', 0), number('end', 999999999999)
    if start > end:
        raise ValueError('开始时间不能晚于结束时间')
    page, limit = max(1, number('page', 1)), min(500, max(1, number('limit', 500)))
    keyword = str(params.get('q', [''])[0]).strip().casefold()
    group_like, photo_like = number('record_like', 0), number('photo_like', 0)
    gallery = params.get('view', ['records'])[0] == 'gallery'
    records, known_images = [], set()
    tags = annotations(output)
    for path in groups.glob('*.json'):
        group = load_group(groups, output, path.stem, active_id, tags)
        if group:
            records.append(group)
            known_images.update(i.get('filename') or i.get('image') for i in group['items'])
    for path in output.glob('*.png'):
        if path.name not in known_images:
            records.append(load_group(groups, output, 'legacy:'+path.name, active_id, tags))
    all_total = len(records)
    filtered = []
    for group in records:
        if not start <= group['created_at'] <= end or group_like and not group['liked']:
            continue
        visible = [i for i in group['items'] if not i.get('deleted')]
        texts = [group['title'], group.get('prompt', ''), group.get('negative_prompt', '')]
        for item in visible:
            texts.extend([item.get('effective_prompt', ''), item.get('negative_prompt', '')])
        if keyword and not any(keyword in str(t).casefold() for t in texts):
            continue
        photos = [i for i in visible if i.get('image') and (output / i['image']).is_file()]
        if photo_like:
            photos = [i for i in photos if i['liked']]
            if not photos:
                continue
        if gallery:
            for item in photos:
                filtered.append(dict(group_id=group['id'], group_title=group['title'],
                    group_liked=group['liked'], created_at=group['created_at'],
                    filename=item['image'], liked=item['liked'], model=item.get('name'),
                    width=group.get('width'), height=group.get('height')))
        else:
            filtered.append(dict(id=group['id'], created_at=group['created_at'], title=group['title'], liked=group['liked'],
                prompt_excerpt=' '.join(str(group.get('prompt', '')).split())[:150],
                state=group.get('state', 'done'), legacy=group.get('legacy', False),
                count=len(visible), done=sum(i.get('state')=='done' for i in visible),
                elapsed=group.get('elapsed', 0), width=group.get('width'), height=group.get('height'),
                models=list(dict.fromkeys(str(i.get('name', '')) for i in visible))))
    filtered.sort(key=lambda g: (g['created_at'], g.get('id') or g['filename']), reverse=True)
    total = len(filtered)
    pages = max(1, (total+limit-1)//limit)
    page = min(page, pages)
    offset = min(total, max(0, number('offset', (page-1)*limit)))
    batch = filtered[offset:offset+limit]
    next_offset = offset+len(batch)
    return dict(groups=[] if gallery else batch, photos=batch if gallery else [],
                total=total, all_total=all_total, page=page, pages=pages,
                next_offset=next_offset, has_more=next_offset<total)


def mutate_history(groups, output, logs, data, active_id=None):
    group_id = data.get('id')
    if not isinstance(group_id, str):
        raise ValueError('无效记录')
    group = load_group(groups, output, group_id, active_id)
    if not group:
        raise ValueError('记录不存在')
    action = data.get('action')
    filename = data.get('filename')
    item = None
    if filename is not None:
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith('.png'):
            raise ValueError('无效图片')
        item = next((i for i in group['items'] if (i.get('filename') or i.get('image'))==filename and not i.get('deleted')), None)
        if not item:
            raise ValueError('图片不属于此记录')
    if action in ('like_record', 'like_photo'):
        if not isinstance(data.get('liked'), bool):
            raise ValueError('无效收藏值')
        with database(output) as db:
            if action == 'like_record':
                db.execute('INSERT INTO records(id,liked) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET liked=excluded.liked', (group_id,int(data['liked'])))
            elif item and item.get('image') and (output/item['image']).is_file():
                db.execute('INSERT INTO photos(filename,liked) VALUES (?,?) ON CONFLICT(filename) DO UPDATE SET liked=excluded.liked', (filename,int(data['liked'])))
            else:
                raise ValueError('图片尚未生成或已删除')
    elif action == 'rename':
        title = data.get('title')
        if not isinstance(title, str) or len(title.strip())>100:
            raise ValueError('名称最多 100 字')
        with database(output) as db:
            db.execute('INSERT INTO records(id,title) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title', (group_id,title.strip()))
    elif action in ('delete_record', 'delete_photo'):
        if data.get('confirm') is not True:
            raise ValueError('请确认永久删除')
        if group_id == active_id:
            raise ValueError('此组正在生成，请结束后删除')
        if action == 'delete_photo' and not item:
            raise ValueError('请选择图片')
        targets = group['items'] if action=='delete_record' else [item]
        # Validate every target before touching files; never allow paths outside output/logs.
        for target in targets:
            name = target.get('filename') or target.get('image')
            if name and (Path(name).name != name or not name.endswith('.png')):
                raise ValueError('记录图片路径无效')
        for target in targets:
            name = target.get('filename') or target.get('image')
            if name:
                for path in (output/name, (output/name).with_suffix('.metadata.json'), logs/(name+'.log')):
                    path.unlink(missing_ok=True)
                with database(output) as db:
                    db.execute('DELETE FROM photos WHERE filename=?', (name,))
            target.update(deleted=True, image=None, state='deleted')
        if action=='delete_record' or group.get('legacy'):
            if not group.get('legacy'):
                (groups/(group_id+'.json')).unlink(missing_ok=True)
            with database(output) as db:
                db.execute('DELETE FROM records WHERE id=?', (group_id,))
        else:
            # Store the original replay options before removing image-specific metadata.
            group['options'] = group['replay']
            for target in targets:
                for key in ('effective_prompt','negative_prompt','requested_negative_prompt','error'):
                    target.pop(key,None)
            for key in ('replay','title','liked'):
                group.pop(key,None)
            write_json(groups/(group_id+'.json'), group)
    else:
        raise ValueError('未知历史操作')
    return dict(ok=True)
