"""Rebuild the context tracks of every session in a library with its catalog's layout rules.

Needs the development runtime (it carries the OCR model). Sessions whose track was already built with the current
layout are skipped, so an interrupted run can simply be started again. Tracks without text-box corners are
OCR'd again in full: roughly 20–60 minutes per hour of video; two sessions run at a time.

  runtime\\python.exe -B -X utf8 scripts\\rebuild_context_tracks.py "<资料库>\\燕云十六声"

Writes only each session's context-track.json, plus one log per session in work\\context-rebuild\\.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import game_catalog  # noqa: E402


def built_with(folder, layout):
    try:
        return json.loads((folder / 'context-track.json').read_text(encoding='utf-8')).get('layout') == layout
    except (OSError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description='按版式规则重建资料库里各场的情景轨道')
    parser.add_argument('vault')
    parser.add_argument('--game', help='游戏名，默认取资料库文件夹名')
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    vault = Path(args.vault).resolve()
    catalog = json.loads(game_catalog.catalog_path(vault, args.game or vault.name).read_text(encoding='utf-8-sig'))
    layout = catalog.get('layout')
    if layout is None:
        raise SystemExit('界面目录里还没有版式规则，先运行 scripts\\apply_layout.py。')
    logs = ROOT / 'work' / 'context-rebuild'
    logs.mkdir(parents=True, exist_ok=True)

    def build(folder):
        if built_with(folder, layout):
            return folder.name, 'skipped (already built with this layout)', 0
        started = time.time()
        with (logs / (folder.name[:22] + '.log')).open('w', encoding='utf-8') as log:
            code = subprocess.call([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'agent_cli.py'), 'context-build', str(folder)],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        state = 'ok' if code == 0 and built_with(folder, layout) else f'failed (exit {code}, see log)'
        return folder.name, state, round(time.time() - started)

    sessions = sorted(path.parent for path in (vault / '场次').glob('*/录像.mp4'))
    print(len(sessions), 'sessions', flush=True)
    with ThreadPoolExecutor(max(1, args.workers)) as pool:
        for name, state, seconds in pool.map(build, sessions):
            print(time.strftime('%H:%M'), name[:22], state, f'{seconds // 60} min', flush=True)


if __name__ == '__main__':
    main()
