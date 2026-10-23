"""Put a game's interface layout rules (docs/layouts/<game>.json) into a library's interface catalog.

Interface path recognition (lit tabs, titles) only runs for a catalog that has `layout`. Run this once per library,
then rebuild the context tracks of existing sessions (scripts/rebuild_context_tracks.py).

  runtime\\python.exe -B -X utf8 scripts\\apply_layout.py "<资料库>\\燕云十六声" --dry-run
  runtime\\python.exe -B -X utf8 scripts\\apply_layout.py "<资料库>\\燕云十六声"

The game defaults to the library folder's name. The old catalog is kept beside it as catalog.json.before-layout-<time>,
and the new one replaces it in one step, so a running recorder never reads a half-written file.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import game_catalog  # noqa: E402


def apply_layout(vault, game=None, dry_run=False):
    vault = Path(vault)
    game = game or vault.resolve().name
    reference = ROOT / 'docs' / 'layouts' / f'{game}.json'
    if not reference.is_file():
        raise ValueError(f'没有这个游戏的版式规则：{reference}')
    layout = json.loads(reference.read_text(encoding='utf-8'))
    path = game_catalog.catalog_path(vault, game)
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    before = data.get('layout')
    data.pop('active_tabs', None)  # the earlier, narrower rule set this layout replaces
    data['layout'] = layout
    game_catalog.validate_catalog(data)
    report = dict(catalog=str(path), game=game, replaced=before is not None, unchanged=before == layout)
    if dry_run or before == layout:
        return report
    backup = path.with_name(f"catalog.json.before-layout-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    temp = path.with_name(path.name + '.layout-tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)
    return dict(report, backup=str(backup))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='把游戏的版式规则写进资料库的界面目录')
    parser.add_argument('vault', help='单个游戏的资料库文件夹，例如 D:\\think-aloud-database\\燕云十六声')
    parser.add_argument('--game', help='游戏名，默认取资料库文件夹名')
    parser.add_argument('--dry-run', action='store_true', help='只检查，不写入')
    args = parser.parse_args()
    print(json.dumps(apply_layout(args.vault, args.game, args.dry_run), ensure_ascii=False, indent=1))
