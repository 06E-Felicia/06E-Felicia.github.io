import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
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
        self.assertTrue(schedule.decision(state,now,'schedule')[0])

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


if __name__=='__main__':unittest.main()
