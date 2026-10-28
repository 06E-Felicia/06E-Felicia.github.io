"""Deterministic midnight-coverage regressions; no browser or live requests."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('flightdat_coverage', ROOT/'flightdata/scraper.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
END = int(collector.datetime.fromisoformat('2026-10-21T00:00:00+08:00').timestamp())


def board(number, times, final=False):
    rows = []
    for index, value in enumerate(times):
        scheduled, estimated = value if isinstance(value, tuple) else (value, None)
        rows.append({'id':f'{number}-{index}', 'scheduledTime':scheduled, 'estimatedTime':estimated})
    return {'props':{'airport':{'iata':'SZX'}, 'flights':rows,
                     'meta':{'date':END-86400, 'hasMoreNextData':not final, 'nextPage':number+1}}}


class CoverageTests(unittest.TestCase):
    def read(self, documents, limit=10):
        with patch.object(collector,'fetch_board',return_value=documents[0]), \
                patch.object(collector,'fetch_next_board',side_effect=documents[1:]) as following:
            result = collector.fetch_board_pages(MagicMock(),'arrivals',{'iata':'SZX'},
                        {'pages_per_board':limit},False,today_end=END)
        return result, following.call_count

    def assert_confirmed(self, pages):
        self.assertIsNone(pages.warning)
        self.assertTrue(pages.coverage['boundary_confirmed'])
        self.assertTrue(pages.coverage['coverage_complete'])
        self.assertEqual(pages.coverage['completion_reason'],'next_day_confirmed')

    def test_one_future_outlier_must_not_hide_later_today_flights(self):
        documents=[board(1,[END-36000]),board(2,[END+2*86400,END-30000]),
                   board(3,[END-18000]),board(4,[END+60,END+120]),board(5,[END+3600])]
        pages,calls=self.read(documents)
        self.assertEqual((len(pages),calls),(5,4))
        self.assert_confirmed(pages)
        self.assertEqual(pages.coverage['raw_flights'],7)

    def test_mixed_confirmation_page_resets_the_boundary_check(self):
        pages,_=self.read([board(1,[END-500]),board(2,[END+60]),
                          board(3,[END-60,END+120]),board(4,[END+300]),board(5,[END+600])])
        self.assertEqual(len(pages),5)
        self.assert_confirmed(pages)

    def test_estimated_early_arrival_is_still_today(self):
        pages,_=self.read([board(1,[END+10]),board(2,[(END+120,END-300)]),
                          board(3,[END+300]),board(4,[END+600])])
        self.assertEqual(len(pages),4)
        self.assert_confirmed(pages)

    def test_unknown_scheduled_time_cannot_confirm_midnight(self):
        for value in [None,0,-1,'bad','NaN']:
            with self.subTest(value=value):
                pages,_=self.read([board(1,[END+1]),board(2,[(value,END+60)]),
                                  board(3,[END+120]),board(4,[END+180])])
                self.assertEqual(len(pages),4)
                self.assert_confirmed(pages)

    def test_missing_estimate_uses_valid_schedule_and_midnight_is_next_day(self):
        pages,_=self.read([board(1,[(END,None),(END+30,'bad')]),board(2,[(END+60,0)])])
        self.assertEqual(len(pages),2)
        self.assert_confirmed(pages)

    def test_busy_airport_reads_beyond_old_six_page_limit(self):
        documents=[board(n,[END-3600*(8-n)]) for n in range(1,8)]
        documents += [board(8,[END+60]),board(9,[END+120])]
        pages,_=self.read(documents)
        self.assertEqual(len(pages),9)
        self.assert_confirmed(pages)

    def test_safety_limit_is_not_reported_as_complete(self):
        pages,_=self.read([board(1,[END-1000]),board(2,[END-500])],limit=2)
        self.assertIn('安全上限',pages.warning)
        self.assertFalse(pages.coverage['coverage_complete'])
        self.assertEqual(pages.coverage['completion_reason'],'page_limit')

    def test_source_exhaustion_is_distinct_from_a_confirmed_day_boundary(self):
        pages,calls=self.read([board(1,[END-3600],final=True)])
        self.assertEqual(calls,0)
        self.assertIsNone(pages.warning)
        self.assertFalse(pages.coverage['coverage_complete'])
        self.assertTrue(pages.coverage['available_complete'])
        self.assertFalse(pages.coverage['boundary_confirmed'])
        self.assertEqual(pages.coverage['completion_reason'],'source_exhausted')

    def test_explicit_empty_final_board_is_valid(self):
        pages,_=self.read([board(1,[],final=True)])
        self.assertIsNone(pages.warning)
        self.assertEqual(pages.coverage['completion_reason'],'source_exhausted')

    def test_empty_page_with_more_data_is_not_a_success(self):
        pages,_=self.read([board(1,[END-3600]),board(2,[])])
        self.assertIn('空页',pages.warning)
        self.assertFalse(pages.coverage['coverage_complete'])

    def test_failed_followup_cannot_confirm_a_single_next_day_page(self):
        pages,_=self.read([board(1,[END+60]),collector.SourceAccessError('HTTP 403')])
        self.assertEqual(len(pages),1)
        self.assertIn('HTTP 403',pages.warning)
        self.assertFalse(pages.coverage['boundary_confirmed'])

    def test_repeated_data_and_cursor_are_not_confirmation(self):
        first=board(1,[END-1000]);second=board(2,[END-500])
        pages,_=self.read([first,second,first])
        self.assertEqual(len(pages),2)
        self.assertEqual(pages.coverage['completion_reason'],'repeated_data')
        second['props']['meta']['nextPage']=2
        pages,_=self.read([first,second])
        self.assertEqual(pages.coverage['completion_reason'],'repeated_cursor')
        self.assertFalse(pages.coverage['coverage_complete'])

    def test_missing_metadata_is_not_assumed_to_mean_no_more_flights(self):
        first=board(1,[END-1000]);first['props']['meta']={}
        pages,_=self.read([first])
        self.assertEqual(pages.coverage['completion_reason'],'missing_pagination')
        self.assertIsNotNone(pages.warning)

    def test_terminal_flags_support_source_numeric_string_and_null_encodings(self):
        for flag in [False,0,'0','false','False',None]:
            with self.subTest(flag=flag):
                data=board(1,[END-3600]);data['props']['meta'].update(hasMoreNextData=flag,nextPage=None)
                pages,_=self.read([data])
                self.assertIsNone(pages.warning)
                self.assertTrue(pages.coverage['available_complete'])
                self.assertFalse(pages.coverage['boundary_confirmed'])

    def test_twelve_hour_window_does_not_claim_full_day_coverage(self):
        data=board(1,[END-12600]);data['props']['meta'].update(
            date=END-55800,hoursRange=12,hasMoreNextData=0,nextPage=None)
        pages,_=self.read([data])
        self.assertIsNone(pages.warning)
        self.assertEqual(pages.coverage['completion_reason'],'source_window_exhausted')
        self.assertEqual(pages.coverage['source_window_to'],END-12600)
        self.assertFalse(pages.coverage['coverage_complete'])
        self.assertTrue(pages.coverage['available_complete'])
        self.assertIn('12 小时',pages.coverage['coverage_note'])

    def test_live_24h_terminal_null_cursor_overrides_stale_more_flag(self):
        documents=[board(n,[END-3600*n]) for n in range(1,7)]
        for number,data in enumerate(documents,1):
            data['props']['meta'].update(date=END-14*3600,hoursRange=24,currentPage=number)
        documents[-1]['props']['meta'].update(hasMoreNextData=True,nextPage=None)
        pages,calls=self.read(documents)
        self.assertEqual((len(pages),calls),(6,5))
        self.assertIsNone(pages.warning)
        self.assertTrue(pages.coverage['coverage_complete'])
        self.assertFalse(pages.coverage['boundary_confirmed'])
        self.assertEqual(pages.coverage['completion_reason'],'source_exhausted')

    def test_null_cursor_needs_a_populated_matching_current_page(self):
        for current in [None,2,'bad']:
            with self.subTest(current=current):
                data=board(1,[END-3600]);data['props']['meta'].update(
                    hasMoreNextData=True,nextPage=None,currentPage=current)
                pages,_=self.read([data])
                self.assertEqual(pages.coverage['completion_reason'],'missing_pagination')
                self.assertFalse(pages.coverage['coverage_complete'])
        data=board(1,[]);data['props']['meta'].update(hasMoreNextData=True,nextPage=None,currentPage=1)
        pages,_=self.read([data])
        self.assertEqual(pages.coverage['completion_reason'],'unexpected_empty_page')

    def test_terminal_cursor_does_not_expand_a_twelve_hour_window(self):
        data=board(1,[END-12600]);data['props']['meta'].update(
            date=END-55800,hoursRange=12,hasMoreNextData=True,nextPage=None,currentPage=1)
        pages,_=self.read([data])
        self.assertIsNone(pages.warning)
        self.assertEqual(pages.coverage['completion_reason'],'source_window_exhausted')
        self.assertFalse(pages.coverage['coverage_complete'])

    def test_window_can_cover_day_end_without_a_flight_exactly_at_midnight(self):
        data=board(1,[END-300],final=True);data['props']['meta'].update(date=END-3600,hoursRange=12)
        pages,_=self.read([data])
        self.assertIsNone(pages.warning)
        self.assertTrue(pages.coverage['coverage_complete'])
        self.assertFalse(pages.coverage['boundary_confirmed'])

    def test_hard_ten_page_cap_even_when_old_config_says_forty(self):
        documents=[board(n,[END-3600+n]) for n in range(1,12)]
        pages,calls=self.read(documents,limit=40)
        self.assertEqual((len(pages),calls),(10,9))
        self.assertEqual(pages.coverage['completion_reason'],'page_limit')

    def test_arrivals_and_departures_keep_independent_coverage_diagnostics(self):
        arrival=[board(1,[END-500]),board(2,[END+60]),board(3,[END+120])]
        departure=[board(1,[END-1000]),board(2,[END-500]),board(3,[END-100])]
        for document in arrival+departure:
            for raw in document['props']['flights']:
                raw['flightNumber']='TEST'+raw['id']
        cfg=collector.load_config();cfg['pages_per_board']=3
        with patch.object(collector,'now_ts',return_value=END-3600), \
                patch.object(collector,'fetch_board',side_effect=[arrival[0],departure[0]]), \
                patch.object(collector,'fetch_next_board',side_effect=arrival[1:]+departure[1:]):
            flights,_=collector.collect_airport(MagicMock(),cfg,cfg['airports'][0],{},{},False)
        self.assertTrue(flights.boards['arrivals']['boundary_confirmed'])
        self.assertFalse(flights.boards['arrivals']['partial'])
        self.assertEqual(flights.boards['departures']['completion_reason'],'page_limit')
        self.assertTrue(flights.boards['departures']['partial'])
        self.assertIn('安全上限',flights.errors['departures'])


if __name__ == '__main__':
    unittest.main()
