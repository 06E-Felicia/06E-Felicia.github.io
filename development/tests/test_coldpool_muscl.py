"""High-order head transport: sharpness, balance, positivity and budgets."""
import unittest
import numpy as np
from scipy.ndimage import binary_dilation
from simulation.coldpool import advance
from simulation.validate import band_geometry


class ColdpoolHeadTests(unittest.TestCase):
    def test_muscl_transports_processed_air_more_sharply_without_changing_budget(self):
        y,x=np.mgrid[:80,:140];h=np.full(x.shape,500.);q=h*3;mx=h*10;zero=h*0
        tracer=h*np.exp(-((x-40)/5)**2);errors=[]
        for order in [False,True]:
            a,b,c,d,e=[f.copy() for f in [h,q,mx,zero,tracer]];external=0
            for _ in range(80):
                a,b,c,d,e,flow,cfl=advance(a,b,c,d,zero,30,2000,tracer=e,higher_order=order);external+=flow
            actual=e[40]/a[40];truth=np.exp(-((np.arange(140)-52)/5)**2)
            errors.append(float(abs(actual-truth).mean()))
            self.assertLess(abs(b.sum()-q.sum()-external)/q.sum(),1e-12)
            self.assertGreaterEqual(float(min(a.min(),b.min(),e.min())),0)
            self.assertLessEqual(cfl,.4000000001)
        self.assertLess(errors[1],errors[0]*.4)

    def test_muscl_keeps_hydrostatic_terrain_at_rest(self):
        y,x=np.mgrid[:30,:40];bed=100+70*np.sin(x/4)*np.cos(y/4);h=600-bed
        a,b,c,d,external,cfl=advance(h,h*3,h*0,h*0,bed,30,2000,higher_order=True)
        np.testing.assert_allclose(a[4:-4,4:-4],h[4:-4,4:-4],atol=1e-10)
        np.testing.assert_allclose(c[4:-4,4:-4],0,atol=1e-10)
        np.testing.assert_allclose(d[4:-4,4:-4],0,atol=1e-10)

    def test_muscl_dry_domain_cannot_invent_water_on_a_ridge(self):
        y,x=np.mgrid[:20,:30];bed=500+200*np.sin(x/2);zero=bed*0
        result=advance(zero,zero,zero,zero,bed,1200,2000,higher_order=True)
        for f in result[:4]:np.testing.assert_array_equal(f,zero)

    def test_curved_band_metric_distinguishes_a_bow_from_a_filled_blob(self):
        y,x=np.mgrid[:100,:100];r=np.hypot(x-45,y-50)
        bow=(abs(r-30)<1.5)&(x>=45);blob=r<20
        def thinness(mask):
            length=band_geometry(binary_dilation(mask),12)
            return length**2/(mask.sum()*12**2)
        self.assertGreater(thinness(bow),4)
        self.assertLess(thinness(blob),4)


if __name__=='__main__':unittest.main()
