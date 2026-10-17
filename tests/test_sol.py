"""Sol reduces horizontal work, never substitutes a weather animation."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from simulation import browser
from simulation.core import Model, Z, settings
from simulation.experiment import random_environment
from simulation.terrain import grid
from simulation.core import VERSION,source_digest


class SolTests(unittest.TestCase):
    def test_sol_grid_tuning_cannot_change_astra_initialization_or_evolution(self):
        outputs=[];configs=[];times=[]
        for sol_grid in [28,32]:
            with patch.object(browser,'SOL_GRID_KM',sol_grid):
                manifest=json.loads(browser.initialize(20260421,json.dumps({'hours':1,'grid_km':12,'frame_minutes':30}),'astra'))
                for _ in range(40):browser.model.step()
                outputs.append({k:v.copy() for k,v in browser.model.fields().items()});configs.append(manifest['config']);times.append(browser.model.time)
        self.assertEqual(configs[0],configs[1]);self.assertEqual(times[0],times[1])
        for key in outputs[0]:np.testing.assert_array_equal(outputs[0][key],outputs[1][key],err_msg=key)
        if os.environ.get('ASTRA_ISOLATION_OUTPUT'):
            Path(os.environ['ASTRA_ISOLATION_OUTPUT']).write_text(json.dumps({'engine':VERSION,'source_sha256':source_digest('experiment.py','browser.py'),
                'physical_source_sha256':source_digest('experiment.py'),'sol_grids_compared':[28,32],
                'same_astra_fields_after_40_steps':True,'compared_field_count':len(outputs[0]),'astra_config':configs[0],'simulated_seconds':times[0]},indent=2))

    def test_astra_validation_is_unchanged(self):
        with self.assertRaises(ValueError):settings({'grid_km':24})
        self.assertEqual(settings({'grid_km':24},grid_limit=24)['grid_km'],24)
        with self.assertRaises(ValueError):settings({'grid_km':25},grid_limit=24)

    def test_same_seed_preserves_sampled_environment(self):
        astra=random_environment(20260421)
        km=browser.SOL_GRID_KM
        sol=random_environment(20260421,{'grid_km':km,'frame_minutes':60},grid_limit=km)
        for key in ['seed','month','moisture','jet','shear','trough','cold_reservoir','sst_c','stochastic']:
            self.assertEqual(astra[key],sol[key])
        other=random_environment(20260422,{'grid_km':km},grid_limit=km)
        self.assertNotEqual(sol['moisture'],other['moisture'])

    def test_output_omits_unused_mixed_parcel_not_mu_cape(self):
        cfg={'bounds':[112,22,114,25],'grid_km':24}
        model=Model(cfg,np.full(grid(cfg['bounds'],24)[0].shape,30),grid_limit=24)
        before=model.temp.copy();clock=model.next_diagnostic
        complete=model.fields();light=model.fields(include_mixed=False)
        self.assertNotIn('mlcape',light);self.assertNotIn('cin',light)
        for key in light:np.testing.assert_array_equal(light[key],complete[key])
        np.testing.assert_array_equal(model.temp,before)
        self.assertEqual(model.next_diagnostic,clock)
        self.assertEqual(len(Z),14)

    def test_browser_sol_profile_is_fixed_and_keeps_physics(self):
        manifest=json.loads(browser.initialize(20260421,json.dumps({'hours':1,'grid_km':4,'frame_minutes':10}),'sol'))
        self.assertEqual(manifest['edition'],'sol')
        self.assertEqual(manifest['product_version'],'2')
        self.assertTrue(browser.model.astra_updates,'Sol must inherit corrected frontal/ice/downdraft physics')
        self.assertEqual(manifest['config']['grid_km'],browser.SOL_GRID_KM)
        self.assertEqual(manifest['config']['frame_minutes'],60)
        self.assertEqual(len(manifest['grid']['z_agl_m']),14)
        while browser.model.time<3600:browser.advance(3600)
        snapshot=json.loads(browser.snapshot());audit=snapshot['audit']
        self.assertLess(abs(audit['water_relative_residual']),.002)
        self.assertLessEqual(audit['max_cfl'],.450001)
        self.assertEqual(set(snapshot['fields']),browser.SOL_FIELDS)
        self.assertEqual(snapshot['hour'],1)
        with self.assertRaises(ValueError):browser.initialize(1,'{}','unknown')

    def test_coarse_head_uses_actual_neighbour_instead_of_rounding_to_self(self):
        for km in (24,browser.SOL_GRID_KM):
            with self.subTest(km=km):
                c={'bounds':[112,22,114,25],'grid_km':km}
                m=Model(c,np.full(grid(c['bounds'],km)[0].shape,30),grid_limit=km)
                m.cold_depth[:,2]=600;m.cold_content[:,2]=2400
                m.cape_deficit.fill(0);m.cape_ceiling.fill(3600);m.mu['cape'].fill(1800);m.cape_capacity.fill(1800)
                nx=np.ones(m.shape);ny=np.zeros(m.shape)
                donor,usable=m.warm_inflow(nx,ny,np.ones(m.shape),np.ones(m.shape))
                y=np.arange(m.shape[0])
                np.testing.assert_array_equal(donor[:,2],y*m.shape[1]+3)
                self.assertTrue(np.all(usable[:,2]))

    def test_legacy_branch_remains_available_but_not_live_sol(self):
        c={'bounds':[112,22,114,25],'grid_km':24}
        old=Model(c,np.full(grid(c['bounds'],24)[0].shape,30),grid_limit=24,astra_updates=False)
        self.assertFalse(old.astra_updates)


if __name__=='__main__':unittest.main()
