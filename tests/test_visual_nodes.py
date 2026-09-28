"""Real decode/encode fixtures; no OBS, private installation, or model calls."""
from fractions import Fraction
import hashlib
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import av
import numpy as np

import visual_nodes as visual


class VisualNodesTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'library' / '场次' / 'fixture'
        self.folder.mkdir(parents=True)
        self.out = self.root / 'evidence'
        self.meta = dict(id='fixture', game='合成画面 </script>', state='可回看',
                         media=dict(duration=3.0), input_offset_seconds=.3,
                         settings=dict(token='private-secret-sentinel'))
        self.write('session.json', self.meta)
        self.write('录像.whisper.json', dict(segments=[dict(start=.6, end=1.2, text=' 原话 </script><img> ')]))
        self.write('input-events.json', dict(version=1, state='complete', duration=3,
            timebase='video_seconds', recording_scope='all', gaps=[], window_states=[],
            intervals=[dict(id='raw1', start=.5, end=.7, device='keyboard', code='KeyA', label='A')]))
        (self.folder / '复盘.md').write_text('保留原有笔记', encoding='utf-8')
        self.pts = [0, 100, 230, 400, 580, 620, 670, 850, 1100, 1500, 1900, 2300, 2700, 2950]
        self.video()
        self.original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.iterdir()}

    def write(self, name, value):
        (self.folder / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def video(self):
        with av.open(str(self.folder / '录像.mp4'), 'w') as output:
            stream = output.add_stream('mpeg4', rate=30)
            stream.width, stream.height = 160, 90
            stream.pix_fmt = 'yuv420p'
            stream.codec_context.max_b_frames = 0
            stream.codec_context.time_base = Fraction(1, 1000)
            for t in self.pts:
                rgb = np.zeros((90, 160, 3), np.uint8)
                if 600 <= t < 800:
                    rgb[25:65, 50:110] = 245
                frame = av.VideoFrame.from_ndarray(rgb, format='rgb24')
                frame.pts, frame.time_base = t, Fraction(1, 1000)
                for packet in stream.encode(frame): output.mux(packet)
            for packet in stream.encode(None): output.mux(packet)

    def extract(self, **options):
        value = visual.extract(self.folder, self.out, **options)
        return value, json.loads(Path(value['index']).read_text(encoding='utf-8'))

    def test_vfr_short_popup_images_actual_times_and_read_only_sources(self):
        value, index = self.extract()
        actual = []
        with av.open(str(self.folder / '录像.mp4')) as video:
            origin = (video.start_time or 0) / av.time_base
            for frame in video.decode(video=0): actual.append(float(frame.pts * frame.time_base) - origin)
        self.assertEqual(index['stats']['decoded_frames'], len(actual))
        self.assertTrue(any(n['kind'] == 'transient' for n in index['nodes']))
        selected = [f for n in index['nodes'] for f in n['frames'] if f['path']]
        self.assertTrue(any(.6 <= f['time'] < .8 for f in selected))
        for frame in selected:
            self.assertIn(frame['time'], actual)
            with av.open(str(self.out / frame['path'])) as image:
                self.assertEqual(next(image.decode(video=0)).width, 160)
        self.assertEqual(self.original, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.iterdir()})
        self.assertNotIn('private-secret-sentinel', json.dumps(index))
        html = Path(value['review']).read_text(encoding='utf-8')
        self.assertNotIn('原话 </script>', html)
        self.assertIn('\\u003c/script>', html)
        read = visual.read_index(value['index'], limit=1)
        self.assertEqual(len(read['nodes']), 1)
        self.assertEqual(read['next_offset'], 1)

    def test_budget_keeps_candidates_and_partial_context_explicit(self):
        _, index = self.extract(max_images=1)
        self.assertGreater(len(index['nodes']), 1)
        self.assertEqual(index['coverage']['selected_images'], 1)
        self.assertGreater(index['coverage']['unpictured_nodes'], 0)
        self.assertEqual(len(list((self.out / 'images').glob('*.jpg'))), 1)
        self.assertEqual(index['context']['inputs']['alignment']['offset_seconds'], .3)
        linked = [n for n in index['nodes'] if n['input_summary']['count']]
        self.assertTrue(linked)
        self.assertTrue(any(n['transcript'] for n in index['nodes']))

    def test_cli_read_is_bounded_json_and_rejects_invalid_pagination(self):
        import agent_cli
        value, _ = self.extract()
        output = io.StringIO()
        with redirect_stdout(output):
            status = agent_cli.main(['visual-read', value['index'], '--limit', '1'])
        self.assertEqual(status, 0)
        reply = json.loads(output.getvalue())
        self.assertTrue(reply['ok'])
        self.assertEqual(len(reply['data']['nodes']), 1)
        for options in (dict(limit=101), dict(offset=-1), dict(start=1)):
            with self.assertRaises(ValueError): visual.read_index(value['index'], **options)

    def test_missing_transcript_still_extracts_and_stale_revision_is_rejected(self):
        # Move our synthetic fixture only; production never removes transcript data.
        (self.folder / '录像.whisper.json').rename(self.root / 'saved-transcript.json')
        value, index = self.extract()
        self.assertTrue(any('尚无逐字稿' in s for s in index['coverage']['notes']))
        self.meta['input_offset_seconds'] = .7
        self.write('session.json', self.meta)
        with self.assertRaisesRegex(ValueError, '过期'):
            visual.read_index(value['index'])

    def test_invalid_ranges_and_library_outputs_do_not_write(self):
        for opts in (dict(start=-1), dict(end=4), dict(start=2,end=1), dict(end=float('nan')),
                     dict(max_images=0), dict(max_images=501)):
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                visual.extract(self.folder, self.out, **opts)
            self.assertFalse(self.out.exists())
        with self.assertRaisesRegex(ValueError, '资料库以外'):
            visual.extract(self.folder, self.folder.parent / 'output')

    def test_preserves_completed_output_and_failure_diagnostics(self):
        self.extract()
        old = (self.out / 'index.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '已存在'): self.extract()
        self.assertEqual(old, (self.out / 'index.json').read_bytes())
        failed = self.root / 'failed'
        with patch.object(visual, '_jpeg', side_effect=ValueError('synthetic encoder failure')):
            with self.assertRaisesRegex(ValueError, 'encoder'):
                visual.extract(self.folder, failed)
        self.assertEqual(json.loads((failed / 'status.json').read_text())['state'], 'failed')
        self.assertFalse((failed / 'index.json').exists())

    def test_node_index_limit_disclosed_even_though_all_frames_scanned(self):
        _, index = self.extract(config=dict(max_nodes=2))
        self.assertEqual(index['stats']['decoded_frames'], len(self.pts))
        self.assertFalse(index['coverage']['node_index_complete'])
        self.assertTrue(any('上限' in s for s in index['coverage']['notes']))

    def test_early_eof_is_not_claimed_complete(self):
        self.meta['media']['duration'] = 6
        self.write('session.json', self.meta)
        _, index = self.extract()
        self.assertFalse(index['coverage']['complete'])
        self.assertTrue(any('文件末尾' in s for s in index['coverage']['notes']))

    def test_vfr_range_between_frames_keeps_real_boundary_pts(self):
        _, index = self.extract(start=.70, end=.80)
        self.assertAlmostEqual(index['stats']['preceding_boundary_frame'], .67, places=3)
        frames = [f for n in index['nodes'] for f in n['frames']]
        self.assertTrue(frames)
        self.assertTrue(all(abs(f['time'] - .67) < .001 for f in frames))
        self.assertTrue(all(f.get('boundary_context') for f in frames))
        self.assertTrue(index['coverage']['complete'])
        self.assertAlmostEqual(index['nodes'][-1]['end'], .8)
        self.assertTrue(visual.read_index(self.out / 'index.json', start=.75, end=.79)['nodes'])

    def test_short_tail_gap_is_reported_without_hidden_tolerance(self):
        self.meta['media']['duration'] = 3.06
        self.write('session.json', self.meta)
        _, index = self.extract()
        self.assertFalse(index['coverage']['complete'])
        tail = index['coverage']['uncovered_ranges'][-1]
        self.assertLess(tail['end'] - tail['start'], .1)
        self.assertGreater(tail['end'] - tail['start'], 0)

    def test_loopback_viewer_byte_ranges_and_no_directory_access(self):
        value, _ = self.extract()
        server = visual.review_server(value['index'])
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = server.review_url
            with urlopen(base) as response:
                html = response.read().decode('utf-8')
            self.assertNotIn(self.folder.as_uri() + '/', html)
            raw = (self.folder / '录像.mp4').read_bytes()
            with urlopen(Request(base + 'video.mp4', headers={'Range':'bytes=10-29'})) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), raw[10:30])
            for route in ('index.json', '../session.json', 'images/../../session.json'):
                with self.assertRaises(HTTPError) as error: urlopen(base + route)
                self.assertEqual(error.exception.code, 404)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + 'video.mp4', headers={'Range':'bytes=999999999-'}))
            self.assertEqual(error.exception.code, 416)
            self.meta['input_offset_seconds'] = .9
            self.write('session.json', self.meta)
            for route in ('', 'video.mp4'):
                with self.assertRaises(HTTPError) as error: urlopen(base + route)
                self.assertEqual(error.exception.code, 409)
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
