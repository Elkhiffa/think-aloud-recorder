"""Incremental preset refresh from explicit local TXT files; no source/session writes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import stat

from app_paths import application_root, vocabulary_dir
from hotword_files import (MAX_FILE_BYTES, compile_hotword_snapshots, dictionary_id,
                           read_dictionary_snapshots, split_words)

FIELDS = ('hotword_files', 'hotword_manual', 'hotwords')
PROTOCOL = 1
MAX_SOURCES = 16


class VocabularyError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def revision(preset):
    return digest({key: preset.get(key) for key in FIELDS})


def _source(root, name):
    if (not isinstance(name, str) or len(name) > 255 or not name
            or re.search(r'[\\/:<>"|?*\x00-\x1f\x7f]', name)
            or name.endswith((' ', '.')) or Path(name).suffix.lower() != '.txt'):
        raise VocabularyError('INVALID_SOURCE', '只接受词库目录中直接存放的 TXT 文件名，不能包含路径。')
    base = vocabulary_dir(root)
    path = base / name
    # A filename must not silently redirect to another dictionary via a link.
    for part in (base, path):
        info = part.lstat()
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise VocabularyError('INVALID_SOURCE', '词库目录和文件不能是符号链接或目录联接。')
    if not path.is_file() or path.resolve().parent != base.resolve():
        raise VocabularyError('INVALID_SOURCE', '词库文件不在当前安装的词库目录内。')
    if path.stat().st_size > MAX_FILE_BYTES:
        raise VocabularyError('INVALID_SOURCE', '词库文件超过 8 MB。')
    before = file_digest(path)
    snapshot = read_dictionary_snapshots([path])[0]
    if file_digest(path) != before:
        raise VocabularyError('CONFLICT', '读取时词库文件发生变化，请重新预览。')
    return dict(name=name, sha256=before, dictionary_id=snapshot['id'],
                word_count=len(snapshot['words'])), snapshot


def _preset(cfg, ident):
    if not isinstance(ident, str) or ident not in cfg.get('presets', {}):
        raise VocabularyError('INVALID_PRESET', '请使用回读接口返回的预设 ID。')
    return cfg['presets'][ident]


def describe(cfg, ident):
    preset = _preset(cfg, ident)
    return dict(preset_id=ident, name=preset.get('name', preset.get('game', '')),
                active=ident == cfg.get('active_preset_id'), revision=revision(preset),
                total_words=len(split_words(preset.get('hotwords', ''))),
                manual_words=len(split_words(preset.get('hotword_manual', ''))),
                dictionaries=[dict(name=row['name'], id=row['id'], word_count=len(row['words']))
                              for row in preset.get('hotword_files', [])])


def status(root, cfg, ident=None, sources=None):
    names = _names(sources or [], allow_empty=True)
    try:
        version = json.loads((application_root(root) / 'portable.json').read_text(encoding='utf-8')).get('version')
    except (OSError, ValueError):
        version = None
    return dict(protocol=PROTOCOL, app_root=str(application_root(root)),
                version=version,
                vocabulary_directory=str(vocabulary_dir(root)),
                active_preset_id=cfg.get('active_preset_id'),
                presets=[describe(cfg, key) for key in ([ident] if ident else cfg.get('presets', {}))],
                sources=[_source(root, name)[0] for name in names])


def _names(names, *, allow_empty=False):
    if (not isinstance(names, list) or not all(isinstance(name, str) for name in names)
            or len(names) > MAX_SOURCES or (not names and not allow_empty)
            or len(set(name.casefold() for name in names)) != len(names)):
        raise VocabularyError('INVALID_SOURCE', f'每次请指定 1 至 {MAX_SOURCES} 个不重复的词库文件名。')
    return names


def preview(root, cfg, ident, sources):
    names = _names(sources)
    preset = _preset(cfg, ident)
    files = deepcopy(preset.get('hotword_files', []))
    changes = []
    for name in names:
        matches = [row for row in files if row['name'].casefold() == name.casefold()]
        if len(matches) != 1:
            raise VocabularyError('SOURCE_NOT_UNIQUE', '指定词库必须在该预设中恰好有一份快照；请先在设置中明确导入。')
        old = matches[0]
        old_words = set(old['words'])
        source, incoming = _source(root, name)
        # Appending only: an accidentally truncated file cannot remove old terms.
        words = list(dict.fromkeys(old['words'] + incoming['words']))
        new = dict(name=old['name'], id=dictionary_id(words), words=words)
        changes.append(dict(**source, before_id=old['id'], after_id=new['id'],
                            before_words=len(old['words']), after_words=len(words),
                            added_words=[word for word in words if word not in old_words],
                            retained_missing_words=len(old_words - set(incoming['words']))))
        files[files.index(old)] = new
    compiled = compile_hotword_snapshots(files, preset.get('hotword_manual', ''),
                                        qwen=preset.get('transcription_provider') == 'qwen')
    if len(compiled['hotword_files']) != len(files):
        raise VocabularyError('DUPLICATE_DICTIONARY', '刷新后有词库内容完全相同，请先在设置中明确保留哪份词库。')
    updated = deepcopy(cfg)
    updated['presets'][ident].update(compiled)
    if ident == cfg.get('active_preset_id'):
        updated.update(deepcopy(compiled))
    plan = dict(protocol=PROTOCOL, app_root=str(application_root(root)), preset_id=ident,
                before_revision=digest(preset), after_revision=digest(updated['presets'][ident]),
                sources=changes, before=describe(cfg, ident), after=describe(updated, ident))
    plan['plan_id'] = digest(plan)
    return plan, updated


def apply_plan(root, cfg, plan):
    if not isinstance(plan, dict) or plan.get('protocol') != PROTOCOL:
        raise VocabularyError('INVALID_PLAN', '无法识别预览计划，请重新生成。')
    body = {key: value for key, value in plan.items() if key != 'plan_id'}
    if plan.get('plan_id') != digest(body) or plan.get('app_root') != str(application_root(root)):
        raise VocabularyError('INVALID_PLAN', '计划被修改或属于另一个安装，请重新预览。')
    ident = plan.get('preset_id')
    current = _preset(cfg, ident)
    try:
        names = _names([row['name'] for row in plan['sources']])
    except (KeyError, TypeError):
        raise VocabularyError('INVALID_PLAN', '计划的词库来源无效。') from None
    if digest(current) == plan.get('after_revision'):
        # Lost-response retries are safe without rewriting config or creating jobs.
        for expected, name in zip(plan['sources'], names):
            source, _ = _source(root, name)
            if any(source[key] != expected.get(key) for key in source):
                raise VocabularyError('CONFLICT', '词库文件已变化，请重新预览。')
        return deepcopy(cfg), False
    if digest(current) != plan.get('before_revision'):
        raise VocabularyError('CONFLICT', '预设在预览后已变化，请重新预览。')
    expected, updated = preview(root, cfg, ident, names)
    if expected != plan:
        raise VocabularyError('CONFLICT', '来源或预设在预览后已变化，请重新预览。')
    return updated, True
