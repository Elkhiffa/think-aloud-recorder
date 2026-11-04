"""按导出规格新建一张 POPO 在线表格：照抄表头和列宽，写入各行，上传截图填进截图列。只建新表，不碰公共表。

用法："$PY" -B -X utf8 write_sheet.py <规格.json> [--doc 已建好的docId]
规格（JSON，UTF-8）：
  title          新表标题
  sheet_name     sheet 名（同公共表的 sheet 名）
  header_rows    [[...], ...]  表头及其上方的行，按原样逐行写入
  col_widths     {"列号": 像素}  可省略；调不成的只记警告
  dropdowns      {"列号": ["选项", ...]}  有固定取值的列，给数据行加下拉
  rows           [{"cells": {"列号": "文字"}, "images": {"列号": "本地图片路径"},
                   "more_images": ["本地图片路径"], "more_col": 列号}]
                 more_images 是截图列放不下的图：上传后把链接追加到 more_col（备注列）
  image_height   有图的行的行高，默认 120
--doc：上次写到一半失败时，用同一份规格写到已建好的表（同样的行号覆盖写入）。
输出 JSON：url、doc_id、sheet_id、写入行数、上传图片数、失败项。
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_table import popo  # noqa: E402

BATCH = 900  # sheet.batchSetCells takes at most 1000 cells per call.


def table(doc, command, payload):
    try:
        try:
            return popo('doc_execute_table', docId=doc, command={'type': command, 'payload': payload})
        except SystemExit:
            # The sheet service now and then answers 操作失败 to a valid command; the same call goes through on retry.
            time.sleep(2)
            return popo('doc_execute_table', docId=doc, command={'type': command, 'payload': payload})
    except SystemExit as error:
        # Say which step failed and which sheet it was, so the same spec can be written again with --doc.
        raise SystemExit(f'{command} 失败（表 {doc}，可修好后用 --doc {doc} 续写）：{error}')


def upload(doc, path):
    """Upload one image through an ASCII-named temporary copy; returns the URL a cell's imageUrl takes."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / (uuid.uuid4().hex + source.suffix.lower())
        shutil.copyfile(source, copy)
        url = popo('doc_upload_local_file', file='@upload:' + str(copy), fileName=source.name, docId=doc)
    return url if isinstance(url, str) else url.get('url')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('spec')
    parser.add_argument('--doc')
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding='utf-8'))
    header_rows, rows = spec.get('header_rows') or [], spec.get('rows') or []
    if not rows:
        raise SystemExit('规格里没有要写的行。')
    if args.doc:
        doc, url = args.doc, None
    else:
        created = popo('doc_create_doc', docType=2, title=spec['title'])
        doc, url = created['docId'], created.get('url')
        print(json.dumps(dict(created=doc, url=url), ensure_ascii=False), file=sys.stderr, flush=True)
    sheet = popo('doc_execute_table', docId=doc, command={'type': 'workbook.getFullData', 'payload': {}})['sheets'][0]
    sheet_id = sheet['sheetId']
    if spec.get('sheet_name') and sheet['title'] != spec['sheet_name']:
        table(doc, 'workbook.renameSheet', {'sheetId': sheet_id, 'newName': spec['sheet_name']})
    first = len(header_rows)
    need = first + len(rows) + 5
    if sheet.get('rowCount', 0) < need:
        table(doc, 'sheet.insertRows', {'sheetId': sheet_id, 'startRowIndex': sheet.get('rowCount', 0), 'count': min(1000, need - sheet.get('rowCount', 0))})
    columns = 1 + max([len(row) - 1 for row in header_rows] + [int(col) for row in rows for col in list(row.get('cells', {})) + list(row.get('images', {}))] + [0])
    if sheet.get('colCount', 0) < columns:
        table(doc, 'sheet.insertCols', {'sheetId': sheet_id, 'startColIndex': sheet.get('colCount', 0), 'count': columns - sheet.get('colCount', 0)})
    warnings = []
    for col, width in (spec.get('col_widths') or {}).items():
        try:  # Cosmetic: a width the sheet refuses must not stop the rows from being written.
            table(doc, 'sheet.resizeCols', {'sheetId': sheet_id, 'col': int(col), 'width': int(width)})
        except SystemExit as error:
            warnings.append(f'第 {int(col) + 1} 列宽度没调成：{str(error)[-120:]}')

    cells = []
    for r, values in enumerate(header_rows):
        cells += [{'row': r, 'col': c, 'value': value, 'style': {'bold': r == first - 1}} for c, value in enumerate(values) if value not in (None, '')]
    dropdowns = {int(col): items for col, items in (spec.get('dropdowns') or {}).items() if items}
    for i, row in enumerate(rows):
        r = first + i
        filled = {int(col): value for col, value in row.get('cells', {}).items()}
        for c, items in dropdowns.items():
            cell = {'row': r, 'col': c, 'dropdown': {'items': items}}
            if filled.get(c) not in (None, ''):
                cell['value'] = filled.pop(c)
            cells.append(cell)
        cells += [{'row': r, 'col': c, 'value': value, 'style': {'wrap': 'wrap', 'verticalAlign': 'top'}} for c, value in filled.items() if value not in (None, '')]
    for start in range(0, len(cells), BATCH):
        table(doc, 'sheet.batchSetCells', {'sheetId': sheet_id, 'cells': cells[start:start + BATCH]})

    failures, uploaded, image_cells = [], 0, []
    height = int(spec.get('image_height') or 120)
    for i, row in enumerate(rows):
        r = first + i
        if not row.get('images') and not row.get('more_images'):
            continue
        for col, path in row.get('images', {}).items():
            try:
                image_cells.append({'row': r, 'col': int(col), 'imageUrl': upload(doc, path)})
                uploaded += 1
            except (OSError, SystemExit) as error:
                failures.append(dict(row=r + 1, image=str(path), error=str(error)[:300]))
        links = []
        for path in row.get('more_images') or []:
            try:
                links.append(upload(doc, path))
                uploaded += 1
            except (OSError, SystemExit) as error:
                failures.append(dict(row=r + 1, image=str(path), error=str(error)[:300]))
        if links and row.get('more_col') is not None:
            col = int(row['more_col'])
            note = str(row.get('cells', {}).get(str(col), '') or '')
            extra = '\n'.join(f'截图{len(row.get("images", {})) + n + 1}：{link}' for n, link in enumerate(links))
            image_cells.append({'row': r, 'col': col, 'value': (note + '\n' + extra).strip()})
        try:  # Cosmetic like column widths: a refused row height must not throw away the images already uploaded.
            table(doc, 'sheet.resizeRows', {'sheetId': sheet_id, 'row': r, 'height': height})
        except SystemExit as error:
            warnings.append(f'第 {r + 1} 行行高没调成：{str(error)[-120:]}')
    for start in range(0, len(image_cells), BATCH):
        table(doc, 'sheet.batchSetCells', {'sheetId': sheet_id, 'cells': image_cells[start:start + BATCH]})
    print(json.dumps(dict(url=url or f'https://docs.popo.netease.com/lingxi/{doc}', doc_id=doc, sheet_id=sheet_id, rows=len(rows), images=uploaded,
                          failures=failures, warnings=warnings), ensure_ascii=False))


if __name__ == '__main__':
    main()
