"""Synthetic, source-indexed partial quotations; no recordings or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

import agent_cli
import agent_protocol as agent
import recorder
from review_runtime import session_review_payload
import visual_nodes


class QuoteWordsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / '资料库 空格' / '场次' / 'word-fixture'
        self.folder.mkdir(parents=True)
        self.meta = dict(id='word-fixture', game='合成词级引用', state='可回看',
                         test=True, transcription_state='ready', media=dict(duration=300))
        self.segment = dict(start=10, end=190, text='  很突兀。  这个入口是什么？ ', speaker_id=0,
                            words=[dict(start=10, end=10.4, word=' 很'),
                                   dict(start=10.4, end=11, word='突兀。'),
                                   dict(start=188, end=188.4, word=' 这个'),
                                   dict(start=188.4, end=188.8, word='入口'),
                                   dict(start=188.8, end=189, word='是'),
                                   dict(start=189, end=190, word='什么？ ')])
        self.segments = [deepcopy(self.segment), dict(start=200, end=201, text='无词级时间戳。')]
        recorder.write(self.folder / 'session.json', self.meta)
        (self.folder / '录像.mp4').write_bytes(b'Synthetic placeholder, not a playable recording')
        (self.folder / '复盘.md').write_text('用户原笔记', encoding='utf-8')
        self.publish()

    def publish(self):
        recorder.write(self.folder / '录像.whisper.json', dict(segments=self.segments))
        self.manifest = agent.publish_ready(self.folder)

    def candidate(self, first=2, stop=6, start=188, end=190, kind='quote_words'):
        return dict(version=1, session_id=self.meta['id'], revision=self.manifest['revision'],
                    summary='合成局部原话分析。',
                    coverage=dict(video_ranges=[], transcript='full', inputs='none', limitations=[]),
                    events=[dict(id='e1', start=start, end=end, title='询问入口含义',
                                 summary='记录者询问入口含义。', context='', basis='explicit', kind='question',
                                 evidence=[dict(kind=kind, ref='t000001', word_range=[first, stop])])],
                    questions=[], ideas=[])

    def reference(self, value):
        return agent.validate_result(self.folder, value)['events'][0]['evidence'][0]

    def test_long_gap_is_not_inherited_by_word_selection_or_automatically_split(self):
        value = self.candidate()
        first = self.candidate(0, 2, 10, 11)['events'][0]
        first.update(id='e0', title='评价突兀')
        value['events'].insert(0, first)
        before = (self.folder / '录像.whisper.json').read_bytes()
        result = agent.validate_result(self.folder, value)
        refs = [event['evidence'][0] for event in result['events']]
        self.assertEqual([(r['ref'], r['word_range'], r['start'], r['end']) for r in refs],
                         [('t000001', [0, 2], 10, 11), ('t000001', [2, 6], 188, 190)])
        self.assertEqual([r['text'] for r in refs], [' 很突兀。', ' 这个入口是什么？ '])
        self.assertEqual([r['speaker_id'] for r in refs], [0, 0])
        # An explicit selection spanning both groups retains the original gap.
        broad = self.reference(self.candidate(0, 6, 10, 190))
        self.assertEqual((broad['start'], broad['end']), (10, 190))
        self.assertEqual((self.folder / '录像.whisper.json').read_bytes(), before)

    def test_forged_display_fields_are_rederived_and_selector_survives_roundtrip(self):
        value = self.candidate()
        value['events'][0]['evidence'][0].update(start=0, end=1, text='forged', speaker_id=55)
        result = agent.validate_result(self.folder, value)
        ref = result['events'][0]['evidence'][0]
        self.assertEqual(ref, dict(kind='quote_words', ref='t000001', word_range=[2, 6],
                                   start=188, end=190, text=' 这个入口是什么？ ', speaker_id=0))
        self.assertEqual(agent.validate_result(self.folder, result), result)

    def test_full_quote_remains_full_and_partial_quote_requires_full_containment(self):
        with self.assertRaisesRegex(ValueError, '事件时间段'):
            self.reference(self.candidate(kind='quote'))
        ref = self.reference(self.candidate(start=10, end=190, kind='quote'))
        self.assertEqual((ref['start'], ref['end'], ref['text']),
                         (10, 190, self.segment['text']))
        self.assertNotIn('word_range', ref)
        for start, end in ((188.1, 190), (188, 189.9)):
            with self.assertRaisesRegex(ValueError, '事件时间段'):
                self.reference(self.candidate(start=start, end=end))

    def test_missing_or_malformed_words_only_disable_partial_quotes(self):
        cases = [None, [], 'invalid', [None], [dict(start=10, end=11, word='')]]
        for words in cases:
            with self.subTest(words=words):
                self.segments[0] = deepcopy(self.segment)
                if words is None:
                    self.segments[0].pop('words')
                else:
                    self.segments[0]['words'] = words
                self.publish()
                self.assertEqual(self.reference(self.candidate(start=10, end=190, kind='quote'))['text'],
                                 self.segment['text'])
                with self.assertRaises(ValueError):
                    agent.quote_words(self.folder, 't000001')
                with self.assertRaises(ValueError):
                    self.reference(self.candidate())
        with self.assertRaises(ValueError):
            agent.quote_words(self.folder, 't000002')

    def test_entire_original_word_array_is_validated_without_filtering_bad_tokens(self):
        changes = [dict(start=float('nan')), dict(end=float('inf')), dict(start=True),
                   dict(end=False), dict(start='10'), dict(start=-1), dict(end=301),
                   dict(start=11, end=10), dict(start=9.94), dict(end=190.06),
                   dict(word=None), dict(word=''), dict(word=' \t '),
                   dict(word='bad\x00text'), dict(word='改写'), dict(word='x' * 20001)]
        for change in changes:
            with self.subTest(change=list(change)):
                self.segments[0] = deepcopy(self.segment)
                # The bad word is deliberately outside the requested [2, 6).
                self.segments[0]['words'][0].update(change)
                self.publish()
                with self.assertRaises(ValueError):
                    self.reference(self.candidate())
                with self.assertRaises(ValueError):
                    agent.quote_words(self.folder, 't000001', 2, 4)
                self.reference(self.candidate(start=10, end=190, kind='quote'))
        self.segments[0] = deepcopy(self.segment)
        self.segments[0]['words'][1].update(start=9.99)
        self.publish()
        with self.assertRaises(ValueError):
            self.reference(self.candidate())

    def test_ranges_reject_nonintegers_empty_reversed_and_out_of_bounds(self):
        invalid = [None, '2,6', (2, 6), [], [2], [0, 2, 6], [True, 6], [0, False],
                   [2.0, 6], [2, '6'], [-1, 6], [2, 2], [6, 2], [0, 7]]
        for selected in invalid:
            with self.subTest(selected=selected):
                value = self.candidate()
                value['events'][0]['evidence'][0]['word_range'] = selected
                with self.assertRaises(ValueError):
                    self.reference(value)
        for ref in (None, [], 'missing', 't1', 't000000', 't000003'):
            with self.subTest(ref=ref):
                value = self.candidate()
                value['events'][0]['evidence'][0]['ref'] = ref
                with self.assertRaises(ValueError):
                    self.reference(value)
                with self.assertRaises(ValueError):
                    agent.quote_words(self.folder, ref)
        value = self.candidate()
        value['revision'] = 'other'
        with self.assertRaises(ValueError):
            self.reference(value)
        value = self.candidate()
        value['coverage']['transcript'] = 'none'
        with self.assertRaises(ValueError):
            self.reference(value)

    def test_query_pages_keep_original_indices_and_never_change_source(self):
        before = (self.folder / '录像.whisper.json').read_bytes()
        first = agent.quote_words(self.folder, 't000001', 0, 2)
        self.assertEqual(first['session_id'], self.meta['id'])
        self.assertEqual(first['revision'], self.manifest['revision'])
        self.assertEqual(first['ref'], 't000001')
        self.assertEqual(first['parent'], {k: self.segment[k] for k in ('start', 'end', 'text', 'speaker_id')})
        self.assertEqual((first['total'], first['offset'], first['next_offset']), (6, 0, 2))
        second = agent.quote_words(self.folder, 't000001', first['next_offset'], 3)
        last = agent.quote_words(self.folder, 't000001', second['next_offset'], 200)
        words = first['words'] + second['words'] + last['words']
        self.assertEqual([r['index'] for r in words], list(range(6)))
        self.assertEqual([r['text'] for r in words], [r['word'] for r in self.segment['words']])
        self.assertIsNone(last['next_offset'])
        empty = agent.quote_words(self.folder, 't000001', 6, 2)
        self.assertEqual(empty['words'], [])
        self.assertIsNone(empty['next_offset'])
        self.assertEqual((self.folder / '录像.whisper.json').read_bytes(), before)
        for offset, limit in ((-1, 2), (7, 2), (True, 2), (0.0, 2),
                              (0, True), (0, 0), (0, 201), (0, 2.0)):
            with self.subTest(offset=offset, limit=limit):
                with self.assertRaises(ValueError):
                    agent.quote_words(self.folder, 't000001', offset, limit)

    def test_overlaps_use_selected_envelope_zero_duration_and_parent_tolerance_are_preserved(self):
        self.segments[0]['words'][0].update(start=9.95, end=11.5)
        self.segments[0]['words'][1].update(start=10.4, end=10.4)
        self.segments[0]['words'][-1].update(end=190.05)
        self.publish()
        ref = self.reference(self.candidate(0, 2, 9.95, 11.5))
        self.assertEqual((ref['start'], ref['end']), (9.95, 11.5))
        zero = self.reference(self.candidate(1, 2, 10.4, 10.4))
        self.assertEqual((zero['start'], zero['end']), (10.4, 10.4))
        last = self.reference(self.candidate(5, 6, 189, 190.05))
        self.assertEqual(last['end'], 190.05)
        self.assertEqual(agent.quote_words(self.folder, 't000001')['words'][0]['start'], 9.95)
        # A parent tolerance never allows values outside the video itself.
        self.segments[0]['end'] = 300
        self.segments[0]['words'][-1]['end'] = 300.001
        self.publish()
        with self.assertRaises(ValueError):
            agent.quote_words(self.folder, 't000001')

    def test_default_evidence_and_visual_context_do_not_expand_words(self):
        with patch('agent_protocol._quote_word_source', side_effect=AssertionError('not on demand')):
            evidence = agent.evidence(self.folder, 100, 110)
            self.assertEqual(evidence['transcript'][0]['text'], self.segment['text'])
            self.assertNotIn('words', evidence['transcript'][0])
            nodes = [dict(start=100, end=110)]
            visual_nodes._context(self.folder, self.meta, 300, nodes)
        self.assertEqual(nodes[0]['transcript'][0]['id'], 't000001')
        self.assertNotIn('words', nodes[0]['transcript'][0])

    def test_query_rejects_revision_change_while_reading(self):
        ready = agent._ready(self.folder)
        changed = (ready[0], ready[1], 'new revision', ready[3])
        with patch('agent_protocol._ready', side_effect=[ready, changed]):
            with self.assertRaisesRegex(ValueError, '读取期间'):
                agent.quote_words(self.folder, 't000001')

    def test_validate_submit_status_review_and_export_keep_local_word_selection(self):
        before = {name: (self.folder / name).read_bytes()
                  for name in ('session.json', '录像.whisper.json', '录像.mp4', '复盘.md')}
        candidate = self.candidate()
        expected = self.reference(candidate)
        job = agent.claim(self.folder, 'synthetic-word-worker')
        receipt = agent.submit(self.folder, job['token'], candidate)
        self.assertEqual((receipt['state'], receipt['events']), ('complete', 1))
        on_disk = recorder.read(self.folder / agent.RESULT)
        self.assertEqual(on_disk['events'][0]['evidence'][0], expected)
        state = agent.preprocessing_status(self.folder, include_result=True)
        self.assertEqual(state['state'], 'complete')
        self.assertEqual(state['result']['events'][0]['evidence'][0], expected)
        self.assertEqual(agent.validate_result(self.folder, on_disk), state['result'])
        payload = session_review_payload(self.folder)
        self.assertEqual(payload['preprocessing']['result']['events'][0]['evidence'][0], expected)
        self.assertEqual(payload['segments'][0]['text'], self.segment['text'])
        self.assertEqual((payload['segments'][0]['start'], payload['segments'][0]['end']), (10, 190))
        with zipfile.ZipFile(recorder.Session(self.folder).package()) as archive:
            result = json.loads(archive.read('场次/word-fixture/体验事件.json'))
            self.assertEqual(result['events'][0]['evidence'][0], expected)
            page = archive.read('场次/word-fixture/独立回看.html').decode('utf-8')
            self.assertIn('"word_range": [2, 6]', page)
            self.assertIn('这个入口是什么', page)
            self.assertFalse(any('agent-' in name for name in archive.namelist()))
        for name, content in before.items():
            self.assertEqual((self.folder / name).read_bytes(), content)

    def test_cli_word_query_is_bounded_and_failure_is_structured(self):
        # Embedded Python's ._pth can prefer its installed app over this checkout.
        # Exercise the real CLI subprocess with its matching source dependencies.
        cli = Path(agent_cli.__file__).resolve()
        bootstrap = (f'import runpy,sys;sys.path.insert(0,{str(cli.parent)!r});'
                     f'sys.argv=[{str(cli)!r},*sys.argv[1:]];'
                     f'runpy.run_path({str(cli)!r},run_name="__main__")')
        command = [sys.executable, '-I', '-B', '-c', bootstrap, 'quote-words', str(self.folder),
                   '--ref', 't000001', '--offset', '2', '--limit', '2']
        run = subprocess.run(command, capture_output=True, encoding='utf-8', creationflags=recorder.HIDDEN)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        value = json.loads(run.stdout)['data']
        self.assertEqual([word['index'] for word in value['words']], [2, 3])
        self.assertEqual(value['next_offset'], 4)
        command[-1] = '201'
        run = subprocess.run(command, capture_output=True, encoding='utf-8', creationflags=recorder.HIDDEN)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(json.loads(run.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
