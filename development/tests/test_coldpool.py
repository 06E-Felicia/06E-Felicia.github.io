import unittest
import numpy as np
from simulation.coldpool import advance, velocity
from simulation.core import Model, collection_rate
from simulation.terrain import grid


class DensityCurrentTests(unittest.TestCase):
    def pool(self):
        y,x=np.mgrid[:61,:101]
        depth=500*np.exp(-((x-45)/6)**2-((y-30)/10)**2)
        return x,y,depth,depth*4,np.zeros_like(depth),np.zeros_like(depth)

    def test_still_cold_pool_expands_without_background_wind(self):
        x,y,h,q,mx,my=self.pool();before=float(np.sum(q*(x-45)**2)/q.sum())
        hn,qn,xn,yn,external,cfl=advance(h,q,mx,my,np.zeros_like(h),1800,2000)
        after=float(np.sum(qn*(x-45)**2)/qn.sum())
        self.assertGreater(after,before*1.7)
        self.assertGreater(float(hn[:,55:].sum()),float(h[:,55:].sum())*2)
        self.assertAlmostEqual(float(qn.sum()),float(q.sum())+external,delta=1e-6)
        np.testing.assert_allclose(qn,4*hn,atol=1e-10)
        self.assertLessEqual(cfl,.40000000001)
        u,v=velocity(hn,xn,yn)
        self.assertGreater(float(u[30,50]),1)
        self.assertLess(float(u[30,40]),-1)

    def test_dry_domain_has_no_invented_current(self):
        a=np.zeros((9,12));result=advance(a,a,a,a,a,3600,4000)
        for field in result[:4]:np.testing.assert_array_equal(field,a)

    def test_processed_air_debt_uses_same_density_current_mass_flux(self):
        x,y,h,q,mx,my=self.pool();tracer=h*1200
        hn,qn,xn,yn,debt,external,cfl=advance(h,q,mx,my,np.zeros_like(h),1200,2000,tracer=tracer)
        np.testing.assert_allclose(debt,1200*hn,atol=1e-8)
        m=self.model();m.cold_depth.fill(600);m.cape_deficit.fill(1200)
        m.transported_wake_debt=np.full(m.shape,1100.)
        # Contrary atmospheric advection must not replace processed cold air
        # with a boundary ghost carrying zero energy debt.
        u,v=m.winds();u[:]=-30;v[:]=0;m.transport_cape_budget(90,u,v)
        np.testing.assert_allclose(m.cape_deficit,1100)

    def test_hydrostatic_reconstruction_keeps_lake_at_rest(self):
        y,x=np.mgrid[:30,:40];bed=100+70*np.sin(x/4)*np.cos(y/4)
        h=600-bed;q=h*3;zero=np.zeros_like(h)
        hn,qn,mx,my,external,cfl=advance(h,q,zero,zero,bed,30,2000)
        np.testing.assert_allclose(hn[4:-4,4:-4],h[4:-4,4:-4],atol=1e-10)
        np.testing.assert_allclose(mx[4:-4,4:-4],0,atol=1e-10)
        np.testing.assert_allclose(my[4:-4,4:-4],0,atol=1e-10)

    def test_high_ridge_blocks_a_shallow_density_current(self):
        x,y,h,q,mx,my=self.pool();h[:,50:]=0;q=h*4
        plain=np.zeros_like(h);ridge=plain.copy();ridge[:,54:57]=1400
        flat=advance(h,q,mx,my,plain,1800,2000)
        blocked=advance(h,q,mx,my,ridge,1800,2000)
        self.assertGreater(float(flat[1][:,57:].sum()),100)
        self.assertLess(float(blocked[1][:,57:].sum()),.01*float(flat[1][:,57:].sum()))

    def model(self):
        cfg={'bounds':[112,22,114,24],'grid_km':8,'stochastic':0,'trough':0}
        return Model(cfg,np.full(grid(cfg['bounds'],8)[0].shape,30))

    def test_cold_interior_is_not_a_fresh_donor_even_with_high_mu_cape(self):
        m=self.model();m.cold_depth.fill(500);m.cold_content.fill(2000);m.mu['cape'].fill(2500)
        m.temp[0]+=np.arange(m.shape[1])[None]*.5
        a=np.ones(m.shape);donors,feeding=m.warm_inflow(a,a*0,a,a)
        self.assertFalse(feeding.any())
        # A colder neighbouring head must not re-label a still-deep, 2 K
        # processed column as warm simply because its relative Q is smaller.
        m.cold_content[:,:m.shape[1]//2]=4000;m.cold_content[:,m.shape[1]//2:]=1000
        donors,feeding=m.warm_inflow(a,a*0,a,a)
        self.assertFalse(feeding.any())
        m.cold_depth[:,m.shape[1]//2:]=0;m.cold_content[:,m.shape[1]//2:]=0
        donors,feeding=m.warm_inflow(a,a*0,a,a)
        self.assertTrue(feeding.any())
        self.assertTrue(np.all(m.cold_content.ravel()[donors[feeding]]==0))

    def test_residual_wake_convergence_is_not_counted_twice(self):
        m=self.model();m.lift.fill(4000);m.synoptic_lift.fill(0)
        m.cold_depth.fill(500);m.cold_content.fill(2000);m.cold_diagnostics()
        np.testing.assert_allclose(m.elevated_displacement(2200,0,500),0)
        # Independent broad ascent can still initiate legitimate elevated CI.
        m.synoptic_lift.fill(2000)
        self.assertGreater(float(m.elevated_displacement(2200,0,500).min()),500)

    def test_drop_collection_conserves_water_and_subsets(self):
        m=self.model();m.temp[:]=285;m.cloud[:]=.001;m.plume_cloud[:]=.0007
        m.rain[:]=.002;m.plume_rain[:]=.0015;m.rain_area[:]=m.plume_rain*.2
        before=(m.cloud+m.rain).copy();rain=m.rain.copy();temperature=m.temp.copy()
        m.accrete_cloud(90)
        np.testing.assert_allclose(m.cloud+m.rain,before,atol=1e-15)
        np.testing.assert_array_equal(m.temp,temperature)
        self.assertGreater(float(np.min(m.rain-rain)),0)
        self.assertTrue(np.all(m.plume_cloud<=m.cloud));self.assertTrue(np.all(m.plume_rain<=m.rain))
        self.assertTrue(np.all(m.rain_area<=m.plume_rain));self.assertGreaterEqual(float(m.cloud.min()),0)

    def test_collection_requires_rain_and_grows_with_drop_concentration(self):
        q=np.array([0.,1e-5,.001,.004]);rate=collection_rate(q,1.)
        self.assertEqual(rate[0],0);self.assertTrue(np.all(np.diff(rate)>0))
        self.assertGreater(collection_rate(.001,1.,.1),collection_rate(.001,1.,1.))
        m=self.model();m.cloud[:]=.001;m.plume_cloud[:]=m.cloud
        before=m.cloud.copy();m.accrete_cloud(90)
        np.testing.assert_array_equal(m.cloud,before);np.testing.assert_array_equal(m.rain,0)

    def test_cape_recharge_uses_net_enthalpy_and_connected_source(self):
        m=self.model();m.cape_deficit.fill(1000)
        # Positive evaporation does not count as recharge if simultaneous
        # sensible cooling removes still more moist enthalpy.
        m.recover_cape_budget(np.full(m.shape,-3000),np.full(m.shape,1.))
        np.testing.assert_allclose(m.cape_deficit,1000)
        m.recover_cape_budget(np.full(m.shape,3000),np.full(m.shape,1.),connection=0)
        np.testing.assert_allclose(m.cape_deficit,1000)
        m.recover_cape_budget(np.full(m.shape,3000),np.full(m.shape,1.),connection=1)
        self.assertLess(float(m.cape_deficit.max()),1000)

    def test_stable_cap_disconnects_surface_flux_from_elevated_source(self):
        m=self.model();m.mu['start_index'].fill(6)
        m.temp[:5]-=8
        u,v=m.winds()
        self.assertLess(float(m.surface_cape_connection(u,v).max()),.01)
        m.mu['start_index'].fill(0)
        np.testing.assert_allclose(m.surface_cape_connection(u,v),1)

    def test_rain_cools_soil_and_preserves_its_memory(self):
        a,b=self.model(),self.model();a.last_rate.fill(60)
        a.ground_temp+=4;b.ground_temp+=4
        a.surface_exchange(300,.2,1);b.surface_exchange(300,.2,1)
        self.assertLess(float(a.ground_temp.mean()),float(b.ground_temp.mean())-.1)
        a.last_rate.fill(0);before=a.ground_temp.copy()
        a.surface_exchange(30,.2,1)
        self.assertLess(float(np.max(np.abs(a.ground_temp-before))),.1)

    def test_environmental_shear_is_not_erased_by_the_outflow_itself(self):
        m=self.model();nx=np.ones(m.shape);ny=nx*0
        u,v=m.winds();before=m.inflow_shear(u,v,nx,ny)
        m.u+=25;m.v-=8;u,v=m.winds();after=m.inflow_shear(u,v,nx,ny)
        np.testing.assert_allclose(after,before,atol=1e-5)
        self.assertGreater(float(after.min()),5)
        np.testing.assert_allclose(m.inflow_shear(u,v,-nx,ny),0,atol=1e-5)

    def test_rkw_uses_wind_difference_across_depth_not_a_jet_layer_mean(self):
        from simulation.core import Z
        m=self.model();one=np.ones(m.shape)
        m.u=m.syn_u.copy();m.v=m.syn_v.copy()
        # Analytic environmental profile: the shallow head samples 1500 m,
        # the deep head 3000 m. A large intervening LLJ must not change this
        # endpoint difference into the old layer-mean/opposite-normal shear.
        u=np.broadcast_to((3+Z*.004)[:,None,None],m.q.shape).copy()
        v=np.broadcast_to((2+Z*.002)[:,None,None],m.q.shape).copy()
        u[4]+=25;v[4]+=25
        shallow=m.inflow_shear(u,v,one,one*0,np.full(m.shape,350))
        deep=m.inflow_shear(u,v,one,one*0,np.full(m.shape,1500))
        np.testing.assert_allclose(shallow,(1500-Z[0])*.004)
        np.testing.assert_allclose(deep,(3000-Z[0])*.004)
        np.testing.assert_allclose(m.inflow_shear(u,v,-one,one*0),0)
        np.testing.assert_allclose(m.inflow_shear(u,v,one*0,one),(1500-Z[0])*.002)

    def test_donor_column_is_sampled_at_receiving_head_depth(self):
        from simulation.core import Z
        m=self.model();m.u=m.syn_u.copy();m.v=m.syn_v.copy()
        y,x=np.indices(m.shape);m.donors=y*m.shape[1]+(x+3)%m.shape[1]
        depth=np.where(x%4<2,350.,1500.)
        u=np.broadcast_to((3+Z*.004)[:,None,None],m.q.shape).copy();v=u*0
        shear=m.inflow_shear(u,v,np.ones(m.shape),np.zeros(m.shape),depth)
        np.testing.assert_allclose(shear,(np.clip(2*depth,1500,3500)-Z[0])*.004)

    def test_leading_jet_uses_pressure_work_to_cross_cin_not_an_lfc_height_shortcut(self):
        m=self.model()
        self.assertGreater(float(m.gust_activation(2000,500,1,1,0,-25)),.7)
        self.assertEqual(float(m.gust_activation(2000,500,1,1,0,-200)),0)
        self.assertEqual(float(m.gust_activation(2000,500,1,0,0,-25)),0)
        self.assertEqual(float(m.gust_activation(2000,500,1,1,2200,-25)),0)
        self.assertEqual(float(m.gust_activation(0,500,1,1,0,0)),0)

    def test_organization_uses_head_overturning_time_not_a_grid_point_delay(self):
        m=self.model()
        self.assertEqual(float(m.organization_timescale(1000,20,1)),150)
        self.assertEqual(float(m.organization_timescale(1000,2,.1)),900)
        self.assertEqual(float(m.organization_timescale(200,20,1)),120)


if __name__=='__main__':unittest.main()
