"""Offline protocol / real-schema mapping / privacy / rollover regressions."""
import base64
import contextlib
from datetime import datetime, timezone, timedelta
from email.message import Message
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from feimadata import budget, client, collect, enrich, normalize, photos, private_key, schedule

NOW = int(datetime.fromisoformat('2026-10-20T12:00:00+08:00').timestamp())
AIRPORT = {'iata':'SZX','name':'深圳宝安国际机场','city':'Shenzhen'}


def raw(**extra):
    row={'flightNumber':'UI123','departure':'测试出发机场','arrival':'深圳宝安',
         'departureCode':'PEK','arrivalCode':'SZX','flightStatus':'计划','delayData':'--',
         'depDate':'2026-10-20','arrDate':'2026-10-20','depPlanHour':'10:00',
         'arrPlanHour':'13:00','depEstHour':'','arrEstHour':'','depActHour':'','arrActHour':'',
         'airlineCode':'UI','flightDesc':'','flightPic':'','aircraftNumber':'',
         'depTerminal':'T2','arrTerminal':'T3'}
    row.update(extra)
    return row


def result(rows=None):
    return {'isError':False,'content':[{'type':'text','text':'Airport flight board'}],
            'structuredContent':{'kind':'collection','items':[raw()] if rows is None else rows}}


def detail(**extra):
    row={'FlightNo':'UI123','FlightDepcode':'PEK','FlightArrcode':'SZX',
         'FlightDeptimePlanDate':'2026-10-20 10:00:00','aircraftNumber':'B30EC',
         'miniAirplaneModels':'A321-253NX','generic':'A21N','FlightCompany':'测试航司',
         'BoardGate':'A1','FlightArrTerminal':'T3','flightPic':'','flightDesc':''}
    row.update(extra)
    return row


def snapshot(rows=None):
    flights=normalize.normalize_board(result(rows),AIRPORT,'arrivals',NOW)[0]
    return {'airport':AIRPORT,'source':'variflight-mcp','generated_at':NOW,'flights':flights,
            'today':flights,'capabilities':dict(normalize.CAPABILITIES)}


