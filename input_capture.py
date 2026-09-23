"""Session-scoped, foreground-filtered input intervals on the video's clock.

The native source is deliberately lazy: importing, readiness checks and preparing a
recorder do not install listeners. Tests inject a source/clock and never capture
this computer's input.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import threading
import time


class InputCaptureError(RuntimeError):
    pass


DEVICES = {'keyboard', 'mouse', 'xbox', 'dualsense'}
KINDS = {'button', 'motion', 'axis', 'trigger'}
GAP_REASONS = {'focus': '目标窗口不在前台，操作采集已暂停',
               'disconnect': '输入设备已断开', 'capture': '操作采集不可用'}


def enabled(settings):
    return settings.get('record_inputs') is True


def capture_readiness(settings, root=None):
    result = {'enabled': enabled(settings), 'ready': True, 'error': ''}
    if not result['enabled']:
        return result
    try:
        if settings.get('source') != '游戏窗口':
            raise InputCaptureError('操作记录仅支持指定游戏窗口，请先切换录制范围。')
        if not settings.get('window'):
            raise InputCaptureError('请先选择需要记录操作的游戏窗口。')
        from input_capture_windows import resolve_target
        from input_capture_devices import resolve_sdl
        resolve_target(settings['window'])
        resolve_sdl(root)
    except Exception as exc:
        result.update(ready=False, error=str(exc) if isinstance(exc, InputCaptureError)
                      else '无法准备操作采集，请重新选择游戏窗口。')
    return result


def prepare_capture(settings, session_path, *, root=None, clock=time.perf_counter):
    if not enabled(settings):
        return None
    check = capture_readiness(settings, root)
    if not check['ready']:
        raise InputCaptureError(check['error'])
    from input_capture_windows import WindowsInputSource, resolve_target
    from input_capture_devices import resolve_sdl
    target = resolve_target(settings['window'])
    return InputRecorder(session_path, lambda: WindowsInputSource(target, resolve_sdl(root), clock), clock=clock)


def direction(x, y):
    if not x and not y:
        return ''
    return ('→', '↘', '↓', '↙', '←', '↖', '↑', '↗')[round(math.atan2(y, x) / (math.pi / 4)) % 8]


class InputRecorder:
    """Translate sanitized source events to intervals; no raw key/text log."""

    def __init__(self, session_path, source_factory, *, clock=time.perf_counter,
                 flush_interval=1.0):
        self.path = Path(session_path) / 'input-events.json'
        self.source_factory = source_factory
        self.clock = clock
        self.flush_interval = flush_interval
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._writer_stop = threading.Event()
        self._writer = self._source = None
        self._active = {}
        self._intervals = []
        self._gaps = []
        self._journal_records = 0
        self._interval_count = 0
        self._gap_count = 0
        self._final = None
        self._owns_journal = False
        self._invalid_from = None
        self._purger = None
        self._durable_until = None
        self.journal_path = self.path.with_name('input-events.journal')
        self.revocation_path = self.path.with_name('input-events.revocation.json')
        self._open_gaps = {}
        self._seq = 0
        self._control_times = {}
        self._origin = None
        self._offset = self._last = 0.0
        self._eligible = False
        self._state = 'prepared'
        self.error = None
        self._last_motion = None

    def _time(self, stamp=None):
        supplied = stamp is not None
        stamp = self.clock() if stamp is None else float(stamp)
        value = max(0.0, stamp - self._origin + self._offset)
        self._last = max(self._last, value)
        # Event timestamps may precede a recent disk snapshot; preserving them
        # is essential for two short transitions drained in one message batch.
        return value if supplied else self._last

    def start(self, origin=None, video_offset=0.0):
        with self._lock:
            if self._state != 'prepared':
                raise InputCaptureError('操作采集已启动，不能重复开始。')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                raise InputCaptureError('本场次已有操作记录，不能覆盖。')
            try:
                with self.journal_path.open('x', encoding='utf-8'):
                    pass
            except FileExistsError as exc:
                raise InputCaptureError('本场次已有操作日志，不能覆盖。') from exc
            self._owns_journal = True
            self._origin = self.clock() if origin is None else float(origin)
            self._offset = max(0.0, float(video_offset))
            self._state = 'recording'
            self._open_gaps['capture:startup'] = {'start': 0., 'type': 'capture', 'reason': '录像启动确认前尚未采集操作'}
            self._open_gaps['focus'] = {'start': self._time(), 'type': 'focus', 'reason': GAP_REASONS['focus']}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._source = self.source_factory()
            self._source.start(self.feed)
            with self._lock:
                self._end_gap('capture:startup', self._time())
            if self.error:
                raise InputCaptureError(self.error)
            self._flush()
            self._writer = threading.Thread(target=self._write_loop, name='InputSidecarWriter', daemon=True)
            self._writer.start()
        except Exception as exc:
            self.stop(error=str(exc) if isinstance(exc, InputCaptureError) else '操作采集启动失败。')
            raise InputCaptureError(self.error) from exc
        return self

    def _close(self, key, at):
        current = self._active.pop(key, None)
        if current:
            current['end'] = round(max(current['start'], at), 6)
            self._intervals.append(current)

    def _close_all(self, at, device=None):
        for key in list(self._active):
            if device is None or key[0] == device:
                self._close(key, at)

    def _end_gap(self, kind, at):
        gap = self._open_gaps.pop(kind, None)
        if gap and at > gap['start']:
            self._gaps.append(dict(gap, end=round(at, 6)))

    def _expire_motion(self, at):
        # A motion interval ends at its last observed sample. The quiet threshold
        # only decides when to commit it; it never invents an extra held duration.
        if self._last_motion is not None and at - self._last_motion > .08:
            self._close(('mouse', 'MouseMove'), self._last_motion)
            self._last_motion = None

    def feed(self, event):
        """Only the source calls this. `foreground` is required on every input."""
        with self._lock:
            if self._state != 'recording':
                return
            at = self._time(event.get('timestamp'))
            self._expire_motion(at)
            typ = event.get('type')
            if typ == 'invalidate':
                cutoff = max(0., at)
                self._invalid_from = cutoff if self._invalid_from is None else min(self._invalid_from, cutoff)
                self.error = '前台窗口通知迟到，已清除不可信区间并停止操作采集。'
                # Failure-only synchronous fence: preserve the earliest revoked
                # boundary even if another invalidation arrives during cleanup.
                try:
                    _record_revocation(self.revocation_path, self._invalid_from)
                except (OSError, ValueError):
                    self.error = '不可信操作区间撤销写入失败，请勿导出此场次操作日志。'
                self._eligible = False
                self._close_all(cutoff)
                if self._purger is None or not self._purger.is_alive():
                    self._purger = threading.Thread(target=self._purge_invalid, name='InputPrivacyCleanup', daemon=True)
                    self._purger.start()
                return
            if typ == 'error':
                self.error = '操作采集中断，视频录制不受影响。'
                # An observer failure can be reported after its last confirmed
                # fence. Unknown time must become a gap, not a longer hold.
                covered = min(at, self._durable_until) if self._durable_until is not None else at
                self._close_all(covered)
                self._eligible = False
                self._open_gaps.setdefault('capture', {'start': covered, 'type': 'capture', 'reason': self.error})
                return
            if self.error:
                return
            if typ == 'watermark':
                self._durable_until = at if self._durable_until is None else max(self._durable_until, at)
                return
            if typ == 'coverage_gap':
                self._gaps.append({'type': 'capture', 'start': at, 'end': max(at, float(event.get('end', at)) - self._origin + self._offset), 'reason': '前台归属无法确认，此次输入未记录'})
                return
            if typ == 'ready':
                self._end_gap('capture:startup', at)
                return
            if typ == 'focus':
                active = event.get('foreground') is True
                if active != self._eligible:
                    self._eligible = active
                    if active:
                        self._end_gap('focus', at)
                    else:
                        self._close_all(at)
                        self._last_motion = None
                        self._open_gaps.setdefault('focus', {'start': at, 'type': 'focus', 'reason': GAP_REASONS['focus']})
                return
            if typ == 'tick':
                return
            if typ == 'disconnect':
                device = event.get('device')
                if device in DEVICES:
                    self._close_all(at, device)
                    self._open_gaps.setdefault('disconnect:' + device,
                        {'start': at, 'type': 'disconnect', 'reason': GAP_REASONS['disconnect'], 'device': device})
                return
            if typ == 'connect':
                self._end_gap('disconnect:' + str(event.get('device')), at)
                return
            # A stale callback may arrive just after focus loss; deny by default.
            if not self._eligible or event.get('foreground') is not True:
                return
            device, code = event.get('device'), event.get('code')
            kind = event.get('kind', 'button')
            if device not in DEVICES or kind not in KINDS or not isinstance(code, str):
                return
            if not code or len(code) > 32 or not code.isascii() or not all(c.isalnum() or c in '_-' for c in code):
                return
            key = (device, code)
            if at < self._control_times.get(key, -1):
                return
            self._control_times[key] = at
            if typ == 'button' and event.get('down') is not True:
                self._close(key, at)
                return
            props = {'device': device, 'code': code, 'label': str(event.get('label', code))[:32], 'kind': kind}
            if typ in ('axis', 'motion'):
                x = max(-1., min(1., float(event.get('x', 0))))
                y = max(-1., min(1., float(event.get('y', 0))))
                value = max(0., min(1., float(event.get('value', math.hypot(x, y)))))
                if not all(math.isfinite(n) for n in (x, y, value)):
                    return
                threshold = .08 if kind == 'trigger' else (.0 if kind == 'motion' else .18)
                if value <= threshold:
                    self._close(key, at)
                    return
                props.update(x=round(x, 3), y=round(y, 3), value=round(value, 3), direction=direction(x, y))
                if typ == 'motion':
                    self._last_motion = at
            current = self._active.get(key)
            if current:
                if typ == 'button':
                    return  # Key auto-repeat is not another physical press.
                # Preserve continuous holds while direction/value are unchanged.
                if all(current.get(k) == v for k, v in props.items()):
                    return
                self._close(key, at)
            self._seq += 1
            interval = dict(props, id='i' + str(self._seq), start=round(at, 6), end=round(at, 6))
            if event.get('resumed'):
                interval['resumed'] = True
            if typ == 'pulse':
                self._intervals.append(interval)
            else:
                self._active[key] = interval

    def _metadata(self, at):
        value = {'version': 1, 'state': self._state, 'duration': round(at, 6),
                 'timebase': 'video_seconds', 'capture_source': 'windows-raw-input+sdl2',
                 'clock': {'basis': 'monotonic', 'offset_seconds': self._offset}}
        if self.error:
            value['error'] = self.error
        return value

    def snapshot(self):
        # A diagnostic snapshot can materialize history, but disk reads/sorting
        # never hold the capture lock. The live writer uses only a small checkpoint.
        with self._write_lock:
            with self._lock:
                if self._final is not None:
                    return self._final
                at = self._time() if self._state == 'recording' else self._last
                if self._durable_until is not None and self._state == 'recording':
                    at = min(at, self._durable_until)
                self._expire_motion(at)
                pending_intervals = [dict(i) for i in self._intervals]
                pending_gaps = [dict(g) for g in self._gaps]
                active = [dict(i, end=round(max(i['start'], at), 6)) for i in self._active.values()]
                open_gaps = [dict(g, end=round(at, 6)) for g in self._open_gaps.values()]
                value = self._metadata(at)
                count = self._journal_records
            intervals, gaps, _ = _read_journal(self.journal_path, count)
            value['intervals'] = sorted(intervals + pending_intervals + active, key=lambda i: (i['start'], i['id']))
            value['gaps'] = sorted(gaps + pending_gaps + open_gaps, key=lambda g: g['start'])
            if self._invalid_from is not None:
                value = _invalidate_value(value, self._invalid_from)
            return value

    def _flush(self):
        with self._write_lock:
            with self._lock:
                at = self._time() if self._state == 'recording' else self._last
                if self._durable_until is not None and self._state == 'recording':
                    at = min(at, self._durable_until)
                self._expire_motion(at)
                intervals, self._intervals = self._intervals, []
                gaps, self._gaps = self._gaps, []
                value = self._metadata(at)
                active = [dict(i, end=round(max(i['start'], at), 6)) for i in self._active.values()]
                open_gaps = [dict(g, end=round(at, 6)) for g in self._open_gaps.values()]
            records = [('interval', i) for i in intervals] + [('gap', g) for g in gaps]
            try:
                if self._invalid_from is not None:
                    # Persist authority before changing either data file. If
                    # checkpoint replacement fails, its stale active holds must
                    # never be resurrected by recovery.
                    with self._lock:
                        _record_revocation(self.revocation_path, self._invalid_from)
                    previous_i, previous_g, valid = _read_journal(self.journal_path, self._journal_records)
                    if not valid:
                        raise ValueError('无法确认操作日志边界')
                    cleaned = _invalidate_value(dict(value, intervals=previous_i + intervals,
                                                     gaps=previous_g + gaps), self._invalid_from)
                    _replace_journal(self.journal_path, cleaned)
                    self._interval_count = len(cleaned['intervals'])
                    self._gap_count = len(cleaned['gaps'])
                    self._journal_records = self._interval_count + self._gap_count
                    records, intervals, gaps, active, open_gaps = [], [], [], [], []

                if records:
                    with self.journal_path.open('a', encoding='utf-8', newline='\n') as handle:
                        for kind, item in records:
                            handle.write(json.dumps({'type': kind, 'value': item}, ensure_ascii=False,
                                                   separators=(',', ':'), allow_nan=False) + '\n')
                        handle.flush()
                        os.fsync(handle.fileno())
                self._journal_records += len(records)
                self._interval_count += len(intervals)
                self._gap_count += len(gaps)
                value.update(state='recording', journal='input-events.journal', journal_records=self._journal_records,
                             interval_count=self._interval_count, gap_count=self._gap_count,
                             active=active, open_gaps=open_gaps, intervals=[], gaps=[])
                _atomic_json(self.path, value)
            except Exception:
                # The last atomic checkpoint remains the recovery authority.
                # Uncheckpointed journal tail must not be mistaken for durable coverage.
                raise

    def _purge_invalid(self):
        try:
            self._flush()
        except Exception:
            self.error = '不可信操作区间清理失败，请勿导出此场次操作日志。'
        finally:
            if self._source:
                self._source.stop()

    def _write_loop(self):
        while not self._writer_stop.wait(self.flush_interval):
            try:
                self._flush()
            except Exception:
                self.feed({'type': 'error'})
                if self._source:
                    self._source.stop()
                return

    def stop(self, duration=None, interrupted=False, error=None, trim_to=None):
        with self._lock:
            if not self._owns_journal:
                return {'version': 1, 'state': 'failed' if error else 'interrupted', 'duration': 0.,
                        'timebase': 'video_seconds', 'intervals': [], 'gaps': [], 'error': error or '操作采集尚未启动。'}
            if self._final is not None:
                return self._final
        if self._source:
            try:
                self._source.stop()
            except Exception:
                error = error or '操作采集未能正常结束。'
        self._writer_stop.set()
        if self._purger and self._purger is not threading.current_thread():
            self._purger.join(timeout=6)
        if self._writer and self._writer is not threading.current_thread():
            self._writer.join(timeout=3)
        with self._lock:
            if self._origin is None:
                self._origin = self.clock()
            at = self._time()
            if duration is not None:
                at = self._last = max(at, float(duration))
            covered = min(at, self._durable_until) if self._durable_until is not None else at
            self._close_all(covered)
            if covered < at:
                self._gaps.append({'start': covered, 'end': at, 'type': 'capture', 'reason': '操作事件确认结束后的录像区间'})
            for gap in list(self._open_gaps):
                self._end_gap(gap, at)
            self.error = error or self.error
            self._state = 'failed' if self.error else ('interrupted' if interrupted else 'complete')
        try:
            if trim_to is not None:
                _record_revocation(self.revocation_path, max(0., float(trim_to)))
            self._flush()
            value = self.snapshot()
            if trim_to is not None:
                value = _trim(value, max(0., float(trim_to)))
            # A trimmed/invalidated final view and its journal must agree;
            # export/recovery must not expose discarded tail records.
            if trim_to is not None or self._invalid_from is not None:
                _replace_journal(self.journal_path, value)
            _atomic_json(self.path, value)
            with self._lock:
                self._last = value['duration']
                self._final = value
            return value
        except (OSError, ValueError):
            self.error = '操作记录文件写入失败。'
            self._state = 'failed'
            # Keep last durable checkpoint recoverable; no broad rewrite on failure.
            return {'version': 1, 'state': 'failed', 'duration': self._last,
                    'timebase': 'video_seconds', 'intervals': [], 'gaps': [], 'error': self.error}


def _invalidate_value(value, cutoff):
    end = value['duration']
    clean = _trim(value, cutoff)
    clean['duration'] = end
    if end > cutoff:
        clean['gaps'].append({'type': 'capture', 'start': cutoff, 'end': end,
                              'reason': '前台边界无法确认，不可信操作数据已清除'})
    return clean


def _replace_journal(path, value):
    temp = path.with_suffix('.journal.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as handle:
        for kind, items in (('interval', value.get('intervals', [])), ('gap', value.get('gaps', []))):
            for item in items:
                handle.write(json.dumps({'type': kind, 'value': item}, ensure_ascii=False,
                                        separators=(',', ':'), allow_nan=False) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _atomic_json(path, value):
    temp = path.with_suffix('.json.tmp')
    with temp.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _read_revocation(path):
    """An unreadable existing revocation fails closed, rather than disappearing."""
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        cutoff = value.get('invalid_from')
        if value.get('version') != 1 or type(cutoff) not in (int, float) or not math.isfinite(cutoff) or cutoff < 0:
            return 0.
        return float(cutoff)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, AttributeError):
        return 0.


def _record_revocation(path, cutoff):
    previous = _read_revocation(path)
    earliest = cutoff if previous is None else min(previous, cutoff)
    _atomic_json(path, {'version': 1, 'invalid_from': earliest})


def _read_journal(path, count):
    intervals, gaps = [], []
    complete = 0
    if count == 0:
        return intervals, gaps, True
    try:
        with path.open('r', encoding='utf-8') as handle:
            for line in handle:
                if complete >= count:
                    break
                if not line.endswith('\n'):
                    break
                record = json.loads(line)
                kind, value = record.get('type'), record.get('value')
                if kind not in ('interval', 'gap') or not isinstance(value, dict):
                    break
                if not all(isinstance(value.get(k), (int, float)) and math.isfinite(value[k]) for k in ('start', 'end')):
                    break
                if value['start'] < 0 or value['end'] < value['start']:
                    break
                (intervals if kind == 'interval' else gaps).append(value)
                complete += 1
    except (OSError, ValueError):
        pass
    return intervals, gaps, complete == count


def _trim(value, cutoff):
    value = dict(value)
    value['duration'] = round(min(value['duration'], cutoff), 6)
    for collection in ('intervals', 'gaps'):
        value[collection] = [dict(item, end=min(item['end'], value['duration']))
                             for item in value.get(collection, []) if item['start'] < value['duration']]
    return value


def recover_capture(session_path, duration=None, *, error=None, trim_to=None):
    """Reconstruct only the committed journal prefix; never resume listeners."""
    path = Path(session_path) / 'input-events.json'
    # This independent authority survives a crash between journal replacement
    # and checkpoint replacement, including checkpoint-only active intervals.
    revoked = _read_revocation(path.with_name('input-events.revocation.json'))
    if trim_to is not None:
        _record_revocation(path.with_name('input-events.revocation.json'), max(0., float(trim_to)))
        revoked = _read_revocation(path.with_name('input-events.revocation.json'))
    try:
        checkpoint = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        checkpoint = {'version': 1, 'duration': 0., 'intervals': [], 'gaps': [], 'timebase': 'video_seconds'}
    durable = max(0., float(checkpoint.get('duration', 0)))
    if checkpoint.get('journal') == 'input-events.journal':
        intervals, gaps, valid = _read_journal(path.with_name('input-events.journal'), int(checkpoint.get('journal_records', 0)))
        if valid:
            intervals.extend(checkpoint.get('active', []))
            gaps.extend(checkpoint.get('open_gaps', []))
        else:
            durable = max([0.] + [i['end'] for i in intervals + gaps])
            error = error or '操作日志不完整，缺失区间已标记。'
        value = {key: checkpoint[key] for key in ('version', 'timebase', 'capture_source', 'clock') if key in checkpoint}
        value.update(duration=durable, intervals=intervals, gaps=gaps)
    else:
        value = dict(checkpoint)
    if revoked is not None:
        value = _invalidate_value(value, revoked)
        error = error or '不可信操作区间已按持久撤销边界排除。'
    value = _trim(value, durable if trim_to is None else min(durable, max(0., float(trim_to))))
    end = max(value['duration'], float(duration or 0))
    if end > value['duration']:
        value['gaps'].append({'type': 'capture', 'start': value['duration'], 'end': end,
                              'reason': '录制异常中断，此区间没有可靠操作数据'})
    value.update(state='interrupted', duration=end)
    if error:
        value['error'] = error
    value['intervals'].sort(key=lambda i: (i['start'], i['id']))
    value['gaps'].sort(key=lambda i: i['start'])
    if checkpoint.get('journal') == 'input-events.journal' or trim_to is not None or revoked is not None:
        _replace_journal(path.with_name('input-events.journal'), value)
    _atomic_json(path, value)
    return value
