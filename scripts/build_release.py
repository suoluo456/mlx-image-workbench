#!/usr/bin/env python3
"""Build small source-only ZIPs with explicit Unix executable permissions."""
import argparse
import hashlib
from pathlib import Path
import stat
import zipfile

from audit_release import ROOT, audit


def add_file(archive, source, name):
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    executable = source.suffix in {'.command', '.sh'}
    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, source.read_bytes())


def build(destination):
    files, problems = audit()
    if problems:
        raise ValueError('\n'.join(problems))
    version = (ROOT / 'VERSION').read_text().strip()
    destination.mkdir(parents=True, exist_ok=True)
    main = destination / f'MLX-Image-Workbench-{version}-macOS.zip'
    addon = destination / f'MLX-Image-Workbench-SillyTavern-{version}.zip'
    with zipfile.ZipFile(main, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            add_file(archive, ROOT / relative, 'MLX-Image-Workbench/' + relative)
    with zipfile.ZipFile(addon, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            if relative.startswith('tavern-extension/') and not Path(relative).name.startswith('test-'):
                name = 'mlx-image-workbench-tavern/' + relative.split('/', 1)[1]
                add_file(archive, ROOT / relative, name)
        if 'tavern-extension/LICENSE' not in files:
            add_file(archive, ROOT / 'LICENSE', 'mlx-image-workbench-tavern/LICENSE')
    sums = []
    for path in (main, addon):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip():
                raise ValueError(f'ZIP 数据校验失败：{path.name}')
            for entry in archive.infolist():
                if entry.filename.endswith(('.command', '.sh')):
                    if ((entry.external_attr >> 16) & 0o777) != 0o755:
                        raise ValueError(f'ZIP 缺少执行权限：{entry.filename}')
        sums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name)
        print(f'{path.name}: {path.stat().st_size:,} bytes')
    (destination / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    build(args.output.resolve())
