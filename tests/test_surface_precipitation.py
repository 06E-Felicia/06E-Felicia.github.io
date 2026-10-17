import unittest
import numpy as np
from simulation.precipitation import SurfaceRain
from simulation.coldpool import advance, velocity


class SurfacePrecipitationTests(unittest.TestCase):
    def coarse(self,a,shape):return a.reshape(shape[0],4,shape[1],4).mean(axis=(1,3),dtype='float64')

    def test_every_step_conserves_actual_fallen_water(self):
        shape=(5,7);rain=SurfaceRain(shape,13);rng=np.random.default_rng(42);coarse=np.zeros(shape)
        for step in range(40):
            convective=rng.uniform(0,.3,shape);background=rng.uniform(0,.01,shape);area=rng.uniform(.01,.8,shape)
            rain.advance((step+1)*30,30,convective,background,area);coarse+=convective+background
            np.testing.assert_allclose(self.coarse(rain.rate,shape),(convective+background)*120,rtol=2e-7)
        np.testing.assert_allclose(self.coarse(rain.total,shape),coarse,rtol=5e-7)

    def test_core_hit_has_finite_burst_and_consistent_event_total(self):
        rain=SurfaceRain((3,4),13);water=np.full((3,4),.25);zero=water*0;area=zero+.125
        # 15 mm/h cell mean over a 15-minute passage. Finite smoothed shafts
        # retain strong bursts without the old hard 8x step-function peak.
        for step in range(15):rain.advance((step+1)*60,60,water,zero,area)
        self.assertGreaterEqual(rain.max_five,7)
        self.assertLessEqual(rain.max_five,10)
        self.assertGreaterEqual(float(rain.total.max()),20)
        self.assertLessEqual(float(rain.total.max()),30)
        total=rain.total.copy()
        for step in range(15,80):rain.advance((step+1)*60,60,zero,zero,area)
        np.testing.assert_array_equal(rain.total,total)
        self.assertEqual(float(rain.accumulation(300).max()),0)
        self.assertEqual(float(rain.accumulation(3600).max()),0)

    def test_uniform_stratiform_is_not_multiplied(self):
        rain=SurfaceRain((3,4),1);zero=np.zeros((3,4));water=zero+1/30
        for step in range(60):rain.advance((step+1)*60,60,zero,water,zero)
        np.testing.assert_allclose(rain.total,2,atol=2e-6)
        np.testing.assert_allclose(rain.accumulation(300),1/6,atol=1e-6)

    def test_seeded_footprints_repeat_but_do_not_create_water(self):
        a,b,c=[SurfaceRain((3,4),seed) for seed in (13,13,14)]
        for step in range(20):
            for rain in (a,b,c):rain.advance((step+1)*60,60,np.ones((3,4)),np.zeros((3,4)),np.full((3,4),.125))
        np.testing.assert_array_equal(a.total,b.total);self.assertFalse(np.array_equal(a.total,c.total))
        np.testing.assert_allclose(self.coarse(c.total,(3,4)),20,rtol=1e-6)

    def test_advected_shafts_reduce_stationary_dry_holes_conservatively(self):
        shape=(8,8);zero=np.zeros(shape);a,b=[SurfaceRain(shape,13) for _ in range(2)]
        for step in range(40):
            for rain in (a,b):
                rain.advance((step+1)*30,30,zero+.25,zero,zero+.125,
                             velocity=(zero+15,zero+5) if rain is b else None,dx=12000)
        self.assertLess(float(np.mean(b.total<.5)),float(np.mean(a.total<.5))*.5)
        for rain in (a,b):np.testing.assert_allclose(self.coarse(rain.total,shape),10,rtol=1e-6)

    def test_output_queries_never_change_integrated_rain(self):
        shape=(3,4);zero=np.zeros(shape);a,b=[SurfaceRain(shape,29) for _ in range(2)]
        for step in range(240):
            for rain in (a,b):rain.advance((step+1)*30,30,zero+.1,zero+.01,zero+.2,velocity=(zero+12,zero+4),dx=6000)
            if step%20==0:a.fields()
            if step%120==0:b.fields()
        np.testing.assert_array_equal(a.total,b.total);np.testing.assert_array_equal(a.rate,b.rate)


class ColdPoolOpenEdgeTests(unittest.TestCase):
    def test_uniform_resting_pool_has_no_rectangle_front_or_edge_wind(self):
        h=np.full((13,17),500.);q=h*4;zero=h*0
        for order in (False,True):
            hn,qn,mx,my,external,cfl=advance(h,q,zero,zero,zero,1800,12000,higher_order=order)
            np.testing.assert_allclose(hn,h,atol=1e-10);np.testing.assert_allclose(qn,q,atol=1e-10)
            np.testing.assert_allclose(mx,zero,atol=1e-10);np.testing.assert_allclose(my,zero,atol=1e-10)
            self.assertAlmostEqual(external,0)

    def test_outgoing_pool_can_leave_and_cannot_reenter(self):
        y,x=np.indices((9,30));h=500*np.exp(-((x-24)/2)**2);q=h*4;zero=h*0
        result=advance(h,q,h*18,zero,zero,7200,4000,higher_order=True)
        self.assertLess(float(result[1].sum()),float(q.sum())*.25)
        self.assertLessEqual(result[-2],0)
        self.assertAlmostEqual(float(result[1].sum()),float(q.sum())+result[-2],delta=1e-7)


if __name__=='__main__':unittest.main()
