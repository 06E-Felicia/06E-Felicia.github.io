import base64
import unittest
import numpy as np
from simulation.core import Model, settings, transport, advect, limited_transport, daylight, sediment, mix_boundary_layer, rain_reflectivity, rain_fall_speed, DZ, Z
from simulation.experiment import random_environment
from simulation.terrain import grid
from simulation.thermo import parcel, saturation
from simulation.run import pack


class PhysicsTests(unittest.TestCase):
    def model(self, **extra):
        c={'bounds':[112,22,113.5,26],'grid_km':10,**extra}
        return Model(c,np.full(grid(c['bounds'],c['grid_km'])[0].shape,30))

    def test_settings_reject_unsafe_values(self):
        for c in [{'seed':0},{'hours':float('nan')},{'grid_km':.1},{'hours':999},{'seed':True},{'unknown':1},{'compact_transport':1}]:
            with self.assertRaises(ValueError):settings(c)

    def test_thermodynamic_reference(self):
        # MetPy 1.7.1 reference: 1203.183 J/kg, -92.785 J/kg, calculated from
        # this same analytic column. Tolerance covers saturation constants.
        p=np.linspace(100000,10000,70);z=-8000*np.log(p/100000)
        t=300-.0065*np.minimum(z,12000)-.001*np.maximum(z-12000,0)
        q=saturation(293,100000)*np.exp(-z/2300)
        result=parcel(p,t,q)
        self.assertAlmostEqual(float(result['cape']),1203.183,delta=35)
        self.assertAlmostEqual(float(result['cin']),-92.785,delta=8)
        dry=parcel(p,t,q*.35)
        self.assertLess(float(dry['cape']),float(result['cape']))

    def test_stable_column(self):
        p=np.linspace(100000,15000,45);z=-8000*np.log(p/100000)
        t=293-.004*z;q=saturation(280,100000)*np.exp(-z/1500)
        self.assertLess(float(parcel(p,t,q)['cape']),1)

    def test_seed_replay_and_new_process(self):
        a,b,c=self.model(seed=123),self.model(seed=123),self.model(seed=124)
        for _ in range(50):a.step();b.step();c.step()
        np.testing.assert_array_equal(a.temp,b.temp)
        np.testing.assert_array_equal(a.total,b.total)
        self.assertGreater(np.max(np.abs(a.temp-c.temp)),.01)
        self.assertEqual(len(set(a.seed_ids)),5)

    def test_stochastic_updates_after_initialization(self):
        a=self.model();before=a.noise.copy()
        while a.time<1000:a.step()
        self.assertFalse(np.array_equal(before,a.noise))

    def test_conservative_transport(self):
        a=np.zeros((20,30));a[8:12,12:16]=1
        out=transport(a,np.ones_like(a)*5,np.ones_like(a)*-2,30,1000)
        self.assertAlmostEqual(float(out.sum()),float(a.sum()),places=10)
        self.assertGreaterEqual(out.min(),0)

    def test_open_boundary_supplies_fresh_inflow_without_reflecting_outflow(self):
        a=np.ones((12,20))*.002;u=np.ones_like(a)*10;v=np.zeros_like(a)
        wet=transport(a,u,v,30,1000,boundary=.018)
        self.assertAlmostEqual(float(wet[0,0]),.002+.3*(.018-.002))
        np.testing.assert_allclose(wet[:,-1],a[:,-1])
        scalar=advect(a,u,v,30,1000,boundary=.018)
        self.assertGreater(float(scalar[:,0].min()),.002)
        self.assertLessEqual(float(scalar.max()),.018)
        cleared=transport(a,u,v,30,1000,boundary=0)
        self.assertLess(float(cleared[:,0].max()),.002)

    def test_departed_front_is_not_reset_by_initial_western_boundary(self):
        m=self.model();warm=m.air<.1;initial_t=m.temp.copy();initial_q=m.q.copy()
        m.synoptic.front_lat.fill(m.cfg['bounds'][1]-4)
        m.air.fill(1);incoming_t,incoming_q=m.upstream_environment()
        self.assertTrue(np.all(incoming_t[0,warm]<initial_t[0,warm]-5))
        self.assertTrue(np.all(incoming_q[0,warm]<initial_q[0,warm]))
        m.step()
        np.testing.assert_allclose(m.air,1,atol=1e-6)

    def test_scalar_advection_preserves_constant_and_bounds(self):
        y,x=np.mgrid[:20,:30];u=np.sin(x/4)*7;v=np.cos(y/4)*5
        np.testing.assert_allclose(advect(np.ones_like(u)*3,u,v,30,1000),3,atol=1e-12)
        a=((x>12)&(y>8)).astype(float);out=advect(a,u,v,30,1000)
        self.assertGreaterEqual(out.min(),0);self.assertLessEqual(out.max(),1)

    def test_boundary_advection_retains_moving_structure(self):
        x=np.arange(100);a=np.broadcast_to(np.exp(-((x-30)/4)**2),(8,100)).copy()
        u=np.full_like(a,10);v=np.zeros_like(a);first=a.copy();limited=a.copy()
        for _ in range(80):
            first=transport(first,u,v,30,1000)
            limited=advect(limited,u,v,30,1000)
        exact=np.broadcast_to(np.exp(-((x-54)/4)**2),a.shape)
        self.assertLess(float(abs(limited-exact).mean()),.7*float(abs(first-exact).mean()))
        self.assertGreaterEqual(float(limited.min()),0)
        self.assertLessEqual(float(limited.max()),1)
        self.assertAlmostEqual(float(limited.sum()),float(a.sum()),places=6)

    def test_boundary_layer_mixing_moves_surface_supply_without_creating_water(self):
        m=self.model();m.q[:5]=.01;m.q[0]=.018
        # A daytime, nearly neutral PBL allows surface fluxes to reach 150 m.
        m.temp[:5]=301*(m.p[:5]/100000)**(287.05/1004)
        before=float(np.sum(m.q*m.mass));bottom=m.q[0].copy();upper=m.q[1].copy()
        u,v=m.winds()
        t,q=mix_boundary_layer(m.temp,m.q,m.p,m.mass,u,v,90,1,m.land)
        self.assertLess(float(np.max(q[0]-bottom)),0)
        self.assertGreater(float(np.min(q[1]-upper)),0)
        self.assertLess(abs(float(np.sum(q*m.mass))-before)/before,1e-6)
        self.assertTrue(np.isfinite(t).all());self.assertGreater(float(q.min()),0)

    def test_elevated_parcel_uses_own_source_and_free_convection_level(self):
        m=self.model();m.temp[:3]-=8;m.q[:3]*=.5;m.diagnostics()
        eligible=(m.mu['start_index']>0)&(m.mu['cape']>100)
        self.assertGreater(int(eligible.sum()),0)
        self.assertEqual(float(m.sb['cape'].max()),0)
        self.assertTrue(np.isfinite(m.mu_lfc[eligible]).all())
        self.assertTrue(np.all(m.mu_lfc[eligible]>=Z[m.mu['start_index'][eligible]]))
        self.assertGreater(float(m.mu['cape'][eligible].max()),1000)

    def test_cell_advection_follows_cloud_layer_not_a_fixed_level(self):
        m=self.model();u,v=m.winds()
        uniform_u,uniform_v=m.steering(np.full_like(u,12),np.full_like(v,-4))
        np.testing.assert_allclose(uniform_u,12,rtol=1e-6)
        np.testing.assert_allclose(uniform_v,-4,rtol=1e-6)
        m.steering_weights=np.zeros_like(m.mass);m.steering_weights[4]=m.mass[4]
        low_u,low_v=m.steering(u,v)
        np.testing.assert_allclose(low_u,u[4],rtol=1e-6)
        np.testing.assert_allclose(low_v,v[4],rtol=1e-6)
        m.steering_weights[:]=0;m.steering_weights[9]=m.mass[9]
        high_u,high_v=m.steering(u,v)
        np.testing.assert_allclose(high_u,u[9],rtol=1e-6)
        np.testing.assert_allclose(high_v,v[9],rtol=1e-6)
        # Vertical turning can reduce u while increasing v. Test which
        # layer supplies BOTH components, not a monotonic zonal profile.
        changed_u=u.copy();changed_v=v.copy()
        changed_u[4]+=100;changed_v[4]-=100
        selected_u,selected_v=m.steering(changed_u,changed_v)
        np.testing.assert_allclose(selected_u,high_u,rtol=1e-6)
        np.testing.assert_allclose(selected_v,high_v,rtol=1e-6)

    def test_surface_wind_is_prognostic_and_front_is_continuous(self):
        m=self.model()
        # The production reservoir now starts outside the domain. Isolate an
        # ENTERED front here to test continuity, not its old initial position.
        m.synoptic.front_lat.fill(24.5);m.air=m.synoptic.external_air()
        m.syn_u,m.syn_v=m.synoptic.surface_target(m.air,0);m.u=m.syn_u.copy();m.v=m.syn_v.copy()
        u,v=m.winds()
        np.testing.assert_allclose(u[0],m.u,atol=1e-6)
        np.testing.assert_allclose(v[0],m.v,atol=1e-6)
        for _ in range(240):m.step()
        crossings=np.sum(np.diff((m.air>=.5).astype('int8'),axis=0)!=0,axis=0)
        self.assertTrue(np.all(crossings==1),'flat-land front must not fragment during spin-up')
        self.assertGreater(float(m.last_rate.max()),0,'frontal precipitation must emerge from unmodified initialization')

    def test_shallow_gust_does_not_transport_the_deep_synoptic_reservoir(self):
        a,b=self.model(seed=613),self.model(seed=613)
        b.cold=5*np.exp(-((b.lat-23.7)/.25)**2-((b.lon-112.6)/.3)**2)
        b.cold_depth=np.where(b.cold>.01,650,0);b.cold_content=b.cold*b.cold_depth
        # A new condensate circulation has its own CFL. Compare the same
        # physical time, not a step count with potentially different dt.
        for m in [a,b]:
            while m.time<1800-1e-6:m.step(1800)
        self.assertGreater(float(np.max(abs(a.v-b.v))),.1)
        np.testing.assert_allclose(a.air,b.air,atol=1e-4)

    def test_stalled_front_has_bounded_shallow_displacement(self):
        m=self.model(trough=0,stochastic=0)
        # Exact stationary contour, equal opposing confluence, stable cold
        # wedge: a controlled forcing test independent of random front bends.
        m.air[:]=1/(1+np.exp(-(m.lat-24.5)*111195/18000))
        m.syn_u.fill(0);m.syn_v[:]=5*(1-2*m.air)
        convergence=-np.gradient(m.syn_v,m.dx,axis=0)
        stalled=m.frontal_lifting(convergence,convergence,0,0)
        near=np.abs(m.air-.5)<.15
        equilibrium=np.maximum(m.w,0)/stalled
        self.assertLess(float(equilibrium[near].max()),150)
        stalled_depth=m.ascent_depth.copy()
        m.syn_v-=6  # actual frontal translation, not only an opposing inflow
        advancing=m.frontal_lifting(convergence,convergence,0,0)
        self.assertGreater(float(m.ascent_depth[near].mean()),float(stalled_depth[near].mean())+700)
        self.assertGreater(float((np.maximum(m.w,0)/advancing)[near].mean()),float(equilibrium[near].mean())*2)

    def test_inhibited_surface_parcel_does_not_get_a_free_300_m_trigger(self):
        m=self.model(trough=0,stochastic=0)
        m.lift.fill(1100);m.lfc.fill(1400)
        m.mu['start_index'].fill(0);m.next_diagnostic=1e9
        m.step()
        self.assertEqual(float(m.initiation.max()),0)

    def test_dry_cold_pool_has_no_invented_echo(self):
        m=self.model();m.cold.fill(5);m.cold_depth.fill(800)
        dbz=rain_reflectivity(m.rain,m.plume_rain,m.rain_area,m.mass/DZ[:,None,None],m.anvil)
        self.assertLess(float(dbz.max()),0)

    def test_detrained_anvil_water_is_conserved_and_melts_into_weak_rain(self):
        m=self.model();m.temp[8:]=260;m.q[:]=saturation(m.temp,m.p)*.99
        # Environmental/detrained cloud is the weak-echo reservoir. Dense
        # convective frozen cloud now has a separate, explicitly tested path.
        m.cloud[8]=.0012;m.organization.fill(.7)
        before=float(np.sum((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass))
        surface=m.trailing_microphysics(90)
        after=float(np.sum((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass)+surface.sum())
        self.assertGreater(float(m.anvil.max()),0)
        self.assertLess(abs(after-before)/before,1e-12)
        echo=rain_reflectivity(m.rain,m.plume_rain,m.rain_area,m.mass/DZ[:,None,None],m.anvil)
        self.assertGreater(float(echo.max()),5);self.assertLess(float(echo.max()),35)
        # Warm melting layer transfers existing frozen water to liquid rain.
        m.anvil.fill(0);m.cloud.fill(0);m.plume_cloud.fill(0)
        m.temp[6]=279;m.anvil[6]=.0002
        before=float(np.sum((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass))
        surface=m.trailing_microphysics(90)
        self.assertGreater(float(m.rain[6].max()),0)
        after=float(np.sum((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass)+surface.sum())
        self.assertLess(abs(after-before)/before,1e-12)

    def test_hourly_rain_uses_accumulated_water_not_current_rate(self):
        m=self.model();m.time=5400;m.total.fill(40);m.last_rate.fill(80)
        m.rain_history=[(1500,np.full(m.shape,10.)),(1800,np.full(m.shape,13.)),(2100,np.full(m.shape,16.)),(5400,m.total.copy())]
        np.testing.assert_allclose(m.hourly_rain(),27)

    def test_drop_spectrum_controls_velocity_and_sedimentation_closes_budget(self):
        density=np.ones((len(Z),2,2))
        weak=rain_fall_speed(np.full_like(density,1e-5),density)
        strong=rain_fall_speed(np.full_like(density,.004),density)
        self.assertTrue(np.all(strong>weak+3))
        local=rain_fall_speed(np.full_like(density,.0004),density,.1)
        np.testing.assert_allclose(local,strong)
        self.assertTrue(np.all(rain_fall_speed(np.full_like(density,.004),density,moment=7)>strong))
        mass=np.broadcast_to(DZ[:,None,None],density.shape).copy()
        water=np.zeros_like(mass);water[4]=.004
        remaining,fallen=sediment(water,mass,180,strong)
        self.assertGreaterEqual(float(remaining.min()),0)
        self.assertAlmostEqual(float(np.sum(remaining*mass)+fallen.sum()),float(np.sum(water*mass)),places=9)

    def test_core_rain_is_occupied_area_flux_not_an_arbitrary_intensity_floor(self):
        m=self.model();m.rain[0]=.002;m.plume_rain[0]=.002;m.rain_area[0]=.0002
        m.step()
        self.assertGreater(float(m.last_core_rate.max()),20)
        self.assertTrue(np.all(m.last_core_rate>=m.last_rate-1e-9))
        self.assertLess(float(m.last_rate.max()),float(m.last_core_rate.max())*.2)
        self.assertIn('rain_hour',m.fields());self.assertIn('fall3',m.fields())

    def test_sedimentation_has_independent_cfl_and_water_budget(self):
        mass=np.broadcast_to(DZ[:,None,None],(len(Z),2,2)).copy()
        r=np.zeros_like(mass);r[3]=.001
        coarse,surface=sediment(r,mass,90)
        fine=r.copy();total=np.zeros((2,2))
        for _ in range(30):fine,fallen=sediment(fine,mass,3);total+=fallen
        self.assertGreater(float(surface.sum()),0,'rain must cross more than one thin layer per 90 s')
        self.assertGreaterEqual(coarse.min(),0)
        self.assertAlmostEqual(float((coarse*mass).sum()+surface.sum()),float((r*mass).sum()),places=9)
        np.testing.assert_allclose(surface,total,rtol=.25,atol=.01)

    def test_random_environment_is_reproducible_and_changes_all_runs(self):
        a=random_environment(123);b=random_environment(123);c=random_environment(124)
        self.assertEqual(a,b);self.assertNotEqual(a,c)
        self.assertGreater(sum(a[k]!=c[k] for k in ['moisture','jet','shear','trough','sst_c']),3)
        self.assertEqual(random_environment(123,{'grid_km':4})['grid_km'],4)
        with self.assertRaises(ValueError):random_environment(123,{'seed':99})

    def test_budget_and_front_rain(self):
        m=self.model()
        # Moist frontal cloud layer: saturation adjustment and warm-rain
        # sedimentation must work independently of the convective trigger.
        m.q=np.minimum(saturation(m.temp,m.p)*1.005,.02).astype('float32')
        m.initial_water=float(np.sum(m.q*m.mass))
        for _ in range(240):m.step()
        audit=m.audit_state()
        self.assertLess(abs(audit['water_relative_residual']),.002)
        self.assertLess(audit['max_cfl'],.7)
        self.assertGreaterEqual(m.q.min(),0)
        self.assertGreaterEqual(m.rain.min(),-1e-12)
        self.assertGreater(m.total.max(),0,'resolved ascent can rain without a prescribed storm')
        self.assertGreater(m.air[-1].mean(),m.air[0].mean())
        self.assertLess(float(m.temp.max()),325)

    def test_output_does_not_change_state(self):
        a=self.model();before=a.temp.copy();clock=a.next_diagnostic
        f=a.fields();np.testing.assert_array_equal(a.temp,before);self.assertEqual(a.next_diagnostic,clock)
        self.assertTrue(np.isfinite(f['sbcape']).all())

    def test_plume_water_is_subset_not_duplicate_reservoir(self):
        m=self.model(moisture=1.2)
        for _ in range(160):m.step()
        self.assertGreater(float(m.plume_cloud.max()),0)
        self.assertGreaterEqual(float(m.plume_cloud.min()),-1e-10)
        self.assertLessEqual(float(np.max(m.plume_cloud-m.cloud)),1e-8)
        self.assertLess(abs(m.audit_state()['water_relative_residual']),.002)

    def test_convective_rain_and_area_moment_are_not_extra_water(self):
        m=self.model(moisture=1.2)
        for _ in range(160):m.step()
        self.assertGreater(float(m.plume_rain.max()),0)
        self.assertGreaterEqual(float(m.plume_rain.min()),0)
        self.assertLessEqual(float(np.max(m.plume_rain-m.rain)),1e-8)
        self.assertLessEqual(float(np.max(m.rain_area-m.plume_rain)),1e-8)
        self.assertGreaterEqual(float(m.rain_area.min()),0)
        self.assertLess(abs(m.audit_state()['water_relative_residual']),.002)

    def test_radar_averages_linear_backscatter_not_grid_mean_rain(self):
        rain=np.full((2,2),.001);density=np.ones_like(rain)
        stratiform=rain_reflectivity(rain,rain*0,rain*0,density)
        uniform=rain_reflectivity(rain,rain,rain,density)
        concentrated=rain_reflectivity(rain,rain,rain*.1,density)
        np.testing.assert_allclose(stratiform,uniform)
        np.testing.assert_allclose(concentrated-uniform,7.5,atol=1e-6)
        self.assertEqual(float(rain_reflectivity(rain*0,rain*0,rain*0,density).max()),-30)

    def test_elevated_cold_column_does_not_get_warm_pbl_mass_flux(self):
        m=self.model();m.temp[:3]-=8;m.q[:3]*=.5;m.air.fill(.9);m.diagnostics()
        elevated=(m.mu['start_index']>=4)&(m.mu['cape']>100)
        self.assertTrue(elevated.any())
        self.assertLess(float(m.deep_support[elevated].max()),.6)
        m.air.fill(0);m.diagnostics()
        np.testing.assert_allclose(m.deep_support,1)

    def test_shared_warm_donor_cannot_be_debited_twice(self):
        m=self.model();before=m.q.copy();donor=m.lon.size//2
        m.donors[0,:2]=donor
        gain=np.zeros_like(m.cloud[1:]);gain[3,0,:2]=100
        received=m.debit_plumes(gain,90)
        removed=float(np.sum((before-m.q)*m.mass))
        self.assertGreater(removed,0);self.assertLess(removed,200)
        self.assertAlmostEqual(removed,float(received.sum()),delta=1e-4)
        changed=np.any(abs(before-m.q)>1e-12,axis=0).ravel()
        self.assertEqual(int(changed.sum()),1);self.assertTrue(changed[donor])
        self.assertGreaterEqual(float(m.q.min()),0)

    def test_elevated_source_has_its_own_moisture_reservoir(self):
        m=self.model();m.mu['start_index'].fill(6)  # 2.2 km source
        before=m.q.copy();gain=np.zeros_like(m.cloud[1:]);gain[8]=.05
        received=m.debit_plumes(gain,90)
        self.assertGreater(float(received.sum()),0,'elevated CAPE cannot be silently starved by a surface pressure cutoff')
        removed=float(np.sum((before-m.q)*m.mass))
        self.assertAlmostEqual(removed,float(received.sum()),delta=1e-6)
        np.testing.assert_array_equal(m.q[:5],before[:5])

    def test_explicit_energy_budget_still_limits_plume_without_a_latitude_clip(self):
        m=self.model();ceiling=m.cape_ceiling
        m.cape_capacity=ceiling.copy()  # fresh idealized 6000-J/kg source below
        self.assertTrue(np.all(np.diff(ceiling,axis=0)<0))
        self.assertGreater(float(ceiling[m.lat<22.5].mean()),3300)
        self.assertLess(float(ceiling[m.lat>24.8].max()),150)
        np.testing.assert_allclose(m.available_cape(np.full(m.shape,6000)),ceiling)
        np.testing.assert_allclose(m.plume_cape(np.full(m.shape,6000)),ceiling)
        f=m.fields();self.assertTrue(np.all(f['mucape']<=ceiling))
        self.assertIn('mucape_raw',f)

    def test_boundary_layer_jet_is_not_halved_by_background_blending(self):
        m=self.model();u,v=m.winds();warm=m.air<.1
        self.assertGreater(float(np.mean(v[4,warm])),10)
        np.testing.assert_allclose(u[0],m.u,atol=1e-6)
        np.testing.assert_allclose(v[0],m.v,atol=1e-6)

    def test_real_convective_mass_debits_energy_and_cannot_reset_by_new_mu_source(self):
        m=self.model();m.mu['cape'].fill(2000);m.cape_capacity=np.minimum(2000,m.cape_ceiling);before=m.available_cape(m.mu['cape']).copy()
        _,air=m.plume_reservoir();gain=np.full_like(m.cloud[1:],.001)
        water=float(np.sum(m.q*m.mass));received=m.debit_plumes(gain,90,air_flux=air*2)
        self.assertGreater(float(m.cape_deficit.max()),0)
        self.assertTrue(np.all(m.available_cape(m.mu['cape'])<before*.4))
        self.assertAlmostEqual(water-float(np.sum(m.q*m.mass)),float(received.sum()),delta=1e-6)
        debt=m.cape_deficit.copy();m.mu['start_index'].fill(6);m.mu['cape'].fill(6000)
        np.testing.assert_array_equal(m.cape_deficit,debt)
        self.assertTrue(np.all(m.available_cape(m.mu['cape'])<=m.cape_ceiling-debt))

    def test_dry_inactive_plume_does_not_consume_cape(self):
        m=self.model();m.debit_plumes(np.zeros_like(m.cloud[1:]),90,air_flux=np.full(m.shape,1000))
        self.assertEqual(float(m.cape_deficit.max()),0)

    def test_occupied_plume_area_includes_activity_once(self):
        m=self.model();m.organization.fill(.5);m.activity.fill(1)
        full=m.plume_coverage(1,1,1)
        m.activity.fill(.25);partial=m.plume_coverage(1,1,1)
        np.testing.assert_allclose(partial,full*.25)
        m.activity.fill(0);np.testing.assert_allclose(m.plume_coverage(1,1,1),0)
        self.assertLessEqual(float(full.max()),.5)

    def test_spent_cape_recovers_only_from_real_boundary_flux(self):
        m=self.model();m.cape_deficit.fill(500);before=m.cape_deficit.copy()
        m.recover_cape_budget(np.zeros(m.shape),np.zeros(m.shape))
        np.testing.assert_array_equal(m.cape_deficit,before)
        m.recover_cape_budget(np.full(m.shape,100),np.full(m.shape,.1))
        self.assertTrue(np.all(m.cape_deficit<before));self.assertTrue(np.all(m.cape_deficit>=0))

    def test_cape_debt_moves_with_low_level_wake_not_cloud_wind(self):
        m=self.model();m.cape_deficit[:,4:6]=500
        before=m.cape_deficit.copy();u=np.zeros_like(m.mass);v=np.zeros_like(u);u[10:]=50
        m.mu['start_index'].fill(0);m.transport_cape_budget(60,u,v)
        np.testing.assert_array_equal(m.cape_deficit,before)
        m.mu['start_index'].fill(6);u[6]=20;m.transport_cape_budget(60,u,v)
        np.testing.assert_array_equal(m.cape_deficit,before)
        u[0]=10;m.transport_cape_budget(60,u,v)
        self.assertGreater(float(m.cape_deficit[:,6].max()),0)

    def test_shared_source_moisture_debit_does_not_stabilize_unprocessed_inflow(self):
        m=self.model();donor=0;m.donors.fill(donor)
        gain=np.zeros_like(m.cloud[1:]);gain[8,-1,-1]=.1
        flow=np.zeros(m.shape);flow[-1,-1]=500
        before=m.q.copy();m.debit_plumes(gain,90,air_flux=flow)
        self.assertGreater(float(np.sum(before[:,0,0]-m.q[:,0,0])),0)
        self.assertEqual(float(m.cape_deficit[0,0]),0)
        self.assertGreater(float(m.cape_deficit[-1,-1]),0)

    def test_fresh_donor_can_feed_leading_edge_but_spent_donor_cannot(self):
        m=self.model();m.mu['cape'].fill(2000);m.sb['cape'].fill(2000)
        m.cape_capacity=np.minimum(2000,m.cape_ceiling)
        m.cape_deficit.fill(1900);m.cape_deficit[:,0]=0;m.donors[:]=np.indices(m.shape)[0]*m.shape[1]
        self.assertGreater(float(m.plume_cape(np.full(m.shape,2000))[m.lat<23].min()),1900)
        m.cape_deficit[:,0]=1900
        self.assertLess(float(m.plume_cape(np.full(m.shape,2000)).max()),101)

    def test_core_rain_evaporation_is_finite_and_conserves_water(self):
        a,b=self.model(),self.model();a.rain[:]=.001;b.rain[:]=.001
        a.plume_rain[:]=a.rain;a.rain_area[:]=a.rain*.25
        before=float(np.sum((a.q+a.rain)*a.mass));a_loss=a.evaporate_rain(90);b_loss=b.evaporate_rain(90)
        self.assertLess(float(a_loss.sum()),float(b_loss.sum()));self.assertGreater(float(a_loss.sum()),0)
        self.assertAlmostEqual(before,float(np.sum((a.q+a.rain)*a.mass)),delta=1e-6)
        self.assertGreaterEqual(float(a.rain.min()),0);self.assertTrue(np.all(a.plume_rain<=a.rain))

    def test_saturated_rain_core_does_not_receive_artificial_water(self):
        m=self.model();m.q[:]=saturation(m.temp,m.p);m.rain[:]=.001;m.plume_rain[:]=m.rain;m.rain_area[:]=m.rain*.3
        before=m.rain.copy();loss=m.evaporate_rain(90)
        np.testing.assert_allclose(loss,0,atol=1e-12);np.testing.assert_allclose(m.rain,before,atol=1e-12)

    def test_subcloud_rain_is_not_shielded_from_downdraft_evaporation(self):
        from simulation.core import rain_evaporation_rate,DZ,LV,CP
        a,b=self.model(),self.model();a.rain[0]=.001;b.rain[0]=.001
        # Equal LOCAL water concentration means the same drops; a narrow
        # shaft has one quarter of the cell-mean water, not smaller drops.
        a.rain[0]*=.25;a.plume_rain[0]=a.rain[0];a.rain_area[0]=a.rain[0]*.25
        a.mu['lcl_pressure'].fill(80000);b.mu['lcl_pressure'].fill(80000)
        qs=saturation(a.temp[0],a.p[0]);dry=np.clip(1-a.q[0]/qs,0,1)
        rate=rain_evaporation_rate(a.plume_rain[0],a.mass[0]/DZ[0],a.temp[0],a.p[0],.25)
        capacity=np.maximum(qs-a.q[0],0)/(1+LV**2*qs/(CP*461.5*a.temp[0]**2))
        expected=np.minimum(a.plume_rain[0]*dry*(-np.expm1(-90*rate)),capacity*.25)
        np.testing.assert_allclose(a.evaporate_rain(90)[0],expected,rtol=1e-5,atol=1e-12)
        np.testing.assert_allclose(expected,b.evaporate_rain(90)[0]*.25,rtol=1e-5,atol=1e-12)

    def test_northern_wave_is_distinct_and_slower_than_cloud_steering(self):
        m=self.model()
        self.assertLess(m.north_trough_lon,96)
        self.assertLess(m.north_phase_speed,.35)
        self.assertGreater(m.north_phase_speed,.25)

    def test_warm_donor_does_not_bypass_stalled_receiver_support(self):
        m=self.model();m.temp[:3]-=8;m.q[:3]*=.5;m.air.fill(.6);m.diagnostics()
        self.assertLess(float(m.deep_support.max()),.7)
        stalled=m.deep_support.copy();m.front_advance.fill(1);m.diagnostics()
        self.assertGreater(float(np.mean(m.deep_support-stalled)),.2)

    def test_warm_inflow_respects_terrain_and_requires_instability(self):
        m=self.model();m.temp[0,:,:4]-=8;m.q[0,:,:4]*=.6;m.diagnostics()
        nx=np.ones(m.shape);ny=np.zeros(m.shape);edge=np.ones(m.shape);balance=np.ones(m.shape)
        donors,feeding=m.warm_inflow(nx,ny,edge,balance)
        self.assertTrue(feeding.any())
        m.h[:,4:]=1500;ids,blocked=m.warm_inflow(nx,ny,edge,balance)
        self.assertFalse(blocked[:,3].any(),'inflow across the 1470 m step must be blocked')
        self.assertTrue(np.all(np.abs(m.h.ravel()[ids][blocked]-m.h[blocked])<500))
        m.mu['cape'].fill(0);_,stable=m.warm_inflow(nx,ny,edge,balance)
        self.assertFalse(stable.any())

    def test_forcing_random_sequence_is_independent_of_scene_refreshes(self):
        a=self.model(seed=719);b=self.model(seed=719)
        for target in [600,1200,1800,2400,2700]:
            while a.time<target-1e-6:a.step(target)
        while b.time<2700-1e-6:b.step(2700)
        np.testing.assert_array_equal(a.noise,b.noise)
        self.assertEqual(a.next_noise,b.next_noise)

    def test_replay_interval_does_not_change_integrated_weather(self):
        a,b=self.model(seed=721),self.model(seed=721)
        for target in [600,1200,1800]:
            while a.time<target-1e-6:a.step(target)
        while b.time<1800-1e-6:b.step(1800)
        for key in ['temp','q','rain','total','activity','cold_content']:
            np.testing.assert_array_equal(getattr(a,key),getattr(b,key))
        self.assertEqual(a.steps,b.steps)

    def test_quantization(self):
        a=np.array([[1.2,100.,np.nan],[-20,2.3,5000]])
        p=pack(a);raw=np.frombuffer(base64.b64decode(p['data']),dtype='<i2').reshape(a.shape)
        out=raw*p['scale']+p['offset'];valid=np.isfinite(a)
        np.testing.assert_allclose(out[valid],a[valid],atol=p['scale']*.51)
        self.assertEqual(raw[0,2],32767)

    def test_density_current_transports_volume_without_multiplying_deficit(self):
        m=self.model();y,x=np.indices(m.shape)
        m.cold_depth=500*np.exp(-((x-7)/2)**2-((y-20)/3)**2)
        m.cold_content=m.cold_depth*4;m.u=(x-7)*.4;m.v=(y-20)*.2
        before=float(m.cold_content.sum());depth=float(m.cold_depth.sum())
        for _ in range(20):m.transport_cold_pool(30)
        self.assertLess(abs(float(m.cold_content.sum())-before)/before,1e-5)
        self.assertLess(abs(float(m.cold_depth.sum())-depth)/depth,1e-5)
        self.assertGreater(float(m.cold_depth.max()),0);self.assertLess(float(m.cold_depth.max()),500)
        self.assertLessEqual(float(m.cold.max()),4.0001)

    def test_evaporation_creates_cold_pool_depth_and_surface_heat_recovers_it(self):
        m=self.model();evap=np.zeros_like(m.q);evap[:4]=.0002
        m.supply_cold_pool(evap)
        self.assertGreater(float(m.cold_depth.min()),0);self.assertGreater(float(m.cold.min()),0)
        before=m.cold.copy();content=float(m.cold_content.sum())
        m.recover_cold_pool(600,np.full(m.shape,2.),1.)
        self.assertLess(float(m.cold_content.sum()),content);self.assertTrue(np.all(m.cold<before))
        self.assertLess(abs(m.audit_state()['coldpool_relative_residual']),1e-6)

    def test_isothermal_variable_depth_pool_lifts_from_head_not_thin_tail(self):
        m=self.model(stochastic=0);m.cold_depth[:,:5]=500;m.cold_content=m.cold_depth*3
        m.activity[:,:5]=.1  # existing episode, not an independent new parent
        m.step()
        self.assertGreater(float(m.gust_lift[:,4:7].max()),300)
        self.assertGreater(float(m.cold_depth[:,4:7].max()),100)

    def test_upper_westerlies_and_cloud_cell_direction_are_distinct_from_front_flow(self):
        m=self.model();u,v=m.winds();cu,cv=m.steering(u,v)
        self.assertGreater(float(u[11].mean()),40)
        self.assertGreater(float(cu.mean()),15)
        self.assertGreater(float(cu.mean()),abs(float(cv.mean())))
        # Cold reservoir is initially external, then enters with a genuinely
        # northerly low-level wind, independent of eastward cell steering.
        m.synoptic.front_lat.fill(24);air=m.synoptic.external_air()
        _,cold_v=m.synoptic.surface_target(air,0)
        self.assertLess(float(cold_v[air>.9].mean()),0)
        f=m.fields();self.assertGreater(float(np.nanmean(f['u300'])),35)

    def test_spring_cool_sea_caps_only_the_boundary_layer(self):
        cfg={'bounds':[112,22,113.5,24],'grid_km':10,'sst_c':20,'seed':610}
        shape=grid(cfg['bounds'],cfg['grid_km'])[0].shape
        land=Model(cfg,np.ones(shape));sea=Model(cfg,np.zeros(shape))
        self.assertLess(float(sea.temp[0].mean()),float(land.temp[0].mean())-3)
        self.assertLess(float(np.abs(sea.temp[9]-land.temp[9]).max()),.02)
        self.assertLess(float(sea.sb['cape'].mean()),float(land.sb['cape'].mean()))
        self.assertLess(float(sea.sb['cin'].mean()),float(land.sb['cin'].mean()))

    def test_stable_marine_entry_and_ridge_disrupt_regeneration_not_radar_pixels(self):
        m=self.model();y,x=np.indices(m.shape)
        m.donors=np.broadcast_to(np.arange(m.shape[0])[:,None]*m.shape[1],m.shape).copy()
        m.mu['cin'].fill(-300);m.mu['cin'][:,0]=-30;m.land[:,4:]=False
        flat,_=m.plume_environment(np.full(m.shape,500),np.full(m.shape,20),np.zeros(m.shape))
        # Charge the finite marine layer once, not an unlimited difference
        # in whole-column CIN plus a second copy of the same entry cost.
        self.assertLess(float(flat[:,4:].mean()),float(flat[:,1:4].mean())*.9)
        self.assertGreater(float(flat[:,4:].mean()),float(flat[:,1:4].mean())*.3)
        m.land[:]=True;m.h[:,4:8]=1800
        ridge,hazard=m.plume_environment(np.full(m.shape,500),np.full(m.shape,20),np.zeros(m.shape))
        self.assertLess(float(ridge[:,4].mean()),.9);self.assertGreater(float(hazard[:,4].mean()),.1)

    def test_surface_origin_does_not_instantly_become_elevated_over_stable_water(self):
        m=self.model();m.land[:]=False;m.sb['cape'].fill(0);m.sb['cin'].fill(-350);m.mu['cin'].fill(-30)
        m.activity.fill(.7);m.surface_activity.fill(0)
        elevated,_=m.plume_environment(np.full(m.shape,500),np.full(m.shape,25),np.zeros(m.shape))
        m.surface_activity=m.activity.copy()
        attached,hazard=m.plume_environment(np.full(m.shape,500),np.full(m.shape,25),np.zeros(m.shape))
        self.assertLess(float(attached.mean()),float(elevated.mean())*.9)
        self.assertGreater(float(hazard.mean()),.1)
        # Only the marine-layer part of CIN is a crossing cost. Increasing
        # whole-column CIN cannot keep increasing that finite boundary cost.
        m.sb['cin'].fill(-3500)
        capped,_=m.plume_environment(np.full(m.shape,500),np.full(m.shape,25),np.zeros(m.shape))
        np.testing.assert_allclose(capped,attached)

    def test_old_surface_plume_cannot_use_all_elevated_offshore_cape(self):
        m=self.model();m.sb['cape'].fill(0);m.mu['cape'].fill(2000)
        m.cape_capacity=np.minimum(2000,m.cape_ceiling)
        m.activity.fill(.8);m.surface_activity=m.activity*.75
        fed=np.full(m.shape,2000.)
        m.land[:]=True;np.testing.assert_allclose(m.plume_cape(fed),np.minimum(2000,m.cape_ceiling))
        m.land[:]=False;np.testing.assert_allclose(m.plume_cape(fed),np.minimum(500,m.cape_ceiling))
        m.surface_activity.fill(0);np.testing.assert_allclose(m.plume_cape(fed),np.minimum(2000,m.cape_ceiling))

    def test_shallow_gust_lift_does_not_reach_high_elevated_source(self):
        m=self.model();m.lift.fill(0)
        shallow=m.elevated_displacement(1500,np.full(m.shape,800),np.full(m.shape,250))
        deep=m.elevated_displacement(1500,np.full(m.shape,800),np.full(m.shape,1000))
        self.assertLess(float(shallow.max()),50)
        self.assertGreater(float(deep.min()),300)
        np.testing.assert_allclose(m.elevated_displacement(0,np.full(m.shape,800),np.full(m.shape,250)),800)

    def test_compact_volume_storage_preserves_physics_and_budget(self):
        m=self.model(compact_transport=True)
        self.assertEqual(m.q.dtype,np.float32)
        for _ in range(200):m.step()
        for key in ['q','cloud','rain','anvil','anvil_nx','anvil_ny','anvil_motion','stratiform_rain','plume_cloud','plume_rain','rain_area']:
            self.assertEqual(getattr(m,key).dtype,np.float32)
        self.assertLess(abs(m.audit_state()['water_relative_residual']),.002)
        self.assertGreater(float(m.total.max()),0)
        self.assertEqual(m.mu['cape'].dtype,np.float64)

    def test_surface_origin_remains_subset_of_cell_activity(self):
        m=self.model()
        for _ in range(100):m.step()
        self.assertGreaterEqual(float(m.surface_activity.min()),0)
        self.assertLessEqual(float(np.max(m.surface_activity-m.activity)),1e-8)

    def test_cell_noise_changes_but_is_seeded_and_not_a_radar_overlay(self):
        a,b=self.model(seed=615),self.model(seed=615);initial=a.cell_noise.copy()
        for _ in range(30):a.step();b.step()
        self.assertFalse(np.array_equal(initial,a.cell_noise))
        np.testing.assert_array_equal(a.cell_noise,b.cell_noise)
        np.testing.assert_array_equal(a.rain,b.rain)

    def test_daytime_heating_and_nocturnal_jet_are_separate_forcings(self):
        self.assertEqual(daylight(12*3600),0);self.assertGreater(daylight(6*3600),.8)
        m=self.model();m.time=20*3600;night=m.winds()[1][4].copy()
        m.time=8*3600;day=m.winds()[1][4]
        self.assertGreater(float((night-day).mean()),1)

    def test_limited_water_flux_preserves_sharp_cell_and_total_mass(self):
        x=np.arange(80);a=np.broadcast_to(np.exp(-((x-25)/3)**2),(10,80)).copy()
        u=np.full_like(a,15);v=np.zeros_like(a);limited=a.copy();donor=a.copy()
        for _ in range(30):
            limited=limited_transport(limited,u,v,20,1000)
            donor=transport(donor,u,v,20,1000)
        self.assertAlmostEqual(float(limited.sum()),float(a.sum()),places=8)
        self.assertGreaterEqual(float(limited.min()),-1e-12)
        exact=np.broadcast_to(np.exp(-((x-34)/3)**2),a.shape)
        self.assertLess(float(np.abs(limited-exact).mean()),float(np.abs(donor-exact).mean()))
        self.assertGreater(float(limited.max()),float(donor.max())*1.1)


if __name__=='__main__':unittest.main()
