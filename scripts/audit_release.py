#!/usr/bin/env python3
"""Audit the explicitly selected public source files, never user directories."""
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.venv', '.venv-reference', '.tools', '.cache', '__pycache__',
            'data', 'models', 'output', 'outputs', 'references', 'logs', 'backups',
            'loras', 'verification', 'experiments', 'dist', 'build'}
SECRET_PATTERNS = [
    re.compile(r'hf_[A-Za-z0-9]{25,}'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{35,}'),
    re.compile(r'sk-[A-Za-z0-9_-]{30,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]


def selected_files(root=ROOT):
    manifest = json.loads((root / 'release-files.json').read_text('utf-8'))
    files = manifest['files']
    if not files or len(files) != len(set(files)):
        raise ValueError('发布清单为空或有重复项')
    return files


def audit(root=ROOT):
    problems = []
    files = selected_files(root)
    for relative in files:
        path = PurePosixPath(relative)
        if (path.is_absolute() or '..' in path.parts or '\\' in relative
                or set(path.parts) & EXCLUDED):
            problems.append(f'不允许的路径：{relative}')
            continue
        source = root / relative
        if source.is_symlink() or not source.is_file():
            problems.append(f'文件缺失或是符号链接：{relative}')
            continue
        if source.stat().st_size > 2_000_000:
            problems.append(f'文件超过源代码包大小限制：{relative}')
            continue
        try:
            content = source.read_text('utf-8')
        except UnicodeDecodeError:
            problems.append(f'公开源码包不接受未审查的二进制文件：{relative}')
            continue
        # Do not print matched values; only report their locations.
        for line_no, line in enumerate(content.splitlines(), 1):
            if ('/' + 'Users' + '/') in line or any(pattern.search(line) for pattern in SECRET_PATTERNS):
                problems.append(f'需检查本机路径或凭据：{relative}:{line_no}')
    return files, problems


if __name__ == '__main__':
    try:
        files, problems = audit()
    except (OSError, ValueError, KeyError) as exc:
        print(f'发布检查失败：{exc}', file=sys.stderr)
        raise SystemExit(1)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        raise SystemExit(1)
    print(f'公开源码检查通过：{len(files)} 个清单文件，无运行数据或模型。')
