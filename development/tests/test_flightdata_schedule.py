import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('flight_schedule',ROOT/'flightdata/schedule.py')
schedule=importlib.util.module_from_spec(spec);spec.loader.exec_module(schedule)


class ScheduleTests(unittest.TestCase):
    def test_freshness_gate_and_manual_override(self):
        now=1792400000
        state={'updated_by':'github-actions','ok':True,'collection_started_at':now-599}
        self.assertFalse(schedule.decision(state,now,'schedule')[0])
        self.assertTrue(schedule.decision(state,now+1,'schedule')[0])
        self.assertTrue(schedule.decision(state,now,'workflow_dispatch')[0])
        self.assertTrue(schedule.decision({},now,'schedule')[0])
        state['ok']=False
        self.assertFalse(schedule.decision(state,now,'schedule')[0])

    def test_new_cn_day_overrides_freshness_and_bad_clocks_are_not_stuck(self):
        now=schedule.datetime.fromisoformat('2026-10-20T00:05:00+08:00').timestamp()
        state={'updated_by':'github-actions','ok':True,'collection_started_at':now-600}
        self.assertTrue(schedule.decision(state,now,'schedule')[0])
        for timestamp in ['bad','NaN',now+10000,0]:
            state['collection_started_at']=timestamp
            self.assertTrue(schedule.decision(state,now,'schedule')[0])

    def test_setup_time_and_minor_scheduler_jitter_do_not_skip_next_tick(self):
        now=1792400000
        state={'updated_by':'github-actions','ok':True,
               'schedule_checked_at':now-600,'collection_started_at':now-450}
        self.assertTrue(schedule.decision(state,now,'schedule')[0])
        state['schedule_checked_at']=now-590
        self.assertTrue(schedule.decision(state,now,'schedule')[0])
        state['schedule_checked_at']=now-500
        self.assertFalse(schedule.decision(state,now,'schedule')[0])

    def test_access_cooldown_survives_midnight_manual_runs_and_partial_data(self):
        now=schedule.datetime.fromisoformat('2026-10-29T23:55:00+08:00').timestamp()
        state={'updated_by':'github-actions','ok':False,'partial':True,
               'schedule_checked_at':now-3600,'retry_not_before':now+1800}
        for event in ['schedule','workflow_dispatch']:
            self.assertFalse(schedule.decision(state,now+600,event)[0])
            self.assertTrue(schedule.decision(state,now+1800,event)[0])
        for corrupt in ['bad','NaN',now+100000,0]:
            state['retry_not_before']=corrupt
            self.assertTrue(schedule.decision(state,now,'schedule')[0])

    def test_backoff_increases_persists_and_resets_after_recovery(self):
        from types import SimpleNamespace
        refusal=SimpleNamespace(status=403,retry_after=0)
        state={};now=1792400000
        for count,delay in enumerate([1800,3600,7200,14400,21600,21600],1):
            state=schedule.access_backoff(state,now,refusal)
            self.assertTrue(state['access_denied'])
            self.assertEqual(state['consecutive_access_denials'],count)
            self.assertEqual(state['retry_not_before'],now+delay)
        self.assertEqual(schedule.access_backoff({},now,SimpleNamespace(status=429,retry_after=20000))['retry_not_before'],now+20000)
        cleared=schedule.access_backoff(state,now)
        self.assertFalse(cleared['access_denied']);self.assertIsNone(cleared['retry_not_before'])
        self.assertEqual(schedule.access_backoff(cleared,now,refusal)['consecutive_access_denials'],1)


if __name__=='__main__':unittest.main()
