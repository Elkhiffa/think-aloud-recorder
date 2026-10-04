"""Machine-readable local bridge. No model, watcher, upload or credential use."""
from session_metadata import session_title
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

# Embedded portable Python can put its own app before the invoked script's
# directory. Keep this CLI and its protocol from the same checkout/install.
sys.path.insert(0, str(Path(__file__).resolve().parent))
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
                                 title=session_title(meta),
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
    for action in ('status', 'preview', 'apply'):
        command = commands.add_parser('vocabulary-' + action, help='本机预设词库快照：回读、预览或应用；需要运行中的记录器')
        command.add_argument('--app-root', default=str(Path(__file__).resolve().parent))
        if action == 'apply':
            command.add_argument('--plan', required=True, help='vocabulary-preview 保存的计划 JSON')
        else:
            command.add_argument('--preset', required=action == 'preview', help='稳定预设 ID')
            command.add_argument('--source', action='append', default=[], help='词库目录中的 TXT 文件名；可重复指定')
            if action == 'preview':
                command.add_argument('--output', required=True, help='在工作目录保存计划；不覆盖已有文件')
    discovery = commands.add_parser('scan', help='扫描已就绪场次；--publish 为旧场次补发信号')
    discovery.add_argument('database')
    discovery.add_argument('--publish', action='store_true')
    discovery.add_argument('--include-test', action='store_true')
    visual = commands.add_parser('visual-nodes', help='本地逐帧检测画面变化；不调用模型，不写入场次')
    visual.add_argument('session')
    visual.add_argument('--output', required=True, help='资料库之外的新输出目录')
    visual.add_argument('--start', type=float, default=0)
    visual.add_argument('--end', type=float)
    visual.add_argument('--max-images', type=int, default=120)
    visual.add_argument('--image-mode', choices=('sequential','seek'), default='sequential',
                        help='配图解码方式；seek 严格复现已选帧，检测仍逐帧进行')
    visual_read = commands.add_parser('visual-read', help='分页读取候选索引和图片路径')
    visual_read.add_argument('index')
    visual_read.add_argument('--start', type=float)
    visual_read.add_argument('--end', type=float)
    visual_read.add_argument('--offset', type=int, default=0)
    visual_read.add_argument('--limit', type=int, default=40)
    visual_overview = commands.add_parser('visual-overview', help='完整时间范围的紧凑导航；不展开原话、图片或低层节点')
    visual_overview.add_argument('index')
    visual_overview.add_argument('--bins', type=int, default=32)
    candidates = commands.add_parser('visual-candidates', help='紧凑读取短区间内的主要与弱候选；不展开原话或整段运动树')
    candidates.add_argument('index')
    candidates.add_argument('--start',type=float,required=True)
    candidates.add_argument('--end',type=float,required=True)
    candidates.add_argument('--offset',type=int,default=0)
    candidates.add_argument('--limit',type=int,default=24)
    candidates.add_argument('--level',choices=('all','primary','weak'),default='all')
    candidates.add_argument('--parent',help='仅在 --level weak 时按主要候选 ID 展开')
    candidates.add_argument('--image-stats',action='store_true',help='按需读取最多12张已有JPEG的像素统计，不解码视频')
    visual_plan = commands.add_parser('visual-plan', help='复用已有索引，分组并建立首轮、补图和复核共用的预算')
    visual_plan.add_argument('index')
    visual_plan.add_argument('--output', required=True)
    visual_plan.add_argument('--total-views', type=int, default=24)
    visual_plan.add_argument('--initial-views', type=int, default=12)
    visual_plan.add_argument('--review-views', type=int, default=4)
    visual_packet = commands.add_parser('visual-packet', help='带问题领取一小包画面；不调用模型')
    visual_packet.add_argument('plan')
    visual_packet.add_argument('--request-id', required=True)
    visual_packet.add_argument('--phase', required=True, choices=('initial','inspect','review'))
    visual_packet.add_argument('--question', required=True)
    visual_packet.add_argument('--at', action='append', type=float)
    visual_packet.add_argument('--start', type=float)
    visual_packet.add_argument('--end', type=float)
    visual_packet.add_argument('--limit', type=int, default=6)
    visual_packet.add_argument('--image-width',type=int,choices=(960,1920),default=960,
                               help='图片最大宽度；1920仅用于需辨认小字的定向补图，不放大原片')
    compare = commands.add_parser('visual-compare', help='短窗内比较局部像素状态，仅输出候选 PTS，不发放图片')
    compare.add_argument('plan')
    compare.add_argument('--request-id', required=True)
    compare.add_argument('--question', required=True)
    compare.add_argument('--start', type=float, required=True)
    compare.add_argument('--end', type=float, required=True)
    compare.add_argument('--region', type=float, nargs=4, metavar=('X','Y','WIDTH','HEIGHT'),
                         help='归一化局部区域，默认全画面；先按原片裁切再比较')
    compare.add_argument('--mode', choices=('candidates','scan'), default='candidates',
                         help='candidates 比较已有候选（最多120秒），scan 明确逐帧细扫（最多30秒）')
    compare.add_argument('--limit', type=int, default=8, help='最多返回1–24个有序像素发生段，截断明确披露')
    visual_budget = commands.add_parser('visual-budget', help='查看本场取材计划的共用预算')
    visual_budget.add_argument('plan')
    extend = commands.add_parser('visual-budget-extend',help='按关键证据需要显式追加额度，保留累计用量')
    extend.add_argument('plan')
    extend.add_argument('--request-id',required=True)
    extend.add_argument('--additional',type=int,required=True)
    extend.add_argument('--reason',required=True)
    visual_review = commands.add_parser('visual-review', help='仅在本机打开候选检查页；Ctrl+C 结束')
    visual_review.add_argument('index')
    visual_review.add_argument('--port', type=int, default=0)
    naming = commands.add_parser('name-activities', help='按已完成事件概括内容，为未命名场次命名或保留手动标题，分别保存短标题与内容详情')
    naming.add_argument('session')
    naming.add_argument('--file', help='工作目录中的活动命名候选 JSON；省略则读取当前命名上下文')
    naming.add_argument('--apply', action='store_true', help='原子保存具体内容标签与名称，保留手动前缀并更新自动摘要；默认仅预览')
    for name in ('publish', 'status', 'evidence', 'quote-words', 'claim', 'reprocess', 'renew', 'fail', 'validate', 'submit', 'frame'):
        command = commands.add_parser(name)
        command.add_argument('session')
        if name in ('renew', 'fail', 'submit'):
            command.add_argument('--token', required=True)
        if name in ('claim', 'reprocess', 'renew'):
            command.add_argument('--seconds', type=int, default=1800)
        if name in ('claim', 'reprocess'):
            command.add_argument('--worker', required=True)
        if name in ('fail', 'reprocess'):
            command.add_argument('--reason', required=True)
        if name in ('validate', 'submit'):
            command.add_argument('--file', required=True, help='工作目录中的候选结果 JSON')
        if name == 'evidence':
            command.add_argument('--start', type=float)
            command.add_argument('--end', type=float)
        if name == 'quote-words':
            command.add_argument('--ref', required=True, help='指定一条原话引用，如 t000040；保留原始词序号')
            command.add_argument('--offset', type=int, default=0)
            command.add_argument('--limit', type=int, default=80, help='每页词数，1–200；默认 80')
        if name == 'frame':
            command.add_argument('--at', type=float, required=True)
            command.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        name = args.command
        if name.startswith('vocabulary-'):
            from vocabulary_ipc import request, MAX_MESSAGE
            action = name.removeprefix('vocabulary-')
            if action == 'apply':
                plan = Path(args.plan)
                if plan.stat().st_size > MAX_MESSAGE:
                    raise ValueError('计划超过 2 MB。')
                payload = dict(action=action, plan=json.loads(plan.read_text(encoding='utf-8-sig')))
            else:
                payload = dict(action=action, preset_id=args.preset, sources=args.source)
            result = request(args.app_root, payload)
            if result.get('ok') and action == 'preview':
                with Path(args.output).open('x', encoding='utf-8') as output:
                    json.dump(result['data'], output, ensure_ascii=False, indent=2, allow_nan=False)
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
            return 0 if result.get('ok') else 1
        elif name == 'scan':
            value = scan(args.database, args.publish, args.include_test)
        elif name == 'visual-nodes':
            from visual_nodes import extract
            def progress(value):
                print(json.dumps(dict(progress=value), ensure_ascii=False), file=sys.stderr, flush=True)
            value = extract(args.session, args.output, start=args.start, end=args.end,
                            max_images=args.max_images, progress=progress, image_mode=args.image_mode)
        elif name == 'visual-read':
            from visual_nodes import read_index
            value = read_index(args.index, start=args.start, end=args.end, offset=args.offset, limit=args.limit)
        elif name == 'visual-overview':
            from visual_nodes import read_overview
            value = read_overview(args.index, bins=args.bins)
        elif name == 'visual-plan':
            from visual_evidence import create_plan
            value = create_plan(args.index, args.output, total=args.total_views,
                                initial=args.initial_views, review=args.review_views)
        elif name == 'visual-candidates':
            from visual_nodes import read_candidates
            value = read_candidates(args.index,start=args.start,end=args.end,offset=args.offset,limit=args.limit,
                                    level=args.level,parent=args.parent,image_stats=args.image_stats)
        elif name == 'visual-packet':
            from visual_evidence import packet
            value = packet(args.plan, args.request_id, phase=args.phase, question=args.question,
                           times=args.at, start=args.start, end=args.end, limit=args.limit,
                           image_width=args.image_width)
        elif name == 'visual-budget':
            from visual_evidence import budget_status
            value = budget_status(args.plan)
        elif name == 'visual-compare':
            from visual_compare import compare
            value = compare(args.plan, args.request_id, question=args.question,
                            start=args.start, end=args.end, region=args.region,
                            mode=args.mode, limit=args.limit)
        elif name == 'visual-budget-extend':
            from visual_evidence import extend_budget
            value = extend_budget(args.plan,args.request_id,additional=args.additional,reason=args.reason)
        elif name == 'visual-review':
            from visual_nodes import review_server
            with review_server(args.index, args.port) as server:
                print(json.dumps(dict(ok=True, url=server.review_url)), flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
            return 0
        elif name == 'publish':
            value = protocol.publish_ready(args.session)
        elif name == 'status':
            value = protocol.preprocessing_status(args.session)
        elif name == 'evidence':
            value = protocol.evidence(args.session, args.start, args.end)
        elif name == 'quote-words':
            value = protocol.quote_words(args.session, args.ref, args.offset, args.limit)
        elif name == 'claim':
            value = protocol.claim(args.session, args.worker, args.seconds)
        elif name == 'reprocess':
            value = protocol.reprocess(args.session, args.worker, args.reason, args.seconds)
        elif name == 'renew':
            value = protocol.renew(args.session, args.token, args.seconds)
        elif name == 'fail':
            value = protocol.fail(args.session, args.token, args.reason)
        elif name == 'frame':
            value = frame(args.session, args.at, args.output)
        elif name == 'name-activities':
            candidate = None
            if args.file:
                path = Path(args.file)
                if path.stat().st_size > 65536:
                    raise ValueError('活动命名候选超过64 KB。')
                candidate = json.loads(path.read_text(encoding='utf-8-sig'))
            value = protocol.name_activities(args.session, candidate, apply=args.apply)
        else:
            path = Path(args.file)
            if path.stat().st_size > protocol.MAX_RESULT:
                raise ValueError('候选结果超过 2 MB。')
            candidate = json.loads(path.read_text(encoding='utf-8-sig'))
            if name == 'submit':
                value = protocol.submit(args.session, args.token, candidate)
            else:
                value = protocol.validate_result(args.session, candidate)
                from event_edits import reviewed
                correction_review = reviewed(args.session, candidate)
                if correction_review:
                    value['corrections_review'] = correction_review
        print(json.dumps(dict(ok=True, data=value), ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps(dict(ok=False, error=str(error)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