class Response(io.BytesIO):
    def __init__(self, payload=b'', content_type='application/json', session=None):
        super().__init__(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        self.headers=Message();self.headers['Content-Type']=content_type
        if session:self.headers['Mcp-Session-Id']=session


class Opener:
    def __init__(self): self.requests=[]
    def open(self, request, timeout):
        self.requests.append(request)
        body=json.loads(request.data);method=body['method'];rid=body.get('id')
        if method=='notifications/initialized':return Response()
        payload={'protocolVersion':'2025-03-26','capabilities':{'tools':{}}} if method=='initialize' else (
            {'tools':[{'name':'getAirportFlightBoard','inputSchema':{'required':['local']}}]} if method=='tools/list' else result())
        return Response({'jsonrpc':'2.0','id':rid,'result':payload},session='private-session' if method=='initialize' else None)


class ProtocolTests(unittest.TestCase):
    def test_handshake_and_board_stay_on_official_host_with_header_only_credentials(self):
        opener=Opener();api=client.Client(key='PRIVATE_TEST_KEY',opener=opener)
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            api.initialize();api.discover_board();board=api.get_board('SZX','1')
        self.assertEqual(len(board['structuredContent']['items']),1)
        self.assertEqual(output.getvalue(),'')
        self.assertEqual([json.loads(r.data)['method'] for r in opener.requests],
                         ['initialize','notifications/initialized','tools/list','tools/call'])
        for request in opener.requests:
            self.assertEqual(request.full_url,client.ENDPOINT)
            self.assertNotIn('PRIVATE_TEST_KEY',request.data.decode())
            self.assertEqual(request.get_header('Authorization'),'Bearer PRIVATE_TEST_KEY')
        self.assertEqual(opener.requests[-1].get_header('Mcp-session-id'),'private-session')
        api.close();self.assertEqual(api._key,'')

    def test_sse_ignores_notifications_and_stops_when_matching_result_arrives(self):
        stream=Response(b': heartbeat\n\ndata: {"method":"notifications/progress"}\n\n'
                        b'data: {"jsonrpc":"2.0","id":4,"result":{"items":[]}}\n\n'
                        b'data: never-read\n\n','text/event-stream')
        self.assertEqual(client.read_result(stream,4),{'items':[]})
        self.assertIn(b'never-read',stream.read())

    def test_rpc_errors_do_not_echo_provider_message_or_key(self):
        response=Response({'id':1,'error':{'code':-32000,'message':'PRIVATE_TEST_KEY'}})
        with self.assertRaises(client.MCPError) as error:client.read_result(response,1)
        self.assertNotIn('PRIVATE_TEST_KEY',str(error.exception))

    def test_http_authorization_and_rate_limit_errors_are_safe_and_not_retried(self):
        for code in (401,403,429):
            class Failing:
                count=0
                def open(self,*args,**kwargs):
                    self.count+=1
                    raise urllib.error.HTTPError(client.ENDPOINT,code,'PRIVATE_TEST_KEY',{},None)
            opener=Failing();api=client.Client(key='PRIVATE_TEST_KEY',opener=opener)
            with self.assertRaises(client.MCPError) as error:api.initialize()
            self.assertEqual(error.exception.http_status,code)
            self.assertEqual(opener.count,1)
            self.assertNotIn('PRIVATE_TEST_KEY',str(error.exception))

    def test_redirects_are_refused_before_forwarding_authorization(self):
        with self.assertRaises(client.MCPError):
            client.NoRedirect().redirect_request(None,None,302,'',{},'https://other.test')

    def test_malformed_or_mismatched_results_cannot_be_published(self):
        for response in (Response(b'not JSON'),Response({'id':2,'result':{}}),
                         Response({'id':1,'result':[]}),Response(b'hello','text/html')):
            with self.assertRaises(client.MCPError):client.read_result(response,1)

    def test_private_key_permissions_and_no_project_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'private';path=directory/'mcp-key'
            with patch.multiple(private_key,KEY_DIR=directory,KEY_FILE=path),patch.dict(os.environ,{},clear=True):
                private_key.save_key('Bearer PRIVATE_TEST_KEY')
                self.assertEqual(private_key.load_key(),'PRIVATE_TEST_KEY')
                self.assertEqual(path.stat().st_mode&0o777,0o600)
                self.assertEqual(directory.stat().st_mode&0o777,0o700)
                path.chmod(0o644)
                with self.assertRaises(private_key.KeyErrorSafe):private_key.load_key()
        self.assertNotIn(str(Path(__file__).resolve().parents[2]),str(private_key.KEY_FILE))


class MappingTests(unittest.TestCase):
    def parse(self,row):return normalize.normalize_board(result([row]),AIRPORT,'arrivals',NOW)[0][0]

    def test_only_observed_structured_collection_is_accepted(self):
        for data in ({},{'structuredContent':{'items':[]}}, {'structuredContent':{'kind':'collection','items':['bad']}}):
            with self.assertRaises(client.MCPError):normalize.normalize_board(data,AIRPORT,'arrivals',NOW)
        rows,info=normalize.normalize_board(result([]),AIRPORT,'arrivals',NOW)
        self.assertEqual(rows,[]);self.assertTrue(info['ok'])

    def test_times_terminal_and_missing_type_are_not_fabricated(self):
        parsed=self.parse(raw(arrEstHour='13:15',aircraftNumber='B1234'))
        self.assertEqual(parsed['estimated_ts']-parsed['scheduled_ts'],900)
        self.assertEqual(parsed['registration'],'B-1234')
        self.assertEqual(parsed['terminal'],'T3')
        for key in ('type','type_family','gate','runway','is_widebody','is_cargo','is_foreign'):
            self.assertIsNone(parsed[key])

    def test_actual_time_precedes_outdated_estimate_for_remaining_counts(self):
        parsed=self.parse(raw(arrPlanHour='12:15',arrEstHour='12:20',arrActHour='11:54',flightStatus='到达',delayData='-21'))
        self.assertEqual(parsed['status_cn'],'已落地')
        self.assertLess(normalize.event_time(parsed),NOW)
        self.assertGreater(parsed['estimated_ts'],NOW)

    def test_incoming_departure_is_en_route_not_already_arrived(self):
        parsed=self.parse(raw(flightStatus='起飞',depActHour='10:01'))
        self.assertEqual(parsed['status'],'en-route');self.assertIsNone(parsed['actual_ts'])

    def test_cancellation_and_unknown_status_remain_source_based(self):
        self.assertEqual(self.parse(raw(flightStatus='提前取消'))['status'],'cancelled')
        self.assertEqual(self.parse(raw(flightStatus='新的状态'))['status_cn'],'新的状态')

    def test_haneda_airport_local_time_is_converted_to_an_absolute_time(self):
        row=raw(arrivalCode='HND',arrPlanHour='13:00')
        parsed=normalize.normalize_board(result([row]),{'iata':'HND'},'arrivals',NOW)[0][0]
        self.assertEqual(parsed['scheduled_ts'],NOW)

    def test_midnight_estimate_rolls_forward_and_24_hour_clock_is_valid(self):
        parsed=self.parse(raw(arrPlanHour='23:50',arrEstHour='00:15'))
        self.assertEqual(parsed['estimated_ts']-parsed['scheduled_ts'],25*60)
        self.assertEqual(datetime.fromtimestamp(parsed['estimated_ts'],normalize.CN).date().isoformat(),'2026-10-21')
        self.assertIsNotNone(normalize.timestamp('2026-10-20','24:00',normalize.CN))

    def test_wrong_airport_and_bad_clocks_do_not_look_like_zero_flights(self):
        for row in (raw(arrivalCode='CAN'),raw(arrPlanHour='bad'),raw(arrDate='2026-02-31')):
            with self.assertRaises(client.MCPError):self.parse(row)
        _,info=normalize.normalize_board(result([raw(),raw(arrPlanHour='bad')]),AIRPORT,'arrivals',NOW)
        self.assertTrue(info['partial']);self.assertEqual(info['skipped_count'],1)

    def test_livery_flag_is_kept_without_loading_provider_theme_images(self):
        parsed=self.parse(raw(flightDesc='测试彩绘',flightPic='https://file.variflight.com/theme.png',authorization='PRIVATE_TEST_KEY'))
        self.assertTrue(parsed['is_special_livery'])
        self.assertIsNone(parsed['photo'])
        self.assertNotIn('PRIVATE_TEST_KEY',json.dumps(parsed))
        for url in ('javascript:alert(1)','http://127.0.0.1/private','https://other.test/image.png',
                    'https://file.variflight.com/image.png?token=private'):
            self.assertIsNone(self.parse(raw(flightPic=url))['photo'])


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.data=Path(self.temporary.name)
        self.patch=patch.multiple(collect,DATA=self.data,INDEX=self.data/'index.json',STATUS=self.data/'status.json')
        self.patch.start()
        self.cache_patch=patch.object(enrich,'CACHE_PATH',self.data/'.cache/details.json')
        self.cache_patch.start()
        self.photos_patch=patch.object(photos,'CACHE_PATH',self.data/'.cache/photos.json')
        self.photos_patch.start()
        collect.write_json(collect.INDEX,{'source':'variflight-mcp','airports':[AIRPORT]})
    def tearDown(self):self.photos_patch.stop();self.cache_patch.stop();self.patch.stop();self.temporary.cleanup()

    def test_legacy_multi_airport_index_can_only_query_shenzhen(self):
        collect.write_json(collect.INDEX,{'airports':[AIRPORT,{'iata':'HND'}]})
        class Fake:
            def __init__(self):self.calls=[]
            def initialize(self):pass
            def discover_board(self):pass
            def close(self):pass
            def get_board(self,code,direction):
                self.calls.append(code);return result([raw()] if direction=='1' else [])
        api=Fake()
        with patch.object(collect.time,'time',return_value=NOW),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.run(client=api,detail_limit=0,photo_limit=0),0)
        self.assertEqual(api.calls,['SZX','SZX'])
        self.assertEqual([a['iata'] for a in collect.read_json(collect.INDEX,{})['airports']],['SZX'])
        with self.assertRaises(client.MCPError):collect.run(codes=['HND'],client=api,detail_limit=0)

    def test_exhausted_daily_budget_still_refreshes_board_but_never_calls_details(self):
        collect.write_json(collect.STATUS,{'daily_detail_budget':{'day':'2026-10-20','used':200}})
        class Fake:
            def initialize(self):pass
            def discover_board(self):pass
            def close(self):pass
            def get_board(self,code,direction):return result([raw()] if direction=='1' else [])
            def get_status(self,*args,**kw):raise AssertionError('daily cap bypassed')
        with patch.object(collect.time,'time',return_value=NOW),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.run(client=Fake(),photo_limit=0),0)
        self.assertEqual(collect.read_json(collect.STATUS,{})['daily_detail_budget']['used'],200)

    def test_publish_preserves_today_history_but_not_tomorrow(self):
        prior_row=normalize.normalize_board(result([raw(flightNumber='OLD',arrPlanHour='11:00')]),AIRPORT,'arrivals',NOW-3600)[0][0]
        current,details=normalize.normalize_board(result([raw(),raw(flightNumber='NEXT',arrDate='2026-10-21')]),AIRPORT,'arrivals',NOW)
        previous={'source':'variflight-mcp','service_day':'2026-10-20','today':[prior_row]}
        snapshot=collect.publish_airport(AIRPORT,{'arrivals':(current,details)},previous,NOW)
        self.assertEqual({r['flight_number'] for r in snapshot['today']},{'OLD','UI123'})
        self.assertTrue(next(r for r in snapshot['today'] if r['flight_number']=='OLD')['from_history'])
        self.assertIsNone(snapshot['boards']['arrivals']['coverage_complete'])

    def test_delay_into_tomorrow_removes_old_today_version(self):
        old,info=normalize.normalize_board(result([raw(arrPlanHour='23:50')]),AIRPORT,'arrivals',NOW)
        new,_=normalize.normalize_board(result([raw(arrPlanHour='23:50',arrEstHour='00:15')]),AIRPORT,'arrivals',NOW+60)
        previous={'source':'variflight-mcp','service_day':'2026-10-20','today':old}
        snapshot=collect.publish_airport(AIRPORT,{'arrivals':(new,info)},previous,NOW+60)
        self.assertEqual(snapshot['today'],[])

    def test_next_day_cleanup_preserves_last_actual_success_timestamp(self):
        path=self.data/'szx.json'
        collect.write_json(path,{'source':'variflight-mcp','service_day':'2026-10-19','generated_at':NOW-86400,
                                 'flights':[{'id':'old'}],'today':[{'id':'old'}]})
        collect.rollover([AIRPORT],NOW)
        cleared=collect.read_json(path,{})
        self.assertEqual(cleared['today'],[]);self.assertEqual(cleared['generated_at'],NOW-86400)

    def test_one_direction_failure_keeps_other_direction_and_previous_day_history(self):
        class Fake:
            def initialize(self):pass
            def discover_board(self):pass
            def get_board(self,airport,direction):
                if direction=='0':raise client.MCPError('test departures unavailable')
                return result()
            def get_status(self,*args):return result([])
            def close(self):pass
        with patch.object(collect.time,'time',return_value=NOW),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.run(client=Fake(),detail_limit=0,photo_limit=0),0)
        status=collect.read_json(collect.STATUS,{})
        self.assertTrue(status['airports']['SZX']['partial'])
        self.assertEqual(len(collect.read_json(self.data/'szx.json',{})['today']),1)

    def test_rate_limit_stops_without_more_board_requests(self):
        class Fake:
            calls=0
            def initialize(self):pass
            def discover_board(self):pass
            def get_board(self,*args):
                self.calls+=1
                raise client.MCPError('limited',429)
            def close(self):pass
        api=Fake()
        with patch.object(collect.time,'time',return_value=NOW),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.run(client=api),1)
        self.assertEqual(api.calls,1)
        self.assertFalse((self.data/'szx.json').exists())

    def test_clean_checkout_collects_real_schema_details_and_does_not_need_local_cache(self):
        class Fake:
            def initialize(self):pass
            def discover_board(self):pass
            def close(self):pass
            def get_board(self,airport,direction):
                return result([raw()] if direction=='1' else [])
            def get_status(self,*args):return result([detail()])
        with patch.object(collect.time,'time',return_value=NOW),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.run(client=Fake(),photo_limit=0),0)
        saved=collect.read_json(self.data/'szx.json',{})
        self.assertEqual(saved['flights'][0]['registration'],'B-30EC')
        self.assertEqual(saved['today'][0]['registration'],'B-30EC')
        self.assertFalse(collect.read_json(collect.STATUS,{})['metadata_failed'])

    def test_metadata_all_missing_is_not_reported_as_full_success(self):
        class Fake:
            def initialize(self):pass
            def discover_board(self):pass
            def close(self):pass
            def get_board(self,*args):return result()
            def get_status(self,*args):return result([])
        with patch.object(collect.time,'time',return_value=NOW),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.run(client=Fake(),photo_limit=0),1)
        self.assertTrue(collect.read_json(collect.STATUS,{})['metadata_failed'])
        self.assertTrue((self.data/'szx.json').exists(),'valid board must still be preserved')

    def test_metadata_only_does_not_rewrite_board_collection_provenance(self):
        collect.write_json(self.data/'szx.json',dict(snapshot(),service_day='2026-10-20'))
        original={'source':'variflight-mcp','connection_state':'ready','updated_at':NOW-60,'run_url':'https://github.com/example/run/1',
                  'airports':{'SZX':{'last_success_at':NOW-60}},'enrichment':{'details':{'route_calls':40}}}
        collect.write_json(collect.STATUS,original)
        with patch.object(collect.time,'time',return_value=NOW),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.run(enrich_only=True,detail_limit=0,photo_limit=0),0)
        saved=collect.read_json(collect.STATUS,{})
        for k in ['run_url','updated_at','enrichment']:self.assertEqual(saved[k],original[k])
        self.assertEqual(saved['last_metadata_enrichment']['details']['route_calls'],0)


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'details.json'
    def tearDown(self):self.temp.cleanup()
    def run_enrich(self,snap,api,limit=40,now=NOW,**kw):
        return enrich.enrich_snapshots([snap],api,limit=limit,now=now,path=self.path,**kw)

    def test_status_tool_uses_documented_args_and_reuses_directory(self):
        class WithDetails(Opener):
            def open(self,request,timeout):
                if json.loads(request.data)['method']=='tools/list':
                    self.requests.append(request)
                    return Response({'id':json.loads(request.data)['id'],'result':{'tools':[
                        {'name':'getAirportFlightBoard','inputSchema':{'required':['local']}},
                        {'name':'getFlightStatus','inputSchema':{'required':['date']}}]}})
                return super().open(request,timeout)
        opener=WithDetails();api=client.Client(key='PRIVATE_TEST_KEY',opener=opener)
        api.initialize();api.discover_board();api.get_status('2026-10-20','PEK','SZX')
        self.assertEqual(sum(json.loads(r.data)['method']=='tools/list' for r in opener.requests),1)
        self.assertEqual(json.loads(opener.requests[-1].data)['params'],
                         {'name':'getFlightStatus','arguments':{'date':'2026-10-20','dep':'PEK','arr':'SZX'}})
        for bad in ('2026-02-31','not-a-date'):
            with self.assertRaises(client.MCPError):api.get_status(bad,'PEK','SZX')

    def test_one_route_enriches_multiple_exact_flights_and_drops_unrelated_fields(self):
        class Fake:
            calls=0
            def get_status(self,*args):
                self.calls+=1
                return result([detail(authorization='PRIVATE_TEST_KEY'),detail(FlightNo='UI124')])
        snap=snapshot([raw(),raw(flightNumber='UI124')]);api=Fake()
        stats=self.run_enrich(snap,api)
        self.assertEqual(api.calls,1);self.assertEqual(stats['matched'],2)
        self.assertEqual(snap['flights'][0]['registration'],'B-30EC')
        self.assertEqual(snap['flights'][0]['type'],'A321-253NX')
        self.assertEqual(snap['flights'][0]['is_widebody'],False)
        self.assertEqual(snap['flights'][0]['airline'],'测试航司')
        self.assertIsNone(snap['flights'][0]['gate'],'departure gate must not be shown as arrival gate')
        self.assertNotIn('PRIVATE_TEST_KEY',json.dumps(snap)+self.path.read_text())
        self.run_enrich(snap,api,now=NOW+60)
        self.assertEqual(api.calls,1,'valid cache must not spend another request')

    def test_airport_date_flight_and_departure_clock_must_all_match(self):
        for extra in ({'FlightNo':'UI999'},{'FlightDepcode':'PKX'},{'FlightArrcode':'HND'},
                      {'FlightDeptimePlanDate':'2026-10-21 10:00:00'},
                      {'FlightDeptimePlanDate':'2026-10-20 11:00:00'}):
            snap=snapshot()
            class Fake:
                def get_status(self,*args):return result([detail(**extra)])
            # Separate path to avoid a previous case's negative cache.
            self.path=Path(self.temp.name)/('case-'+str(len(extra))+str(hash(str(extra)))+'.json')
            self.run_enrich(snap,Fake())
            self.assertIsNone(snap['flights'][0]['registration'])

    def test_assignment_change_cannot_retain_previous_registration_or_photo(self):
        class Fake:
            reg='B30EC'
            def get_status(self,*args):return result([detail(aircraftNumber=self.reg)])
        snap=snapshot();api=Fake();self.run_enrich(snap,api)
        for f in snap['flights']:f['photo']={'source':'planespotters','reg':'B-30EC'}
        api.reg='B1234';self.run_enrich(snap,api,now=NOW+31*60)
        self.assertEqual(snap['flights'][0]['registration'],'B-1234')
        self.assertIsNone(snap['flights'][0]['photo'])

    def test_board_assignment_wins_over_conflicting_cached_registration(self):
        snap=snapshot([raw(aircraftNumber='B1234')])
        class Fake:
            def get_status(self,*args):return result([detail()])
        self.run_enrich(snap,Fake())
        self.assertEqual(snap['flights'][0]['registration'],'B-1234')
        self.assertIsNone(snap['flights'][0]['type'])

    def test_ambiguous_source_duplicates_are_not_arbitrarily_assigned(self):
        entries=enrich.parse_details(result([detail(),detail(aircraftNumber='B1234')]))
        self.assertEqual(next(iter(entries.values()))['fields'],{})

    def test_budget_and_rate_limit_are_enforced_and_do_not_remove_board(self):
        class Fake:
            calls=0
            def get_status(self,*args):
                self.calls+=1
                raise client.MCPError('limited',429)
        snap=snapshot([raw(),raw(flightNumber='UI124',departureCode='CTU')]);api=Fake()
        with contextlib.redirect_stdout(io.StringIO()):stats=self.run_enrich(snap,api)
        self.assertEqual(api.calls,1);self.assertEqual(stats['fatal_status'],429)
        self.assertEqual(len(snap['flights']),2)
        api=Fake();self.run_enrich(snap,api,limit=0)
        self.assertEqual(api.calls,0)

    def test_empty_unassigned_results_have_short_negative_cache_and_daily_pruning(self):
        class Fake:
            calls=0
            def get_status(self,*args):self.calls+=1;return result([])
        api=Fake();snap=snapshot();self.run_enrich(snap,api)
        self.run_enrich(snap,api,now=NOW+60);self.assertEqual(api.calls,1)
        self.run_enrich(snap,api,now=NOW+16*60);self.assertEqual(api.calls,2)
        self.run_enrich({'airport':AIRPORT,'flights':[],'today':[]},api,now=NOW+4*86400)
        self.assertEqual(json.loads(self.path.read_text())['entries'],{})

    def test_known_models_not_registrations_drive_aircraft_classification(self):
        for model,code,wide,four in [('A330-343','A333',True,False),('777-31H','B77W',True,False),
                                    ('A380-800','A388',True,True),('737 MAX 8','B38M',False,False),
                                    ('JET','JET',None,None)]:
            fields=enrich.aircraft_model(model,code)
            self.assertEqual(fields['is_widebody'],wide)
            self.assertEqual(fields['is_four_engine'],four)
        self.assertIsNone(enrich.aircraft_model('JET','JET')['type'])

    def test_structured_error_is_not_a_successful_empty_detail_response(self):
        with self.assertRaises(client.MCPError):enrich.parse_details({'structuredContent':{
            'kind':'collection','items':[],'error':{'code':'DENIED'}}})

    def test_multiple_airports_are_batched_without_loosening_record_identity(self):
        class Fake:
            calls=[]
            def get_status(self,*args):
                self.calls.append(args)
                return result([detail(),detail(FlightNo='UI124',FlightDepcode='CTU',aircraftNumber='B1234')])
        snap=snapshot([raw(),raw(flightNumber='UI124',departureCode='CTU')]);api=Fake()
        stats=self.run_enrich(snap,api,limit=1)
        self.assertEqual(len(api.calls),1)
        self.assertEqual(set(api.calls[0][1].split(',')),{'PEK','CTU'})
        self.assertEqual(api.calls[0][2],'SZX')
        self.assertEqual({f['registration'] for f in snap['flights']},{'B-30EC','B-1234'})
        self.assertEqual(stats['batch_routes'],2)

    def test_eight_airports_share_one_call_without_guessing_missing_assignments(self):
        codes=['PEK','CTU','SHA','PVG','NKG','HFE','WUH','HRB']
        rows=[raw(flightNumber='UI'+str(200+i),departureCode=code) for i,code in enumerate(codes)]
        class Fake:
            calls=[]
            def get_status(self,*args):
                self.calls.append(args)
                return result([detail(FlightNo='UI'+str(200+i),FlightDepcode=code,
                                      aircraftNumber='B1234' if i!=7 else '') for i,code in enumerate(codes)])
        snap=snapshot(rows);api=Fake();stats=self.run_enrich(snap,api,limit=1)
        self.assertEqual(stats['route_calls'],1)
        self.assertEqual(set(api.calls[0][1].split(',')),set(codes))
        self.assertEqual(sum(bool(f.get('registration')) for f in snap['flights']),7)

    def test_today_curated_missing_registration_precedes_tomorrow_and_ordinary(self):
        snap=snapshot([raw(flightNumber='UI201',departureCode='PEK',arrPlanHour='12:30'),
            raw(flightNumber='UI202',departureCode='CTU',flightDesc='彩绘',arrPlanHour='16:00'),
            raw(flightNumber='UI203',departureCode='SHA',depDate='2026-10-21',arrDate='2026-10-21')])
        class Fake:
            calls=[]
            def get_status(self,*args):self.calls.append(args);return result([])
        api=Fake();self.run_enrich(snap,api,limit=1)
        self.assertEqual(api.calls[0][0],'2026-10-20')
        self.assertEqual(api.calls[0][1].split(',')[0],'CTU')

    def test_known_curated_assignment_cannot_steal_priority_from_missing_curated(self):
        snap=snapshot([raw(flightNumber='UI201',departureCode='PEK',flightDesc='已知彩绘',aircraftNumber='B1234'),
            raw(flightNumber='UI202',departureCode='PEK'),
            raw(flightNumber='UI203',departureCode='CTU',flightDesc='缺号彩绘',arrPlanHour='16:00')])
        class Fake:
            calls=[]
            def get_status(self,*args):self.calls.append(args);return result([])
        api=Fake();self.run_enrich(snap,api,limit=1)
        self.assertEqual(api.calls[0][1].split(',')[0],'CTU')

    def test_slow_batch_is_split_once_within_original_call_budget(self):
        codes=['PEK','CTU','SHA','PVG','NKG','HFE','WUH','HRB']
        snap=snapshot([raw(flightNumber='UI'+str(200+i),departureCode=c) for i,c in enumerate(codes)])
        class Fake:
            def __init__(self):self.calls=[]
            def get_status(self,*args):
                self.calls.append(args)
                if len(self.calls)==1:raise client.MCPError('timeout',retryable=True)
                return result([detail(FlightNo='UI'+str(200+i),FlightDepcode=c) for i,c in enumerate(codes)])
        api=Fake()
        with contextlib.redirect_stdout(io.StringIO()):stats=self.run_enrich(snap,api,limit=3)
        self.assertEqual(stats['route_calls'],2)
        self.assertLessEqual(len(api.calls[1][1].split(',')),4)
        self.assertTrue(all(f.get('registration') for f in snap['flights']))

    def test_selected_summary_missing_registration_gets_exact_flight_fallback(self):
        class Fake:
            def __init__(self):self.calls=[]
            def get_status(self,*args,fnum=None):
                self.calls.append((args,fnum))
                return result([detail(miniAirplaneModels='A350-941',generic='A359',
                                      aircraftNumber='B1234' if fnum else '')])
        snap=snapshot();api=Fake();stats=self.run_enrich(snap,api,limit=2)
        self.assertEqual(stats['route_calls'],2);self.assertEqual(stats['single_calls'],1)
        self.assertEqual(api.calls[1][1],'UI123')
        self.assertEqual(snap['flights'][0]['registration'],'B-1234')
        self.run_enrich(snap,api,limit=2,now=NOW+60)
        self.assertEqual(len(api.calls),2,'exact lookup must reuse its real assignment')

    def test_exact_empty_result_does_not_erase_verified_type_or_repeat(self):
        class Fake:
            def __init__(self):self.calls=0
            def get_status(self,*args,fnum=None):
                self.calls+=1
                return result([] if fnum else [detail(miniAirplaneModels='A350-941',generic='A359',aircraftNumber='')])
        snap=snapshot();api=Fake();stats=self.run_enrich(snap,api,limit=2)
        self.assertIsNone(snap['flights'][0]['registration'])
        self.assertEqual(snap['flights'][0]['type'],'A350-941')
        self.run_enrich(snap,api,limit=2,now=NOW+60)
        self.assertEqual(api.calls,2)

    def test_missing_actions_cache_recovers_details_from_verified_public_snapshot(self):
        class Fake:
            def get_status(self,*args):return result([detail()])
        old=snapshot();self.run_enrich(old,Fake())
        new=snapshot()
        # A different cache file simulates a fresh GitHub runner.
        stats=enrich.enrich_snapshots([new],None,limit=0,now=NOW+60,
              path=Path(self.temp.name)/'cold.json',previous=[old])
        self.assertEqual(new['flights'][0]['registration'],'B-30EC')
        self.assertEqual(stats['route_calls'],0)


