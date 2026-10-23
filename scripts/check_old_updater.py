"""Release gate: install a new package with an OLD release's own updater, the way an in-app update does.

In-app updates are checked, planned and installed by the INSTALLED version's updater (updater.prepare_install copies
its own update_installer.py); 0.9.0 passed every check made with the new updater and still could not be installed
from 0.8.x. This script unpacks an old full release into a scratch folder, then — with that old install's own
Python and modules — rebuilds the new stage from the changed-files package (or extracts the full package),
self-checks it, writes the plan, copies the old helper and runs it with --no-launch. It passes only if the
scratch install ends up on the new version with every file matching the new manifest.

  runtime\\python.exe -B -X utf8 scripts\\check_old_updater.py --old <old full zip> --new <new full zip>
      [--update <new changed-files zip>] --version <new version> --work <empty scratch folder>

Writes only under --work. Never touches the real installation or any library.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]

# Runs inside the OLD install's runtime: only that release's modules are imported.
DRIVER = r'''
import json, shutil, sys, uuid
from pathlib import Path
app, kind, package, version, work = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
sys.path.insert(0, str(app))
import update_installer as old
from app_paths import application_root
install = app.parent
work.mkdir(parents=True)  # the updater creates its work folder before staging (updater.py download step)
stage = work / 'package'
if kind == 'update':
    old.assemble_package(package, install, stage, expected_version=version)
else:
    old.extract_package(package, stage, expected_version=version)
attempt = work / ('attempt-' + uuid.uuid4().hex)
attempt.mkdir()
old.self_check(stage, attempt)
plan = old.build_plan(install, stage, attempt)
shutil.copy2(app / 'update_installer.py', attempt / 'update_installer.py')
shutil.copy2(app / 'app_paths.py', attempt / 'app_paths.py')
old.write_recovery_entry(plan)
print(json.dumps(dict(attempt=str(attempt), python=str(application_root(stage) / 'runtime' / 'python.exe'),
                      files=len(plan['files']), version=plan['version'])))
'''


def unpack(archive, target):
    with zipfile.ZipFile(archive) as source:
        source.extractall(target)
    return target / 'app'


def run_case(name, old_zip, kind, package, version, work):
    case = work / name
    case.mkdir(parents=True)
    app = unpack(old_zip, case / 'install')
    old_version = json.loads((app / 'portable.json').read_text(encoding='utf-8'))['version']
    driver = case / 'driver.py'
    driver.write_text(DRIVER, encoding='utf-8')
    prepared = subprocess.run([str(app / 'runtime' / 'python.exe'), '-B', '-X', 'utf8', str(driver), str(app), kind,
                               str(package), version, str(case / 'w')], capture_output=True, text=True, encoding='utf-8')
    if prepared.returncode:
        return dict(case=name, from_version=old_version, ok=False, step='prepare (old updater)', error=prepared.stderr.strip()[-600:])
    plan = json.loads(prepared.stdout.strip().splitlines()[-1])
    attempt = Path(plan['attempt'])
    helper = subprocess.run([plan['python'], '-B', str(attempt / 'update_installer.py'), '--job', str(attempt / 'job.json'),
                             '--no-launch'], cwd=attempt, capture_output=True, text=True, encoding='utf-8')
    job = json.loads((attempt / 'job.json').read_text(encoding='utf-8'))
    installed = json.loads((app / 'portable.json').read_text(encoding='utf-8'))['version']
    # The new release's own inventory check over the finished install.
    sys.path.insert(0, str(ROOT))
    from update_installer import verified_inventory
    try:
        verified_inventory(case / 'install')
        inventory = 'ok'
    except Exception as error:  # reported, not raised: every case is shown
        inventory = f'{type(error).__name__}: {error}'
    ok = helper.returncode == 0 and job.get('state') in ('complete', 'installed') and installed == version and inventory == 'ok'
    return dict(case=name, from_version=old_version, kind=kind, ok=ok, state=job.get('state'), message=job.get('message'),
                installed=installed, files_replaced=plan['files'], inventory=inventory)


def main():
    parser = argparse.ArgumentParser(description='用旧版自己的更新器安装新包，确认软件内更新能成功')
    parser.add_argument('--old', action='append', required=True, help='旧版完整包 zip，可重复给多个')
    parser.add_argument('--new', required=True, help='新版完整包 zip')
    parser.add_argument('--update', help='新版增量包 zip')
    parser.add_argument('--version', required=True)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    # Absolute like the real updater's work folder: the old self_check runs the launcher with cwd=stage, so a
    # relative report path would be written inside the stage and read from elsewhere.
    args.work = args.work.resolve()
    if args.work.exists() and any(args.work.iterdir()):
        raise SystemExit('--work 必须是空文件夹或不存在。')
    results = []
    for old_zip in args.old:
        label = Path(old_zip).name.split('-windows')[0].replace('ExperienceRecorder-', '')
        if args.update:
            results.append(run_case(f'{label}-update', old_zip, 'update', Path(args.update).resolve(), args.version, args.work))
        results.append(run_case(f'{label}-full', old_zip, 'full', Path(args.new).resolve(), args.version, args.work))
    for row in results:
        print(json.dumps(row, ensure_ascii=False), flush=True)
    raise SystemExit(0 if all(row['ok'] for row in results) else 1)


if __name__ == '__main__':
    main()
