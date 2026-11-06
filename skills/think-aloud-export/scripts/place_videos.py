"""把操作记录视频作为附件放进已写好的 POPO 表格：表格只显示文件名，点开全屏播放。

POPO 的表格接口写不出附件卡片（照原样写回也只显示文字），网页上把文件拖进单元格才行。所以这里用 ego 浏览器：
键盘选中目标格，再模拟把文件拖进去，不弹系统文件窗口。文件落在当前选中的格子，所以每放一个都回读这一格，
不对就停下，不继续往下放。没有 ego 或中途失败时，视频都已按编号存好，汇报里列出没放上的行，用户手动拖进去。

用法："$PY" -B -X utf8 place_videos.py <videos.json> --doc <docId> --work <工作目录>
videos.json：[{"row": 行号（从 0 起）, "col": 列号（从 0 起）, "file": "本地 mp4 路径"}]，按表里的先后排，编号照这个顺序。
输出 JSON：folder（按编号存好的视频）、placed、skipped（目标格已有内容）、failed（没放上，含原因）。
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_table import popo  # noqa: E402

PREFIX = '操作记录录屏'
UPLOAD_SECONDS = 90
# An empty spot in the sheet to take keyboard focus; a click only selects, and Ctrl+Home follows at once.
FOCUS = (1600, 700)


def video_name(number):
    """Short on purpose: the cell shows the name cut to the column width and cannot wrap, so the fixed part must say what it is."""
    return f'{PREFIX}{number:02d}.mp4'


def attachment_name(cell):
    if not cell or cell.get('cellType') != 'attachment':
        return None
    return cell['value']['richText'][0]['style']['e']['attachment']['name']


def plan(jobs, cells):
    """Number every video in order, and set aside targets that already hold something so nothing gets overwritten."""
    filled = {(cell['row'], cell['col']): attachment_name(cell) for cell in cells if cell.get('value') not in (None, '')}
    ready, skipped, done = [], [], []
    for number, job in enumerate(jobs, 1):
        item = dict(job, name=video_name(number))
        where = (job['row'], job['col'])
        (ready if where not in filled else done if filled[where] == item['name'] else skipped).append(item)
    return ready, skipped, done


def script(url, job, path, first):
    """One round in ego: select the cell by keyboard, then drop the file on the sheet."""
    arrows = f"for (let i = 0; i < {job['row']}; i++) await page.keyboard.press('ArrowDown');\nfor (let i = 0; i < {job['col']}; i++) await page.keyboard.press('ArrowRight');"
    opening = f"await page.goto({json.dumps(url)});\nawait page.waitForTimeout(6000);\n" if first else ''
    return f"""const task = await taskSpace("think aloud export");
const page = task.page("p1");
{opening}await page.mouse.click({FOCUS[0]}, {FOCUS[1]}, {{ label: "focus the sheet" }});
await page.keyboard.press("Control+Home");
await page.waitForTimeout(200);
{arrows}
await page.waitForTimeout(300);
const data = {{ items: [], files: [{json.dumps(str(path))}], dragOperationsMask: 1 }};
for (const type of ["dragEnter", "dragOver", "drop"]) {{
  await page.cdp("Input.dispatchDragEvent", {{ type, x: {FOCUS[0]}, y: {FOCUS[1]}, data }});
  await page.waitForTimeout(200);
}}
"""


def read_cells(doc):
    # The sheet service now and then answers 操作失败 to a valid command; the same call goes through on retry.
    for attempt in range(4):
        try:
            return popo('doc_execute_table', docId=doc, command={'type': 'workbook.getFullData', 'payload': {}})['sheets'][0]['cells']
        except SystemExit:
            if attempt == 3:
                raise
            time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('videos')
    parser.add_argument('--doc', required=True)
    parser.add_argument('--work', required=True)
    args = parser.parse_args()
    jobs = json.loads(Path(args.videos).read_text(encoding='utf-8'))
    folder = Path(args.work).resolve() / 'videos'
    folder.mkdir(parents=True, exist_ok=True)
    ready, skipped, done = plan(jobs, read_cells(args.doc))
    for item in ready + skipped + done:
        shutil.copyfile(item['file'], folder / item['name'])
    report = dict(folder=str(folder), placed=[dict(row=i['row'] + 1, col=i['col'] + 1, name=i['name']) for i in done], skipped=[dict(row=i['row'] + 1, col=i['col'] + 1, name=i['name'], reason='目标格已有内容') for i in skipped], failed=[])
    ego = shutil.which('ego-browser')
    url = f'https://docs.popo.netease.com/lingxi/{args.doc}'
    stop = None if ego else '没有 ego 浏览器'
    round_file = Path(args.work).resolve() / 'place-round.mjs'
    for index, item in enumerate(ready):
        if stop:
            report['failed'].append(dict(row=item['row'] + 1, col=item['col'] + 1, name=item['name'], reason=stop))
            continue
        round_file.write_text(script(url, item, folder / item['name'], index == 0), encoding='utf-8')
        run = subprocess.run([ego, 'nodejs', '-e', f"await import({json.dumps(round_file.as_uri())})"], capture_output=True, text=True, encoding='utf-8', errors='replace')
        landed = None
        for _ in range(UPLOAD_SECONDS // 3):
            time.sleep(3)
            landed = next((c for c in read_cells(args.doc) if attachment_name(c) == item['name']), None)
            if landed:
                break
        where = (landed['row'], landed['col']) if landed else None
        if where == (item['row'], item['col']):
            report['placed'].append(dict(row=item['row'] + 1, col=item['col'] + 1, name=item['name']))
            continue
        stop = f'{item["name"]} 落到了第 {where[0] + 1} 行第 {where[1] + 1} 列' if where else f'{item["name"]} 没有放上：{(run.stderr or run.stdout)[-160:].strip()}'
        report['failed'].append(dict(row=item['row'] + 1, col=item['col'] + 1, name=item['name'], reason=stop))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
