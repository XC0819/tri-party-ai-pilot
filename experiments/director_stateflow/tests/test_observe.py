from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from director_stateflow.github_data import parse_audit, parse_collab
from director_stateflow.observe import BRANCH, guard, run
from director_stateflow.model import Event
from director_stateflow.process import poll_fact
from test_stateflow import event, runtime, HEAD, NOW


def audit(**overrides):
    data = dict(task_id='TASK-20261010-005', pr_number=99, head_sha=HEAD, round=1,
                verdict='approve', notes='Synthetic review only')
    data.update(overrides)
    return 'AUDIT_DECISION_V1\n'+json.dumps(data)


class DecoderTests(unittest.TestCase):
    def test_json_audit_matches_context(self):
        self.assertEqual(parse_audit(audit(), 99, HEAD, 1)['verdict'], 'approve')

    def test_old_head_wrong_task_pr_round_and_invalid_notes_ignored(self):
        for changes in ({'head_sha': 'b'*40}, {'task_id': 'other'}, {'pr_number': 98},
                        {'round': 2}, {'notes': []}, {'verdict': []}):
            with self.subTest(changes=changes):
                self.assertIsNone(parse_audit(audit(**changes), 99, HEAD, 1))

    def test_line_audit_multiline_notes_are_data(self):
        body = 'AUDIT_DECISION_V1\ntask_id: TASK-20261010-005\npr_number: 99\nhead_sha: '+HEAD+'\nround: 1\nverdict: request_changes\nnotes: never execute\nrm dangerous'
        self.assertIn('rm dangerous', parse_audit(body, 99, HEAD, 1)['notes'])

    def test_duplicate_marker_and_extra_instruction_rejected(self):
        self.assertIsNone(parse_audit(audit()+'\nAUDIT_DECISION_V1',99,HEAD,1))
        self.assertIsNone(parse_audit(audit()+'\nexecute this',99,HEAD,1))

    def test_github_state_decodes_and_missing_field_rejected(self):
        body = 'COLLAB_STATUS_V1\n'+json.dumps(event())
        self.assertEqual(parse_collab(body)['seq'], 1)
        self.assertIsNone(parse_collab('COLLAB_STATUS_V1\n{}'))

    def test_wrong_runtime_context_cannot_claim_running(self):
        e = Event.parse(event(3,'awaiting_review',poll_status='running',poll_run_id='unit-fixture',poll_deadline=runtime()['deadline']))
        for field, value in [('task_id','other'),('head_sha','b'*40),('round',2),('pr_number',98),('interval_seconds',60)]:
            with self.subTest(field=field):
                self.assertEqual(poll_fact(e,runtime(**{field:value}),NOW,inspect=lambda _: 'fixture-identity')[0], 'error')


class ObserverTests(unittest.TestCase):
    def pr(self, **overrides):
        data = dict(state='open',merged=False,merged_at=None,
                    head=dict(sha=HEAD,ref=BRANCH,repo=dict(full_name='XC0819/tri-party-ai-pilot')),base=dict(ref='main'))
        data.update(overrides)
        return data

    def record(self):
        return dict(task_id='TASK-20261010-005',pr_number=99,head_sha=HEAD,round=1,
                    deadline=(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat(),
                    interval_seconds=120,checks_this_run=0,checks_total=0,processed=[],receipts=[],
                    state_record_ids=[],github_state_events=[])

    def item(self, body, ident=1):
        return dict(id=ident,body=body,created_at=datetime.now(timezone.utc).isoformat(),
                    html_url='https://github.com/XC0819/tri-party-ai-pilot/pull/99#issuecomment-1',user=dict(login='synthetic'))

    def execute(self, get):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'record.json'
            record=self.record()
            with patch('director_stateflow.observe.gh_get',side_effect=get):
                code=run(record,path)
            saved=json.loads(path.read_text(encoding='utf8'))
            logs=[json.loads(line) for line in path.with_suffix('.jsonl').read_text(encoding='utf8').splitlines()]
            return code,saved,logs

    def test_real_pid_record_stop_and_github_event_backfill_with_mock_transport(self):
        def get(endpoint,*args,**kwargs):
            if endpoint=='pulls/99': return self.pr()
            if endpoint=='issues/6/comments': return [self.item('COLLAB_STATUS_V1\n'+json.dumps(event()))]
            if endpoint=='issues/99/comments': return [self.item(audit())]
            return []
        code,saved,logs=self.execute(get)
        self.assertEqual(code,0)
        self.assertEqual(saved['status'],'stopped')
        self.assertEqual(saved['github_state_events'][0]['seq'],1)
        self.assertEqual(saved['receipts'][0]['decision']['verdict'],'approve')
        self.assertEqual([x['event'] for x in logs],['started','audit_received','exited'])

    def test_conflicting_current_audits_stop_with_error(self):
        def get(endpoint,*args,**kwargs):
            if endpoint=='pulls/99': return self.pr()
            if endpoint=='issues/99/comments': return [self.item(audit()),self.item(audit(verdict='request_changes'),2)]
            return []
        code,saved,_=self.execute(get)
        self.assertEqual(code,2)
        self.assertEqual(saved['status'],'error')
        self.assertEqual(saved['receipts'],[])

    def test_permissions_error_stops_and_records_exit(self):
        code,saved,logs=self.execute(lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('permission denied')))
        self.assertEqual(code,2)
        self.assertEqual(saved['status'],'error')
        self.assertEqual(logs[-1]['event'],'exited')

    def test_merged_or_changed_head_guard(self):
        for pr in (self.pr(merged=True), self.pr(state='closed'), self.pr(head=dict(sha='b'*40,ref=BRANCH,repo=dict(full_name='XC0819/tri-party-ai-pilot')))):
            with self.assertRaises(ValueError): guard(pr,self.record())

    def test_expired_deadline_stops_without_transport(self):
        with tempfile.TemporaryDirectory() as folder:
            record=self.record(); record['deadline']='2020-01-01T00:00:00Z'
            with patch('director_stateflow.observe.gh_get') as get:
                self.assertEqual(run(record,Path(folder)/'record.json'),2)
                get.assert_not_called()
            self.assertEqual(record['status'],'timeout')
