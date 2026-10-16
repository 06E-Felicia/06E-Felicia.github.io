"""Actual condensate/area/phase budgets, not prescribed line intensities."""
import unittest
import numpy as np
from simulation.core import Model,DZ,LV,LF,CP,G
from simulation.thermo import saturation,saturation_ice
from simulation.terrain import grid


class ConvectiveIceTests(unittest.TestCase):
    def model(self,compact=False):
        c={'bounds':[112,22,113,24],'grid_km':12,'seed':13,'compact_transport':compact}
        return Model(c,np.full(grid(c['bounds'],12)[0].shape,30))

    def water(self,m):
        return float(((m.q+m.cloud+m.rain+m.anvil+m.graupel)*m.mass).sum(dtype='float64'))

    def test_mixed_phase_core_splits_actual_water_between_fast_ice_and_anvil(self):
        for compact in [False,True]:
            m=self.model(compact);m.temp[8]=263.15;m.q[:]=saturation_ice(m.temp,m.p)*.99
            m.cloud[8]=.0012;m.plume_cloud[8]=.0012;m.plume_cloud_area[8]=.00024
            before=self.water(m);fall=m.trailing_microphysics(60)
            self.assertGreater(float(m.graupel.max()),0);self.assertGreater(float(m.anvil.max()),0)
            self.assertLess(abs(self.water(m)+fall.sum()-before)/before,2e-7 if compact else 1e-12)
            self.assertTrue(np.all(m.graupel_area<=m.graupel+1e-10))
            self.assertTrue(np.all(m.plume_cloud_area<=m.plume_cloud+1e-10))

    def test_environmental_cloud_does_not_become_convective_graupel(self):
        m=self.model();m.temp[8]=263.15;m.q[:]=saturation_ice(m.temp,m.p)*.99;m.cloud[8]=.0012
        before=self.water(m);fall=m.trailing_microphysics(90)
        self.assertEqual(float(m.graupel.max()),0);self.assertGreater(float(m.anvil.max()),0)
        self.assertLess(abs(self.water(m)+fall.sum()-before)/before,1e-12)

    def test_fast_ice_melting_keeps_its_core_area_and_does_not_create_water(self):
        m=self.model();m.temp[:9]=280;m.q[:]=saturation(m.temp,m.p)
        m.graupel[6]=.002;m.graupel_area[6]=.0004
        before=self.water(m);temperature=m.temp.copy();fall=m.sediment_convective_ice(90)
        self.assertGreater(float(m.plume_rain.max()),0)
        np.testing.assert_allclose(m.rain_area,m.plume_rain*.2,atol=1e-12)
        self.assertLess(abs(self.water(m)+fall.sum()-before)/before,1e-12)
        self.assertTrue(np.all(m.temp<=temperature))
        self.assertEqual(float(m.stratiform_rain.max()),0,'core melt must not be relabelled as broad stratiform rain')

    def test_dense_core_ice_falls_faster_than_sparse_detrained_ice(self):
        m=self.model();m.graupel.fill(.001);m.graupel_area.fill(.0002);m.anvil.fill(.00005)
        self.assertTrue(np.all(m.graupel_fall_speed()>m.ice_fall_speed()))

    def test_evaporation_core_cannot_use_the_whole_cells_humidity_capacity(self):
        m=self.model();m.rain[:]=.02;m.plume_rain[:]=m.rain;m.rain_area[:]=m.rain*.02
        qs=saturation(m.temp,m.p)
        capacity=np.maximum(qs-m.q,0)/(1+LV*LV*qs/(CP*461.5*m.temp**2))
        before=self.water(m);loss=m.evaporate_rain(90)
        self.assertTrue(np.all(loss<=capacity*.02+1e-12))
        self.assertLess(abs(self.water(m)-before)/before,1e-12)

    def test_repeated_downdrafts_cannot_accumulate_unlimited_parcel_work(self):
        m=self.model();m.rain[2:9]=.001;m.downburst_energy.fill(1e9)
        evaporation=np.zeros_like(m.rain);evaporation[2:7]=.0001
        before_t=m.temp+LV/CP*evaporation;before_q=np.maximum(m.q-evaporation,0)
        qs=saturation(before_t,m.p)
        wet=np.maximum(qs-before_q,0)/(1+LV*LV*qs/(CP*461.5*before_t**2))
        potential=G*(wet*(LV/CP-.61*before_t)/np.maximum(before_t,200)+m.rain)*DZ[:,None,None]
        bound=potential[2:9].sum(axis=0)
        m.downdraft_momentum(evaporation,60)
        self.assertTrue(np.all(m.downburst_energy<=bound+1e-9))


if __name__=='__main__':unittest.main()
