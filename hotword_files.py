"""Local dictionary import and shared hotword validation; no network or settings writes."""
from pathlib import Path
import hashlib
import json
import re
import unicodedata
from urllib.parse import quote

from scel_to_text import parse_scel, ScelFormatError

MAX_WORDS = 2000
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_DICTIONARY_FILES = 128
MAX_MANUAL_CHARS = 128000
SOGOU_DICTIONARIES = 'https://pinyin.sogou.com/dict/'
from app_paths import installation_root

BUNDLED_DICTIONARY = Path('vocabularies/uiux-terms.txt')


def split_words(text):
    return list(dict.fromkeys(word.strip() for word in re.split(r'[,，;；、\r\n]+', text.lstrip('\ufeff')) if word.strip()))


def validate_words(words, *, qwen=True):
    words = list(dict.fromkeys(word.strip() for word in words if word.strip()))
    if len(words) > MAX_WORDS:
        raise ValueError(f'合并后有 {len(words)} 个词，最多支持 {MAX_WORDS} 个。请先精简词库，或按场景拆分使用。')
    for word in words:
        if any(ord(char) < 32 or ord(char) == 127 for char in word):
            raise ValueError('词条包含无法识别的控制字符，请使用纯文本词库。')
        too_long = len(word) > 15 if any(ord(char) > 127 for char in word) else len(word.split()) > 7
        if qwen and too_long:
            raise ValueError(f'词条“{word[:24]}”过长。Qwen 中文或中英混合词条最多 15 个字符，纯英文最多 7 个单词。')
    return words


def read_words(path, *, qwen=True):
    path = Path(path)
    if path.suffix.lower() not in ('.txt', '.scel'):
        raise ValueError('请选择搜狗细胞词库（.scel）或纯文本词库（.txt）。')
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('词库文件超过 8 MB，请选择较小的游戏专用词库。')
    if path.suffix.lower() == '.scel':
        try:
            words = [record['word'] for record in parse_scel(path)['records']]
        except ScelFormatError as error:
            raise ValueError('无法读取这份搜狗词库：' + str(error)) from error
    else:
        data = path.read_bytes()
        encodings = ('utf-16',) if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'gb18030')
        text = None
        for encoding in encodings:
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError('文本编码无法识别，请另存为 UTF-8、UTF-16 或 GBK 文本。')
        # Also accept word-first TXT exports with tab-separated pinyin/frequency.
        lines = [line.split('\t', 1)[0] for line in text.splitlines() if not line.lstrip().startswith('#')]
        words = split_words('\n'.join(lines))
    words = validate_words(words, qwen=qwen)
    if not words:
        raise ValueError('词库中没有可导入的词条。TXT 请每行填写一个词，或用逗号分隔。')
    return words


def merge_files(current, paths, *, qwen=True):
    existing = split_words(current)
    incoming = []
    for path in paths:
        incoming.extend(read_words(path, qwen=qwen))
    # Validate everything before the caller changes the editor or saved settings.
    merged = validate_words(existing + incoming, qwen=qwen)
    return merged, len(merged) - len(existing)


def _normalized_snapshot_words(words):
    if not isinstance(words, list) or not words or len(words) > MAX_WORDS:
        raise ValueError(f'每个词库必须包含 1 至 {MAX_WORDS} 个词条。')
    if any(not isinstance(word, str) for word in words):
        raise ValueError('词库词条必须是文本。')
    if sum(len(word.encode('utf-8')) for word in words) > MAX_FILE_BYTES:
        raise ValueError('词库词条快照超过 8 MB。')
    normalized = validate_words([unicodedata.normalize('NFC', word).strip() for word in words], qwen=False)
    if not normalized:
        raise ValueError('词库中没有可用词条。')
    return normalized


def dictionary_id(words):
    """Identity depends on normalized content, not filename, path or word order."""
    normalized = _normalized_snapshot_words(words)
    canonical = json.dumps(sorted(normalized), ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def compile_hotword_snapshots(files, manual, *, qwen=False):
    """Validate untrusted bridge payload and derive the sole transcription text.

    No source path is accepted. Returned lists are newly owned snapshots so a
    caller cannot mutate another preset by retaining an input list reference.
    """
    if not isinstance(files, list) or len(files) > MAX_DICTIONARY_FILES:
        raise ValueError(f'请最多选择 {MAX_DICTIONARY_FILES} 个词库文件。')
    if not isinstance(manual, str) or len(manual) > MAX_MANUAL_CHARS:
        raise ValueError(f'手动补充词条必须是文本，且不能超过 {MAX_MANUAL_CHARS} 个字符。')
    snapshots, combined, seen = [], [], set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {'id', 'name', 'words'}:
            raise ValueError('词库文件信息格式不正确。')
        name = item['name']
        if (not isinstance(name, str) or not name or len(name) > 255
                or re.search(r'[\\/:<>"|?*\x00-\x1f\x7f]', name)
                or name.endswith((' ', '.')) or Path(name).suffix.lower() not in ('.txt', '.scel')):
            raise ValueError('词库名称必须是 TXT 或 SCEL 文件名，不能包含路径。')
        words = _normalized_snapshot_words(item['words'])
        ident = dictionary_id(words)
        if item['id'] != ident:
            raise ValueError('词库内容与标识不一致，请重新选择该文件。')
        if ident in seen:
            continue
        seen.add(ident)
        snapshots.append(dict(id=ident, name=name, words=words))
        combined.extend(words)
    combined.extend(unicodedata.normalize('NFC', word) for word in split_words(manual))
    combined = validate_words(combined, qwen=qwen)
    return dict(hotword_files=snapshots, hotword_manual=manual, hotwords='\n'.join(combined))


def read_dictionary_snapshots(paths):
    """Parse an entire multi-file selection atomically, without storing paths."""
    if len(paths) > MAX_DICTIONARY_FILES:
        raise ValueError(f'请最多选择 {MAX_DICTIONARY_FILES} 个词库文件。')
    files = []
    for value in paths:
        path = Path(value)
        try:
            words = _normalized_snapshot_words(read_words(path, qwen=False))
        except OSError:
            raise ValueError(f'无法读取词库“{path.name}”，请检查该文件是否仍存在且可访问。') from None
        except ValueError as error:
            raise ValueError(f'词库“{path.name}”未导入：{error}') from None
        files.append(dict(id=dictionary_id(words), name=path.name, words=words))
    # Enforce the combined vocabulary limit as well as each source file limit.
    return compile_hotword_snapshots(files, '', qwen=False)['hotword_files']


def bundled_dictionary_snapshots(root):
    """Fresh defaults from the shipped file, never a scan of personal dictionaries.

    An incomplete installation must not invent active terms or prevent existing
    presets from loading. Release validation requires this file separately.
    """
    try:
        files = read_dictionary_snapshots([installation_root(root) / BUNDLED_DICTIONARY])
        return compile_hotword_snapshots(files, '', qwen=True)['hotword_files']
    except (OSError, ValueError):
        return []


def dictionary_search_url(game):
    game = game.strip()
    if not game or game == '自由探索':
        return SOGOU_DICTIONARIES
    # The official search page uses GBK-encoded path segments.
    return 'https://pinyin.sogou.com/dict/search/search_list/' + quote(game, safe='', encoding='gbk', errors='replace') + '/normal'
