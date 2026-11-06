"""Synthetic v2 judgments; no recording, OCR, or real library writes."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

import agent_protocol as agent
from desk_runtime import INSTANCE_FIELDS
from export_rows import export_rows
from issue_registry import query_instances
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

    def test_a_redo_does_not_see_the_previous_pass(self):
        """触发路径：agent 重整一场已有结果的场次，领取前后读 status 和 evidence → 看不到旧类型、旧原话、旧标题；重整进行中连旧数量也看不到，提交后能回读新数量。"""
        job = agent.claim(self.folder, 'first-pass')
        agent.submit(self.folder, job['token'], self.candidate())
        meta = json.loads((self.folder / 'session.json').read_text(encoding='utf-8'))
        meta.update(session_name='旧整理起的标题', session_name_source='agent', activity_naming=dict(applied_name='旧整理起的标题', short_title='旧整理起的标题'))
        recorder.write(self.folder / 'session.json', meta)
        before = agent.agent_status(self.folder)
        self.assertEqual(before['instances'], 1)
        self.assertFalse({'kinds', 'quote', 'event_titles', 'result'} & set(before))
        self.assertNotIn('旧整理起的标题', json.dumps(agent.evidence(self.folder), ensure_ascii=False))
        redo = agent.reprocess(self.folder, 'second-pass', '重整')
        during = agent.agent_status(self.folder)
        self.assertFalse({'kinds', 'quote', 'event_titles', 'instances', 'events'} & set(during))
        self.assertEqual((during['state'], during['label']), ('complete', '重新分析中'))
        agent.submit(self.folder, redo['token'], self.candidate())
        self.assertEqual(agent.agent_status(self.folder)['instances'], 1)

    def test_the_recorders_own_title_still_reaches_the_agent(self):
        """触发路径：记录者手动给场次起了名 → 这是素材的一部分，重整的 agent 仍能读到。"""
        meta = json.loads((self.folder / 'session.json').read_text(encoding='utf-8'))
        meta.update(session_name='手动起的名字', session_name_source='manual')
        recorder.write(self.folder / 'session.json', meta)
        self.assertEqual(agent.evidence(self.folder)['title'], '手动起的名字')

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

    def test_submit_reports_screen_check_without_blocking(self):
        """触发路径：外部 agent 提交带“组名/页签”编号的整理，而这个游戏的界面目录还没有版式规则 → 提交照常完成，回执里说明未核对页签。"""
        candidate = self.candidate()
        candidate['instances'][0].update(screen='背包/道具', screen_proposed=True, elements=[])
        job = agent.claim(self.folder, 'synthetic-v2-worker')
        submitted = agent.submit(self.folder, job['token'], candidate)
        self.assertEqual(submitted['state'], 'complete')
        self.assertEqual(submitted['screen_check']['checked'], 0)
        self.assertIn('layout', submitted['screen_check']['skipped'])

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

    def test_operation_cost_is_its_own_kind(self):
        """触发路径：记录者说“这个好麻烦”“又要退出再进” → agent 记为操作成本，跨场次能把“能做但费劲”和“做不到”分开查。"""
        candidate = self.candidate()
        candidate['instances'][0]['kind'] = 'cost'
        self.assertEqual(agent.validate_result(self.folder, candidate)['instances'][0]['kind'], 'cost')
        candidate['instances'][0]['kind'] = 'tedious'
        with self.assertRaisesRegex(ValueError, 'design_defect'):
            agent.validate_result(self.folder, candidate)

    def defect(self, defect='missing_info', **extra):
        candidate = self.candidate()
        row = candidate['instances'][0]
        del row['kind']
        row.update(design_defect=defect, symptom='not_found', evidence_source='behavior', valence='negative', intensity=2, owner='ui_interaction', **extra)
        return candidate

    def test_a_design_defect_keeps_its_fields_and_old_results_read_as_before(self):
        """触发路径：单场整理按设计缺陷提交 → 表象、次缺陷、证据来源等原样存下，校验幂等；旧结果写 kind，不用这些字段，读法不变。"""
        validated = agent.validate_result(self.folder, self.defect(secondary_defect='visual_hierarchy'))
        row = validated['instances'][0]
        self.assertEqual((row['design_defect'], row['symptom'], row['secondary_defect'], row['owner']), ('missing_info', 'not_found', 'visual_hierarchy', 'ui_interaction'))
        self.assertNotIn('kind', row)
        self.assertEqual(agent.validate_result(self.folder, validated), validated)
        legacy = agent.validate_result(self.folder, self.candidate())['instances'][0]
        self.assertEqual(legacy['kind'], 'confusion')
        self.assertNotIn('design_defect', legacy)
        self.assertNotIn('owner', legacy)
        self.assertEqual((agent.instance_type(row), agent.instance_type(legacy)), ('missing_info', 'confusion'))

    def test_a_design_defect_is_refused_with_how_to_fix_it(self):
        """触发路径：agent 写错字段 → 校验拒绝并说明该怎么改，不把半成品存进场次。"""
        cases = [(dict(design_defect='misunderstood'), 'design_defect'),
                 (dict(symptom=None), 'symptom'),
                 (dict(symptom='confused'), 'symptom'),
                 (dict(owner=None), 'owner'),
                 (dict(kind='confusion'), '不要再写 kind'),
                 (dict(secondary_defect='missing_info'), 'secondary_defect'),
                 (dict(secondary_defect='observation'), 'secondary_defect'),
                 (dict(design_defect='value', valence='positive'), '正面评价')]
        for change, message in cases:
            candidate = self.defect()
            candidate['instances'][0].update(change)
            with self.assertRaisesRegex(ValueError, message, msg=str(change)):
                agent.validate_result(self.folder, candidate)
        unreleased = self.candidate()
        unreleased['instances'][0]['kind'] = 'misunderstood'
        with self.assertRaisesRegex(ValueError, 'design_defect'):
            agent.validate_result(self.folder, unreleased)

    def test_a_display_error_always_carries_a_bug_and_may_have_no_symptom(self):
        """触发路径：文字重叠、显示卡住这类错误，玩家不一定卡住 → 不用填表象，但必须带 bug，QA 才收得到。"""
        candidate = self.defect('display_error')
        del candidate['instances'][0]['symptom']
        with self.assertRaisesRegex(ValueError, '一定带 bug'):
            agent.validate_result(self.folder, candidate)
        candidate['instances'][0]['bug'] = 'suspected'
        self.assertEqual(agent.validate_result(self.folder, candidate)['instances'][0]['bug'], 'suspected')

    def test_an_observation_needs_no_judged_fields_and_is_no_problem(self):
        """触发路径：正面评价记成观察 → 不要求表象和落地方，也不算进问题数。"""
        candidate = self.candidate()
        row = candidate['instances'][0]
        del row['kind']
        row.update(design_defect='observation', valence='positive', evidence_source='spoken', intensity=1, owner='gameplay')
        validated = agent.validate_result(self.folder, candidate)['instances'][0]
        self.assertFalse(agent.is_problem(validated))
        del row['valence'], row['evidence_source'], row['intensity'], row['owner']
        self.assertFalse(agent.is_problem(agent.validate_result(self.folder, candidate)['instances'][0]))

    def test_the_type_and_its_fields_reach_the_readers(self):
        """触发路径：跨场次查询、导出表格、场次库详情读这一条 → 都拿到统一的类型和表象、次缺陷，不用区分它是新结果还是旧结果。"""
        job = agent.claim(self.folder, 'synthetic-v2-worker')
        agent.submit(self.folder, job['token'], self.defect(secondary_defect='visual_hierarchy'))
        query = query_instances(self.vault, kind='missing_info')[0]
        self.assertEqual((query['kind'], query['symptom'], query['secondary_defect']), ('missing_info', 'not_found', 'visual_hierarchy'))
        self.assertEqual(query_instances(self.vault, kind='confusion'), [])
        row = export_rows(self.vault, ['fixture'])['rows'][0]
        self.assertEqual((row['kind'], row['problem'], row['symptom'], row['secondary_defect']), ('missing_info', True, 'not_found', 'visual_hierarchy'))
        self.assertTrue({'design_defect', 'secondary_defect'} <= set(INSTANCE_FIELDS), 'the desk draws the type and the secondary defect')

    def test_the_session_label_and_bars_count_both_generations(self):
        """触发路径：场次库和主窗口读场次状态 → 新缺陷按问题计数，比例条的键是缺陷名；旧场次的计数不变。"""
        job = agent.claim(self.folder, 'synthetic-v2-worker')
        agent.submit(self.folder, job['token'], self.defect())
        state = agent.preprocessing_status(self.folder)
        self.assertEqual(state['label'], '已整理 · 1 个问题')
        self.assertEqual(state['kinds'], {'missing_info': 1})
        job = agent.reprocess(self.folder, 'synthetic-v2-worker', '换回旧结果核对')
        agent.submit(self.folder, job['token'], self.candidate())
        state = agent.preprocessing_status(self.folder)
        self.assertEqual(state['label'], '已整理 · 1 个问题')
        self.assertEqual(state['kinds'], {'confusion': 1})

    def test_statement_check_flags_quote_collages_and_hidden_references(self):
        """触发路径：陈述把原话串成拼贴、或写“见另一条”“第 120 秒” → validate 和提交回执都提醒（不拦截），agent 提交前改掉。"""
        candidate = self.candidate()
        candidate['instances'][0]['statement'] = '他说“一”“二”“三”“四”，详见另一条。'
        job = agent.claim(self.folder, 'synthetic-v2-worker')
        submitted = agent.submit(self.folder, job['token'], candidate)
        self.assertEqual(sorted(w['problem'] for w in submitted['statement_check']['warnings']), ['hidden_reference', 'quotes'])
        self.assertEqual(agent.statement_check([dict(id='i1', statement='他说“找不到入口”。')])['warnings'], [])

    def test_bug_is_marked_beside_the_kind_explicit_or_suspected(self):
        """触发路径：单场整理把“设计没问题、实现出了问题”的判断标成 bug → 回看里 Bug 组和它原本的类型组都列出。"""
        candidate = self.candidate()
        candidate['instances'][0]['issue_tags'] = ['BUG']
        self.assertEqual(agent.validate_result(self.folder, candidate)['instances'][0]['bug'], 'explicit',
                         'an older result with only the BUG tag reads as explicit')
        candidate['instances'][0].update(issue_tags=[], bug='suspected')
        instance = agent.validate_result(self.folder, candidate)['instances'][0]
        self.assertEqual((instance['bug'], instance['kind']), ('suspected', 'confusion'), 'the kind stays as judged')
        candidate['instances'][0]['bug'] = 'explicit'
        with self.assertRaisesRegex(ValueError, '同时在 issue_tags 里写 BUG'):
            agent.validate_result(self.folder, candidate)
        candidate['instances'][0].update(bug='suspected', issue_tags=['BUG'])
        with self.assertRaisesRegex(ValueError, '疑似 bug 不挂 BUG'):
            agent.validate_result(self.folder, candidate)
        candidate['instances'][0].update(bug='maybe', issue_tags=[])
        with self.assertRaisesRegex(ValueError, 'explicit（记录者明说）或 suspected'):
            agent.validate_result(self.folder, candidate)
        candidate['instances'][0].pop('bug')
        self.assertNotIn('bug', agent.validate_result(self.folder, candidate)['instances'][0])

    def test_review_bugs_join_session_marks_and_library_bug_links(self):
        """触发路径：用户打开回看或资料库详情 → Bug 组既有单场标的，也有洞察里挂到 BUG 的；疑似子议题算疑似，明说优先，
        反例和挂在旧结果上的对应不算。跨场次整理用 instances-query --bug 取单场标的候选。"""
        from issue_registry import query_instances
        candidate = self.candidate()
        second = dict(candidate['instances'][0], id='i2', said=[dict(kind='quote', ref='t000001')],
                      refers_to=dict(start=2, end=4, basis='same_time'), issue_tags=[], statement='入口点了没反应。')
        third = dict(second, id='i3', statement='入口文字被裁掉一半。')
        candidate['instances'][0].update(issue_tags=[], bug='suspected')
        candidate['instances'] += [second, third]
        job = agent.claim(self.folder, 'synthetic-v2-worker')
        agent.submit(self.folder, job['token'], candidate)
        digest = agent._file_hash(agent._path(self.folder, agent.RESULT))
        registry = recorder.read(self.vault / 'issues.json')
        registry['issues'] += [dict(id='BUG', title='Bug', description='', status='confirmed'),
                               dict(id='BUG.1', parent='BUG', title='入口没反应', description='', status='confirmed'),
                               dict(id='BUG.2', parent='BUG', title='疑似：入口文字被裁切', description='', status='confirmed')]
        recorder.write(self.vault / 'issues.json', registry)
        link = lambda instance, issue, role='support', at=digest: dict(issue=issue, session_id='fixture', instance_id=instance,
                                                                     result_sha256=at, reason='合成理由', role=role)
        recorder.write(self.vault / 'issue-links.json', dict(version=1, links=[
            link('i1', 'BUG.1'),                      # the library says explicit: wins over the session's suspected
            link('i3', 'BUG.2'),                      # under a 疑似 sub-issue: suspected
            link('i2', 'BUG.1', role='counter'),      # counter evidence is not a bug
            link('i2', 'BUG.2', at='0' * 64),     # bound to an older result: no longer counts
            link('i2', 'TA-01')]))
        state = agent.preprocessing_status(self.folder, include_result=True)
        self.assertEqual(state['bugs'], {'i1': 'explicit', 'i3': 'suspected'})
        self.assertNotIn('bugs', agent.preprocessing_status(self.folder))
        self.assertEqual([row['instance_id'] for row in query_instances(self.vault, bug='suspected')], ['i1'])
        self.assertEqual([row['instance_id'] for row in query_instances(self.vault, bug='any')], ['i1'])
        self.assertEqual(query_instances(self.vault, bug='explicit'), [])
        self.assertEqual(session_review_payload(self.folder)['preprocessing']['bugs'], state['bugs'])

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

    def test_new_screen_is_proposed_with_route_and_free_text_elements(self):
        """触发路径：agent 整理新场次 → 记录者从别处跳进一个目录里还没有的界面 → 未标提议的名称会让整份结果被拒，标为提议后留待用户确认，跳转路线另记。"""
        candidate = self.candidate()
        row = candidate['instances'][0]
        row.update(screen='武林录/挑战/镇守·挑战', elements=['领取奖励消耗'],
                   route=['培养/装备', '武林录/挑战/镇守·挑战'])
        with self.assertRaisesRegex(ValueError, '不在目录中'):
            agent.validate_result(self.folder, candidate)
        row['screen_proposed'] = True
        instance = agent.validate_result(self.folder, candidate)['instances'][0]
        self.assertTrue(instance['screen_proposed'])
        self.assertEqual(instance['route'], ['培养/装备', '武林录/挑战/镇守·挑战'])
        self.assertEqual(instance['elements'], ['领取奖励消耗'])
        row.update(screen=None, screen_proposed=False, screen_context='multi_screen')
        self.assertEqual(agent.validate_result(self.folder, candidate)['instances'][0]['screen_context'], 'multi_screen')
        row.update(screen='bag.items', screen_context='hud')
        with self.assertRaisesRegex(ValueError, 'screen_context'):
            agent.validate_result(self.folder, candidate)

    def test_earlier_session_and_comparison_referents(self):
        """触发路径：记录者说“前两天那个同款 bug”或“这边要点最大、那边不用” → 所指在本场之前或有两个时刻，旧格式只能塞进备注，跨场次分析找不到复现信号。"""
        candidate = self.candidate()
        row = candidate['instances'][0]
        row.update(kind='negative', refers_to=dict(basis='earlier_session', note='前两天那场的同款自动滚动 bug'),
                   compare_to=dict(start=2, end=3, note='另一处数量弹窗'))
        instance = agent.validate_result(self.folder, candidate)['instances'][0]
        self.assertEqual(instance['refers_to'], dict(start=None, end=None, basis='earlier_session',
                                                    note='前两天那场的同款自动滚动 bug'))
        self.assertEqual(instance['compare_to'], dict(start=2, end=3, note='另一处数量弹窗'))
        self.assertEqual(instance['kind'], 'negative')
        row['refers_to'] = dict(basis='earlier_session')
        with self.assertRaisesRegex(ValueError, '所指说明'):
            agent.validate_result(self.folder, candidate)
        job = agent.claim(self.folder, 'synthetic-v2-worker')
        row['refers_to'] = dict(basis='earlier_session', note='前两天那场')
        agent.submit(self.folder, job['token'], candidate)
        self.assertEqual(agent.preprocessing_status(self.folder)['state'], 'complete')

    def test_instance_cites_input_record(self):
        """触发路径：手柄场里记录者说“按了没反应” → 关键证据是操作记录 → 实例只能引用画面时只好写进备注。"""
        recorder.write(self.folder / 'input-events.json', dict(
            version=1, state='complete', duration=12, timebase='video_seconds', recording_scope='all',
            window_states=[dict(start=0, end=12, state='foreground')],
            intervals=[dict(id='raw1', start=2, end=2.2, device='gamepad', code='A', label='A'),
                       dict(id='raw2', start=2.5, end=2.6, device='gamepad', code='A', label='A'),
                       dict(id='raw3', start=5, end=5.1, device='gamepad', code='A', label='A')], gaps=[]))
        manifest = agent.publish_ready(self.folder)
        candidate = self.candidate()
        candidate['revision'] = manifest['revision']
        candidate['instances'][0]['evidence'].append(dict(kind='input', ref='i0000001'))
        with self.assertRaisesRegex(ValueError, '未检查操作记录'):
            agent.validate_result(self.folder, candidate)
        candidate['coverage']['inputs'] = 'partial'
        evidence = agent.validate_result(self.folder, candidate)['instances'][0]['evidence']
        self.assertEqual((evidence[1]['kind'], evidence[1]['ref'], evidence[1]['text']), ('input', 'i0000001', 'A'))
        # 原始操作逐条读不了；摘要把短间隔的连按合成一段，首尾编号仍可直接引用。
        segments = agent.input_summary(self.folder, 0, 12)['segments']
        self.assertEqual([(row['count'], row['first_ref'], row['last_ref']) for row in segments],
                         [(2, 'i0000001', 'i0000002'), (1, 'i0000003', 'i0000003')])


if __name__ == '__main__':
    unittest.main()
