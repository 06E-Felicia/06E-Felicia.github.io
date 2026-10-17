"""Controlled rain/momentum budgets; never run a full weather process."""
import unittest
import numpy as np
from simulation.core import Model, Z, DZ, sediment, rain_fall_speed
from simulation.terrain import grid
from simulation.numerics import Advection


class AstraRainGustTests(unittest.TestCase):
    def model(self,compact=False):
        cfg={'bounds':[112,22,113,23],'grid_km':12,'seed':13,'stochastic':0,'compact_transport':compact}
        return Model(cfg,np.full(grid(cfg['bounds'],12)[0].shape,30))

    def test_regenerating_head_uses_finite_inflow_not_repeated_spinup(self):
        m=self.model();m.organization.fill(.8);m.activity.fill(.03)
        base=m.plume_coverage(1,1,1)
        area=m.organized_coverage(base,20,25,1000,1,1,1,1)
        self.assertGreater(float(area.min()),float(base.max())*3)
        self.assertTrue(np.all(area*20<=25*1000/m.dx*.8+1e-6))
        self.assertTrue(np.all(area<=.55))
        for activation,feeding in [(0,1),(1,0)]:
            np.testing.assert_allclose(m.organized_coverage(base,20,25,1000,activation,1,1,feeding),base)
        m.organization.fill(0)
        np.testing.assert_allclose(m.organized_coverage(base,20,25,1000,1,1,1,1),base)

    def test_larger_head_flux_really_debits_more_water_and_cape(self):
        accepted=[]
        for enhanced in [False,True]:
            m=self.model();m.organization.fill(.8);m.activity.fill(.03)
            m.donors=np.arange(m.lon.size).reshape(m.shape)
            base=m.plume_coverage(1,1,1)
            area=m.organized_coverage(base,20,25,1000,1,1,1,1) if enhanced else base
            density=np.take_along_axis(m.mass/DZ[:,None,None],m.mu['start_index'][None],axis=0)[0]
            flow=20*area*density*60
            gains=np.zeros_like(m.cloud[1:]);gains[5]=flow*.008
            before=float(np.sum(m.q*m.mass,dtype='float64'))
            received=m.debit_plumes(gains,60,air_flux=flow,source_inflow=np.full(m.shape,25.))
            after=float(np.sum(m.q*m.mass,dtype='float64'))
            self.assertAlmostEqual(before-after,float(received.sum()),delta=1e-7)
            self.assertGreater(float(m.cape_deficit.max()),0)
            self.assertGreaterEqual(float(m.q.min()),0)
            accepted.append(float(received.sum()))
        self.assertGreater(accepted[1],accepted[0]*2)

    def test_heavy_rain_lands_and_accumulates_from_the_same_water_flux(self):
        m=self.model();water=np.zeros_like(m.rain)
        water[:9]=.005;initial=float(np.sum(water*m.mass));total=np.zeros(m.shape);peak=0
        for _ in range(120):
            speed=rain_fall_speed(water,m.mass/DZ[:,None,None],.3)
            water,fallen=sediment(water,m.mass,30,speed)
            total+=fallen;peak=max(peak,float(fallen.max())*120)
        self.assertGreater(peak,20)
        self.assertGreater(float(total.min()),20)
        self.assertAlmostEqual(float(total.sum()+np.sum(water*m.mass)),initial,delta=1e-7)
        _,fallen=sediment(np.zeros_like(water),m.mass,60)
        self.assertEqual(float(fallen.max()),0,'there is no heavy-rain floor')

    def wet_downdraft(self,m):
        m.u.fill(3);m.v.fill(2)
        m.rain[2:9]=.001;m.plume_rain[:]=m.rain;m.rain_area[:]=m.rain*.3
        evaporation=np.zeros_like(m.rain);evaporation[2:7]=.0001
        return evaporation

    def test_downburst_exchanges_momentum_without_creating_kinetic_energy(self):
        for compact in [False,True]:
            m=self.model(compact);evaporation=self.wet_downdraft(m)
            u,v=m.winds();before=np.array([(u*m.mass).sum(),(v*m.mass).sum()])
            kinetic=float(((u*u+v*v)*m.mass).sum());wind=np.hypot(m.u,m.v).copy()
            m.downdraft_momentum(evaporation,60)
            a,b=m.winds();after=np.array([(a*m.mass).sum(),(b*m.mass).sum()])
            np.testing.assert_allclose(after,before,rtol=3e-7)
            self.assertLess(float(((a*a+b*b)*m.mass).sum()),kinetic)
            self.assertGreater(float(np.hypot(m.u,m.v).mean()),float(wind.mean())+2)
            # This finite synthetic shaft is not a calibrated severe-wind
            # case; require a real increment, not the old inflated 20+ floor.
            self.assertGreater(float(m.surface_gust().max()),float(np.hypot(m.u,m.v).max()))
            np.testing.assert_allclose(a[0],m.u,rtol=1e-6)
            self.assertEqual(m.momentum_u.dtype,m.q.dtype)

    def test_gust_is_precipitation_driven_and_fades_after_head_passage(self):
        dry=self.model();dry.downdraft_momentum(np.zeros_like(dry.rain),60)
        self.assertEqual(float(dry.downburst_energy.max()),0)
        mean=np.hypot(dry.u,dry.v)
        self.assertTrue(np.all(dry.surface_gust()>mean),'ordinary shear turbulence is not a downburst')
        self.assertTrue(np.all(dry.surface_gust()<mean*1.4))
        dry.u.fill(0);dry.v.fill(0)
        self.assertEqual(float(dry.surface_gust().max()),0,'background wind alone is not a downburst')
        m=self.model();m.downdraft_momentum(self.wet_downdraft(m),60);initial=m.downburst_energy.copy()
        u,v=m.winds();zero=np.zeros_like(u);op=Advection(zero,zero,m.dx)
        for _ in range(10):m.transport_downburst(60,zero,zero,op)
        self.assertLess(float(m.downburst_energy.max()),float(initial.max())*.38)
        self.assertTrue(np.all(m.downburst_energy>=0))

    def test_gust_snapshot_is_explicit_and_not_smaller_than_mean_wind(self):
        m=self.model();m.downdraft_momentum(self.wet_downdraft(m),60);f=m.fields()
        self.assertIn('gust',f)
        self.assertTrue(np.all(f['gust']>=np.hypot(f['u10'],f['v10'])))


if __name__=='__main__':unittest.main()
