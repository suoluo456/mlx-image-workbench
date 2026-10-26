"""Local MLX model definitions. No downloads occur during generation."""
import json
from pathlib import Path
from workbench_paths import ROOT, MODEL_DIR
TURBO_MAX_DIMENSION = 2560
MODELS = {
    'zimage': dict(name='Z-Image-Turbo', steps=9, base='z-image-turbo', folder='z-image-turbo-mflux-q8', cli='mflux-generate-z-image-turbo', supports_negative=False),
    'qwen21_turbo': dict(name='Qwen-Image-2.1 Turbo', steps=8, precision='MLX 8bit',
                         base='qwen-image-2.1-turbo', backend='mlx',
                         folder='Qwen-Image-2.1-Turbo-MLX-8bit', cli='qwen21_turbo_cli.py',
                         fixed_steps=True, max_dimension=TURBO_MAX_DIMENSION, supports_negative=False),
    'qwen21_turbo_ref': dict(name='Qwen Turbo · 人物参考', steps=8, precision='MLX 8bit',
                         base='qwen-image-2.1-turbo', backend='mlx', hidden=True,
                         folder='Qwen-Image-2.1-Turbo-Reference-MLX-8bit', cli='qwen21_reference_cli.py',
                         python='.venv-reference', fixed_steps=True, max_dimension=1536,
                         supports_negative=False),
}
def ready(key):
    model = MODELS[key]
    folder = MODEL_DIR / model['folder']
    program = ROOT / model['cli'] if model['cli'].endswith('.py') else ROOT / '.venv/bin' / model['cli']
    if not program.is_file():
        return False
    if key == 'qwen21_turbo_ref' and (not (ROOT/'.venv-reference/bin/mflux-generate-qwen-2.1-edit').is_file()
                                    or not (folder/'transformer/config.json').is_file()
                                    or not ready('qwen21_turbo')):
        return False
    try:
        manifest = json.loads((folder / '.ready.json').read_text())
        if not isinstance(manifest, dict):
            return False
        files = manifest.get('files')
        if not isinstance(files, dict) or not files:
            return False
        for name, size in files.items():
            if (not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts
                    or not isinstance(size, int) or isinstance(size, bool) or size < 0):
                return False
            path = folder / name
            if not path.resolve().is_relative_to(MODEL_DIR.resolve()) or not path.is_file() or path.stat().st_size != size:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False

def catalog():
    return [dict(id=key, name=m['name'], steps=m['steps'], precision=m.get('precision', '8bit'), ready=ready(key),
                 supports_negative=m['supports_negative'], fixed_steps=m.get('fixed_steps', False),
                 max_dimension=m.get('max_dimension', 2560)) for key, m in MODELS.items() if not m.get('hidden')]