class PhotoTests(unittest.TestCase):
    def test_existing_photo_service_cache_is_reused_by_registration_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shared=root/'shared.json'
            collect.write_json(shared,{'B-1234':{'updated_at':NOW,'photo':{'source':'planespotters',
                'src':'https://t.plnspttrs.net/1/test.jpg','link':'https://www.planespotters.net/photo/1/b-1234-test',
                'photographer':'Test author'},'type':'WRONG','flight_number':'OTHER'}})
            snap=snapshot([raw(aircraftNumber='B1234')])
            stats=photos.attach_photos([snap],limit=0,now=NOW,path=root/'own.json',shared=shared,delay=0)
            self.assertEqual(stats['calls'],0)
            self.assertEqual(snap['flights'][0]['photo']['reg'],'B-1234')
            self.assertIsNone(snap['flights'][0]['type'])
            self.assertEqual(snap['flights'][0]['flight_number'],'UI123')
    def test_missing_actions_cache_recovers_signed_reference_photo_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=snapshot([raw(aircraftNumber='B1234')]);new=snapshot([raw(aircraftNumber='B1234')])
            old['enriched_at']=NOW
            old['flights'][0]['photo']={'source':'planespotters','reg':'B-1234',
                'src':'https://t.plnspttrs.net/1/test.jpg','link':'https://www.planespotters.net/photo/1/b-1234-test',
                'photographer':'Test author','provider':'reference'}
            stats=photos.attach_photos([new],now=NOW+60,path=Path(tmp)/'cold.json',limit=0,previous=[old],delay=0)
            self.assertEqual(stats['calls'],0)
            self.assertEqual(new['flights'][0]['photo']['reg'],'B-1234')
    def test_reference_photo_has_registration_source_credit_and_safe_urls(self):
        raw_photo={'thumbnail_large':{'src':'https://t.plnspttrs.net/1/image.jpg'},
                   'link':'https://www.planespotters.net/photo/1/b-30ec-test', 'photographer':'Test author'}
        photo=photos.normalize_photo(raw_photo,'B-30EC')
        self.assertEqual(photo['reg'],'B-30EC');self.assertIn('非本航班实拍',photo['provider'])
        for key,value in [('photographer',''),('link','https://evil.test/photo/1'),('reg','B1234')]:
            self.assertIsNone(photos.normalize_photo(dict(raw_photo,**{key:value}),'B-30EC'))
        self.assertIsNone(photos.safe_url('https://t.plnspttrs.net.evil.test/x',True))

    def test_photo_cache_deduplication_and_missing_photo_backoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap=snapshot([raw(aircraftNumber='B1234'),raw(flightNumber='UI124',aircraftNumber='B1234')])
            calls=[]
            def fetch(reg):calls.append(reg);return None
            path=Path(tmp)/'photos.json'
            photos.attach_photos([snap],now=NOW,path=path,fetcher=fetch,delay=0)
            photos.attach_photos([snap],now=NOW+3600,path=path,fetcher=fetch,delay=0)
            self.assertEqual(calls,['B-1234'])

    def test_photo_http_limit_stops_and_does_not_fallback_to_theme_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap=snapshot([raw(aircraftNumber='B1234',flightPic='https://file.variflight.com/theme.png'),
                           raw(flightNumber='UI124',aircraftNumber='B5678')]);calls=[]
            def fetch(reg):calls.append(reg);raise photos.PhotoError('limited',429)
            photos.attach_photos([snap],now=NOW,path=Path(tmp)/'photos.json',fetcher=fetch,delay=0)
            self.assertEqual(len(calls),1)
            self.assertIsNone(snap['flights'][0]['photo'])

    def test_legacy_theme_image_is_removed_even_with_no_photo_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap=snapshot([raw(aircraftNumber='B1234',flightDesc='彩绘')])
            snap['flights'][0]['photo']={'src':'https://file.variflight.com/theme.png','provider':'theme'}
            stats=photos.attach_photos([snap],now=NOW,path=Path(tmp)/'photos.json',limit=0,delay=0,
                                      shared=Path(tmp)/'missing.json')
            self.assertEqual(stats['calls'],0)
            self.assertIsNone(snap['flights'][0]['photo'])


