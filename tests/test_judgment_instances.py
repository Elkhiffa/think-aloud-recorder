"""Synthetic v2 judgments; no recording, OCR, or real library writes."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

import agent_protocol as agent
import recorder
from review_runtime import session_review_payload


class JudgmentInstanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name)
        self.folder = self.vault / '场次' / 'fixture'
        self.folder.mkdir(parents=True)
        self.meta = dict(id='fixture', game='合成游戏', state='可回看', test=True,
                         transcription_state='ready', media=dict(duration=12))
        recorder.write(self.folder / 'session.json', self.meta)
        recorder.write(self.folder / '录像.whisper.json', dict(segments=[
            dict(start=2, end=4, text='这个入口是什么？', speaker_id=0,
                 words=[dict(start=2, end=2.5, word='这个'), dict(start=2.5, end=3, word='入口'),
                        dict(start=3, end=4, word='是什么？')]),
            dict(start=8, end=10, text='刚才入口看不懂。', speaker_id=0)]))
        (self.folder / '录像.mp4').write_bytes(b'Synthetic video placeholder, not playback evidence')
        (self.folder / '复盘.md').write_text('合成用户笔记', encoding='utf-8')
        recorder.write(self.vault / 'issues.json', dict(version=1, issues=[
            dict(id='TA-01', title='入口含义', description='', status='confirmed'),
            dict(id='N-001', title='候选议题', description='', status='candidate')]))
        catalog = self.vault / 'game-assets' / self.meta['game'] / 'catalog.json'
        catalog.parent.mkdir(parents=True)
        recorder.write(catalog, dict(version=1, game=self.meta['game'], screens=[
            dict(id='bag.items', name='背包道具', source='manual',
                 match=dict(all_of=['道具'], any_of=[], none_of=[]),
                 elements=[dict(id='bag.items.auto_use', name='自动使用道具', aliases=[], notes='')])]))
        self.manifest = agent.publish_ready(self.folder)

    def candidate(self):
        return dict(version=2, session_id='fixture', revision=self.manifest['revision'], summary='合成整理。',
                    coverage=dict(video_ranges=[dict(start=0, end=12)], transcript='full', inputs='none', limitations=[]),
                    events=[dict(id='e1', start=0, end=12, title='寻找入口', summary='记录者询问入口含义。',
                                 context='', basis='explicit', kind='question',
                                 evidence=[dict(kind='quote', ref='t000001')])], questions=[], ideas=[],
                    instances=[dict(id='i1', event_id='e1',
                                    said=[dict(kind='quote', ref='t000002'),
                                          dict(kind='quote_words', ref='t000001', word_range=[1, 3])],
                                    refers_to=dict(start=0, end=1.5, basis='retrospective', note='回指刚才画面。'),
                                    screen='bag.items', elements=['bag.items.auto_use'], kind='confusion',
                                    statement='记录者未理解入口的含义。', issue_tags=['TA-01', 'N-001'],
                                    evidence=[dict(kind='video', start=1, end=1, observation='合成入口按钮。')],
                                    confidence='high')])

    def test_valid_v2_submits_and_expands_source_quotes(self):
        """触发路径：外部 agent 按新格式提交一场整理。"""
        candidate = self.candidate()
        candidate['instances'][0]['said'][1].update(start=0, end=0, text='agent 自填文字')
        validated = agent.validate_result(self.folder, candidate)
        self.assertEqual(validated['version'], 2)
        said = validated['instances'][0]['said']
        self.assertEqual((said[0]['start'], said[0]['end'], said[0]['text']), (8, 10, '刚才入口看不懂。'))
        self.assertEqual((said[1]['start'], said[1]['end'], said[1]['text']), (2.5, 4, '入口是什么？'))
        self.assertEqual(said[1]['word_range'], [1, 3])
        self.assertEqual(agent.validate_result(self.folder, validated), validated)
        job = agent.claim(self.folder, 'synthetic-v2-worker')
        submitted = agent.submit(self.folder, job['token'], candidate)
        self.assertEqual(submitted['instances'], 1)
        state = agent.preprocessing_status(self.folder, include_result=True)
        self.assertEqual((state['state'], state['instances']), ('complete', 1))
        self.assertEqual(state['result']['instances'], validated['instances'])
        self.assertEqual(recorder.read(self.folder / agent.RESULT)['version'], 2)
        self.assertEqual(session_review_payload(self.folder)['preprocessing']['result']['instances'], validated['instances'])

    def test_refers_to_outside_video_is_rejected(self):
        """触发路径：agent 给出超出录像时长的时间（LLM 写错时间是已发生过的问题）→ 回看点击后定位到不存在的位置。"""
        candidate = self.candidate()
        candidate['instances'][0]['refers_to'].update(start=11, end=13, basis='unknown')
        with self.assertRaisesRegex(ValueError, '超出录像范围'):
            agent.validate_result(self.folder, candidate)

    def test_retrospective_after_earliest_said_time_is_rejected(self):
        """触发路径：agent 把“刚才……”标成回顾，却把所指时间写在说话之后 → 追溯方向错误。"""
        candidate = self.candidate()
        candidate['instances'][0]['refers_to']['end'] = 3
        with self.assertRaisesRegex(ValueError, '不能晚于说出口'):
            agent.validate_result(self.folder, candidate)

    def test_unknown_issue_tag_is_rejected(self):
        """触发路径：agent 自造一个不在 issues.json 里的标签 → 按议题筛选时这条实例永远查不到。"""
        candidate = self.candidate()
        candidate['instances'][0]['issue_tags'] = ['TA-missing']
        with self.assertRaisesRegex(ValueError, '议题标签不存在'):
            agent.validate_result(self.folder, candidate)

    def test_unknown_event_id_is_rejected(self):
        """触发路径：agent 把实例挂到不存在的事件下 → 回看页无处显示。"""
        candidate = self.candidate()
        candidate['instances'][0]['event_id'] = 'e-missing'
        with self.assertRaisesRegex(ValueError, '事件不存在'):
            agent.validate_result(self.folder, candidate)

    def test_v1_remains_readable_valid_displayed_and_exportable(self):
        """触发路径：升级后打开已有 21 场旧格式结果。"""
        candidate = self.candidate()
        candidate['version'] = 1
        candidate.pop('instances')
        expected = agent.validate_result(self.folder, candidate)
        self.assertEqual(expected['version'], 1)
        self.assertNotIn('instances', expected)
        recorder.write(self.folder / agent.RESULT, candidate)
        before = (self.folder / agent.RESULT).read_bytes()
        state = agent.preprocessing_status(self.folder, include_result=True)
        self.assertEqual((state['state'], state['instances']), ('complete', 0))
        self.assertEqual(state['result']['events'][0]['title'], '寻找入口')
        review = session_review_payload(self.folder)['preprocessing']['result']
        self.assertEqual(review['version'], 1)
        self.assertNotIn('instances', review)
        with zipfile.ZipFile(recorder.Session(self.folder).package()) as archive:
            exported = json.loads(archive.read('场次/fixture/体验事件.json'))
            self.assertEqual(exported['version'], 1)
            self.assertEqual(exported['events'], review['events'])
            self.assertNotIn('instances', exported)
            self.assertIn('寻找入口', archive.read('场次/fixture/独立回看.html').decode('utf-8'))
        self.assertEqual((self.folder / agent.RESULT).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
