"""Sol initiation closure is finite, budget-neutral and edition-isolated."""
import json
import unittest
from unittest.mock import patch
import numpy as np
from simulation import browser
from simulation.core import Model,source_digest
from simulation.sol import SolModel
from simulation.terrain import grid
from simulation.experiment import random_environment
from simulation.run import terrain_for


class SolTriggerTests(unittest.TestCase):
    def model(self,km=28):
        cfg={'seed':20260423,'grid_km':km,'bounds':[106,21,113,25.5]}
        m=SolModel(cfg,np.full(grid(cfg['bounds'],km)[0].shape,30.),grid_limit=28)
        m.time=m.synoptic.genesis_start+.5*m.synoptic.genesis_duration
        m.air.fill(0);m.cape_deficit.fill(0)
        return m

    def correction(self,m,convergence=1e-4):
        a=np.full(m.shape,convergence);zero=np.zeros(m.shape)
        restoring=Model.frontal_lifting(m,a,a,zero,zero)
        original=m.background_w.copy()
        actual=m.frontal_lifting(a,a,zero,zero)
        np.testing.assert_array_equal(restoring,actual)
        return m.background_w-original

    def test_sol_compensates_only_the_finite_positive_confluence(self):
        m=self.model();_,permission=m.synoptic.genesis(m.time)
        water=m.q.copy();temp=m.temp.copy();cape=m.mu['cape'].copy()
        correction=self.correction(m)
        self.assertGreater(float(correction.max()),.1)
        np.testing.assert_array_equal(correction[permission==0],0)
        self.assertLessEqual(float(m.background_w.max()),.8)
        np.testing.assert_array_equal(m.q,water)
        np.testing.assert_array_equal(m.temp,temp)
        np.testing.assert_array_equal(m.mu['cape'],cape)
        np.testing.assert_array_equal(m.initiation,0)
        np.testing.assert_array_equal(m.rain,0)

    def test_no_correction_without_convergence_or_outside_episode(self):
        for mode in ['divergent','zero','closed','before','after','no_soundings']:
            with self.subTest(mode=mode):
                m=self.model();c=1e-4
                if mode=='divergent':c=-1e-4
                if mode=='zero':c=0
                if mode=='closed':m.genesis_closed=True
                if mode=='before':m.time=m.synoptic.genesis_start
                if mode=='after':m.time=m.synoptic.genesis_start+m.synoptic.genesis_duration
                if mode=='no_soundings':m.synoptic.genesis_center=None
                np.testing.assert_array_equal(self.correction(m,c),0)

    def test_spent_wake_or_frontal_cold_air_cannot_gain_extra_lift(self):
        for mode in ['cold_pool','spent_cape','cold_air']:
            with self.subTest(mode=mode):
                m=self.model()
                if mode=='cold_pool':
                    m.cold_depth.fill(600);m.cold_content.fill(2400);m.cold_diagnostics()
                if mode=='spent_cape':m.cape_deficit[:]=m.cape_capacity
                if mode=='cold_air':m.air.fill(1)
                np.testing.assert_array_equal(self.correction(m),0)

    def test_reference_resolution_needs_no_extra_lift(self):
        np.testing.assert_array_equal(self.correction(self.model(12)),0)

    def test_inaccessible_lfc_still_blocks_convection(self):
        m=self.model();m.next_diagnostic=m.time+3600
        m.lfc.fill(np.inf);m.mu_lfc.fill(np.inf)
        m.step(m.time+30)
        np.testing.assert_array_equal(m.initiation,0)
        np.testing.assert_array_equal(m.activity,0)

    def test_only_sol_browser_path_selects_sol_model(self):
        astra=json.loads(browser.initialize(20260421,'{"hours":1,"grid_km":12}','astra'))
        self.assertIs(type(browser.model),Model)
        self.assertEqual(astra['source_sha256'],source_digest('experiment.py','browser.py'))
        sol=json.loads(browser.initialize(20260421,'{"hours":1}','sol'))
        self.assertIs(type(browser.model),SolModel)
        self.assertEqual(sol['source_sha256'],source_digest('experiment.py','browser.py','sol.py'))
        self.assertEqual(sol['config']['grid_km'],28)

    def test_astra_matches_core_without_any_sol_closure(self):
        # Use the unchanged shared core as reference, not a golden hash that
        # would wrongly fail on a different NumPy/SciPy floating-point build.
        cfg=random_environment(20260421,{'hours':1,'grid_km':12,'frame_minutes':30})
        height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
        reference=Model(cfg,height)
        for _ in range(40):reference.step()
        with patch.object(SolModel,'frontal_lifting',side_effect=AssertionError('Sol path reached Astra')):
            browser.initialize(20260421,'{"hours":1,"grid_km":12,"frame_minutes":30}','astra')
            for _ in range(40):browser.model.step()
        fields=browser.model.fields();original=reference.fields()
        self.assertEqual(len(fields),39)
        self.assertEqual(browser.model.time,reference.time)
        self.assertEqual(browser.model.cfg,reference.cfg)
        for key in fields:np.testing.assert_array_equal(fields[key],original[key],err_msg=key)


if __name__=='__main__':unittest.main()
