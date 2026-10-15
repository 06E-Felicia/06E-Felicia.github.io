"""Causal trailing-cloud tests: real water, phase changes and source memory.

These controlled mechanism tests do NOT certify real squall-line morphology.
"""
import unittest
import numpy as np
from simulation.core import Model
from simulation.terrain import grid
from simulation.thermo import saturation, saturation_ice
from simulation.numerics import Advection


class StratiformTests(unittest.TestCase):
    def model(self,**options):
        cfg={'bounds':[111,22,113,24],'grid_km':10,**options}
        return Model(cfg,np.full(grid(cfg['bounds'],cfg['grid_km'])[0].shape,30))

    def water(self,m):
        return float(np.sum((m.q+m.cloud+m.rain+m.anvil)*m.mass,dtype='float64'))

    def test_ice_saturation_reference_and_liquid_parcels_unchanged(self):
        self.assertAlmostEqual(float(saturation_ice(np.array(253.15),80000)),.0008035,delta=2e-6)
        self.assertLess(float(saturation_ice(np.array(253.15),80000)),float(saturation(253.15,80000)))
        np.testing.assert_array_equal(saturation_ice(np.array([273.15,290.]),80000),saturation(np.array([273.15,290.]),80000))

    def test_supersaturation_and_dry_cold_air_do_not_invent_ice(self):
        m=self.model();m.temp[8:]=260;m.q[:]=saturation(m.temp,m.p)*.99
        m.cold.fill(8);m.cold_depth.fill(1000);before=self.water(m)
        fallen=m.trailing_microphysics(90)
        self.assertEqual(float(m.anvil.max()),0)
        self.assertEqual(float(m.rain.max()),0)
        self.assertAlmostEqual(self.water(m)+fallen.sum(),before,places=8)

    def test_freezing_processes_environmental_as_well_as_plume_cloud(self):
        m=self.model();m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p)*.99
        m.cloud[9]=.0012;m.plume_cloud[9]=.0006
        before=self.water(m);surface=m.trailing_microphysics(90)
        self.assertGreater(float(m.anvil[9].mean()),.0005)
        self.assertLess(float(m.cloud[9].mean()),.00065)
        np.testing.assert_allclose(m.plume_cloud[9],m.cloud[9]*.5)
        self.assertLess(abs(self.water(m)+surface.sum()-before)/before,1e-12)

    def test_ice_growth_debits_real_supersaturated_vapour(self):
        m=self.model();m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p)
        m.q[9]*=1.2;m.anvil[9]=.0002
        before=self.water(m);vapour=float(np.sum(m.q*m.mass));temperature=m.temp[9].copy()
        surface=m.trailing_microphysics(90)
        self.assertLess(float(np.sum(m.q*m.mass)),vapour)
        self.assertTrue(np.all(m.temp[9]>temperature))
        self.assertLess(abs(self.water(m)+surface.sum()-before)/before,1e-12)

    def test_sublimation_conserves_water_and_cools(self):
        m=self.model();m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p)*.3;m.anvil[9]=.0002
        before=self.water(m);vapour=float(np.sum(m.q*m.mass));temperature=m.temp[9].copy()
        surface=m.trailing_microphysics(90)
        self.assertGreater(float(np.sum(m.q*m.mass)),vapour)
        self.assertTrue(np.all(m.temp[9]<temperature))
        self.assertLess(abs(self.water(m)+surface.sum()-before)/before,1e-12)

    def test_rearward_transport_survives_parent_updraft_decay(self):
        m=self.model();m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p)*.99
        m.cloud[9]=m.plume_cloud[9]=.0012;m.activity.fill(.9)
        m.trailing_microphysics(90);u,v=m.winds();before=m.anvil_winds(u,v)
        self.assertGreater(float(np.max(np.hypot(before[0]-u,before[1]-v))),1)
        m.activity.fill(0);m.organization.fill(0);m.mu['cape'].fill(0)
        after=m.anvil_winds(u,v)
        for actual,expected in zip(after,before):np.testing.assert_array_equal(actual,expected)

    def test_no_ice_has_no_diagnosed_outflow(self):
        m=self.model();u,v=m.winds();au,av=m.anvil_winds(u,v)
        np.testing.assert_array_equal(au,u);np.testing.assert_array_equal(av,v)

    def test_consistent_carrier_flux_matches_original_water_scheme(self):
        rng=np.random.default_rng(810);water=rng.random((3,17,25))
        u=np.full_like(water,7.);v=np.full_like(water,-3.)
        op=Advection(u,v,1000)
        moments=np.stack([water*.8,water*(-.6),water*(-12)])
        actual,carried=op.carry(water,moments,30)
        np.testing.assert_array_equal(actual,op(water,30,boundary=0,conservative=True))
        for index,value in enumerate([.8,-.6,-12]):np.testing.assert_allclose(carried[index],actual*value,atol=2e-15)

    def test_vacuum_edge_does_not_generate_unbounded_source_velocity(self):
        rng=np.random.default_rng(812);water=np.zeros((2,19,31));water[:,5:15,8:20]=rng.random((2,10,12))*.003
        colour=rng.uniform(-14,24,water.shape);moments=np.stack([water*.8,water*.6,water*colour])
        op=Advection(np.full_like(water,7.),np.full_like(water,-3.),1000)
        for _ in range(100):water,moments=op.carry(water,moments,30)
        active=water>1e-30;speed=moments[2][active]/water[active]
        self.assertGreaterEqual(float(speed.min()),-14-1e-10);self.assertLessEqual(float(speed.max()),24+1e-10)
        self.assertTrue(np.isfinite(moments).all());self.assertGreaterEqual(float(water.min()),0)

    def test_melt_is_tagged_as_rain_not_new_water(self):
        m=self.model();m.temp[6]=280;m.q[:]=saturation_ice(m.temp,m.p)*.99;m.anvil[6]=.0003
        before=self.water(m);surface=m.trailing_microphysics(90)
        self.assertGreater(float(m.stratiform_rain.max()),0)
        np.testing.assert_array_equal(m.stratiform_rain,m.rain)
        self.assertLess(abs(self.water(m)+surface.sum()-before)/before,1e-12)

    def test_evaporation_retains_stratiform_rain_subset(self):
        m=self.model();m.rain[:]=.0003;m.plume_rain[:]=.0001;m.stratiform_rain[:]=.00015
        before=self.water(m);m.evaporate_rain(90)
        np.testing.assert_allclose(m.stratiform_rain,.75*(m.rain-m.plume_rain),atol=1e-15)
        self.assertLess(abs(self.water(m)-before)/before,1e-12)

    def test_vapour_and_condensate_share_one_donor_budget(self):
        m=self.model();m.donors.fill(m.lon.size//2)
        cloud=np.full_like(m.cloud[1:],.2);vapour=cloud*.5
        before=float(np.sum(m.q*m.mass));a,b=m.debit_plumes(cloud,90,vapor_gain=vapour)
        np.testing.assert_allclose(a*.5,b)
        self.assertGreater(float(b.sum()),0)
        self.assertLess(abs(before-float(np.sum(m.q*m.mass))-float(a.sum()+b.sum())),1e-9)
        self.assertGreaterEqual(float(m.q.min()),0)

    def test_ice_moments_and_rain_tag_remain_finite_in_full_steps(self):
        m=self.model()
        for _ in range(80):m.step()
        for key in ['anvil','anvil_nx','anvil_ny','anvil_motion','stratiform_rain','last_stratiform_rate']:
            self.assertTrue(np.isfinite(getattr(m,key)).all(),key)
        self.assertLess(float(np.max(m.stratiform_rain+m.plume_rain-m.rain)),1e-8)
        self.assertLess(abs(m.audit_state()['water_relative_residual']),1e-6)


if __name__=='__main__':unittest.main()
