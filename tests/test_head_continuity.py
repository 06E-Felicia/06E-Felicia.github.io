"""Head coherence follows actual cold-air flux; no echo bridges or new air."""
import unittest
import numpy as np
from simulation.core import Model
from simulation.sol import SolModel
from simulation.terrain import grid
from simulation.coldpool import advance


class HeadContinuityTests(unittest.TestCase):
    def model(self,edition='astra'):
        km=12 if edition=='astra' else 28
        cfg={'seed':20261017,'grid_km':km,'bounds':[109,21,116,25.5],'stochastic':0}
        return (Model if edition=='astra' else SolModel)(cfg,np.full(grid(cfg['bounds'],km)[0].shape,30.),grid_limit=28)

    def test_organization_uses_identical_density_current_flux_on_both_editions(self):
        for edition in ['astra','sol']:
            m=self.model(edition);y,x=np.indices(m.shape)
            m.cold_depth=500*np.exp(-((x-m.shape[1]*.4)/3)**2-((y-m.shape[0]*.5)/5)**2)
            m.cold_content=4*m.cold_depth
            m.cold_mx=18*m.cold_depth;m.cold_my=5*m.cold_depth
            m.organization=.7*np.exp(-((x-m.shape[1]*.4)/4)**2)
            initial=m.organization.copy();water=m.q.copy();cold=float(m.cold_content.sum())
            expected=advance(m.cold_depth,m.cold_content,m.cold_mx,m.cold_my,m.h,90,m.dx,
                             tracer=m.cold_depth*initial,higher_order=True)
            m.transport_cold_pool(90)
            np.testing.assert_allclose(m.organization,np.clip(expected[4]/np.maximum(expected[0],1e-9),0,1),atol=1e-10)
            self.assertAlmostEqual(float(m.cold_content.sum()),cold+m.cold_external,places=7)
            np.testing.assert_array_equal(m.q,water)
            self.assertTrue(np.all((m.organization>=0)&(m.organization<=.7+1e-9)))

    def test_uniform_head_memory_survives_translation_without_surface_wind_drag(self):
        m=self.model();m.cold_depth.fill(600);m.cold_content.fill(2400)
        m.cold_mx=m.cold_depth*20;m.cold_my=m.cold_depth*6;m.organization.fill(.6)
        m.u.fill(-15);m.v.fill(-10)
        m.transport_cold_pool(90)
        np.testing.assert_allclose(m.organization,.6,atol=1e-12)
        before=m.organization.copy()
        m.evolve_head_organization(90,before,600,20,1)
        np.testing.assert_array_equal(m.organization,before)

    def test_no_cold_air_cannot_transport_or_invent_head_organization(self):
        m=self.model();m.organization.fill(.8);m.transport_cold_pool(90)
        np.testing.assert_array_equal(m.organization,0)

    def test_memory_alone_does_not_create_rain_or_bypass_missing_inflow(self):
        for edition in ['astra','sol']:
            m=self.model(edition);m.organization.fill(.8)
            zero=np.zeros(m.shape);one=zero+1
            np.testing.assert_array_equal(m.organized_coverage(zero,20,0,800,one,one,one,one,supply_depth=1000),0)
            np.testing.assert_array_equal(m.organized_coverage(zero,20,15,800,one,one,one,zero,supply_depth=1000),0)
            m.evolve_head_organization(900,zero,800,20,one)
            self.assertTrue(np.all(m.organization<.8))
            np.testing.assert_array_equal(m.total,0)


if __name__=='__main__':unittest.main()
