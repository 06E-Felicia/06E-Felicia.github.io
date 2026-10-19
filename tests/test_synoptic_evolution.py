"""External-front and evolving-wind tests, no full Astra integration."""
import unittest
import numpy as np
from simulation.core import Model, Z
from simulation.terrain import grid
from simulation.synoptic import SynopticDriver


class SynopticEvolutionTests(unittest.TestCase):
    def model(self,seed=20260421):
        c={'seed':seed,'bounds':[106,20,117,26.7],'grid_km':28}
        lon,lat=grid(c['bounds'],28)
        terrain=900*np.exp(-((lat-25.1)/.25)**2)
        return Model(c,terrain,grid_limit=28)

    def test_reservoir_starts_outside_and_both_provinces_cross_south_boundary(self):
        for seed in [20260421,20260422,20260423]:
            m=self.model(seed);s=m.synoptic
            self.assertTrue(np.all(s.front_lat>m.cfg['bounds'][3]))
            self.assertLess(float(m.air.max()),.15)
            start=s.front_lat.copy();slow=s.speed(0).copy()
            # Local terrain may delay a segment; require eventual passage,
            # not a straightened front meeting an exact 72-hour deadline.
            for n in range(96*12):
                previous=s.front_lat.copy();s.advance(300,n*300)
                self.assertTrue(np.all(s.front_lat<previous),'the external pressure front must continue southward')
            self.assertTrue(np.all(s.front_lat<m.cfg['bounds'][1]))
            self.assertGreater(float(np.min(s.speed(96*3600))),float(np.max(slow))*2)

    def test_local_upcoming_ridge_retards_its_segment_not_the_entire_front(self):
        c={'seed':20260421,'grid_km':12,'bounds':[108,23,115,26.7],'jet':1.,'cold_reservoir':1.}
        lon,lat=grid(c['bounds'],12)
        h=1200*np.exp(-((lat-25.25)/.2)**2-((lon-111.5)/.5)**2)
        s=SynopticDriver(c,lon,lat,h);s.front_lat.fill(25.55);s.crest.fill(25.15)
        velocity=s.speed(0);ridge=abs(lon[0]-111.5)<.25;gap=lon[0]>114
        self.assertLess(float(velocity[ridge].mean()),float(velocity[gap].mean())*.85)

    def test_resolved_inflow_bends_front_and_northerlies_do_not_invert_resistance(self):
        m=self.model();s=m.synoptic;s.front_lat.fill(25.8)
        zero=np.zeros(m.shape);flow=np.where(m.lon<111,1.,9.)
        for n in range(72):s.advance(300,n*300,zero,flow)
        residual=s.front_lat-np.polyval(np.polyfit(m.lon[0],s.front_lat,1),m.lon[0])
        self.assertGreater(float(np.ptp(residual)),.05)
        north=self.model().synoptic;south=self.model().synoptic
        for driver,v in [(north,-25),(south,25)]:
            driver.advance(60,0,zero,np.full(m.shape,v))
            self.assertTrue(np.isfinite(driver.front_lat).all())
        self.assertLess(float(north.front_lat.mean()),float(south.front_lat.mean()))

    def test_lee_speed_depends_on_crest_crossing_not_only_time(self):
        s=self.model().synoptic;s.front_lat[:]=s.crest+.5;before=s.speed(20000)
        s.front_lat[:]=s.crest-.8;after=s.speed(20000)
        self.assertTrue(np.all(after>before*2))

    def test_lowland_route_is_not_held_by_an_unpassed_distant_crest(self):
        c={'seed':20261017,'grid_km':12,'bounds':[108,23,115,26.7],'jet':1.,'cold_reservoir':1.}
        lon,lat=grid(c['bounds'],12)
        ridge=950*np.exp(-((lat-25.1)/.3)**2)
        h=np.where(lon<111,40,ridge)
        s=SynopticDriver(c,lon,lat,h);s.front_lat.fill(25.65);s.crest.fill(25.15)
        speed=s.speed(0);west=lon[0]<110;east=lon[0]>113
        self.assertGreater(float(speed[west].mean()),1.5*float(speed[east].mean()))
        # Swap the terrain, not the province names: the unobstructed eastern
        # corridor must then lead. No hard-coded Guangxi multiplier exists.
        swapped=SynopticDriver(c,lon,lat,np.where(lon>111,40,ridge))
        swapped.front_lat.fill(25.65);swapped.crest.fill(25.15)
        speed=swapped.speed(0)
        self.assertGreater(float(speed[east].mean()),1.5*float(speed[west].mean()))

    def test_day_two_warm_sector_is_not_swept_away_by_early_front(self):
        for seed in [20260421,20260422,20260423,20260425,20261017]:
            s=self.model(seed).synoptic
            for n in range(24*12):s.advance(300,n*300)
            self.assertGreater(float(s.front_lat.min()),25.5)
            self.assertTrue(np.all(s.speed(0)>0))

    def test_extra_upstream_travel_delays_front_without_holding_it_stationary(self):
        for seed in [20260421,20260423,20261017]:
            m=self.model(seed);s=m.synoptic
            original=m.cfg['bounds'][3]+.4+.10*np.sin((m.lon[0]-110)/1.7+s.phase)
            offset=1.45*np.sqrt(m.cfg['cold_reservoir'])*s.regional_pattern()*12*3600/111195
            np.testing.assert_allclose(s.front_lat-original,offset,rtol=1e-12)
            self.assertEqual(s.COASTAL_DELAY_SECONDS,12*3600)
            earlier=self.model(seed).synoptic;earlier.front_lat=original.copy()
            arrivals={}
            for n in range(84*12):
                for name,driver in [('original',earlier),('delayed',s)]:
                    previous=driver.front_lat.copy();driver.advance(300,n*300)
                    self.assertTrue(np.all(driver.front_lat<previous))
                    if name not in arrivals and np.interp(114,m.lon[0],driver.front_lat)<=22.54:
                        arrivals[name]=(n+1)/12
            self.assertEqual(set(arrivals),{'original','delayed'})
            self.assertGreater(arrivals['delayed']-arrivals['original'],9)
            self.assertLess(arrivals['delayed']-arrivals['original'],16)
            # Changing the cold-reservoir starting position must not shift
            # the Bay trough, random streams or the warm-sector day clock.
            self.assertEqual(s.bay_lon,earlier.bay_lon)
            self.assertEqual(s.genesis_start,earlier.genesis_start)
            np.testing.assert_array_equal(s.ascent(0,111),earlier.ascent(0,111))

    def test_500hpa_steering_is_on_the_southwesterly_downstream_side(self):
        for seed in [20260421,20260423,20260425,20261017,20261018]:
            m=self.model(seed)
            for hour in [0,6,12,24,36,48,72]:
                m.time=hour*3600;f=m.fields(include_mixed=False)
                # Meteorological FROM bearing, not arrow travel direction.
                bearing=(np.degrees(np.arctan2(-f['u500'],-f['v500']))+360)%360
                self.assertGreaterEqual(float(bearing.min()),225)
                self.assertLessEqual(float(bearing.max()),270)

    def test_deepening_warm_pool_does_not_reverse_normal_background_shear_south(self):
        for seed in [20260421,20261017,20261018]:
            m=self.model(seed);warm=(m.lat>21)&(m.lat<23.7)&(m.air<.1)
            for hour in [0,6,12]:
                m.time=hour*3600;u,v=m.winds()
                for depth in [1200,1600]:
                    du,dv=m.environmental_shear(u,v,np.full(m.shape,depth))
                    self.assertGreater(float(np.median(du[warm])),0)
                    self.assertGreater(float(np.median(dv[warm])),0)

    def test_middle_turn_does_not_rewrite_low_level_jet_or_upper_jet_speed(self):
        m=self.model();s=m.synoptic;z=Z[:,None,None]
        u,v,ju,jv=s.free_winds(z,6*3600,111,np.zeros(m.shape))
        # This regression bounds the profile, not the final storm position.
        bearing=np.degrees(np.arctan2(v,u))
        self.assertGreater(float(np.median(bearing[8:10])),12)
        self.assertLess(float(np.median(bearing[8:10])),30)
        self.assertGreater(float(np.median(bearing[7])),20)
        self.assertLess(float(np.max(bearing[0])),15)
        self.assertLess(float(np.max(bearing[-1])),15)
        self.assertGreater(float(np.mean(np.hypot(u[11],v[11]))),30)
        self.assertGreater(float(np.mean(jv[3:5])),1)

    def test_upper_cloud_northward_flow_is_reduced_without_losing_low_level_shear(self):
        m=self.model();s=m.synoptic;z=Z[:,None,None]
        for hour in [0,6,12,24,48]:
            # Compare the exact same speeds/waves/LLJ, only the former
            # uniform middle turn versus the new vertically veering turn.
            u,v,ju,jv=s.free_winds(z,hour*3600,111,np.zeros(m.shape))
            current=s.middle_flow_turn(z)
            previous=.44*np.clip((z-1200)/1300,0,1)*np.clip((10000-z)/3000,0,1)
            change=previous-current
            old_u=u*np.cos(change)-v*np.sin(change)
            old_v=u*np.sin(change)+v*np.cos(change)
            np.testing.assert_allclose(np.hypot(u,v),np.hypot(old_u,old_v),rtol=1e-12)
            np.testing.assert_allclose(u[:8],old_u[:8],rtol=1e-12)
            np.testing.assert_allclose(v[:8],old_v[:8],rtol=1e-12)
            self.assertGreater(float(np.mean(v[9])),0)
            self.assertLess(float(np.mean(v[9])),float(np.mean(old_v[9]))*.7)
            self.assertTrue(np.all(u[9]>0))

    def test_front_does_not_cancel_inflow_far_ahead_of_its_position(self):
        m=self.model();s=m.synoptic;s.front_lat.fill(25.6)
        _,v=s.surface_target(np.zeros(m.shape),0)
        ahead=(m.lat<24.5)&(m.lat>24.2)
        self.assertTrue(ahead.any())
        self.assertGreater(float(v[ahead].min()),.9*5*m.cfg['jet'])

    def test_pressure_front_does_not_reset_internal_cold_air(self):
        m=self.model();initial=m.air.copy();m.synoptic.advance(36*3600,0)
        np.testing.assert_array_equal(m.air,initial)
        self.assertGreater(float(m.synoptic.external_air().max()),.9)

    def test_925_500_300_winds_change_in_both_components(self):
        m=self.model();initial=m.fields(include_mixed=False)
        m.time=12*3600;m.trough_lon+=4
        later=m.fields(include_mixed=False)
        for level in [925,500,300]:
            for component in ['u','v']:
                self.assertGreater(float(np.nanmax(np.abs(later[f'{component}{level}']-initial[f'{component}{level}']))),.25)
        self.assertGreater(float(np.mean(np.hypot(later['u300'],later['v300']))),30)

    def test_bay_trough_keeps_south_china_downstream_without_a_local_shortwave(self):
        m=self.model()
        x,y,packet,strength=m.synoptic.wave(m.time,m.trough_lon)
        a=m.synoptic.ascent(m.time,m.trough_lon)
        self.assertTrue(np.all(x>0));self.assertTrue(np.all(a>0));self.assertLess(float(a.max()),.04)
        self.assertTrue(87<=m.synoptic.bay_lon<=91);self.assertTrue(16<=m.synoptic.bay_lat<=19)
        # Moving a stale local-shortwave coordinate has no regional effect.
        np.testing.assert_array_equal(a,m.synoptic.ascent(m.time,118))
        for hour in [0,6,12,24,48,72]:
            u,v,_,_=m.synoptic.free_winds(Z[:,None,None],hour*3600,111,np.zeros(m.shape))
            for k in [9,11]:
                self.assertTrue(np.all(u[k]>0));self.assertTrue(np.all(v[k]>0))

    def test_turbulent_gust_varies_with_roughness_and_stability(self):
        m=self.model();m.u.fill(10);m.v.fill(0);m.downburst_energy.fill(0)
        ordinary=m.surface_gust().copy();m.temp[0]-=8;stable=m.surface_gust()
        self.assertTrue(np.all(stable<ordinary))
        self.assertTrue(np.all(stable>10));self.assertTrue(np.all(ordinary<14))

    def test_equal_seed_reproduces_pressure_trajectory(self):
        a=self.model(19).synoptic;b=self.model(19).synoptic;c=self.model(20).synoptic
        for n in range(36*12):
            for s in [a,b,c]:s.advance(300,n*300)
        np.testing.assert_array_equal(a.front_lat,b.front_lat)
        self.assertGreater(float(np.max(abs(a.front_lat-c.front_lat))),.05)

    def test_advancing_front_allows_deep_instability_instead_of_a_convection_ban(self):
        m=self.model();m.air[:]=1/(1+np.exp(-(m.lat-23)*111195/18000))
        m.synoptic.front_lat.fill(23);m.syn_u,m.syn_v=m.synoptic.surface_target(m.air,36*3600)
        m.u=m.syn_u.copy();m.v=m.syn_v.copy()
        convergence=-(np.gradient(m.syn_u,m.dx,axis=-1)+np.gradient(m.syn_v,m.dx,axis=-2))
        m.frontal_lifting(convergence,convergence,0,0);m.diagnostics()
        near=(m.air>.2)&(m.air<.8)
        self.assertGreater(float(m.front_advance[near].mean()),.9)
        self.assertGreater(float(m.deep_support[near].min()),.3)
        self.assertGreater(float(m.available_cape(m.mu['cape'])[near].max()),150)
        self.assertGreater(float(m.background_w[near].max()),.01)


if __name__=='__main__':unittest.main()
