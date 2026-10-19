"""Causal stress/momentum/neutral-wake regressions; no full Astra process."""
import unittest
import numpy as np
from simulation.core import Model, Z
from simulation.terrain import grid


class WindWakeTests(unittest.TestCase):
    def model(self,sea=False):
        cfg={'bounds':[112,22,113,23],'grid_km':12,'seed':13,'stochastic':0}
        return Model(cfg,np.full(grid(cfg['bounds'],12)[0].shape,0 if sea else 30))

    def test_stress_dissipates_ke_and_is_counted_once_over_shallow_mass(self):
        m=self.model();m.u.fill(25);m.v.fill(-10);u,v=m.winds();momentum=np.array([np.sum(u*m.mass,dtype='float64'),np.sum(v*m.mass,dtype='float64')])
        old_u=m.u.copy();old_v=m.v.copy();energy=((u*u+v*v)*m.mass).sum()
        m.surface_friction(90);a,b=m.winds();np.testing.assert_allclose(a[10:],u[10:],atol=2e-5);np.testing.assert_allclose(b[10:],v[10:],atol=2e-5)
        expected=np.array([np.sum((m.u-old_u)*m.surface_mixed_mass),np.sum((m.v-old_v)*m.surface_mixed_mass)])
        np.testing.assert_allclose(np.array([np.sum(a*m.mass,dtype='float64'),np.sum(b*m.mass,dtype='float64')])-momentum,expected,rtol=2e-5)
        self.assertLess(float(((a*a+b*b)*m.mass).sum()),float(energy))
        self.assertTrue(np.all(m.u>0));self.assertTrue(np.all(m.v<0))
        for _ in range(100):m.surface_friction(90)
        np.testing.assert_array_equal(m.momentum_u,0,'ground drag must not accumulate an anti-drag jet aloft')

    def test_land_drag_is_stronger_and_increases_with_wind_speed(self):
        ratios=[]
        for sea,speed in [(True,25),(False,25),(False,8)]:
            m=self.model(sea);m.u.fill(speed);m.v.fill(0);m.surface_friction(90);ratios.append(float(m.u.mean())/speed)
        self.assertLess(ratios[1],ratios[0]);self.assertLess(ratios[1],ratios[2])
        sea=self.model(True);self.assertGreater(float(sea.drag_coefficient(np.full(sea.shape,40)).mean()),float(sea.drag_coefficient(np.full(sea.shape,8)).mean()))

    def test_stable_surface_inhibits_downward_momentum_transfer(self):
        responses=[]
        for stable in (False,True):
            m=self.model();m.u.fill(3);m.v.fill(2);m.rain[2:9]=.001;m.plume_rain[:]=m.rain;m.rain_area[:]=m.rain*.3
            # Isolate stability against the SAME aligned source momentum.
            # With varying layer directions, changing which layers reach
            # the ground need not monotonically change the final wind norm.
            u,v=m.winds();m.momentum_u[2:9]+=20-u[2:9];m.momentum_v[2:9]-=v[2:9]
            if stable:
                from simulation.thermo import saturation
                m.temp[:2]-=8;m.q[:2]=np.minimum(m.q[:2],saturation(m.temp[:2],m.p[:2])*.9)
            evaporation=np.zeros_like(m.rain);evaporation[2:7]=.0001;m.downdraft_momentum(evaporation,60)
            responses.append((float(m.downburst_energy.max()),float(np.hypot(m.u,m.v).mean())))
        self.assertLess(responses[1][0],responses[0][0]);self.assertLess(responses[1][1],responses[0][1])

    def test_gust_does_not_linearly_stack_ideal_speed_on_background(self):
        m=self.model();m.u.fill(12.7);m.v.fill(0);m.syn_u.fill(8);m.syn_v.fill(0)
        old_energy=.5*(49.3-8)**2;m.downburst_energy.fill(.25*old_energy)
        gust=m.surface_gust();self.assertTrue(np.all(gust>12.7));self.assertLess(float(gust.max()),25)
        # The explicitly bounded educational scenario now allows up to 32;
        # supplied work must still be sufficient (never a gust floor).
        m.downburst_energy.fill(1500);self.assertEqual(float(m.surface_gust().max()),32)
        m.downburst_energy.fill(0)
        self.assertTrue(np.all(m.surface_gust()>12.7));self.assertTrue(np.all(m.surface_gust()<17))

    def test_neutral_layer_retires_mass_momentum_but_keeps_cape_memory(self):
        m=self.model();m.cold_depth.fill(600);m.cold_content.fill(48);m.cold_mx.fill(4800);m.cold_my.fill(0);m.cape_deficit.fill(900)
        initial=float(m.cold_content.sum());m.cold_diagnostics();self.assertLess(float(m.cold_surface_coupling(90).max()),.04)
        for _ in range(160):m.recover_cold_pool(90,np.zeros(m.shape),0)
        self.assertLess(float(m.cold_depth.max()),1);self.assertLess(float(np.abs(m.cold_mx).max()),8)
        self.assertAlmostEqual(float(m.cold_content.sum())+m.cold_recovery,initial,places=6)
        np.testing.assert_array_equal(m.cape_deficit,900,'retiring a layer cannot reset consumed CAPE')

    def test_strong_cold_head_survives_and_keeps_density_circulation(self):
        m=self.model();m.cold_depth.fill(600);m.cold_content.fill(2400);m.cold_diagnostics()
        self.assertGreater(float(m.cold_surface_coupling(90).min()),.55)
        m.recover_cold_pool(600,np.zeros(m.shape),0)
        self.assertGreater(float(m.cold_depth.min()),550);self.assertGreater(float(m.cold.min()),2.5)

    def test_impulse_transfer_is_area_limited_and_upper_troposphere_excluded(self):
        m=self.model();m.u.fill(0);m.v.fill(0);m.rain[2:9]=.001;m.plume_rain[:]=m.rain;m.rain_area[:]=m.rain*.03
        evaporation=np.zeros_like(m.rain);evaporation[2:7]=.0001
        # Entire upper-jet momentum must not be imported by a 3% shaft.
        m.momentum_u[10:]=100;u,v=m.winds()
        m.downdraft_momentum(evaporation,60)
        self.assertLess(float(np.hypot(m.u,m.v).max()),3)
        a,b=m.winds();np.testing.assert_allclose(a[10:],u[10:],atol=2e-5);np.testing.assert_allclose(b[10:],v[10:],atol=2e-5)


if __name__=='__main__':unittest.main()
