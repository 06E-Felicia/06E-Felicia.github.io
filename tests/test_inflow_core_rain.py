"""Vector inflow and finite moist-source capture, not latitude/rain masks."""
import unittest
import numpy as np
from simulation.core import Model,DZ
from simulation.sol import SolModel
from simulation.terrain import grid


class InflowCoreRainTests(unittest.TestCase):
    def model(self,edition='astra'):
        km=12 if edition=='astra' else 28
        cfg={'seed':20261017,'bounds':[111,22,114,25],'grid_km':km,'stochastic':0}
        return (Model if edition=='astra' else SolModel)(cfg,np.full(grid(cfg['bounds'],km)[0].shape,30),grid_limit=28)

    def test_expanding_north_flank_has_no_inflow_if_source_jet_overtakes_it(self):
        for edition in ['astra','sol']:
            m=self.model(edition);u=np.full_like(m.q,5.);v=np.full_like(m.q,12.)
            one=np.ones(m.shape);zero=one*0
            before=m.q.copy()
            # Material spreads north at 25, but the system translates north
            # only at 3 while its warm source layer flows north at 12.
            flux=m.head_inflow(one*18,one*3,one*20,one*25,u,v,zero,one)
            np.testing.assert_array_equal(flux,0)
            np.testing.assert_array_equal(m.head_inflow(one*18,one*12,one*20,one*25,u,v,zero,one),0)
            np.testing.assert_array_equal(m.q,before)
            # The same source supplies the actual eastward leading head.
            forward=m.head_inflow(one*18,one*3,one*20,one*25,u,v,one,zero)
            np.testing.assert_allclose(forward,15)

    def test_slow_surface_wind_cannot_impersonate_deep_warm_inflow(self):
        m=self.model();u=np.full_like(m.q,5.);v=np.full_like(m.q,12.);v[0]=0
        one=np.ones(m.shape);zero=one*0
        _,layer_v,depth=m.source_inflow_layer(u,v)
        self.assertGreater(float(layer_v.min()),3)
        self.assertGreater(float(depth.min()),500)
        np.testing.assert_array_equal(m.head_inflow(one*18,one*3,one*20,one*25,u,v,zero,one),0)

    def test_inflow_direction_is_rotation_invariant(self):
        m=self.model();u=np.full_like(m.q,5.);v=np.full_like(m.q,12.);one=np.ones(m.shape)
        theta=.63;c=np.cos(theta);s=np.sin(theta)
        def rotated(x,y):return c*x-s*y,s*x+c*y
        for nx,ny in [(1,0),(0,1),(-.6,.8)]:
            base=m.head_inflow(one*18,one*3,one*20,one*25,u,v,one*nx,one*ny)
            a,b=rotated(one*18,one*3);p,q=rotated(one*20,one*25)
            ru,rv=rotated(u,v);rx,ry=rotated(one*nx,one*ny)
            np.testing.assert_allclose(m.head_inflow(a,b,p,q,ru,rv,rx,ry),base,atol=3e-6)

    def test_source_capture_increases_real_air_flux_without_inventing_supply(self):
        for edition in ['astra','sol']:
            m=self.model(edition);m.organization.fill(.6);m.activity.fill(.01)
            zero=np.zeros(m.shape);one=zero+1
            shallow=m.organized_coverage(zero,25,20,200,one,one,one,one)
            layer=m.organized_coverage(zero,25,20,200,one,one,one,one,supply_depth=1000)
            self.assertGreater(float(layer.min()),float(shallow.max())*4)
            self.assertTrue(np.all(layer*25<=20*1000/m.dx+1e-9))
            self.assertTrue(np.all(layer<=.55))
            for feeding,inflow in [(zero,20),(one,0)]:
                np.testing.assert_array_equal(m.organized_coverage(zero,25,inflow,200,one,one,one,feeding,supply_depth=1000),0)


if __name__=='__main__':unittest.main()
