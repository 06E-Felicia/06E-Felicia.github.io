"""Scenario constraints do not bypass parcel work or modify existing rain."""
import unittest
import numpy as np
from scipy.ndimage import label
from simulation.core import Model
from simulation.terrain import grid


class SingleEpisodeTests(unittest.TestCase):
    def model(self,seed=20260421):
        c={'seed':seed,'grid_km':12,'bounds':[105,20,117,26.7]}
        return Model(c,np.full(grid(c['bounds'],12)[0].shape,30.))

    def test_one_connected_finite_confluence_episode(self):
        m=self.model();s=m.synoptic
        self.assertIsNotNone(s.genesis_center)
        for t in [0,s.genesis_start,s.genesis_start+s.genesis_duration,72*3600]:
            for a in s.genesis(t):np.testing.assert_array_equal(a,0)
        t=s.genesis_start+.5*s.genesis_duration;flow,permission=s.genesis(t)
        self.assertEqual(label(permission>.1)[1],1)
        self.assertGreater(float(flow.max()),0);self.assertLess(float(flow.min()),0)
        convergence=-np.gradient(flow,m.dx,axis=1)
        self.assertGreater(float(convergence[permission>.8].max()),1e-4)
        # Forcing alone must not populate a prescribed rain/cold-pool object.
        np.testing.assert_array_equal(m.rain,0);np.testing.assert_array_equal(m.cold_content,0)

    def test_episode_is_seeded_and_does_not_repeat_without_new_soundings(self):
        a=self.model();b=self.model();c=self.model(20260423)
        self.assertEqual(a.synoptic.genesis_center,b.synoptic.genesis_center)
        self.assertNotEqual(a.synoptic.genesis_center,c.synoptic.genesis_center)
        for hour in [12,24,48,72]:
            np.testing.assert_array_equal(a.synoptic.genesis(hour*3600)[1],0)

    def test_next_day_can_open_new_episode_without_cape_or_cold_pool_reset(self):
        m=self.model();m.time=86400;m.genesis_closed=True;m.genesis_started=True
        m.cape_deficit.fill(100);m.cold_depth[:,0]=500;m.cold_content[:,0]=1500;m.cold_diagnostics()
        cold=m.cold_content.copy();debt=m.cape_deficit.copy()
        m.step(86401)
        self.assertEqual(m.convective_day,1);self.assertIsNotNone(m.synoptic.genesis_center)
        self.assertTrue(86400<m.synoptic.genesis_start<86400+5401)
        self.assertFalse(m.genesis_closed)
        self.assertGreater(float(m.cape_deficit.mean()),90)
        self.assertGreater(float(m.cold_content.sum()),float(cold.sum())*.9)

    def test_new_day_cannot_relabel_exhausted_cold_wake_as_fresh(self):
        m=self.model();m.time=86400;m.genesis_closed=True
        m.air.fill(1);m.cold_depth.fill(600);m.cold_content.fill(2400);m.cold_diagnostics()
        m.cape_deficit[:]=m.cape_capacity
        m.step(86401)
        self.assertEqual(m.convective_day,1);self.assertIsNone(m.synoptic.genesis_center)
        np.testing.assert_array_equal(m.initiation,0)

    def test_dry_organization_cannot_close_the_initiation_window(self):
        m=self.model();m.time=m.synoptic.genesis_start+1800
        m.organization.fill(1);m.genesis_started=True
        m.activity.fill(0);m.last_rate.fill(0)
        m.step(m.time+1)
        self.assertFalse(m.genesis_closed)

    def test_weak_drizzle_layer_is_not_misclassified_as_exhausted_storm_wake(self):
        m=self.model();m.air.fill(0);m.cape_deficit.fill(0)
        for cooling,depth in [(.3,150),(.8,80)]:
            m.cold_depth.fill(depth);m.cold_content.fill(cooling*depth);m.cold_diagnostics()
            self.assertTrue(m.fresh_initiation_air().all())
        m.cold_depth.fill(600);m.cold_content.fill(2400);m.cold_diagnostics()
        self.assertFalse(m.fresh_initiation_air().any())
        m.cold_depth.fill(80);m.cold_content.fill(24);m.cold_diagnostics()
        m.cape_capacity.fill(1000)
        m.cape_deficit[:]=.8*m.cape_capacity
        self.assertFalse(m.fresh_initiation_air().any())

    def test_balanced_oblique_head_can_overcome_cin_but_still_needs_energy(self):
        m=self.model();r=np.sqrt(.5);balance=m.cold_head_balance(20,20,0,r,r)
        self.assertGreater(m.gust_activation(6000,1000,1,balance,0,-40),.5)
        self.assertEqual(m.gust_activation(0,1000,1,balance,0,-40),0)
        self.assertEqual(m.gust_activation(6000,1000,1,0,0,-40),0)
        self.assertEqual(m.gust_activation(6000,1000,1,balance,5000,-40),0)

    def test_32m_s_is_an_envelope_not_a_gust_floor(self):
        m=self.model();m.u.fill(8);m.v.fill(0);m.syn_u.fill(8);m.syn_v.fill(0)
        m.downburst_energy.fill(0);self.assertLess(float(m.surface_gust().max()),12)
        m.downburst_energy.fill(440);self.assertGreater(float(m.surface_gust().min()),30)
        self.assertLessEqual(float(m.surface_gust().max()),32)
        m.downburst_energy.fill(800);np.testing.assert_array_equal(m.surface_gust(),32)

    def test_unrelated_environmental_cold_patch_cannot_seed_second_episode(self):
        m=self.model();m.genesis_closed=True
        m.cold_depth[:,:20]=600;m.cold_content=m.cold_depth*4
        m.step()
        np.testing.assert_array_equal(m.initiation,0)


if __name__=='__main__':unittest.main()
