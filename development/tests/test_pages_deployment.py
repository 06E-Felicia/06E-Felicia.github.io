"""Pages retry transitions and effective runner deadlines (requires PyYAML)."""
import importlib.util
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(importlib.util.find_spec('yaml'),'PyYAML required to validate workflow configuration')
class PagesDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml
        cls.load=lambda self,p:yaml.safe_load((ROOT/p).read_text())

    def test_attempts_obey_platform_cap_and_reuse_the_uploaded_artifact(self):
        action=self.load('.github/actions/deploy-pages-with-retry/action.yml')
        self.assertEqual(action['runs']['using'],'composite')
        attempts=[s for s in action['runs']['steps'] if 'uses' in s]
        self.assertEqual([s['id'] for s in attempts],['first','second','third'])
        for s in attempts:
            self.assertEqual(s['uses'],'actions/deploy-pages@v4')
            self.assertLessEqual(s['with']['timeout'],600000)
            self.assertNotIn('artifact_name',s['with'])
        self.assertTrue(attempts[0]['continue-on-error'])
        self.assertTrue(attempts[1]['continue-on-error'])
        self.assertFalse(attempts[2].get('continue-on-error',False))
        output=action['outputs']['page_url']['value']
        self.assertLess(output.index('steps.third'),output.index('steps.second'))
        self.assertLess(output.index('steps.second'),output.index('steps.first'))

    def test_success_stops_retries_and_three_failures_remain_a_failure(self):
        steps=[s for s in self.load('.github/actions/deploy-pages-with-retry/action.yml')['runs']['steps'] if 'uses' in s]
        def condition(text,seen):
            terms=[]
            for term in text.split('&&'):
                m=re.fullmatch(r"\s*steps\.(\w+)\.outcome\s*==\s*'(\w+)'\s*",term)
                self.assertIsNotNone(m,text)
                terms.append(seen.get(m[1])==m[2])
            return all(terms)
        for sequence,expected_count,expected_failure in [(['success'],1,False),(['failure','success'],2,False),(['failure','failure','success'],3,False),(['failure']*3,3,True)]:
            with self.subTest(sequence=sequence):
                seen={};count=0;failed=False
                for s in steps:
                    if 'if' in s and not condition(s['if'],seen):continue
                    outcome=sequence[count];count+=1;seen[s['id']]=outcome
                    if outcome=='failure' and not s.get('continue-on-error',False):failed=True
                self.assertEqual((count,failed),(expected_count,expected_failure))
        self.assertFalse(condition(steps[1]['if'],{'first':'cancelled'}))
        self.assertFalse(condition(steps[2]['if'],{'first':'failure','second':'success'}))

    def test_publishers_have_real_thirty_minute_deadlines_and_checkout_protection(self):
        for workflow,jobname in [('update','update-weather'),('simulation','publish')]:
            with self.subTest(workflow=workflow):
                job=self.load(f'.github/workflows/{workflow}.yml')['jobs'][jobname]
                self.assertEqual(job['timeout-minutes'],40)
                deploy=[s for s in job['steps'] if s.get('id')=='deployment']
                self.assertEqual(len(deploy),1)
                self.assertEqual(deploy[0]['uses'],'./.github/actions/deploy-pages-with-retry')
                self.assertEqual(deploy[0]['timeout-minutes'],30)
                self.assertNotIn('with',deploy[0])
                checkout=next(s for s in job['steps'] if s.get('uses','').startswith('actions/checkout@'))
                self.assertEqual(checkout['with']['ref'],'${{ github.event.repository.default_branch }}')
                self.assertEqual(job['permissions']['pages'],'write')
                self.assertEqual(job['permissions']['id-token'],'write')
                upload=next(i for i,s in enumerate(job['steps']) if s.get('uses','').startswith('actions/upload-pages-artifact@'))
                self.assertLess(upload,job['steps'].index(deploy[0]))
        source=(ROOT/'.github/workflows/update.yml').read_text()
        self.assertIn('for attempt in 1 2 3',source)
        self.assertIn('git rebase FETCH_HEAD',source)
        self.assertNotIn('git push --force',source)
        self.assertNotIn('1800000',source)

if __name__=='__main__':unittest.main()
