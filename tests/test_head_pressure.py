"""Pressure work per contacted parcel is distinct from head contact area."""
import unittest
import numpy as np
from simulation.core import Model,G
from simulation.sol import SolModel
from simulation.terrain import grid


class HeadPressureTests(unittest.TestCase):
    def model(self,edition='astra'):
        km=12 if edition=='astra' else 28
        cfg={'bounds':[112,22,114,24],'grid_km':km,'seed':13,'stochastic':0}
        return (Model if edition=='astra' else SolModel)(cfg,np.full(grid(cfg['bounds'],km)[0].shape,30),grid_limit=28)

    def test_contact_fraction_is_linear_not_squared_parcel_work(self):
        for edition in ['astra','sol']:
            m=self.model(edition)
            full=m.gust_activation(2400,800,1,.8,0,-20)
            self.assertGreater(float(full),.8)
            for contact in [.1,.25,.5,.75]:
                self.assertAlmostEqual(float(m.gust_activation(2400,800,contact,.8,0,-20)),float(full)*contact)

    def test_partially_occupied_head_can_overcome_real_cin(self):
        m=self.model();q=2400.;balance=.8;contact=.35;cin=-30.
        work=G*q/295*balance
        self.assertLess(work*contact**2,-cin,'old mixed-cell work wrongly fails')
        self.assertGreater(work,-cin)
        self.assertGreater(float(m.gust_activation(q,800,contact,balance,0,cin)),.2)

    def test_no_work_or_no_contact_never_initiates_and_elevated_barrier_remains(self):
        m=self.model()
        for args in [(0,800,1,1,0,0),(2400,800,0,1,0,-20),
                     (2400,800,.5,0,0,-20),(2400,800,.5,1,0,-200),
                     (2400,400,.5,1,2200,-20)]:
            self.assertEqual(float(m.gust_activation(*args)),0)
        # Work is bounded by the supplied cold content, with no energy floor.
        self.assertLess(float(m.gust_activation(10,100,.5,1,0,0)),.01)

    def test_pressure_diagnosis_does_not_change_cold_air_or_water(self):
        m=self.model();m.cold_depth.fill(500);m.cold_content.fill(1800)
        before=[a.copy() for a in [m.cold_depth,m.cold_content,m.q,m.cape_deficit]]
        m.gust_activation(m.cold_content,m.cold_depth,.4,.6,0,-20)
        for a,b in zip(before,[m.cold_depth,m.cold_content,m.q,m.cape_deficit]):np.testing.assert_array_equal(a,b)

    def test_shared_head_normal_is_not_each_rain_shaft_normal(self):
        m=self.model();y,x=np.indices(m.shape);centre=m.shape[1]//2
        m.cold_content=2000*(1-np.tanh((x-centre)/.7))*.5*(1+.4*np.cos(2*np.pi*y/3))
        m.cold_depth=m.cold_content/3
        before=m.cold_content.copy()
        from scipy.ndimage import gaussian_filter
        raw=gaussian_filter(before,.5);shared=m.cold_head_pressure()
        def obliqueness(q):
            dy,dx=np.gradient(q,m.dx)
            return np.abs(dy)/np.maximum(np.hypot(dx,dy),1e-9)
        # Same actual pressure, but a coherent warm-side boundary instead
        # of an artificial north/south normal between 1-grid-cell shafts.
        a=obliqueness(raw)[3:-3,centre-1:centre+1]
        b=obliqueness(shared)[3:-3,centre-1:centre+1]
        self.assertLess(float(b.mean()),float(a.mean())*.5)
        np.testing.assert_array_equal(m.cold_content,before)

    def test_shared_head_does_not_create_contact_ahead_of_the_cold_air(self):
        m=self.model();x=np.indices(m.shape)[1];centre=m.shape[1]//2
        m.cold_depth=np.where(x<centre,600.,0.);m.cold_content=3*m.cold_depth
        pressure=m.cold_head_pressure();dy,dx=np.gradient(pressure,m.dx)
        from scipy.ndimage import maximum_filter
        depth=maximum_filter(m.cold_depth,3)
        contact=m.convective_head_edge(np.hypot(dx,dy),depth)
        self.assertTrue(np.any(pressure[:,centre:]>0),'the diagnostic alone can sense a head ahead')
        np.testing.assert_array_equal(contact[:,centre:],0,'but no arrived cold volume means no lifting contact')
        np.testing.assert_array_equal(m.gust_activation(pressure,depth,contact,1,0,0)[:,centre:],0)

    def test_pressure_geometry_rotates_with_the_weather_not_the_map(self):
        m=self.model();y,x=np.indices(m.shape);m.cold_content=500*np.exp(-((x-5)**2/5+(y-7)**2/20))
        a=m.cold_head_pressure();m.cold_content=np.rot90(m.cold_content)
        np.testing.assert_allclose(m.cold_head_pressure(),np.rot90(a),atol=1e-10)

    def test_ambient_resistance_does_not_veto_lateral_cold_air_merging(self):
        a,b=self.model(),self.model();y,x=np.indices(a.shape)
        for m in [a,b]:
            m.syn_u.fill(0);m.syn_v.fill(0)
            m.cold_depth=600*np.exp(-((x-7)**2+(y-8)**2)/18)
            m.cold_content=3*m.cold_depth
            m.cold_mx=m.cold_depth*(x-7)*2;m.cold_my=m.cold_depth*(y-8)*2
        # Change only the overlying shear/steering direction. Cold material
        # does not get an extra 2.5x brake on a different compass flank;
        # subsequent shear/inflow gates still control new cloud production.
        a.steering=lambda u,v:(np.ones(a.shape)*20,np.zeros(a.shape))
        b.steering=lambda u,v:(np.zeros(b.shape),np.ones(b.shape)*20)
        a.cold_head_friction(90);b.cold_head_friction(90)
        np.testing.assert_allclose(a.cold_mx,b.cold_mx)
        np.testing.assert_allclose(a.cold_my,b.cold_my)
        np.testing.assert_array_equal(a.cold_content,b.cold_content)
        np.testing.assert_array_equal(a.q,b.q)

    def donor_head(self,edition='astra'):
        m=self.model(edition);x=m.shape[1]//2;y=m.shape[0]//2
        m.cold_depth[:,:x+1]=600;m.cold_content[:,:x+1]=1800
        m.cold_depth[:,x+1]=150;m.cold_content[:,x+1]=450
        m.mu['cape'].fill(3000);m.cape_capacity.fill(3000);m.cape_deficit.fill(0)
        return m,y,x

    def test_mature_two_cell_head_uses_nearest_real_warm_column(self):
        for edition in ['astra','sol']:
            m,y,x=self.donor_head(edition);one=np.ones(m.shape)
            q=m.q.copy();donors,feeding=m.warm_inflow(one,one*0,one,one)
            self.assertTrue(feeding[y,x]);self.assertEqual(donors[y,x],y*m.shape[1]+x+2)
            self.assertEqual(float(m.cold_depth.ravel()[donors[y,x]]),0)
            np.testing.assert_array_equal(m.q,q,'finding a donor does not supply synthetic moisture')
            m.cold_depth[:,x+1]=0;m.cold_content[:,x+1]=0
            donors,feeding=m.warm_inflow(one,one*0,one,one)
            self.assertEqual(donors[y,x],y*m.shape[1]+x+1,'always prefer the nearest valid donor')

    def test_oblique_shear_is_a_lifting_cost_not_a_veto_on_real_warm_air(self):
        for edition in ['astra','sol']:
            m,y,x=self.donor_head(edition);one=np.ones(m.shape);before=m.q.copy()
            donors,feeding=m.warm_inflow(one,one*0,one,one*0)
            self.assertTrue(feeding[y,x])
            self.assertEqual(donors[y,x],y*m.shape[1]+x+2)
            # Finding real supply never bypasses the separate pressure/CIN
            # calculation, creates rain, or consumes/duplicates its moisture.
            self.assertEqual(m.gust_activation(2400,800,1,0,0,-20),0)
            np.testing.assert_array_equal(m.q,before)
            np.testing.assert_array_equal(m.rain,0)
            np.testing.assert_array_equal(m.activity,0)

    def test_two_cell_lookup_cannot_jump_a_ridge_or_another_cold_peak(self):
        for barrier in ['ridge','pool']:
            m,y,x=self.donor_head();one=np.ones(m.shape)
            if barrier=='ridge':m.h[:,x+1]=900
            else:m.cold_depth[:,x+1]=900;m.cold_content[:,x+1]=2700
            donors,feeding=m.warm_inflow(one,one*0,one,one)
            self.assertFalse(feeding[y,x]);self.assertEqual(donors[y,x],y*m.shape[1]+x)

    def test_two_cell_lookup_does_not_borrow_beyond_the_finite_head(self):
        m,y,x=self.donor_head();one=np.ones(m.shape)
        m.cold_depth[:,x+2]=150;m.cold_content[:,x+2]=450
        donors,feeding=m.warm_inflow(one,one*0,one,one)
        self.assertFalse(feeding[y,x],'a warm column three cells away is not a donor')
        self.assertEqual(donors[y,x],y*m.shape[1]+x)

    def test_fine_grid_also_prefers_nearest_valid_donor_without_half_cell_rounding(self):
        for km in [4,6,8]:
            cfg={'bounds':[112,22,114,24],'grid_km':km,'seed':13,'stochastic':0}
            m=Model(cfg,np.full(grid(cfg['bounds'],km)[0].shape,30),grid_limit=28)
            y=m.shape[0]//2;x=m.shape[1]//2;one=np.ones(m.shape)
            m.cold_depth[:,:x+1]=500;m.cold_content[:,:x+1]=1500
            m.mu['cape'].fill(3000);m.cape_capacity.fill(3000)
            donors,feeding=m.warm_inflow(one,one*0,one,one)
            self.assertTrue(feeding[y,x]);self.assertEqual(donors[y,x],y*m.shape[1]+x+1)


if __name__=='__main__':unittest.main()
