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

    def test_legacy_access_cooldown_does_not_block_any_later_run(self):
        now=schedule.datetime.fromisoformat('2026-10-29T23:55:00+08:00').timestamp()
        state={'updated_by':'github-actions','ok':False,'partial':True,
               'schedule_checked_at':now-3600,'retry_not_before':now+1800}
        for event in ['schedule','workflow_dispatch','push']:
            self.assertTrue(schedule.decision(state,now+600,event)[0])
            self.assertTrue(schedule.decision(state,now+1800,event)[0])
        for corrupt in ['bad','NaN',now+100000,0]:
            state['retry_not_before']=corrupt
            self.assertTrue(schedule.decision(state,now,'schedule')[0])

    def test_push_and_manual_validation_ignore_normal_freshness(self):
        now=1792400000
        state={'updated_by':'github-actions','schedule_checked_at':now-20,
               'access_denied':True,'retry_not_before':now+21600}
        self.assertFalse(schedule.decision(state,now,'schedule')[0])
        for event in ['push','workflow_dispatch']:
            self.assertTrue(schedule.decision(state,now,event)[0])


if __name__=='__main__':unittest.main()
