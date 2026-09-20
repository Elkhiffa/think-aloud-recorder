"""Local dictionary import and shared hotword validation; no network or settings writes."""
from pathlib import Path
import re
from urllib.parse import quote

from scel_to_text import parse_scel, ScelFormatError

MAX_WORDS = 2000
MAX_FILE_BYTES = 8 * 1024 * 1024
SOGOU_DICTIONARIES = 'https://pinyin.sogou.com/dict/'


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


def dictionary_search_url(game):
    game = game.strip()
    if not game or game == '自由探索':
        return SOGOU_DICTIONARIES
    # The official search page uses GBK-encoded path segments.
    return 'https://pinyin.sogou.com/dict/search/search_list/' + quote(game, safe='', encoding='gbk', errors='replace') + '/normal'
