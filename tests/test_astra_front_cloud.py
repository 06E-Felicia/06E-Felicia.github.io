"""Small controlled mechanisms, not a new full-domain weather simulation."""
import unittest
import numpy as np
from simulation.core import Model, Z, DZ, advect, sediment
from simulation.terrain import grid
from simulation.thermo import saturation_ice


class AstraFrontCloudTests(unittest.TestCase):
    def model(self,seed=1,legacy=False,bounds=None,km=10):
        cfg={'bounds':bounds or [111,22,113,26],'grid_km':km,'seed':seed,'trough':0,'stochastic':0}
        return Model(cfg,np.full(grid(cfg['bounds'],km)[0].shape,30),astra_updates=not legacy)

    def water(self,m):
        return float(np.sum((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass,dtype='float64'))

    def test_tilted_front_and_broad_weak_overrunning(self):
        m=self.model(bounds=[111,23.5,115,26.5],km=6)
        m.air[:]=1/(1+np.exp(-(m.lat-24.5)*111195/18000))
        layers=m.frontal_layers();lat=m.lat[:,0]
        positions=[np.interp(.5,layers[k,:,0],lat) for k in [0,3,4,5]]
        self.assertTrue(all(b>a for a,b in zip(positions,positions[1:])))
        self.assertGreater((positions[-1]-positions[0])*111.195,140)
        m.syn_u.fill(4);m.syn_v[:]=5*(1-2*m.air);m.u=m.syn_u.copy();m.v=m.syn_v.copy()
        conv=-np.gradient(m.syn_v,m.dx,axis=0);m.frontal_lifting(conv,conv,0,0)
        u,v=m.winds();w=m.resolved_ascent(u,v)
        band=np.maximum(w[4].mean(axis=1),0)
        self.assertGreater(int((band>.005).sum())*6,40,'overrunning must not be one or two grid rows')
        self.assertLess(float(w[4].max()),.2,'this is weak sloping ascent, not a forced deep updraft')
        self.assertGreater(float((lat*band).sum()/band.sum()),24.8)
        self.assertGreater(float(u[4].mean()),5,'condensate uses eastward layered winds')

    def test_environmental_frontal_ice_is_not_given_convective_rear_flow(self):
        m=self.model();m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p)*.99
        m.cloud[9]=.0012;before=self.water(m)
        surface=m.trailing_microphysics(90)
        self.assertGreater(float(m.anvil.max()),0)
        for name in ['anvil_nx','anvil_ny','anvil_motion']:self.assertEqual(float(np.max(abs(getattr(m,name)))),0)
        u,v=m.winds();au,av=m.anvil_winds(u,v)
        np.testing.assert_array_equal(au,u);np.testing.assert_array_equal(av,v)
        self.assertLess(abs(self.water(m)+surface.sum()-before)/before,1e-12)

    def test_boundary_thermodynamics_follow_the_same_sloping_front(self):
        m=self.model();t,_=m.upstream_environment()
        np.testing.assert_allclose(t,m.radiative_reference)
        initial=m.frontal_layers().copy();m.air=np.clip(m.air+.2,0,1)
        t,_=m.upstream_environment()
        expected=-7*(m.frontal_layers()-initial)*np.exp(-Z[:,None,None]/5000)
        np.testing.assert_allclose(t-m.radiative_reference,expected,atol=1e-12)

    def test_frontal_cloud_pulse_advects_east_without_moving_surface_front(self):
        m=self.model(bounds=[110,23,116,26],km=10)
        m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p)*.99
        m.cloud[9]=.001*np.exp(-((m.lon-112)/.3)**2-((m.lat-25.2)/.4)**2)
        m.trailing_microphysics(90);front=m.air.copy();u,v=m.winds();au,av=m.anvil_winds(u,v)
        initial=m.anvil[9].copy();x=m.lon*111195*np.cos(np.radians(24.5))
        start=float((initial*x).sum()/initial.sum())
        # Isolate the actual same transport operator, no rain position mask.
        op=__import__('simulation.numerics',fromlist=['Advection']).Advection(au[9],np.zeros_like(av[9]),m.dx)
        carried=initial.copy()
        for _ in range(40):carried=op(carried,90,boundary=0,conservative=True)
        end=float((carried*x).sum()/carried.sum())
        self.assertGreater(end-start,40000)
        np.testing.assert_array_equal(m.air,front)

    def test_detached_ice_falls_out_faster_without_water_or_echo_deletion(self):
        fractions=[]
        for legacy in [True,False]:
            m=self.model(legacy=legacy);m.q[:]=saturation_ice(m.temp,m.p);m.anvil[9]=.0005
            initial_ice=float((m.anvil*m.mass).sum());before=self.water(m);surface=0
            for _ in range(120):
                surface+=float(m.trailing_microphysics(60).sum())
                m.rain,fallen=sediment(m.rain,m.mass,60);surface+=float(fallen.sum())
                # The tag is a subset of that same rain, not extra water.
                m.stratiform_rain,_=sediment(m.stratiform_rain,m.mass,60)
            fractions.append(float((m.anvil*m.mass).sum())/initial_ice)
            self.assertLess(abs(self.water(m)+surface-before)/before,1e-10)
            self.assertGreater(surface,0)
        self.assertLess(fractions[1],.03)
        self.assertLess(fractions[1],fractions[0]*.6)

    def test_cloud_edge_mixing_is_closed_and_ventilates_humidity(self):
        m=self.model();m.anvil[9,:,5:10]=.0003
        m.q[9,:,5:10]*=2;before=self.water(m);wet=float(m.q[9,:,5].mean());dry=float(m.q[9,:,4].mean())
        m.mix_stratiform_air(90)
        self.assertLess(float(m.q[9,:,5].mean()),wet);self.assertGreater(float(m.q[9,:,4].mean()),dry)
        self.assertLess(abs(self.water(m)-before)/before,1e-12)

    def test_seeded_surge_geometry_supports_both_provinces(self):
        regimes=set()
        for seed in range(1,18):
            m=self.model(seed,bounds=[106,24,117,26],km=12)
            m.north_trough_lon=111.2+m.front_phase;s=m.synoptic_surge();regimes.add(m.front_regime)
            west=float(s[(m.lon>107)&(m.lon<110)].mean());east=float(s[(m.lon>113)&(m.lon<116)].mean())
            self.assertGreater(min(west,east),.5*m.cfg['cold_reservoir'])
            if m.front_regime=='west':self.assertGreater(west,east*1.1)
            if m.front_regime=='east':self.assertGreater(east,west*1.1)
            if m.front_regime=='coupled':self.assertLess(abs(east-west),.2*m.cfg['cold_reservoir'])
        self.assertEqual(regimes,{'coupled','west','east','mixed'})

    def test_pre_surge_front_drifts_and_undulates_over_48h_passive_transport(self):
        m=self.model(bounds=[107,23,116,27],km=12)
        m.air=1/(1+np.exp(-(m.lat-25.1)*111195/18000));zero=np.zeros(m.shape)
        def positions():return np.array([np.interp(.5,m.air[:,x],m.lat[:,x]) for x in range(m.shape[1])])
        initial=positions()
        # Only surface-tracer advection under the background confluence; no
        # microphysics, storms or whole 48-hour weather process is computed.
        for _ in range(960):
            velocity=5*(1-2*m.air)-.5*m.air-m.frontal_drift()
            m.air=np.clip(advect(m.air,zero,velocity,180,m.dx),0,1)
        shift=(initial-positions())*111.195
        self.assertGreater(float(np.mean(shift)),10)
        self.assertLess(float(np.mean(shift)),140)
        self.assertGreater(float(np.std(shift)),1,'regional frontal undulation must not be a rigid line')

    def test_legacy_physics_branch_remains_reproducible_with_corrected_boundaries(self):
        cfg={'bounds':[112,22,114,25],'grid_km':24,'seed':173}
        m=Model(cfg,np.full(grid(cfg['bounds'],24)[0].shape,30),grid_limit=24,astra_updates=False)
        other=Model(cfg,np.full(grid(cfg['bounds'],24)[0].shape,30),grid_limit=24,astra_updates=False)
        for _ in range(3):m.step();other.step()
        for key in ['temp','q','cloud','rain','anvil','air','u','v','total']:
            np.testing.assert_array_equal(getattr(m,key),getattr(other,key))


if __name__=='__main__':unittest.main()
