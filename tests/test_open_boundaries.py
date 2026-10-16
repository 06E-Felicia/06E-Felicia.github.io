"""No full weather runs: directional ghost cells and geolocated DEM sampling."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from simulation.numerics import Advection
from simulation.run import terrain_for
from simulation.terrain import grid
from simulation.resolution_quality import overlap


class OpenBoundaryTests(unittest.TestCase):
    def test_outflow_does_not_use_external_heat_or_vapour_in_its_limiter(self):
        y,x=np.indices((8,15));base=290+x*.5+y*.2
        for axis in ('x','y'):
            for sign in (-1,1):
                u=np.full_like(base,sign*8 if axis=='x' else 0.)
                v=np.full_like(base,sign*8 if axis=='y' else 0.)
                a=base.copy();b=base.copy()
                edge=(slice(None),-1 if sign>0 else 0) if axis=='x' else (-1 if sign>0 else 0,slice(None))
                a[edge]-=80;b[edge]+=80
                op=Advection(u,v,12000)
                np.testing.assert_array_equal(op(base,60,boundary=a),op(base,60,boundary=b))

    def test_inflow_still_brings_real_water_supply(self):
        a=np.full((6,12),.006);u=np.full_like(a,10);v=np.zeros_like(a)
        result=Advection(u,v,12000)(a,60,boundary=.018)
        self.assertGreater(float(result[:,0].mean()),.006)
        np.testing.assert_allclose(result[:,-2:],a[:,-2:],atol=1e-15)

    def test_rain_pulse_leaves_without_boundary_reinjection(self):
        y,x=np.indices((6,20));a=np.exp(-((x-13)/2)**2)
        op=Advection(np.full_like(a,15.),np.zeros_like(a),1000)
        initial=a.sum()
        for _ in range(160):a=op(a,20,boundary=0,conservative=True)
        self.assertGreaterEqual(float(a.min()),-1e-12)
        self.assertLess(float(a.sum()),initial*1e-5)

    def test_dem_is_sampled_at_model_coordinates_not_stretched_to_endpoints(self):
        bounds=[110,22,114,25];lon,lat=grid(bounds,4)
        height=100+20*(lon-110)+30*(lat-22)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'dem.npz'
            np.savez(path,height=height,bounds=bounds,grid_km=4,source='controlled ramp',zoom=7)
            for km in (6,12,28):
                actual,_=terrain_for({'bounds':bounds,'grid_km':km},path)
                x,y=grid(bounds,km)
                expected=100+20*(np.clip(x,lon.min(),lon.max())-110)+30*(np.clip(y,lat.min(),lat.max())-22)
                np.testing.assert_allclose(actual,expected,atol=1e-10)

    def test_resolution_matching_preserves_constant_and_area_integral(self):
        x=np.arange(8,dtype=float);target=np.array([1.5,5.5])
        weights,coverage=overlap(x,target)
        np.testing.assert_allclose(weights@np.ones(8),1)
        np.testing.assert_allclose(coverage,1)
        np.testing.assert_allclose((weights@x).sum()*4,x.sum())


if __name__=='__main__':unittest.main()
