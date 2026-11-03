"""Offline regression for the optional document transport."""
import html
import importlib.util
import json
from pathlib import Path
from unittest import TestCase, main, mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fr24_document', ROOT/'flightdata/document_transport.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def response(status, page=1, challenge=False):
    data = {'props': {'airport': {'iata': 'SZX'}, 'flights': [{'id': str(page)}],
                      'meta': {'nextPage': page+1, 'hoursRange': 24}}}
    body = ('<div id="app" data-page="' + html.escape(json.dumps(data), quote=True) + '"></div>'
            + '<a href="?page=' + str(page+1) + '">next</a>').encode()
    class Response:
        headers = {'cf-mitigated': 'challenge'} if challenge else {'content-type': 'text/html'}
        def __init__(self): self.status = status
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return body
    return Response()


class DocumentTests(TestCase):
    def setUp(self):
        self.client = module.DocumentTransport(None, lambda r, msg: PermissionError(msg))
        self.airport = {'iata': 'SZX'}

    @mock.patch.object(module.time, 'sleep')
    def test_follows_observed_link_and_stops_on_refusal(self, sleep):
        self.client.opener = SimpleNamespace(open=mock.Mock(side_effect=[response(200), response(200, 2), response(403, challenge=True)]))
        first = self.client.first('arrivals', self.airport)
        second = self.client.next('arrivals', self.airport, first)
        self.assertEqual(second['props']['flights'][0]['id'], '2')
        with self.assertRaises(PermissionError):
            self.client.next('arrivals', self.airport, second)
        self.assertEqual(self.client.opener.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @mock.patch.object(module.random, 'uniform', return_value=3.5)
    @mock.patch.object(module.time, 'sleep')
    def test_spacing_includes_first_page_of_next_board(self, sleep, uniform):
        self.client.opener = SimpleNamespace(open=mock.Mock(return_value=response(200)))
        self.client.first('arrivals', self.airport)
        self.client.first('departures', self.airport)
        uniform.assert_called_once_with(3.5, 4.0)
        sleep.assert_called_once_with(3.5)

    @mock.patch.object(module.time, 'sleep')
    def test_does_not_follow_offsite_or_repeated_data(self, sleep):
        self.client.opener = SimpleNamespace(open=mock.Mock(return_value=response(200)))
        first = self.client.first('arrivals', self.airport)
        first['_pagination_links'] = ['https://example.org/data/airports/szx/arrivals?page=2']
        with self.assertRaises(RuntimeError):
            self.client.next('arrivals', self.airport, first)
        first['_pagination_links'] = ['?page=2']
        with self.assertRaises(RuntimeError):
            self.client.next('arrivals', self.airport, first)
        self.assertEqual(self.client.opener.open.call_count, 2)


if __name__ == '__main__':
    main()
