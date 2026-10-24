"""Install the two analysis skills that ship with the app into the user's own agents.

Follows docs/agent-integration.md "Skill 安装与更新": only agents the user actually has (%USERPROFILE%\\.claude,
%USERPROFILE%\\.codex) are touched; an installed copy that differs is first backed up outside the skill folders
(app/state/skill-backups/, so the backup is never loaded as a second skill); only files that ship are written, and
files the user added to a skill folder are left in place and listed.
"""
import os
from pathlib import Path
import shutil
import uuid

SKILLS = ('think-aloud-judgments', 'think-aloud-insight')
AGENTS = (('Claude Code', 'claude', '.claude'), ('Codex', 'codex', '.codex'))


def source_root(root):
    """Installed app: app/docs/skills (packaged there); source checkout: skills/."""
    root = Path(root)
    packaged = root / 'docs' / 'skills'
    return packaged if packaged.is_dir() else root / 'skills'


def _files(folder):
    return {path.relative_to(folder).as_posix(): path for path in sorted(folder.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts}


def _write(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_bytes(data)
    os.replace(temp, target)


def install(root, home, stamp):
    """Returns one row per agent and skill: installed / updated / unchanged, with backup and extra files."""
    root, home, base = Path(root), Path(home), source_root(root)
    sources = {}
    for name in SKILLS:
        files = _files(base / name)
        if 'SKILL.md' not in files:
            raise ValueError('软件包里缺少分析 skill：' + name)
        sources[name] = files
    agents = [(label, key, home / folder) for label, key, folder in AGENTS if (home / folder).is_dir()]
    if not agents:
        raise ValueError('没有找到 Claude Code 或 Codex（用户目录下的 .claude 或 .codex 文件夹）。请先安装并打开一次 agent，再回来安装。')
    rows = []
    for label, key, agent in agents:
        for name, files in sources.items():
            target = agent / 'skills' / name
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise ValueError(f'{label} 的技能目录里 {name} 不是普通文件夹，未改动。')
            changed = [relative for relative, path in files.items()
                       if not (target / relative).is_file() or (target / relative).read_bytes() != path.read_bytes()]
            row = dict(agent=label, skill=name, path=str(target), backup=None, extra_files=[])
            if target.exists():
                row['extra_files'] = sorted(set(_files(target)) - set(files))
            if not changed:
                rows.append(dict(row, state='unchanged'))
                continue
            if target.exists():
                backup = root / 'state' / 'skill-backups' / stamp / key / name
                shutil.copytree(target, backup)
                row['backup'] = str(backup)
            for relative in changed:
                _write(target / relative, files[relative].read_bytes())
            rows.append(dict(row, state='updated' if row['backup'] else 'installed'))
    return dict(source=str(base), results=rows)
