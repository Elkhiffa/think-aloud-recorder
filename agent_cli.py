"""Machine-readable local bridge. No model, watcher, upload or credential use."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import agent_protocol as protocol


def scan(database, publish=False, include_test=False):
    base = Path(database).resolve() / '场次'
    if not base.is_dir():
        raise ValueError('资料库中没有“场次”目录。请传入资料库根目录。')
    sessions, skipped = [], []
    ids = {}
    for file in sorted(base.glob('*/session.json')):
        folder = file.parent.resolve()
        if folder.parent != base.resolve():
            continue
        try:
            meta, _, _, complete = protocol._identity(folder)
            if meta.get('test') and not include_test:
                continue
            if meta['id'] in ids:
                ids[meta['id']] = None
            else:
                ids[meta['id']] = folder
        except (OSError, ValueError, TypeError) as error:
            skipped.append(dict(folder=str(folder), reason=str(error)))
    for ident, folder in ids.items():
        if folder is None:
            skipped.append(dict(session_id=ident, reason='场次编号重复，未选择任何副本。'))
            continue
        try:
            if publish:
                protocol.publish_ready(folder)
            meta, _, revision, marker = protocol._ready(folder)
            state = protocol.preprocessing_status(folder)
            sessions.append(dict(session_id=ident, folder=str(folder), revision=revision,
                                 title=meta.get('session_name') or meta.get('game') or ident,
                                 preprocessing=state, test=bool(meta.get('test'))))
        except (OSError, ValueError, TypeError) as error:
            skipped.append(dict(session_id=ident, folder=str(folder), reason=str(error)))
    return dict(version=protocol.VERSION, sessions=sessions, skipped=skipped)


def frame(folder, at, output):
    meta, material, revision, _ = protocol._ready(folder)
    protocol._span(dict(start=at, end=at), material['duration'])
    output = Path(output).resolve()
    if output.is_relative_to(Path(folder).resolve()) or output.suffix.lower() not in ('.png', '.jpg'):
        raise ValueError('截图需保存到场次以外的工作目录，扩展名为 .png 或 .jpg。')
    if output.exists():
        raise ValueError('截图输出已存在，请使用新的文件名。')
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.stem + '.' + uuid.uuid4().hex + output.suffix)
    try:
        from recorder import FFMPEG, HIDDEN
        run = subprocess.run([str(FFMPEG), '-nostdin', '-hide_banner', '-loglevel', 'error',
                              '-ss', str(at), '-i', str(protocol._path(folder, '录像.mp4')),
                              '-frames:v', '1', '-vf', 'scale=min(1920\\,iw):-2', '-y', str(tmp)],
                             capture_output=True, timeout=40, creationflags=HIDDEN)
        if run.returncode or not tmp.is_file():
            raise ValueError('无法在此时间提取画面，请检查录像。')
        if protocol._ready(folder)[2] != revision:
            raise ValueError('提取期间素材已更新，请重试。')
        # Windows rename fails if the destination appeared during extraction.
        os.rename(tmp, output)
        return dict(path=str(output), session_id=meta['id'], revision=revision, at=at,
                    source='录像.mp4', note='静态画面只证明此时画面，不证明前后过程。')
    finally:
        tmp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Think Aloud 外部预处理接口（本地文件，JSON 输出）')
    commands = parser.add_subparsers(dest='command', required=True)
    discovery = commands.add_parser('scan', help='扫描已就绪场次；--publish 为旧场次补发信号')
    discovery.add_argument('database')
    discovery.add_argument('--publish', action='store_true')
    discovery.add_argument('--include-test', action='store_true')
    for name in ('publish', 'status', 'evidence', 'claim', 'renew', 'fail', 'validate', 'submit', 'frame'):
        command = commands.add_parser(name)
        command.add_argument('session')
        if name in ('renew', 'fail', 'submit'):
            command.add_argument('--token', required=True)
        if name in ('claim', 'renew'):
            command.add_argument('--seconds', type=int, default=1800)
        if name == 'claim':
            command.add_argument('--worker', required=True)
        if name == 'fail':
            command.add_argument('--reason', required=True)
        if name in ('validate', 'submit'):
            command.add_argument('--file', required=True, help='工作目录中的候选结果 JSON')
        if name == 'evidence':
            command.add_argument('--start', type=float)
            command.add_argument('--end', type=float)
        if name == 'frame':
            command.add_argument('--at', type=float, required=True)
            command.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        name = args.command
        if name == 'scan':
            value = scan(args.database, args.publish, args.include_test)
        elif name == 'publish':
            value = protocol.publish_ready(args.session)
        elif name == 'status':
            value = protocol.preprocessing_status(args.session)
        elif name == 'evidence':
            value = protocol.evidence(args.session, args.start, args.end)
        elif name == 'claim':
            value = protocol.claim(args.session, args.worker, args.seconds)
        elif name == 'renew':
            value = protocol.renew(args.session, args.token, args.seconds)
        elif name == 'fail':
            value = protocol.fail(args.session, args.token, args.reason)
        elif name == 'frame':
            value = frame(args.session, args.at, args.output)
        else:
            path = Path(args.file)
            if path.stat().st_size > protocol.MAX_RESULT:
                raise ValueError('候选结果超过 2 MB。')
            candidate = json.loads(path.read_text(encoding='utf-8-sig'))
            value = protocol.submit(args.session, args.token, candidate) if name == 'submit' else protocol.validate_result(args.session, candidate)
        print(json.dumps(dict(ok=True, data=value), ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps(dict(ok=False, error=str(error)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
