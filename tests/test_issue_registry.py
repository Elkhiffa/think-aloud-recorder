from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import agent_protocol as protocol
import event_edits
import issue_registry as issues


class IssueRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name)
        issues.add_issue(self.vault, '目标丢失', 'TA-01', 'confirmed')
        issues.add_issue(self.vault, '入口不明', 'TA-02', 'confirmed')

    def make_session(self, ident, created, tags):
        folder = self.vault / '场次' / ident
        folder.mkdir(parents=True)
        protocol._write(folder, 'session.json', dict(id=ident, game='合成游戏', created=created,
                        state='可回看', transcription_state='ready', media=dict(duration=12),
                        input_offset_seconds=1, settings=dict(record_inputs=False)))
        protocol._write(folder, '录像.whisper.json', dict(segments=[
            dict(start=2, end=4, text='不知道应该去哪里。', speaker_id=0)]))
        (folder / '录像.mp4').write_bytes(b'synthetic video placeholder')
        manifest = protocol.publish_ready(folder)
        result = dict(version=2, session_id=ident, revision=manifest['revision'], summary='合成整理。',
                      coverage=dict(video_ranges=[dict(start=0, end=12)], transcript='full',
                                    inputs='none', limitations=['合成数据']),
                      events=[dict(id='e1', start=0, end=12, title='寻找目标', summary='表达方向疑惑。',
                                   context='', basis='explicit', kind='friction',
                                   evidence=[dict(kind='quote', ref='t000001')])],
                      questions=[], ideas=[], instances=[
                          dict(id='i1', event_id='e1', said=[dict(kind='quote', ref='t000001')],
                               refers_to=dict(start=2, end=4, basis='same_time'), screen=None,
                               elements=[], kind='confusion', statement='不知道目标方向。',
                               issue_tags=tags, evidence=[dict(kind='video', start=3, end=3,
                                                               observation='合成目标按钮。')], confidence='high')])
        job = protocol.claim(folder, 'synthetic-worker')
        protocol.submit(folder, job['token'], result)
        return folder

    def test_query_filters_issue_across_complete_sessions(self):
        """触发路径：用户要处理“目标丢失”议题 → 需要列出所有场次中挂了该标签的实例，按时间排序依次回看。"""
        self.make_session('later', '2026-10-09T12:00:00+08:00', ['TA-01'])
        earlier = self.make_session('earlier', '2026-10-08T12:00:00+08:00', ['TA-01', 'TA-02'])
        self.make_session('other', '2026-10-07T12:00:00+08:00', ['TA-02'])
        stale = self.make_session('stale', '2026-10-06T12:00:00+08:00', ['TA-01'])
        protocol._write(stale, '录像.whisper.json', dict(segments=[dict(start=2, end=4, text='重新转写。')]))
        result = protocol._load(earlier, protocol.RESULT)
        second = deepcopy(result['instances'][0])
        second.update(id='i2', refers_to=dict(start=6, end=7, basis='unknown'))
        result['instances'].insert(0, second)
        protocol._write(earlier, protocol.RESULT, result)
        rows = issues.query_instances(self.vault, issue=['TA-01'])
        self.assertEqual([(row['session_id'], row['instance_id']) for row in rows],
                         [('earlier', 'i1'), ('earlier', 'i2'), ('later', 'i1')])
        self.assertEqual(rows[0]['said_start'], 2)
        self.assertEqual(rows[0]['refers_start'], 2)
        self.assertEqual(rows[0]['refers_end'], 4)

    def test_merge_rewrites_references_backs_up_and_preserves_calibration(self):
        """触发路径：用户发现两个标签说的是同一个问题 → 合并后旧标签的实例全部归到新标签，原结果可追溯。"""
        first = self.make_session('first', '2026-10-08T12:00:00+08:00', ['TA-01', 'TA-02'])
        second = self.make_session('second', '2026-10-09T12:00:00+08:00', ['TA-01'])
        state = protocol.preprocessing_status(first, include_result=True)
        request = dict(**state['editing'], event_id='e1', fields=event_edits.editable(state['result']['events'][0]))
        request['fields']['title'] = '用户校准后的标题'
        event_edits.save(first, request)
        original_corrections = event_edits._read(first)['history']
        # 同一合并路径包含旧旁车快照；合并必须保留其解释偏移的含义。
        raw = protocol._load(second, protocol.RESULT)
        context = raw.pop('analysis_context')
        protocol._write(second, protocol.RESULT, raw)
        protocol._write(second, protocol.ANALYSIS_CONTEXT,
                        dict(result_sha256=protocol._file_hash(second / protocol.RESULT), **context))
        originals = {folder: (folder / protocol.RESULT).read_bytes() for folder in (first, second)}
        merged = issues.merge_issues(self.vault, 'TA-01', 'TA-02')
        self.assertEqual((merged['sessions'], merged['instances'], merged['corrections_migrated']), (2, 2, 1))
        self.assertEqual([row['id'] for row in issues.list_issues(self.vault)['issues']], ['TA-02'])
        for folder in (first, second):
            raw = protocol._load(folder, protocol.RESULT)
            self.assertEqual(raw['instances'][0]['issue_tags'], ['TA-02'])
            self.assertEqual(next((folder / 'agent-history').glob('*.json')).read_bytes(), originals[folder])
            self.assertEqual(protocol.preprocessing_status(folder)['state'], 'complete')
        state = protocol.preprocessing_status(first, include_result=True)
        self.assertEqual(state['result']['events'][0]['title'], '用户校准后的标题')
        self.assertTrue(state['result']['events'][0]['manually_edited'])
        history = event_edits._read(first)['history']
        self.assertEqual(history[:len(original_corrections)], original_corrections)
        self.assertNotEqual(history[-1]['id'], original_corrections[0]['id'])
        self.assertEqual(history[-1]['base_result_sha256'], protocol._file_hash(first / protocol.RESULT))
        self.assertEqual(protocol._load(second, protocol.RESULT)['analysis_context'], context)


if __name__ == '__main__':
    unittest.main()
