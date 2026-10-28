"""Actual fine-DEM obstacles; no hardcoded radar attenuation around a city."""
import unittest
import numpy as np
from simulation.core import Model,settings
from simulation.run import terrain_for


class CoastalTerrainTests(unittest.TestCase):
    def model(self,terrain=True):
        cfg=settings({'grid_km':12,'seed':20260423,'terrain':terrain})
        h,meta=terrain_for(cfg,'assets/data/simulation-terrain.npz')
        return Model(cfg,h),meta

    def test_real_summits_survive_coarse_sampling_without_becoming_full_cell_walls(self):
        m,meta=self.model()
        phoenix=(m.lon>113.4)&(m.lon<113.65)&(m.lat>22.3)&(m.lat<22.55)
        hk=(m.lon>113.85)&(m.lon<114.5)&(m.lat>22.12)&(m.lat<22.58)
        self.assertGreater(float(m.terrain_peak[phoenix].max()),500)
        self.assertGreater(float(m.terrain_peak[hk].max()),850)
        self.assertLess(float(m.h[hk].max()),float(m.terrain_peak[hk].max())*.65)
        self.assertGreater(float(m.terrain_relief[hk].max()),100)
        self.assertEqual(meta['coastal_detail']['grid_km'],.25)

    def test_disabling_terrain_removes_unresolved_obstacles_too(self):
        m,_=self.model(False)
        np.testing.assert_array_equal(m.h,0);np.testing.assert_array_equal(m.terrain_relief,0)
        np.testing.assert_array_equal(m.terrain_peak,0);np.testing.assert_array_equal(m.terrain_cover,0)

    def test_hills_act_on_warm_inflow_not_a_radar_or_rain_mask(self):
        m,_=self.model();one=np.ones(m.shape);u,v=m.winds()
        # Same atmospheric state and resolved terrain in both calls. Only
        # unresolved real-DEM obstruction differs, including at the summit.
        real,hazard=m.plume_environment(one*300,one*20,one*0,u,v)
        relief=m.terrain_relief.copy();m.terrain_relief.fill(0)
        flat,flat_hazard=m.plume_environment(one*300,one*20,one*0,u,v)
        hk=(m.lon>113.85)&(m.lon<114.5)&(m.lat>22.12)&(m.lat<22.58)&(relief>100)
        self.assertTrue(hk.any());self.assertTrue(np.all(real[hk]<flat[hk]))
        self.assertTrue(np.all(hazard[hk]>flat_hazard[hk]))
        np.testing.assert_array_equal(m.rain,0)


if __name__=='__main__':unittest.main()
