"""Local-only storyboard audit files. No generation calls or chat writes."""
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone

ROUTE = '/api/tavern/diagnostics'
LIMIT = 4 * 1024 * 1024
_lock = threading.RLock()


def serialize(data):
    # Preserve a malformed JSON escape or a clipped UTF-16 surrogate verbatim.
    return (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode('utf-8', errors='backslashreplace')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', value):
        raise ValueError('分镜诊断编号无效')
    return value


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('分镜诊断格式无效')
    result = {'schema_version': 1, 'id': identifier(data.get('id'))}
    for key in ('nonce', 'created_at', 'updated_at', 'chat_key', 'source_role', 'generation_type',
                'model', 'status', 'stage', 'finish_reason', 'message_name', 'protagonist', 'persona_avatar'):
        value = data.get(key)
        if value is not None:
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError('分镜诊断字段无效：'+key)
            result[key] = value
    for key in ('revision', 'story_length', 'payload_count', 'panel_count', 'message_id'):
        if key in data:
            value = data[key]
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100_000_000:
                raise ValueError('分镜诊断字段无效：'+key)
            result[key] = value
    if 'complete' in data:
        if not isinstance(data['complete'], bool):
            raise ValueError('分镜完成标记无效')
        result['complete'] = data['complete']
    blocks = data.get('raw_blocks', [])
    if not isinstance(blocks, list) or len(blocks) > 32:
        raise ValueError('原始分镜块数量无效')
    result['raw_blocks'] = []
    for block in blocks:
        if (not isinstance(block, dict) or not isinstance(block.get('text'), str)
                or len(block['text']) > 256000 or block.get('channel') not in ('content', 'reasoning', 'reasoning_content')
                or not isinstance(block.get('length'), int) or isinstance(block.get('length'), bool)
                or not len(block['text']) <= block['length'] <= 100_000_000
                or any(not isinstance(block.get(key), bool) for key in ('closed', 'truncated', 'parse_overflow'))):
            raise ValueError('原始分镜块格式无效')
        result['raw_blocks'].append({key:block[key] for key in
            ('text', 'channel', 'length', 'closed', 'truncated', 'parse_overflow')})
    if 'error' in data:
        error = data['error']
        if not isinstance(error, dict):
            raise ValueError('分镜错误信息无效')
        result['error'] = {}
        for key, limit in [('name', 200), ('message', 4000), ('stack', 10000)]:
            value = error.get(key, '')
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError('分镜错误信息过长')
            result['error'][key] = value
    if 'eligible_people' in data:
        people = data['eligible_people']
        if not isinstance(people, list) or len(people) > 100:
            raise ValueError('分镜人物映射无效')
        result['eligible_people'] = []
        for person in people:
            if not isinstance(person, dict) or any(not isinstance(person.get(key), str) or len(person[key]) > 300
                    for key in ('id', 'name', 'avatar')):
                raise ValueError('分镜人物映射无效')
            result['eligible_people'].append({key:person[key] for key in ('id', 'name', 'avatar')})
    return result


def save(folder, data):
    record = validate(data)
    with _lock:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / (record['id']+'.json')
        if path.exists():
            previous = json.loads(path.read_text())
            if previous.get('revision', 0) >= record.get('revision', 0):
                return {'id':record['id'], 'revision':previous.get('revision', 0)}
        record['saved_at'] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                stream.write(serialize(record))
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'id':record['id'], 'revision':record.get('revision', 0)}


def read(folder, value=None):
    if value:
        path = folder / (identifier(value)+'.json')
        if not path.is_file():
            raise FileNotFoundError('该分镜诊断不存在')
        return json.loads(path.read_text())
    paths = sorted(folder.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[:50]
    fields = ('id', 'updated_at', 'status', 'stage', 'source_role', 'generation_type', 'message_id', 'error')
    return {'directory':str(folder), 'records':[{key:record[key] for key in fields if key in record}
        for record in (json.loads(path.read_text()) for path in paths)]}
