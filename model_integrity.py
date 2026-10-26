"""Small, CPU-only checks for installed MLX transformer indexes."""
import json
import struct
from pathlib import Path


def validate_transformer_index(model):
    folder = Path(model) / 'transformer'
    index = json.loads((folder / 'model.safetensors.index.json').read_text())
    weights = index.get('weight_map') if isinstance(index, dict) else None
    if not isinstance(weights, dict) or not weights:
        raise ValueError('Turbo 绘图权重索引为空，请运行模型检查与修复')
    shards = {}
    for name, filename in weights.items():
        if not isinstance(name, str) or not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError('Turbo 绘图权重索引无效')
        shards.setdefault(filename, set()).add(name)
    for filename, expected in shards.items():
        path = folder / filename
        with path.open('rb') as stream:
            raw = stream.read(8)
            if len(raw) != 8:
                raise ValueError('Turbo 绘图权重文件不完整')
            length = struct.unpack('<Q', raw)[0]
            if not 0 < length <= 64 * 1024 * 1024:
                raise ValueError('Turbo 绘图权重头无效')
            header = json.loads(stream.read(length))
        if not isinstance(header, dict):
            raise ValueError('Turbo 绘图权重头无效')
        actual = set(header) - {'__metadata__'}
        if actual != expected:
            raise ValueError('Turbo 绘图权重与索引不一致，请运行模型检查与修复')
        payload_size = path.stat().st_size - 8 - length
        for key in actual:
            tensor = header[key]
            offsets = tensor.get('data_offsets', []) if isinstance(tensor, dict) else []
            if (not isinstance(offsets, list) or len(offsets) != 2
                    or any(isinstance(i, bool) or not isinstance(i, int) for i in offsets)
                    or not 0 <= offsets[0] <= offsets[1] <= payload_size):
                raise ValueError('Turbo 绘图权重数据不完整')
    return True
