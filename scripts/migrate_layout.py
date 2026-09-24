"""One-time, offline flat-to-compact migration. Keep an external backup and recovery journal."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_paths import application_root, COMPACT_LAYOUT
from update_installer import (atomic_json, blockers, child, inventory, read_json,
                              reject_reparse, self_check, sha256, verified_inventory, UpdateError)

DATA_NAMES = {'config.json', 'state', 'staging', 'models', '.portable-setup.lock',
              'app.lock', 'update.lock', '__pycache__', '应用日志.txt', '环境自检结果.json', '启动错误.txt'}


def copy_checked(source, target):
    """Never follow links and never report a backup until every copied byte matches."""
    reject_reparse(source)
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            copy_checked(item, target / item.name)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        before = sha256(source)
        shutil.copy2(source, target)
        if sha256(target) != before or sha256(source) != before:
            raise UpdateError('迁移期间文件发生变化，原目录未被覆盖。')


def _save(job):
    atomic_json(Path(job['work']) / 'migration.json', job)


def fingerprint(root, names):
    result = {}
    for name in names:
        path = child(root, name)
        for item in ([path] if path.is_file() else sorted(path.rglob('*'))):
            reject_reparse(item)
            if item.is_file():
                result[item.relative_to(root).as_posix()] = sha256(item)
    return result


def prepare(root, package, work):
    root, package, work = (Path(p).resolve() for p in (root, package, work))
    for path in (root, package, work):
        reject_reparse(path)
    if work.exists() or work.is_relative_to(root) or root.is_relative_to(work):
        raise UpdateError('请选择安装目录外一个新的备份目录。')
    if work.anchor.casefold() != root.anchor.casefold():
        raise UpdateError('备份目录须与安装目录位于同一磁盘，以便安全切换与恢复。')
    if any(a.is_relative_to(b) or b.is_relative_to(a) for a, b in ((package, root), (package, work))):
        raise UpdateError('新包、安装目录和备份目录必须相互独立。')
    if application_root(root) != root or (root / 'app').exists():
        raise UpdateError('这个入口只用于首次整理旧版平铺目录。')
    if application_root(package) != package / 'app':
        raise UpdateError('需要已校验的新目录格式安装包。')
    if blockers(root):
        raise UpdateError('请先正常退出记录器、回看窗口和此目录内的 OBS。')
    records = verified_inventory(package)
    old = inventory(read_json(root / 'package-manifest.json'))
    names = {name.split('/')[0] for name in old} | DATA_NAMES | {'package-manifest.json'}
    names -= {'vocabularies', 'Think Aloud.exe', 'ExperienceRecorder.exe'}
    names |= {name for name in ('Think Aloud.exe', 'ExperienceRecorder.exe') if (root / name).exists()}
    selected = sorted(name for name in names if (root / name).exists())
    observed = selected + (['vocabularies'] if (root / 'vocabularies').exists() else [])
    snapshot = fingerprint(root, observed)
    work.mkdir(parents=True)
    job = {'schema': 1, 'root': str(root), 'package': str(package), 'work': str(work),
           'selected': selected, 'observed': observed, 'snapshot': snapshot,
           'had_vocabulary': (root / 'vocabularies').exists(),
           'state': 'preparing', 'moved': [], 'published': [],
           'preserved_root_items': sorted(p.name for p in root.iterdir() if p.name not in selected)}
    _save(job)
    # Complete the protected-data copy before any move or software replacement.
    for name in ('config.json', 'state', 'staging', 'models', 'vocabularies', 'tools/obs/config'):
        source = child(root, name)
        if source.exists():
            copy_checked(source, work / 'user-data' / name)
    candidate = work / 'candidate'
    app = candidate / 'app'
    app.mkdir(parents=True)
    for name in selected:
        if name not in ('Think Aloud.exe', 'ExperienceRecorder.exe'):
            copy_checked(root / name, app / name)
    # Overlay only independently verified software, never private files.
    for name in [*records, 'app/package-manifest.json']:
        if name.startswith('vocabularies/'):
            if not (root / 'vocabularies').exists():
                copy_checked(package / name, candidate / name)
            continue
        copy_checked(package / name, candidate / name)
    cfg_path = app / 'config.json'
    old_location = None
    if cfg_path.is_file():
        cfg = read_json(cfg_path)
        old_location = cfg.get('_portable_root')
        cfg['_portable_root'] = str(root)
        atomic_json(cfg_path, cfg)
    # Only rewrite the recorder's known default, retaining all OBS scenes/devices.
    profile = app / 'tools/obs/config/obs-studio/basic/profiles/Experience/basic.ini'
    if profile.is_file():
        raw = profile.read_bytes()
        for base in (str(root), old_location):
            if base:
                old_path = str(Path(base) / 'staging').encode('utf-8')
                raw = raw.replace(b'RecFilePath=' + old_path + b'\r\n',
                                  b'RecFilePath=' + str(root / 'app/staging').encode('utf-8') + b'\r\n')
                raw = raw.replace(b'RecFilePath=' + old_path + b'\n',
                                  b'RecFilePath=' + str(root / 'app/staging').encode('utf-8') + b'\n')
        profile.write_bytes(raw)
    registry = app / 'state/models.json'
    if registry.is_file():
        entry = read_json(registry)
        model = Path(entry.get('path', ''))
        if not entry.get('relative') and model.is_absolute() and model.is_relative_to(root):
            relative = model.relative_to(root)
            if relative.parts[0] in selected and (app / relative).is_dir():
                entry.update(path=relative.as_posix(), relative=True)
                atomic_json(registry, entry)
        elif entry.get('relative') and model.parts and model.parts[0] not in selected:
            # A user-selected folder left beside the app must still resolve there.
            entry.update(path=str((root / model).resolve()), relative=False)
            atomic_json(registry, entry)
    # Keep old shortcuts functional while hiding their legacy name in Explorer.
    if 'ExperienceRecorder.exe' in selected:
        copy_checked(candidate / 'Think Aloud.exe', candidate / 'ExperienceRecorder.exe')
    job['candidate_snapshot'] = fingerprint(candidate, [p.name for p in candidate.iterdir()])
    job['state'] = 'prepared'
    _save(job)
    return job


def validate_recovery(job, journal=None):
    if job.get('schema') != 1 or job.get('state') not in ('applying', 'recovering', 'recovery_required'):
        raise UpdateError('这不是待恢复的目录迁移事务。')
    root, work, package = (Path(job[k]).resolve() for k in ('root', 'work', 'package'))
    for path in (root, work, package):
        reject_reparse(path)
    if journal is not None and Path(journal).resolve() != work / 'migration.json':
        raise UpdateError('恢复记录与备份目录不匹配。')
    if root == Path(root.anchor) or root.anchor.casefold() != work.anchor.casefold():
        raise UpdateError('恢复目录无效。')
    if any(a.is_relative_to(b) or b.is_relative_to(a) for a, b in ((root, work), (package, root), (package, work))):
        raise UpdateError('恢复目录不能相互包含。')
    old_manifest = work / 'original/package-manifest.json'
    if not old_manifest.exists():
        old_manifest = root / 'package-manifest.json'
    if sha256(old_manifest) != job.get('snapshot', {}).get('package-manifest.json'):
        raise UpdateError('旧软件清单与迁移记录不匹配。')
    allowed = {name.split('/')[0] for name in inventory(read_json(old_manifest))} | DATA_NAMES | {'package-manifest.json'}
    allowed |= {'Think Aloud.exe', 'ExperienceRecorder.exe'}
    allowed -= {'vocabularies'}
    selected, moved, published = (job.get(k, []) for k in ('selected', 'moved', 'published'))
    if (not all(isinstance(items, list) and all(isinstance(n, str) for n in items) and len(items) == len(set(items)) for items in (selected, moved, published))
            or not set(selected) <= allowed or not set(moved) <= set(selected)
            or not set(published) <= {'app', 'Think Aloud.exe', 'ExperienceRecorder.exe', 'vocabularies'}):
        raise UpdateError('恢复记录包含未授权的目录条目。')
    for name in moved:
        source = child(work / 'original', name)
        expected = {key: value for key, value in job['snapshot'].items() if key == name or key.startswith(name + '/')}
        if source.exists():
            if fingerprint(work / 'original', [name]) != expected:
                raise UpdateError('备份内容已改变，已停止自动恢复。')
        elif not child(root, name).exists() or fingerprint(root, [name]) != expected:
            job['state'] = 'recovery_required'; _save(job)
            raise UpdateError('原文件和备份均未通过检查，需要修复缺失备份，尚未恢复旧版本。')
    for name in published:
        if (root / name).exists() and not (work / 'candidate' / name).exists():
            expected = {key: value for key, value in job['candidate_snapshot'].items() if key == name or key.startswith(name + '/')}
            if fingerprint(root, [name]) != expected:
                raise UpdateError('新目录已有额外修改，已保留文件并停止自动恢复。')


def recover(job, journal=None):
    validate_recovery(job, journal)
    root, work = Path(job['root']), Path(job['work'])
    if blockers(root):
        raise UpdateError('仍有程序占用，备份已保留，请正常退出后重试恢复。')
    job['state'] = 'recovering'; _save(job)
    # Inspect durable intent plus source existence: a crash can precede journal completion.
    for name in reversed(job['published']):
        source = child(root, name)
        staged = work / 'candidate' / name
        if source.exists() and not staged.exists():
            held = work / 'failed' / name
            held.parent.mkdir(parents=True, exist_ok=True)
            source.rename(held)
    for name in reversed(job['moved']):
        backup = child(work / 'original', name)
        target = child(root, name)
        if backup.exists():
            if target.exists():
                raise UpdateError('恢复目标已被额外修改，原文件和备份均保留。')
            backup.rename(target)
    job['state'] = 'rolled_back'; _save(job)


def apply(job, checker=self_check, after_move=lambda count: None):
    root, work = Path(job['root']), Path(job['work'])
    if job['state'] != 'prepared' or blockers(root):
        raise UpdateError('迁移状态改变或程序仍在运行，请先退出。')
    if ((root / 'vocabularies').exists() != job['had_vocabulary']
            or fingerprint(root, job['observed']) != job['snapshot']):
        raise UpdateError('准备后原文件已改变，已保留原目录，请重新准备迁移。')
    job['state'] = 'applying'; _save(job)
    try:
        for count, name in enumerate(job['selected'], 1):
            source, backup = child(root, name), child(work / 'original', name)
            backup.parent.mkdir(parents=True, exist_ok=True)
            job['moved'].append(name); _save(job)
            source.rename(backup)
            after_move(count)
        for name in ('app', 'Think Aloud.exe', 'ExperienceRecorder.exe', 'vocabularies'):
            source = work / 'candidate' / name
            if source.exists():
                job['published'].append(name); _save(job)
                source.rename(child(root, name))
        checker(root, work)
        if os.name == 'nt' and (root / 'ExperienceRecorder.exe').exists():
            import ctypes
            if not ctypes.windll.kernel32.SetFileAttributesW(str(root / 'ExperienceRecorder.exe'), 2):
                raise OSError('无法设置旧入口的兼容属性。')
        job['state'] = 'complete'; _save(job)
    except Exception:
        recover(job)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--recover', type=Path, help='External migration.json journal')
    args = parser.parse_args()
    if args.recover:
        recover(read_json(args.recover), args.recover)
    else:
        if not all((args.root, args.package, args.backup)):
            parser.error('--root, --package and --backup are required')
        apply(prepare(args.root, args.package, args.backup))


if __name__ == '__main__':
    main()
