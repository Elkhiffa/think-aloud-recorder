"""Extract ordinary text and pinyin from a Sogou SCEL data file, without an IME.

Binary layout reference: https://github.com/lewangdev/scel2txt
This reader supports the common 0x44 and 0x45 layouts. Unknown or truncated
layouts fail explicitly instead of silently returning a partial vocabulary.
"""
import argparse
import json
from pathlib import Path
import struct


class ScelFormatError(ValueError):
    pass


class Reader:
    def __init__(self, data, position, end=None):
        self.data = data
        self.position = position
        self.end = len(data) if end is None else end

    def take(self, size):
        if size < 0 or self.position + size > self.end:
            raise ScelFormatError(f'词库数据不完整，偏移 {self.position:#x}。')
        value = self.data[self.position:self.position + size]
        self.position += size
        return value

    def u16(self):
        return struct.unpack('<H', self.take(2))[0]

    def text(self, size):
        if not size or size % 2:
            raise ScelFormatError('词库文本长度无效。')
        try:
            return self.take(size).decode('utf-16le')
        except UnicodeDecodeError as error:
            raise ScelFormatError('词库文本不是有效 UTF-16LE。') from error


def parse_scel(path):
    data = Path(path).read_bytes()
    offsets = {0x44: 0x2628, 0x45: 0x26C4}
    if len(data) < 8 or data[:4] != b'\x40\x15\x00\x00' or data[4] not in offsets:
        raise ScelFormatError('不支持的搜狗词库格式；需要常见的 .scel 词库文件。')
    word_start = offsets[data[4]]
    if len(data) <= word_start:
        raise ScelFormatError('词库文件不完整或没有词条。')

    def metadata(start, end):
        try:
            return data[start:end].decode('utf-16le').split('\0', 1)[0]
        except UnicodeDecodeError as error:
            raise ScelFormatError('词库说明编码无效。') from error

    pinyin = {}
    reader = Reader(data, 0x1544, word_start)
    while reader.position < word_start:
        index, size = reader.u16(), reader.u16()
        if not size:
            if any(data[reader.position:word_start]):
                raise ScelFormatError('拼音表格式无法识别。')
            break
        syllable = reader.text(size)
        if index in pinyin and pinyin[index] != syllable:
            raise ScelFormatError('拼音表索引重复。')
        pinyin[index] = syllable
        if syllable == 'zuo':
            break
    if not pinyin:
        raise ScelFormatError('词库缺少拼音表。')

    records = []
    reader = Reader(data, word_start)
    while reader.position < len(data):
        count, index_bytes = reader.u16(), reader.u16()
        if not count or not index_bytes or index_bytes % 2:
            raise ScelFormatError(f'词组结构无效，偏移 {reader.position:#x}。')
        syllables = []
        for unused in range(index_bytes // 2):
            index = reader.u16()
            if index not in pinyin:
                raise ScelFormatError(f'词条引用了不存在的拼音索引 {index}。')
            syllables.append(pinyin[index])
        for unused in range(count):
            word = reader.text(reader.u16())
            if '\0' in word or '\n' in word or '\r' in word:
                raise ScelFormatError('词条包含无效分隔字符。')
            extension = reader.take(reader.u16())
            records.append({'word': word, 'pinyin': ' '.join(syllables),
                            'source_frequency': int.from_bytes(extension[:2], 'little') if len(extension) >= 2 else None})
    return {'title': metadata(0x130, 0x338), 'category': metadata(0x338, 0x540),
            'description': metadata(0x540, 0xD40), 'records': records,
            'bytes_consumed': reader.position, 'file_bytes': len(data)}


def main():
    parser = argparse.ArgumentParser(description='将搜狗 .scel 细胞词库转换为 UTF-8 文本。')
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path, help='纯文本输出路径；每行一个词。')
    parser.add_argument('--details', type=Path, help='可选：另存词条、拼音和来源词频 JSON。')
    args = parser.parse_args()
    result = parse_scel(args.source)
    words = list(dict.fromkeys(r['word'].strip() for r in result['records'] if r['word'].strip()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n'.join(words) + '\n', encoding='utf-8')
    if args.details:
        args.details.parent.mkdir(parents=True, exist_ok=True)
        args.details.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(result["records"])} records; {len(words)} unique words; {args.output}')


if __name__ == '__main__':
    main()
