"""Material front thermodynamics, trigger work and non-striped CAPE."""
import unittest
import numpy as np
from simulation.core import Model
from simulation.numerics import Advection
from simulation.terrain import grid


class AirMassTriggerTests(unittest.TestCase):
    def model(self):
        cfg={'seed':20260423,'bounds':[112,22,113,23],'grid_km':12}
        return Model(cfg,np.full(grid(cfg['bounds'],12)[0].shape,30.))

    def test_cape_does_not_clip_to_geographical_row(self):
        m=self.model();raw=np.linspace(1200,4500,m.lon.size).reshape(m.shape)
        m.cape_capacity[:]=5000;m.cape_deficit.fill(0)
        np.testing.assert_allclose(m.available_cape(raw),raw)
        self.assertTrue(np.any(m.available_cape(raw)>m.cape_ceiling))
        # A real exhausted air-mass budget still wins over a large raw CAPE.
        m.cape_deficit.fill(5000);np.testing.assert_array_equal(m.available_cape(raw),0)

    def test_random_variability_cannot_lift_unforced_air(self):
        m=self.model();m.cell_noise.fill(2)
        for ascent in [0,-.1]:
            m.background_w.fill(ascent)
            np.testing.assert_array_equal(m.trigger_perturbation(np.zeros(m.shape)),0)
        m.background_w.fill(.08)
        self.assertGreater(float(m.trigger_perturbation(np.zeros(m.shape)).min()),0)
        m.background_w.fill(0)
        self.assertGreater(float(m.trigger_perturbation(np.full(m.shape,500)).min()),0)

    def test_unchanged_material_front_does_not_reset_processed_air(self):
        m=self.model();m.air.fill(.7);m.temp[:2]-=2;m.q[:3]*=.7
        t=m.temp.copy();q=m.q.copy();layers=m.frontal_layers()
        zero=np.zeros_like(m.q)
        m.transport_front_thermodynamics(layers,layers,Advection(zero,zero,m.dx),90)
        np.testing.assert_array_equal(m.temp,t);np.testing.assert_array_equal(m.q,q)
        self.assertEqual(m.frontal_exchange_water,0)

    def test_cold_air_entry_changes_actual_sounding_not_only_tracer(self):
        m=self.model();old=m.frontal_layers();before=float(m.mu['cape'].mean())
        m.air.fill(.999999)
        zero=np.zeros_like(m.q)
        m.transport_front_thermodynamics(old,m.frontal_layers(),Advection(zero,zero,m.dx),90)
        m.diagnostics()
        self.assertLess(float(m.mu['cape'].mean()),before*.15)
        self.assertLess(m.frontal_exchange_water,0)
        self.assertLess(abs(m.audit_state()['water_relative_residual']),1e-7)

    def test_unorganized_mass_flux_is_small_but_organized_head_retained(self):
        m=self.model();m.activity.fill(1);one=np.ones(m.shape)
        m.organization.fill(0);a=m.plume_coverage(one,one,one)
        m.organization.fill(.7);b=m.plume_coverage(one,one,one)
        self.assertLessEqual(float(a.max()),.02)
        self.assertGreater(float(b.min()),.5)

    def test_source_free_strong_pool_recovers_without_erasing_energy_debt(self):
        m=self.model();m.cold_depth.fill(600);m.cold_content.fill(2400)
        m.cold_mx[:]=600*m.syn_u;m.cold_my[:]=600*m.syn_v
        m.cold_diagnostics();m.cape_deficit.fill(800)
        initial=float(m.cold_content.sum())
        for _ in range(160):m.recover_cold_pool(90,np.zeros(m.shape),0)
        self.assertLess(float(m.cold.max()),.5)
        self.assertAlmostEqual(float(m.cold_content.sum())+m.cold_recovery,initial,places=6)
        np.testing.assert_array_equal(m.cape_deficit,800)

    def test_ten_vs_sixty_minute_output_cannot_lose_integrated_rain(self):
        a,b=self.model(),self.model()
        for m,interval in [(a,600),(b,3600)]:
            for target in range(interval,4*3600+1,interval):
                while m.time<target-1e-6:m.step(target)
                m.fields(include_mixed=False);m.surface_rain.fields()
        self.assertEqual(a.steps,b.steps)
        for name in ['q','temp','activity','total']:
            np.testing.assert_array_equal(getattr(a,name),getattr(b,name))
        np.testing.assert_array_equal(a.surface_rain.total,b.surface_rain.total)

    def test_deep_postfrontal_air_does_not_reignite_during_six_hour_heating(self):
        m=self.model();warm=float(m.mu['cape'].mean());old=m.frontal_layers();m.air.fill(1)
        zero=np.zeros_like(m.q)
        m.transport_front_thermodynamics(old,m.frontal_layers(),Advection(zero,zero,m.dx),90)
        m.synoptic.front_lat.fill(19)
        m.syn_u,m.syn_v=m.synoptic.surface_target(m.air,0);m.u=m.syn_u.copy();m.v=m.syn_v.copy();m.diagnostics()
        peak=0
        while m.time<21600-1e-6:
            m.step(21600);peak=max(peak,float(m.initiation.max()))
        fields=m.fields(include_mixed=False)
        self.assertEqual(peak,0)
        self.assertLess(float(fields['mucape'].mean()),warm*.1)
        self.assertLess(float(fields['mucape'].max()),warm*.2)
        self.assertLess(abs(m.audit_state()['water_relative_residual']),1e-7)


if __name__=='__main__':unittest.main()