class DailyTests(unittest.TestCase):
    def test_manual_dispatch_never_silently_skips_collection_or_save(self):
        self.assertTrue(schedule.due({'updated_at':NOW},NOW+60,'workflow_dispatch'))
        self.assertTrue(schedule.due({'updated_at':NOW},NOW-60,'workflow_dispatch'))
        self.assertFalse(schedule.due({'updated_at':NOW},NOW+60,'schedule'))
    def test_two_china_time_slots_and_failed_attempts(self):
        at=lambda text:int(datetime.fromisoformat(text).timestamp())
        self.assertFalse(schedule.due({},at('2026-10-20T05:59:59+08:00')))
        morning=at('2026-10-20T06:00:00+08:00');afternoon=at('2026-10-20T14:00:00+08:00')
        self.assertTrue(schedule.due({},morning))
        self.assertFalse(schedule.due({'last_attempt_at':morning,'successes':0},morning+60))
        self.assertTrue(schedule.due({'last_attempt_at':morning},afternoon))
        self.assertFalse(schedule.due({'schedule_slots':['2026-10-20T14:00']},afternoon+60))
        self.assertFalse(schedule.due({},afternoon,cron='0 22 * * *'))
        self.assertTrue(schedule.due({},morning,cron='0 22 * * *'))
        self.assertTrue(schedule.due({'last_attempt_at':afternoon},morning+86400))

    def test_shared_daily_budget_reserves_afternoon_and_persists_failures(self):
        at=lambda text:int(datetime.fromisoformat(text).timestamp())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'budget.json';records=[]
            b=budget.DetailBudget(path,{},at('2026-10-20T06:00:00+08:00'),records.append)
            for _ in range(100):self.assertTrue(b.reserve())
            self.assertFalse(b.reserve())
            resumed=budget.DetailBudget(path,{},at('2026-10-20T08:00:00+08:00'))
            self.assertEqual(resumed.remaining(),0)
            pm=budget.DetailBudget(path,{},at('2026-10-20T14:00:00+08:00'))
            for _ in range(100):self.assertTrue(pm.reserve())
            self.assertFalse(pm.reserve());self.assertEqual(pm.record()['used'],200)
            cold=budget.DetailBudget(Path(tmp)/'cold.json',{'daily_detail_budget':pm.record()},at('2026-10-20T16:00:00+08:00'))
            self.assertEqual(cold.remaining(),0)
            next_day=budget.DetailBudget(path,{},at('2026-10-21T06:00:00+08:00'))
            self.assertEqual(next_day.remaining(),100)

    def test_workflow_manual_only_and_never_exposes_key_in_source(self):
        root=Path(__file__).resolve().parents[2]
        workflow=(root/'.github/workflows/feimadata.yml').read_text()
        self.assertNotIn('cron:',workflow)
        self.assertIn('  workflow_dispatch:',workflow)
        self.assertIn('secrets.VARIFLIGHT_MCP_KEY',workflow)
        self.assertIn('feimadata.schedule',workflow)
        self.assertEqual(enrich.DEFAULT_DETAIL_LIMIT,200)
        self.assertIn('--airports SZX --detail-limit 200 --photo-limit 60',workflow)
        self.assertIn('steps.privacy.outcome',workflow)
        self.assertIn('/feimadata/.cache/',(root/'.gitignore').read_text())


if __name__=='__main__':unittest.main()
