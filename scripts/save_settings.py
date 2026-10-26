"""Set only the explicit optional-integration choice; preserve other preferences."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
raw = Path(os.environ.get('MLX_WORKBENCH_DATA_DIR', ROOT / 'data')).expanduser()
data = raw.resolve() if raw.is_absolute() else (ROOT / raw).resolve()
data.mkdir(parents=True, exist_ok=True)
path = data / 'settings.json'
try:
    settings = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError
except (OSError, ValueError):
    print('错误：已有 settings.json 无法读取；原文件已保留，请修复该设置文件后重试。', file=sys.stderr)
    sys.exit(1)
settings['tavern_enabled'] = os.environ['MLX_TAVERN_INSTALL'] == 'yes'
temp = path.with_suffix('.json.tmp')
temp.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
temp.replace(path)
