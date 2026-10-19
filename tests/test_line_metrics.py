"""Distinguish a whole-line bow from embedded bends without filling echoes."""
import unittest
import numpy as np
from simulation.line_metrics import morphology


class LineMetricTests(unittest.TestCase):
    def fields(self,front):
        y,x=np.indices((100,120));echo=np.where(abs(x-front[:,None])<2,45.,0.)
        activity=(echo>0)*.5;air=activity*0
        cold=np.where((x<front[:,None])&(x>front[:,None]-15),2.,0.)
        return echo,activity,air,cold,cold*250

    def test_large_arc_has_more_broad_departure_than_small_embedded_bows(self):
        y=np.arange(100)
        broad=morphology(*self.fields(55+18*np.sin(y*np.pi/100)),4)
        local=morphology(*self.fields(55+3*np.sin(y*np.pi/12)),4)
        self.assertGreater(broad['broad_front_rms_km'],local['broad_front_rms_km']*4)
        self.assertLess(np.median(local['embedded_bow_half_prominence_widths_km']),70)

    def test_straight_north_south_front_has_no_artificial_bow(self):
        m=morphology(*self.fields(np.full(100,55)),4)
        self.assertLess(abs(m['tilt_from_north_deg']),1e-8)
        self.assertLess(m['front_rms_departure_km'],1e-8)
        self.assertEqual(m['embedded_bow_half_prominence_widths_km'],[])

    def test_cold_area_uses_real_temperature_depth_and_matching_pool(self):
        arrays=self.fields(np.full(100,55));before=[a.copy() for a in arrays]
        m=morphology(*arrays,4)
        self.assertEqual(m['all_cold_area_km2'],int(((arrays[3]>.5)&(arrays[4]>100)).sum())*16)
        for a,b in zip(arrays,before):np.testing.assert_array_equal(a,b)
        arrays=list(arrays);arrays[4]=np.zeros_like(arrays[4])
        self.assertEqual(morphology(*arrays,4)['matched_cold_area_km2'],0)

    def test_detached_southern_echo_is_counted_only_in_same_actual_cold_pool(self):
        y,x=np.indices((60,80));echo=np.zeros_like(x,dtype=float)
        echo[24:55,40:43]=50;echo[10:18,40:43]=45
        activity=(echo>0)*.5;air=activity*0
        cold=np.where((x>=30)&(x<=42)&(y>=10)&(y<55),2.,0.)
        before=echo.copy();m=morphology(echo,activity,air,cold,cold*300,4)
        self.assertEqual(m['same_pool_southern_fragments'],1)
        self.assertEqual(m['same_pool_southern_fragment_cells'],24)
        np.testing.assert_array_equal(echo,before)
        cold[18:24]=0
        self.assertEqual(morphology(echo,activity,air,cold,cold*300,4)['same_pool_southern_fragments'],0)

    def test_northern_strength_is_reported_separately_not_hidden_in_one_average(self):
        arrays=list(self.fields(np.full(100,55)))
        arrays[0][50:]=np.where(arrays[0][50:]>0,55,0)
        m=morphology(*arrays,4)
        self.assertGreater(m['north_half_50dbz_area_km2'],0)
        self.assertEqual(m['south_half_50dbz_area_km2'],0)

    def test_south_band_axis_distinguishes_a_zonal_tail_from_a_long_vertical_band(self):
        vertical=morphology(*self.fields(np.full(100,55)),4)
        self.assertLess(abs(vertical['south_band_axis_from_north_deg']),1)
        arrays=list(self.fields(np.full(100,55)))
        arrays[0][:50]=0;arrays[0][40:50,10:55]=45
        arrays[1]=(arrays[0]>0)*.5
        zonal=morphology(*arrays,4)
        self.assertGreater(abs(zonal['south_band_axis_from_north_deg']),55)
        self.assertGreater(zonal['south_band_ew_span_km'],zonal['south_band_ns_span_km'])

    def test_southern_rear_ice_and_weak_echo_are_not_the_thermal_cold_pool(self):
        arrays=list(self.fields(np.full(100,55)))
        arrays[0][:50,20:52]=25
        ice=np.zeros_like(arrays[0]);ice[:50,20:52]=.5
        rain=np.zeros_like(ice);rain[:50,20:52]=2.
        m=morphology(*arrays,4,anvil_column=ice,stratiform_rate=rain)
        self.assertGreater(m['south_rear150_weak_echo_area_km2'],m['south_rear150_cold_area_km2'])
        self.assertEqual(m['north_rear150_anvil_mass_kg'],0)
        self.assertGreater(m['south_rear150_anvil_mean_distance_km'],50)
        self.assertGreater(m['south_rear150_stratiform_area_km2'],0)


if __name__=='__main__':unittest.main()
