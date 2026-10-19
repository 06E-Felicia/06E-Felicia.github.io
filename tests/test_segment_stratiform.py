"""Real segmented heads and ice export, not painted radar connections."""
import unittest
import numpy as np
from unittest.mock import patch
from simulation.core import Model
from simulation.terrain import grid
from simulation.thermo import saturation


class SegmentStratiformTests(unittest.TestCase):
    def model(self):
        c={'bounds':[110,21,115,26],'grid_km':12,'seed':13,'stochastic':1}
        return Model(c,np.full(grid(c['bounds'],12)[0].shape,30))

    def test_cluster_process_keeps_small_segments_not_a_broad_lobe(self):
        m=self.model();y,x=np.indices(m.shape)
        m.cell_noise=np.cos(y*2*np.pi/8)+2*np.cos(y*2*np.pi/60)
        raw=m.cell_noise.copy();f=m.cell_variability()
        column=np.log(f[:,m.shape[1]//2]);short=np.cos(np.arange(m.shape[0])*2*np.pi/8)
        long=np.cos(np.arange(m.shape[0])*2*np.pi/60)
        self.assertGreater(abs(np.dot(column-column.mean(),short)),abs(np.dot(column-column.mean(),long)))
        self.assertAlmostEqual(float(f.mean()),1)
        np.testing.assert_array_equal(m.cell_noise,raw)

    def test_segmented_heads_in_one_real_pool_close_rear_mother_forcing(self):
        m=self.model();m.synoptic.genesis_half_length=150000
        mature=np.zeros(m.shape,dtype=bool);mature[5:33,18]=np.arange(5,33)%3!=0
        m.cold_depth[4:34,16:20]=600;m.cold_content=3*m.cold_depth;m.cold_diagnostics()
        self.assertTrue(m.mature_genesis_line(mature))
        # A cold-pool connection does not paint rain in the head gaps.
        np.testing.assert_array_equal(m.rain,0)
        np.testing.assert_array_equal(m.activity,0)

    def test_unconnected_or_sparse_short_bows_cannot_close_the_mother(self):
        m=self.model();m.synoptic.genesis_half_length=150000
        mature=np.zeros(m.shape,dtype=bool);mature[5:33,18]=np.arange(5,33)%3!=0
        m.cold_depth[mature]=600;m.cold_content=3*m.cold_depth;m.cold_diagnostics()
        self.assertFalse(m.mature_genesis_line(mature))
        m.cold_depth[4:34,16:20]=600;m.cold_content=3*m.cold_depth;m.cold_diagnostics()
        mature[:]=False;mature[5:33:5,18]=True
        self.assertFalse(m.mature_genesis_line(mature))

    def test_wider_footprint_does_not_anchor_the_origin_after_a_mature_line(self):
        m=self.model();m.synoptic.genesis_half_length=240000
        mature=np.zeros(m.shape,dtype=bool);mature[5:30,18]=np.arange(5,30)%3!=0
        m.cold_depth[4:31,16:20]=600;m.cold_content=3*m.cold_depth;m.cold_diagnostics()
        self.assertTrue(m.mature_genesis_line(mature))

    def test_very_cold_anvil_does_not_aggregate_as_fast_as_dendritic_snow(self):
        a,b=self.model(),self.model()
        for m,t in [(a,238.15),(b,258.15)]:
            m.temp.fill(t);m.anvil.fill(.0002)
            m.anvil_number.fill(.0002/(4/3*np.pi*300*.00015**3))
        before=a.anvil.copy();n=a.anvil_number.copy()
        for _ in range(20):a.aggregate_ice_number(90);b.aggregate_ice_number(90)
        self.assertGreater(float(a.anvil_number.mean()),float(b.anvil_number.mean())*1.5)
        self.assertTrue(np.all(a.anvil_number<=n))
        np.testing.assert_array_equal(a.anvil,before)
        np.testing.assert_array_equal(b.anvil,before)

    def test_new_unrimed_ice_is_not_instantly_aggregated_into_fast_graupel(self):
        m=self.model();m.temp.fill(235);m.plume_cloud.fill(.0005);m.plume_cloud_area.fill(.0001)
        detrain=m.plume_cloud*.5;before=detrain.copy()
        converted=m.convective_ice(90,detrain,np.ones_like(detrain))
        self.assertLess(float(converted.sum()/detrain.sum()),.03)
        np.testing.assert_array_equal(detrain,before)
        np.testing.assert_allclose(m.graupel,converted)

    def test_shared_orientation_retains_narrow_contact_and_rotates(self):
        m=self.model();y,x=np.indices(m.shape);cx=m.shape[1]//2
        m.cold_content=2000*(1-np.tanh((x-cx)/.7))*.5*(1+.4*np.cos(2*np.pi*y/4))
        pressure=m.cold_head_pressure();before=m.cold_content.copy()
        gy,gx=np.gradient(pressure,m.dx);raw_y=-gy/np.maximum(np.hypot(gx,gy),1e-10)
        nx,ny=m.cold_head_normal(pressure);middle=np.s_[4:-4,cx-1:cx+1]
        self.assertLess(float(np.abs(ny[middle]).mean()),float(np.abs(raw_y[middle]).mean()))
        rx,ry=m.cold_head_normal(np.rot90(pressure))
        arrived=np.rot90(np.hypot(gx,gy)>1e-5)
        np.testing.assert_allclose(rx[arrived],np.rot90(ny)[arrived],atol=1e-10)
        np.testing.assert_allclose(ry[arrived],-np.rot90(nx)[arrived],atol=1e-10)
        np.testing.assert_array_equal(m.cold_content,before)

    def test_rear_export_is_finite_and_does_not_change_cold_air_or_water(self):
        m=self.model();m.mu['cape'].fill(3000);m.cape_capacity.fill(3000);m.cape_deficit.fill(0)
        before=[a.copy() for a in [m.q,m.anvil,m.cold_depth,m.cold_content]]
        u,v=m.winds();nx,ny,target=m.outflow_origin(u,v);cu,cv=m.storm_motion(u,v)
        relative=cu*nx+cv*ny-target;mask=np.hypot(nx,ny)>.9
        np.testing.assert_allclose(relative[mask],np.sqrt(6000)*.45,atol=1e-5)
        self.assertLessEqual(float(relative.max()),35.00001)
        for a,b in zip(before,[m.q,m.anvil,m.cold_depth,m.cold_content]):np.testing.assert_array_equal(a,b)

    def test_mature_donor_fed_plume_keeps_rear_export_over_an_exhausted_receiver(self):
        m=self.model();m.mu['cape'].fill(0);m.mu['cape'][:,0]=3000
        m.cape_capacity.fill(3000);m.cape_deficit.fill(3000);m.cape_deficit[:,0]=0
        m.donors[:]=np.indices(m.shape)[0]*m.shape[1]
        u,v=m.winds();nx,ny,target=m.outflow_origin(u,v);cu,cv=m.storm_motion(u,v)
        np.testing.assert_allclose(cu*nx+cv*ny-target,np.sqrt(6000)*.45,atol=1e-5)
        m.cape_deficit[:,0]=3000
        _,_,exhausted=m.outflow_origin(u,v)
        np.testing.assert_allclose(cu*nx+cv*ny-exhausted,0,atol=1e-6)

    def test_pattern_slowdown_does_not_reverse_the_initial_rear_export_normal(self):
        m=self.model();u=np.full_like(m.mass,30.);v=u*0;u[4]=24
        m.steering=lambda u,v:(np.ones(m.shape)*30,np.zeros(m.shape))
        m.storm_motion=lambda u,v:(np.ones(m.shape)*21,np.zeros(m.shape))
        nx,ny,_=m.outflow_origin(u,v)
        np.testing.assert_allclose(nx,1,atol=1e-10)
        np.testing.assert_allclose(ny,0,atol=1e-10)

    def test_curved_southern_pressure_flank_cannot_turn_ice_export_along_the_line(self):
        m=self.model();y,x=np.indices(m.shape)
        m.activity.fill(.7);m.organization.fill(.5)
        m.cold_depth[:]=800
        m.cold_content=2400*np.exp(-((y-y.mean())**2+(x-x.mean())**2)/30)
        u=np.full_like(m.mass,30.);v=u*0;u[4]=10
        m.steering=lambda u,v:(np.full(m.shape,30.),np.zeros(m.shape))
        m.storm_motion=lambda u,v:(np.full(m.shape,21.),np.zeros(m.shape))
        m.mu['cape'].fill(3000);m.cape_capacity.fill(3000);m.cape_deficit.fill(0)
        before=[a.copy() for a in [m.cold_content,m.cold_depth,m.q,m.anvil]]
        nx,ny,target=m.outflow_origin(u,v)
        np.testing.assert_allclose(nx,1);np.testing.assert_allclose(ny,0)
        self.assertTrue(np.all(target<0),'energetic ice export may spread west even on a curved southern flank')
        for a,b in zip(before,[m.cold_content,m.cold_depth,m.q,m.anvil]):np.testing.assert_array_equal(a,b)

    def test_rear_circulation_rotates_with_shear_and_no_shear_does_not_invent_west(self):
        m=self.model();u=np.full_like(m.mass,30.);v=u*0;u[4]=10
        m.steering=lambda u,v:(np.full(m.shape,30.),np.zeros(m.shape))
        m.storm_motion=lambda u,v:(np.full(m.shape,21.),np.zeros(m.shape))
        nx,ny,target=m.outflow_origin(u,v)
        m.steering=lambda u,v:(np.zeros(m.shape),np.full(m.shape,30.))
        m.storm_motion=lambda u,v:(np.zeros(m.shape),np.full(m.shape,21.))
        rx,ry,rotated=m.outflow_origin(v,u)
        np.testing.assert_allclose(rx,-ny);np.testing.assert_allclose(ry,nx)
        np.testing.assert_allclose(target,rotated)
        m.steering=lambda u,v:(u[4],v[4])
        x,y,t=m.outflow_origin(u,v)
        np.testing.assert_array_equal(x,0);np.testing.assert_array_equal(y,0)

    def test_moist_middle_layer_is_initial_finite_water_not_a_permanent_rain_source(self):
        with patch.object(Model,'MIDLEVEL_HUMIDITY_BOOST',0):dry=self.model()
        moist=self.model()
        self.assertTrue(np.all(moist.q>=dry.q-1e-12))
        self.assertGreater(float(moist.q[8].mean()),float(dry.q[8].mean()))
        self.assertLessEqual(float(np.max(moist.q/saturation(moist.temp,moist.p))),.980001)
        self.assertAlmostEqual(moist.initial_water,float((moist.q*moist.mass).sum()),places=7)
        self.assertEqual(moist.audit_state()['water_relative_residual'],0)
        for field in ['rain','cloud','anvil','cold_content','total']:
            np.testing.assert_array_equal(getattr(moist,field),0)


if __name__=='__main__':unittest.main()
