"""Validate workflow-run publish gating without any live GitHub request."""
import ast
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class PublishGateTests(unittest.TestCase):
    def test_only_a_run_that_saved_status_publishes_the_site(self):
        source=(ROOT/'.github/workflows/update.yml').read_text()
        code=textwrap.dedent(source.split("python3 - <<'PY'\n",1)[1].split('\n          PY',1)[0])
        ast.parse(code)
        for same in [True,False]:
            with self.subTest(same=same),tempfile.TemporaryDirectory(prefix='flightdat-publish-') as temporary:
                output=Path(temporary)/'output'
                env={'EVENT_NAME':'workflow_run','EVENT_SCHEDULE':'','SOURCE_RUN_URL':'https://github.com/test/actions/runs/123',
                     'GH_REPOSITORY':'test/repo','GH_TOKEN':'offline-fixture','GITHUB_OUTPUT':str(output)}
                body={'run_url':env['SOURCE_RUN_URL'] if same else 'https://github.com/test/actions/runs/122'}
                with patch.dict(os.environ,env),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(body).encode())):
                    exec(compile(code,'weather-publish-gate','exec'),{})
                self.assertEqual(output.read_text(),f'run={str(same).lower()}\n')


if __name__=='__main__':unittest.main()
