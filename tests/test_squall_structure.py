"""Causal budget tests, not shape masks or guaranteed seeded weather."""
import unittest
import numpy as np
from simulation.core import Model,rain_evaporation_rate
from simulation.terrain import grid
from simulation.coldpool import velocity


class StructureTests(unittest.TestCase):
    def model(self):
        cfg={'bounds':[112,22,114,24],'grid_km':12,'seed':13,'stochastic':0}
        return Model(cfg,np.full(grid(cfg['bounds'],12)[0].shape,30.))

    def test_drop_size_not_a_fixed_fractional_evaporation_timer(self):
        water=np.array([0.,1e-5,.001,.005])
        rates=rain_evaporation_rate(water,1.,290.,90000.)
        self.assertEqual(rates[0],0)
        self.assertTrue(np.all(np.diff(rates[1:])<0))
        self.assertGreater(rates[1],rates[-1]*4)
        # Identical local concentration in a quarter-sized shaft.
        np.testing.assert_allclose(rain_evaporation_rate(.001/4,1.,290.,90000.,.25),rates[2])

    def test_head_drag_preserves_cold_mass_and_only_damps_outward_relative_flow(self):
        m=self.model();y,x=np.indices(m.shape);cx,cy=np.array(m.shape[::-1])/2
        m.cold_depth=600*np.exp(-((x-cx)**2+(y-cy)**2)/20)
        m.cold_content=m.cold_depth*3;m.cold_mx=m.cold_depth*(m.syn_u+(x-cx)*2)
        m.cold_my=m.cold_depth*(m.syn_v+(y-cy)*2)
        depth=m.cold_depth.copy();content=m.cold_content.copy()
        u,v=velocity(depth,m.cold_mx,m.cold_my);before=(u-m.syn_u)**2+(v-m.syn_v)**2
        m.cold_head_friction(90);u,v=velocity(depth,m.cold_mx,m.cold_my)
        after=(u-m.syn_u)**2+(v-m.syn_v)**2
        np.testing.assert_array_equal(m.cold_depth,depth);np.testing.assert_array_equal(m.cold_content,content)
        self.assertTrue(np.all(after<=before+1e-7));self.assertGreater(m.cold_head_dissipation,0)
        m.cold_mx=depth*m.syn_u;m.cold_my=depth*m.syn_v
        mx=m.cold_mx.copy();my=m.cold_my.copy();m.cold_head_friction(90)
        np.testing.assert_allclose(m.cold_mx,mx);np.testing.assert_allclose(m.cold_my,my)

    def test_no_extra_intrinsic_speed_is_added_to_already_moving_head(self):
        m=self.model();u,v=m.winds();s=m.mu['start_index'][None]
        su=np.take_along_axis(u,s,axis=0)[0];sv=np.take_along_axis(v,s,axis=0)[0]
        m.donors=np.arange(m.lon.size).reshape(m.shape);one=np.ones(m.shape)
        a=m.head_inflow(su,sv,su+5,sv,u,v,one,one*0)
        np.testing.assert_allclose(a,5,atol=1e-6)
        m.cold_content.fill(5000)
        np.testing.assert_allclose(m.head_inflow(su,sv,su+5,sv,u,v,one,one*0),5,atol=1e-6)

    def test_finite_descending_air_dilutes_but_does_not_invent_cooling(self):
        a,b=self.model(),self.model();evap=np.zeros_like(a.rain);evap[:5]=.0001
        a.downdraft_mass_depth.fill(0);b.downdraft_mass_depth.fill(1000)
        a.supply_cold_pool(evap);b.supply_cold_pool(evap)
        np.testing.assert_allclose(a.cold_content,b.cold_content)
        self.assertTrue(np.all(b.cold_depth>=a.cold_depth))
        self.assertTrue(np.all(b.cold<=a.cold))
        before=b.cold_depth.copy();b.supply_cold_pool(evap*0)
        np.testing.assert_array_equal(b.cold_depth,before)

    def test_support_is_not_multiplied_again_in_occupied_area(self):
        m=self.model();m.activity.fill(.4);m.organization.fill(.7)
        np.testing.assert_allclose(m.plume_coverage(.2,1,.3),m.plume_coverage(1,1,1))
        self.assertTrue(np.all(m.plume_coverage(.2,1,.3)<.55))

    def test_cluster_strength_changes_real_mass_flux_without_exceeding_head_supply(self):
        m=self.model();m.cfg['stochastic']=1;m.organization.fill(.5);m.activity.fill(.3)
        y,x=np.indices(m.shape);m.cell_noise=np.where(y%6<3,1.,-1.)
        factor=m.cell_variability();base=m.plume_coverage(1,factor,1)
        area=m.organized_coverage(base,20,30,1200,1,1,1,1,factor)
        self.assertGreater(float(area[y%6<3].mean()),float(area[y%6>=3].mean())*2)
        self.assertTrue(np.all(area<=.55))
        self.assertTrue(np.all(area*20<=np.maximum(base*20,30*1200/m.dx)+1e-6))
        m.cfg['stochastic']=0;np.testing.assert_array_equal(m.cell_variability(),1)

    def test_shared_plumes_cannot_process_more_donor_air_than_exists(self):
        m=self.model();m.donors.fill(0);_,air=m.plume_reservoir()
        gains=np.zeros_like(m.cloud[1:]);gains[5]=.01
        flow=np.full(m.shape,air[0,0]);before=m.q.copy()
        received=m.debit_plumes(gains,60,air_flux=flow)
        # One column of air shared by every plume, not one copy per receiver.
        self.assertLessEqual(float(received.sum()),float(gains.sum()/m.lon.size)+1e-8)
        self.assertAlmostEqual(float(np.sum((before-m.q)*m.mass)),float(received.sum()),places=7)

    def test_transport_diffusion_does_not_erase_cluster_variability_or_raise_mean(self):
        m=self.model();m.cfg['stochastic']=1
        y,x=np.indices(m.shape);m.cell_noise=np.sin(x/2)+np.cos(y/3)
        before=m.cell_variability();m.cell_noise=m.cell_noise*.1+7
        after=m.cell_variability()
        np.testing.assert_allclose(after,before,rtol=1e-12)
        self.assertAlmostEqual(float(after.mean()),1)
        self.assertGreater(float(after.std()),.4)

    def test_shear_coherence_weakens_oblique_flanks_without_fixing_map_direction(self):
        m=self.model();root=np.sqrt(.5)
        self.assertEqual(m.cold_head_balance(20,20,0,1,0),1)
        self.assertGreater(m.cold_head_balance(20,20,0,root,root),.4)
        self.assertLess(m.cold_head_balance(20,20,0,root,root),1)
        self.assertEqual(m.cold_head_balance(20,20,0,-1,0),0)
        # Rotate BOTH environment and head by 90 degrees: same physics.
        self.assertEqual(m.cold_head_balance(20,0,20,0,1),1)
        self.assertAlmostEqual(m.cold_head_balance(20,0,20,-root,root),m.cold_head_balance(20,20,0,root,root))


if __name__=='__main__':unittest.main()
