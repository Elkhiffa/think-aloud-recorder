"""Move a flat library into the per-game layout: <library>\\<game>\\ holds everything the library root held.

Run by the user, once, while nobody uses the library (decided 2026-10-19, docs/plans/2026-10-19-redesign.md):

    runtime\\python.exe -B -X utf8 scripts\\migrate_library_layout.py --library D:\\think-aloud-database --game 燕云十六声 --app "D:\\Think Aloud\\app"
    (add --apply to actually move; without it the script only prints the plan and the checks)

What it does with --apply:
1. refuses if the installed app is running, if any session is being processed by an agent, or if the
   target folder already exists;
2. moves every top-level entry of the library into <library>\\<game>\\ (same-volume renames: no copying,
   hard links and file times stay as they are);
3. checks the moved library: same session count, no stale issue links, every report citation resolves;
4. backs up the app's config.json, then points every preset that used the old folder at the new one and
   records the old folder as the library root (资料总库).
Nothing is deleted.
"""
import argparse, json, msvcrt, os, shutil, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def app_running(app):
    lock = app / 'app.lock'
    if not lock.exists():
        return False
    with lock.open('a+b') as handle:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return True
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    return False


def active_claims(library):
    now, busy = time.time(), []
    for state in (library / '场次').glob('*/agent-state.json'):
        try:
            job = json.loads(state.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if job.get('state') == 'processing' and float(job.get('expires_at') or 0) > now:
            busy.append(state.parent.name)
    return busy


def cli(*args):
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(REPO / 'agent_cli.py'), *map(str, args)],
                            cwd=REPO, capture_output=True, text=True, encoding='utf-8')
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {'ok': False, 'error': (result.stderr or result.stdout)[-500:]}


def check(vault):
    """Session count, stale links and unresolved report citations of a library folder."""
    sessions = len(list((vault / '场次').glob('*/session.json'))) if (vault / '场次').is_dir() else 0
    stale = None
    listing = cli('issues-list', vault)
    if listing.get('ok'):
        stale = sum(int(row.get('links_stale') or 0) for row in listing['data'].get('issues', listing['data']) if isinstance(row, dict))
    unresolved = {}
    for report in sorted((vault / '洞察').glob('*.md')) if (vault / '洞察').is_dir() else []:
        result = cli('insight-validate', vault, report.name)
        unresolved[report.name] = len(result['data'].get('unresolved', [])) if result.get('ok') else result.get('error')
    return dict(sessions=sessions, stale_links=stale, unresolved_citations=unresolved)


def main():
    parser = argparse.ArgumentParser(description='把资料库整体搬进以游戏命名的子文件夹。')
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--game', required=True)
    parser.add_argument('--app', type=Path, help='安装版的 app 文件夹（含 config.json），用于改写资料库路径')
    parser.add_argument('--keep', action='append', default=[], help='留在资料总库根目录、不搬进游戏文件夹的项（可多次指定），如 .obsidian')
    parser.add_argument('--apply', action='store_true', help='真正执行；不加只预览')
    args = parser.parse_args()
    library = args.library.resolve()
    name = args.game.strip()
    if not name or any(c in name for c in '<>:"/\\|?*') or name in ('.', '..'):
        sys.exit('游戏名不能用作文件夹名：' + repr(args.game))
    target = library / name
    keep = set(args.keep)
    entries = sorted(p for p in library.iterdir() if p != target and p.name not in keep)
    print('资料库：', library)
    print('目标文件夹：', target)
    print('将移动 %d 项：' % len(entries))
    for entry in entries:
        print('  ', entry.name + ('\\' if entry.is_dir() else ''))
    if keep:
        print('留在根目录：', '、'.join(sorted(keep)))
    problems = []
    if target.exists():
        problems.append('目标文件夹已存在，已停止：' + str(target))
    if not (library / '场次').is_dir():
        problems.append('资料库根目录下没有“场次”，看起来已经搬过或路径不对。')
    if args.app and app_running(args.app):
        problems.append('安装版正在运行，请先完全退出 Think Aloud。')
    busy = active_claims(library) if (library / '场次').is_dir() else []
    if busy:
        problems.append('这些场次正在被 agent 整理，请等它们完成或释放：' + '、'.join(busy))
    before = check(library)
    print('搬迁前核对：', json.dumps(before, ensure_ascii=False))
    if problems:
        for problem in problems:
            print('不能执行：', problem)
        sys.exit(1)
    if not args.apply:
        print('这是预览。确认无误后加 --apply 执行。')
        return
    target.mkdir()
    moved = []
    try:
        for entry in entries:
            os.replace(entry, target / entry.name)
            moved.append(entry.name)
    except OSError as error:
        print('移动失败，已移动的项保留在新位置：', moved)
        raise SystemExit('请把上面列出的项移回 %s 后重试：%s' % (library, error))
    after = check(target)
    print('搬迁后核对：', json.dumps(after, ensure_ascii=False))
    ok = (after['sessions'] == before['sessions'] and after['stale_links'] == before['stale_links']
          and after['unresolved_citations'] == before['unresolved_citations'])
    print('核对结果：', '一致' if ok else '与搬迁前不一致，请把输出发给开发会话检查')
    if args.app:
        config = args.app / 'config.json'
        if config.is_file():
            backup = args.app / 'state' / ('config.before-library-move-%s.json' % time.strftime('%Y%m%d-%H%M%S'))
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config, backup)
            data = json.loads(config.read_text(encoding='utf-8'))
            same = lambda value: isinstance(value, str) and value and Path(value).resolve() == library
            changed = 0
            for settings in [data, *data.get('presets', {}).values()]:
                if same(settings.get('vault')):
                    settings['vault'] = str(target)
                    changed += 1
            data['library_root'] = str(library)
            temp = config.with_name(config.name + '.moving')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temp, config)
            print('已改写安装版配置：%d 处资料库路径；备份在 %s' % (changed, backup))
    print('完成。')


if __name__ == '__main__':
    main()
