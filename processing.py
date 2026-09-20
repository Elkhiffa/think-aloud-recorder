"""Supervise an isolated process so a native crash cannot close the GUI."""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from recorder import HIDDEN, ROOT, Session


def process_isolated(session, progress=lambda text: None, transcription_settings=None):
    # pythonw has no console streams. Use python with a hidden console and pipes.
    executable = Path(sys.executable).with_name('python.exe')
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    log_path = session.path / '转写进程日志.txt'
    progress('启动独立整理进程…')
    reported_error = None
    complete = False
    with log_path.open('a', encoding='utf-8') as log:
        log.write('\n整理启动 ' + datetime.now().astimezone().isoformat() + '\n')
        log.flush()
        args = [str(executable), '-u', str(ROOT / 'processing_worker.py'), str(session.path)]
        if transcription_settings is not None:
            args.extend(['--settings-json', json.dumps(transcription_settings, ensure_ascii=False)])
        worker = subprocess.Popen(
            args,
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8',
            errors='replace', creationflags=HIDDEN,
        )
        for line in worker.stdout:
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                log.write(line)
                continue
            if event.get('kind') == 'progress':
                progress(event.get('text', ''))
            elif event.get('kind') == 'error':
                reported_error = event.get('text', '整理失败')
            elif event.get('kind') == 'complete':
                complete = True
        worker.stdout.close()
        code = worker.wait()
        log.write(f'整理退出码 {code} (0x{code & 0xffffffff:08X})\n')
    session.meta = Session(session.path).meta
    if code == 0 and complete and session.meta.get('state') == '可回看':
        return
    if reported_error:
        raise RuntimeError(reported_error)
    error = '整理进程意外退出，原始录像已保留。可以点击“重试生成回看”；详情见转写进程日志。'
    history = session.meta.get('error_history', [])
    history.append({'time': datetime.now().astimezone().isoformat(),
                    'error': error, 'worker_exit_code': code})
    session.update(state='失败', error=error, error_history=history)
    raise RuntimeError(error)
