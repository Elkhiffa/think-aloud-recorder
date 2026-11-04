"""读一张 POPO 在线表格的格式：每个 sheet 的表头行、每列已用过的取值、截图列、列宽。只读。

用法："$PY" -B -X utf8 read_table.py <表格链接或 docId> [--sheet 名称] [--output 文件]
不带 --sheet 时列出全部 sheet 的概况；带 --sheet 时给出这个 sheet 的详细格式。
需要 popo-cli（POPO 文档的命令行，CodeMaker / popo-doc skill 自带）。
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

IMAGE = re.compile(r'^https?://\S+/(file/download|api/admin/file)\S*\.(png|jpe?g|gif|webp)', re.I)


def popo(tool, **params):
    exe = shutil.which('popo-cli')
    if not exe:
        raise SystemExit('找不到 popo-cli。请在装了 popo-doc skill 的 agent（如 CodeMaker）里运行。')
    args = [exe, 'popo', tool]
    with tempfile.TemporaryDirectory() as folder:
        for key, value in params.items():
            if isinstance(value, (dict, list)):
                path = Path(folder) / (key + '.json')
                path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
                args.append(f'{key}=@file:{path}')
            else:
                args.append(f'{key}={value}')
        done = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
    try:
        reply = json.loads(done.stdout)
    except ValueError:
        raise SystemExit(f'popo-cli {tool} 没有返回 JSON：{(done.stdout or done.stderr)[-500:]}')
    data = reply
    for _ in range(4):  # The gateway nests {ok, data:{data:{data:{status, data}}}}.
        if isinstance(data, dict) and 'data' in data and 'status' not in data:
            data = data['data']
    if not isinstance(data, dict) or data.get('status') != 1:
        raise SystemExit(f'popo-cli {tool} 失败：{json.dumps(reply, ensure_ascii=False)[-600:]}')
    return data['data']


def doc_id(value):
    match = re.search(r'([0-9a-f]{32})', value)
    if not match:
        raise SystemExit('认不出文档编号：请给 docs.popo.netease.com 的表格链接或 32 位 docId。')
    return match.group(1)


def text(value):
    if isinstance(value, dict) and 'richText' in value:
        return ''.join(part.get('text', '') for part in value['richText'])
    return '' if value is None else str(value)


def header_row(rows):
    """The first row with at least five short labels (验收表 puts names in row 1 and the header in row 2)."""
    for index in sorted(rows)[:6]:
        labels = [value for value in rows[index].values() if value and len(value) <= 20 and not IMAGE.match(value)]
        if len(labels) >= 5:
            return index
    return min(rows) if rows else 0


def describe(sheet, detail):
    rows = {}
    for cell in sheet['cells']:
        rows.setdefault(cell['row'], {})[cell['col']] = text(cell.get('value') if cell.get('value') is not None else cell.get('formula'))
    head = header_row(rows)
    data_rows = [index for index in sorted(rows) if index > head]
    summary = dict(title=sheet['title'], hidden=sheet.get('hidden', False), header_row=head, data_rows=len(data_rows),
                   header=[dict(col=col, label=label) for col, label in sorted(rows.get(head, {}).items())])
    if not detail:
        return summary
    columns = []
    for col, label in sorted(rows.get(head, {}).items()):
        values = [rows[index].get(col, '') for index in data_rows if rows[index].get(col)]
        images = sum(1 for value in values if IMAGE.match(value))
        counts = Counter(value for value in values if not IMAGE.match(value))
        short = {value: n for value, n in counts.most_common() if len(value) <= 24}
        columns.append(dict(col=col, label=label, filled=len(values), images=images,
                            # A column whose values repeat is a closed vocabulary (类别、优先级、问题类型…).
                            vocabulary=list(short) if counts and len(short) <= 12 and len(short) <= 0.6 * len(values) and sum(short.values()) >= 0.6 * len(values) else [],
                            samples=[value[:80] for value, _ in counts.most_common(3)]))
    summary.update(preface=[dict(row=index, cells={str(col): value for col, value in sorted(rows[index].items())})
                            for index in sorted(rows) if index < head],
                   columns=columns, col_widths=sheet.get('colWidths') or {}, row_heights=sheet.get('rowHeights') or {})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('table')
    parser.add_argument('--sheet')
    parser.add_argument('--output')
    args = parser.parse_args()
    ident = doc_id(args.table)
    detail = popo('doc_get_doc_detail', docId=ident)
    if detail.get('type') != 2:
        raise SystemExit('这个链接不是 POPO 在线表格（docType=2）。')
    data = popo('doc_execute_table', docId=ident, command={'type': 'workbook.getFullData', 'payload': {}})
    sheets = data['sheets']
    if args.sheet:
        chosen = [sheet for sheet in sheets if sheet['title'].strip() == args.sheet.strip()]
        if not chosen:
            raise SystemExit('没有这个 sheet：' + args.sheet + '。现有：' + '、'.join(sheet['title'] for sheet in sheets))
        value = dict(doc_id=ident, title=detail.get('title', '').strip(), sheet=describe(chosen[0], True))
    else:
        value = dict(doc_id=ident, title=detail.get('title', '').strip(), sheets=[describe(sheet, False) for sheet in sheets])
    output = json.dumps(value, ensure_ascii=False, indent=1)
    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(args.output)
    else:
        sys.stdout.write(output + '\n')


if __name__ == '__main__':
    main()
