"""Independent energy ledger and convective/environmental cloud provenance."""
import unittest
import numpy as np
from simulation.core import Model
from simulation.terrain import grid
from simulation.thermo import saturation_ice
from simulation.coldpool import advance


class EnergyCloudBudgetTests(unittest.TestCase):
    def model(self):
        c={'bounds':[112,22,113,23],'grid_km':12,'seed':13}
        return Model(c,np.full(grid(c['bounds'],12)[0].shape,30))

    def test_resolved_cape_loss_is_not_subtracted_twice(self):
        m=self.model();m.cape_capacity.fill(2000);m.cape_deficit.fill(1200)
        np.testing.assert_allclose(m.available_cape(np.full(m.shape,500)),500)
        np.testing.assert_allclose(m.available_cape(np.full(m.shape,2000)),800)
        m.cape_deficit.fill(2000);np.testing.assert_array_equal(m.available_cape(np.full(m.shape,3000)),0)
        m.recover_cape_budget(np.zeros(m.shape),np.zeros(m.shape));np.testing.assert_array_equal(m.cape_deficit,2000)

    def test_fresh_donor_and_receiver_budgets_are_not_multiplied(self):
        m=self.model();m.cape_capacity.fill(2000);m.mu['cape'].fill(2000);m.sb['cape'].fill(2000)
        m.cape_deficit.fill(2000);m.cape_deficit[:,0]=0;m.donors[:]=np.indices(m.shape)[0]*m.shape[1]
        np.testing.assert_allclose(m.plume_cape(np.full(m.shape,2000)),2000)
        m.cape_deficit[:,0]=2000;np.testing.assert_array_equal(m.plume_cape(np.full(m.shape,2000)),0)

    def test_environmental_ice_is_not_labelled_as_old_convective_cloud(self):
        m=self.model();m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p);m.cloud[9]=.001
        m.trailing_microphysics(90)
        self.assertGreater(float(m.anvil.max()),0);np.testing.assert_array_equal(m.anvil_convective,0)
        self.assertGreater(m.environmental_ice_source,0);self.assertEqual(m.convective_ice_source,0)

    def test_convective_label_is_a_carried_subset_not_extra_water(self):
        m=self.model();m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p)
        m.cloud[9]=.001;m.plume_cloud[9]=.001;m.plume_cloud_area[9]=.0002
        m.trailing_microphysics(90)
        self.assertGreater(float(m.anvil_convective.max()),0)
        for _ in range(10):m.step()
        self.assertTrue(np.all(m.anvil_convective>=-1e-12))
        self.assertTrue(np.all(m.anvil_convective<=m.anvil+1e-10))

    def test_multiple_cold_pool_tracers_share_one_mass_flux(self):
        y,x=np.indices((9,21));h=500*np.exp(-((x-8)/3)**2);q=h*3;zero=h*0
        out=advance(h,q,h*8,zero,zero,600,12000,tracer=np.stack([h*500,h*2000]),higher_order=True)
        np.testing.assert_allclose(out[4],out[0]*500,rtol=2e-12,atol=1e-8)
        np.testing.assert_allclose(out[5],out[4]*4,rtol=2e-12,atol=1e-8)

    def test_precipitating_ice_collects_existing_cloud_conservatively(self):
        m=self.model();m.temp[8]=258;m.cloud[8]=.001;m.plume_cloud[8]=.0005;m.plume_cloud_area[8]=.0001
        m.anvil[8]=.001;m.anvil_convective[8]=.0007;m.graupel[8]=.001;m.graupel_area[8]=.0002
        initial=float(((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass).sum())
        old_cloud=m.cloud.copy();old_ice=m.anvil.copy();old_graupel=m.graupel.copy()
        m.collect_precipitating_ice(90)
        after=float(((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass).sum())
        self.assertAlmostEqual(after,initial,places=8)
        self.assertTrue(np.any(m.cloud<old_cloud));self.assertTrue(np.any(m.anvil<old_ice));self.assertTrue(np.any(m.graupel>old_graupel))
        self.assertTrue(np.all(m.anvil_convective<=m.anvil+1e-12));self.assertTrue(np.all(m.graupel_area<=m.graupel))

    def test_dilution_changes_crystal_number_not_particle_size(self):
        m=self.model();m.anvil.fill(.0002)
        particle=4/3*np.pi*300*.00015**3;m.anvil_number[:]=m.anvil/particle
        radius=m.ice_radius().copy();speed=m.ice_fall_speed().copy()
        m.anvil/=1000;m.anvil_number/=1000
        np.testing.assert_allclose(m.ice_radius(),radius,rtol=1e-12)
        np.testing.assert_allclose(m.ice_fall_speed(),speed,rtol=1e-7)

    def test_deposition_grows_crystals_without_creating_new_particle_number(self):
        m=self.model();m.temp[9]=250;m.q[:]=saturation_ice(m.temp,m.p);m.q[9]*=1.3
        m.anvil[9]=.0002;particle=4/3*np.pi*300*.00015**3;m.anvil_number[:]=m.anvil/particle
        number=float((m.anvil_number*m.mass).sum());radius=float(m.ice_radius()[9].mean())
        before=float(((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass).sum())
        fallen=m.trailing_microphysics(90)
        after=float(((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass).sum()+fallen.sum())
        self.assertLess(float((m.anvil_number*m.mass).sum()),number)
        self.assertGreater(float(m.ice_radius()[9].mean()),radius)
        self.assertAlmostEqual(before,after,places=8)

    def test_sublimated_crystals_retire_at_existing_minimum_radius_without_losing_water(self):
        m=self.model();m.anvil.fill(1e-25);m.anvil_number.fill(.01)
        before=m.anvil.copy();m.limit_ice_number()
        np.testing.assert_array_equal(m.anvil,before)
        np.testing.assert_allclose(m.ice_radius(),1e-6,rtol=1e-12)
        np.testing.assert_allclose(m.anvil_number,m.anvil/(4/3*np.pi*300*1e-18),rtol=1e-12)
        m.anvil.fill(0);m.limit_ice_number();np.testing.assert_array_equal(m.anvil_number,0)

    def test_subnormal_ice_does_not_overflow_number_or_moment_transport(self):
        m=self.model();m.anvil.fill(1e-320);m.anvil_number.fill(1e-4)
        m.anvil_nx[:]=m.anvil*.8;m.anvil_motion[:]=m.anvil*20
        with np.errstate(over='raise',invalid='raise'):
            for _ in range(5):m.step()
        for key in ['anvil','anvil_number','anvil_nx','anvil_motion']:
            self.assertTrue(np.isfinite(getattr(m,key)).all())


if __name__=='__main__':unittest.main()
