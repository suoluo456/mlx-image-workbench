"""Local, content-addressed reference images; never fetch arbitrary image URLs."""
import base64
import hashlib
import io
import re
import warnings
import uuid
from pathlib import Path

from PIL import Image, ImageOps
from workbench_paths import REFERENCES_DIR

DIRECTORY = REFERENCES_DIR
MAX_BYTES = 10 * 1024 * 1024


def resolve(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{64}\.png', identifier):
        raise ValueError('参考图编号无效，请重新上传')
    path = DIRECTORY / identifier
    if not path.is_file():
        raise ValueError('参考图不存在，请重新上传')
    return path


def upload(data):
    if not isinstance(data, dict) or not isinstance(data.get('image'), str):
        raise ValueError('请选择参考图')
    encoded = data['image']
    if len(encoded) > MAX_BYTES * 4 // 3 + 100:
        raise ValueError('参考图最多 10 MB')
    try:
        raw = base64.b64decode(encoded.split(',', 1)[-1], validate=True)
        if len(raw) > MAX_BYTES:
            raise ValueError('参考图最多 10 MB')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or source.width*source.height > 32_000_000:
                    raise ValueError('请使用不超过 3200 万像素的 PNG、JPG 或 WebP')
                image = ImageOps.exif_transpose(source).convert('RGB')
                image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                result = io.BytesIO()
                image.save(result, format='PNG')
    except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('参考图无法读取，请使用 PNG、JPG 或 WebP') from exc
    raw = result.getvalue()
    identifier = hashlib.sha256(raw).hexdigest() + '.png'
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = DIRECTORY / identifier
    if not path.exists():
        temp = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        temp.write_bytes(raw)
        temp.replace(path)
    return dict(id=identifier, image='/references/'+identifier, width=image.width, height=image.height)
