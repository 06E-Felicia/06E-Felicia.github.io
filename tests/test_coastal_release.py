"""Fractional shorelines, finite entry work and moving environmental release."""
import unittest
import numpy as np
from simulation.core import Model
from simulation.terrain import TerrainField,grid
from simulation.sol import SolModel


class CoastalReleaseTests(unittest.TestCase):
    def model(self,fraction=None,edition='astra'):
        km=12 if edition=='astra' else 28
        cfg={'seed':20261017,'bounds':[111,21,115,25],'grid_km':km,'sst_c':20,'stochastic':0}
        h=np.full(grid(cfg['bounds'],km)[0].shape,30.)
        if fraction is not None:
            zero=np.zeros_like(h);h=TerrainField(h,zero,h.copy(),zero,np.full(h.shape,fraction))
        return (Model if edition=='astra' else SolModel)(cfg,h,grid_limit=28)

    def test_crossing_fifty_percent_land_does_not_jump_to_an_entire_marine_column(self):
        for edition in ['astra','sol']:
            a,b=self.model(.49,edition),self.model(.51,edition)
            self.assertFalse(a.land.any());self.assertTrue(b.land.all())
            self.assertLess(float(np.max(np.abs(a.temp-b.temp))),.2)
            self.assertLess(float(np.max(np.abs(a.q-b.q))),.0002)
            np.testing.assert_array_equal(a.rain,0);np.testing.assert_array_equal(b.rain,0)

    def test_fractional_surface_exchange_keeps_the_actual_external_water_account(self):
        for fraction in [0,.25,.49,.51,.75,1]:
            m=self.model(fraction);before=float(np.sum(m.q*m.mass));external=m.external_water
            m.surface_exchange(30,.8,.8)
            change=float(np.sum(m.q*m.mass))-before
            self.assertAlmostEqual(change,m.external_water-external,delta=1e-7)
            self.assertTrue(np.isfinite(m.temp).all())

    def test_whole_column_inhibition_does_not_multiply_the_same_marine_entry_cost(self):
        m=self.model();m.land.fill(False);m.activity.fill(.5);m.surface_activity.fill(.5)
        m.sb['cape'].fill(0);m.mu['cape'].fill(2000);m.sb['cin'].fill(-250)
        m.donors=np.broadcast_to(np.arange(m.shape[0])[:,None]*m.shape[1],m.shape).copy()
        one=np.ones(m.shape)
        m.mu['cin'].fill(-300);m.mu['cin'][:,0]=-30
        finite,hazard=m.plume_environment(one*500,one*20,one*0)
        m.mu['cin'].fill(-3000);m.mu['cin'][:,0]=-30
        deeper,deeper_hazard=m.plume_environment(one*500,one*20,one*0)
        np.testing.assert_allclose(finite[:,1:],deeper[:,1:])
        np.testing.assert_allclose(hazard[:,1:],deeper_hazard[:,1:])
        self.assertTrue(np.all(finite[:,1:]<1))
        np.testing.assert_array_equal(m.rain,0)

    def test_weakening_over_mixed_coast_is_continuous_and_cold_sea_still_weakens(self):
        m=self.model();m.activity.fill(.7);m.surface_activity.fill(.7)
        m.sb['cape'].fill(0);m.mu['cape'].fill(2000);m.sb['cin'].fill(-250)
        one=np.ones(m.shape);values=[]
        for fraction in [0,.49,.51,1]:
            m._land_fraction=np.full(m.shape,fraction)
            efficiency,_=m.plume_environment(one*500,one*20,one*0)
            values.append(float(efficiency.mean()))
        self.assertLess(values[0],values[1]);self.assertLess(values[1],values[2]);self.assertLess(values[2],values[3])
        self.assertLess(values[2]-values[1],.03)

    def test_confluence_translation_uses_actual_flow_and_does_not_move_cloud_or_add_water(self):
        m=self.model();s=m.synoptic
        self.assertIsNotNone(s.genesis_center)
        start=s.genesis_center;before=m.q.copy();rain=m.rain.copy()
        u=np.full(m.shape,15.);v=np.full(m.shape,-3.)
        s.advect_genesis(600,s.genesis_start+s.genesis_duration*.5,u,v)
        self.assertAlmostEqual((s.genesis_center[0]-start[0])*111195*np.cos(np.radians(start[1])),9000,places=7)
        self.assertAlmostEqual((s.genesis_center[1]-start[1])*111195,-1800,places=7)
        np.testing.assert_array_equal(m.q,before);np.testing.assert_array_equal(m.rain,rain)
        self.assertEqual(s.genesis_initial_center,start)

    def test_ended_or_unstarted_packet_does_not_gain_an_automatic_track(self):
        m=self.model();s=m.synoptic;start=s.genesis_center;one=np.ones(m.shape)
        for t in [s.genesis_start,s.genesis_start+s.genesis_duration,96*3600]:
            s.advect_genesis(600,t,one*20,one*4)
            self.assertEqual(s.genesis_center,start)
        m.step(1)
        self.assertFalse(m.genesis_started);self.assertEqual(s.genesis_center,start)


if __name__=='__main__':unittest.main()
