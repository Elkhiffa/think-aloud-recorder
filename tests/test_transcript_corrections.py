from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import agent_protocol as protocol
import insight_report
import transcript_corrections as fixes


class TranscriptCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name)

    def make_session(self, ident, text):
        folder = self.vault / '场次' / ident
        folder.mkdir(parents=True)
        protocol._write(folder, 'session.json', dict(id=ident, game='合成游戏', created='2026-10-08T12:00:00+08:00',
                        state='可回看', transcription_state='ready', media=dict(duration=12),
                        input_offset_seconds=1, settings=dict(record_inputs=False)))
        protocol._write(folder, '录像.whisper.json', dict(segments=[dict(start=2, end=4, text=text, speaker_id=0)]))
        (folder / '录像.mp4').write_bytes(b'synthetic video placeholder')
        manifest = protocol.publish_ready(folder)
        result = dict(version=2, session_id=ident, revision=manifest['revision'], summary='合成整理。',
                      coverage=dict(video_ranges=[dict(start=0, end=12)], transcript='full', inputs='none', limitations=['合成数据']),
                      events=[dict(id='e1', start=0, end=12, title='切换页签', summary='焦点跳走。', context='',
                                   basis='explicit', kind='friction', evidence=[dict(kind='quote', ref='t000001')])],
                      questions=[], ideas=[], instances=[
                          dict(id='i1', event_id='e1', said=[dict(kind='quote', ref='t000001')],
                               refers_to=dict(start=2, end=4, basis='same_time'), screen=None, elements=[],
                               kind='obstacle', statement='手柄焦点跳走。', issue_tags=[],
                               evidence=[dict(kind='video', start=3, end=3, observation='合成焦点框。')], confidence='high')])
        job = protocol.claim(folder, 'synthetic-worker')
        protocol.submit(folder, job['token'], result)
        return folder

    def said(self, folder):
        state = protocol.preprocessing_status(folder, include_result=True)
        self.assertEqual(state['state'], 'complete')
        return state['result']['instances'][0]['said'][0]

    def test_confirmed_rule_corrects_quotes_everywhere_without_touching_transcripts(self):
        """触发路径：agent 发现“左焦”是“走焦”的误转写 → 提议全库规则 → 用户看过命中后确认 → 各场引用显示修正后的字，逐字稿和整理结果都不重做。"""
        first = self.make_session('20261008-120000-aaaaaa', '左焦一直跳到右边。')
        second = self.make_session('20261009-120000-bbbbbb', '这个左焦逻辑不直观。')
        raw = {folder: (folder / '录像.whisper.json').read_bytes() for folder in (first, second)}
        revision = protocol._ready(first)[2]
        proposed = fixes.propose(self.vault, [dict(basis='手柄术语；上下文是焦点移动', **{'from': '左焦', 'to': '走焦'})], 'codex-1008')
        self.assertEqual(proposed[0]['hits'], 2)
        # A proposal changes nothing the user sees.
        self.assertNotIn('corrected_text', self.said(first))
        listed = fixes.list_corrections(self.vault)
        self.assertEqual([hit['corrected'] for hit in listed[0]['hits']], ['走焦一直跳到右边。', '这个走焦逻辑不直观。'])
        fixes.decide(self.vault, [proposed[0]['id']], 'confirmed')
        self.assertEqual(self.said(first)['text'], '左焦一直跳到右边。')
        self.assertEqual(self.said(first)['corrected_text'], '走焦一直跳到右边。')
        self.assertEqual(self.said(second)['corrected_text'], '这个走焦逻辑不直观。')
        self.assertEqual(protocol.evidence(first)['transcript'][0]['corrected_text'], '走焦一直跳到右边。')
        for folder, data in raw.items():
            self.assertEqual((folder / '录像.whisper.json').read_bytes(), data)
        self.assertEqual(protocol._ready(first)[2], revision, 'confirming a correction must not make results stale')
        # The transcript in the second session was right after all: exclude it from the rule.
        fixes.exclude(self.vault, proposed[0]['id'], '20261009-120000-bbbbbb', 't000001')
        self.assertNotIn('corrected_text', self.said(second))
        self.assertEqual(self.said(first)['corrected_text'], '走焦一直跳到右边。')

    def test_single_fix_rejection_and_invalid_proposals(self):
        """触发路径：单场 agent 提议一处误听 → 只改这一段；驳回后不生效；对不上逐字稿的提议整批不写。"""
        first = self.make_session('20261008-120000-aaaaaa', '斜视以后再打。')
        second = self.make_session('20261009-120000-bbbbbb', '我斜视看了一眼。')
        once = fixes.propose(self.vault, [dict(basis='战斗术语“卸势”', session_id='20261008-120000-aaaaaa', ref='t000001',
                                               **{'from': '斜视', 'to': '卸势'})], 'claude-1008')[0]
        fixes.decide(self.vault, [once['id']], 'confirmed')
        self.assertEqual(self.said(first)['corrected_text'], '卸势以后再打。')
        self.assertNotIn('corrected_text', self.said(second))
        fixes.decide(self.vault, [once['id']], 'rejected')
        self.assertNotIn('corrected_text', self.said(first))
        before = fixes.read(self.vault)
        with self.assertRaisesRegex(ValueError, '找不到要改的原文'):
            fixes.propose(self.vault, [dict(basis='合成', **{'from': '斜视', 'to': '卸势'}),
                                       dict(basis='合成', **{'from': '不存在的词', 'to': '别的'})], 'claude-1008')
        with self.assertRaisesRegex(ValueError, '同时给出'):
            fixes.propose(self.vault, [dict(basis='合成', session_id='20261008-120000-aaaaaa', **{'from': '斜视', 'to': '卸势'})], 'x')
        self.assertEqual(fixes.read(self.vault), before)

    def test_report_quote_with_confirmed_wording_passes_validation(self):
        """触发路径：跨场次 agent 在报告里引用修正后的原话 → insight-validate 在用户确认前列为对不上，确认后通过，不靠附录表。"""
        folder = self.make_session('20261008-120000-aaaaaa', '左焦一直跳到右边。')
        (self.vault / '洞察').mkdir()
        (self.vault / '洞察' / '手柄.md').write_text(
            '# 手柄\n\n记录者说“走焦一直跳到右边”[1008 i1](i:20261008-120000-aaaaaa/i1)。\n', encoding='utf-8')
        report = insight_report.validate_report(self.vault, '手柄.md')
        self.assertEqual((report['quotes_checked'], len(report['quotes_unverified'])), (1, 1))
        rule = fixes.propose(self.vault, [dict(basis='手柄术语', **{'from': '左焦', 'to': '走焦'})], 'claude')[0]
        fixes.decide(self.vault, [rule['id']], 'confirmed')
        self.assertEqual(insight_report.validate_report(self.vault, '手柄.md')['quotes_unverified'], [])
        # Two confirmed library rules may not correct the same original differently.
        other = fixes.propose(self.vault, [dict(basis='另一种猜测', **{'from': '左焦', 'to': '左键'})], 'codex')[0]
        with self.assertRaisesRegex(ValueError, '已有确认的全库规则'):
            fixes.decide(self.vault, [other['id']], 'confirmed')


if __name__ == '__main__':
    unittest.main()
