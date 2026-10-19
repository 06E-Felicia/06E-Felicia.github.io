"""Frontal initiation, warm-pattern motion, flatter flanks and new episodes."""
import unittest
import numpy as np
from simulation.core import Model,Z
from simulation.sol import SolModel
from simulation.terrain import grid
from simulation.coldpool import velocity


class FrontalLineDynamicsTests(unittest.TestCase):
    def model(self,edition='astra'):
        km=12 if edition=='astra' else 28
        c={'seed':20261017,'bounds':[108,21,115,25.5],'grid_km':km,'stochastic':0}
        return (Model if edition=='astra' else SolModel)(c,np.full(grid(c['bounds'],km)[0].shape,30),grid_limit=28)

    def front(self,m,advancing=True):
        m.air[:]=1/(1+np.exp(-(m.lat-23.3)*111195/18000))
        m.synoptic.front_lat.fill(23.3)
        m.syn_u.fill(4)
        m.syn_v[:]=5*(1-2*m.air)-(6 if advancing else 0)
        m.u=m.syn_u.copy();m.v=m.syn_v.copy()
        conv=-np.gradient(m.syn_v,m.dx,axis=0)
        m.frontal_lifting(conv,conv,0,0)

    def test_advancing_front_has_its_own_permission_after_warm_window(self):
        for edition in ['astra','sol']:
            m=self.model(edition);self.front(m);m.genesis_closed=True
            allowed=m.frontal_initiation_permission()
            self.assertGreater(float(allowed.max()),.5)
            self.assertEqual(float(allowed[m.air>.85].max()),0)
            self.assertEqual(float(allowed[m.air<.015].max()),0)
            m.air.fill(.5)
            np.testing.assert_array_equal(m.frontal_initiation_permission(),0)

    def test_stalled_front_and_spent_wake_remain_blocked(self):
        for reason in ['stalled','cold_pool','spent']:
            m=self.model();self.front(m)
            if reason=='stalled':m.front_advance.fill(0)
            if reason=='cold_pool':
                m.cold_depth.fill(600);m.cold_content.fill(2400);m.cold_diagnostics()
            if reason=='spent':m.cape_deficit[:]=m.cape_capacity
            np.testing.assert_array_equal(m.frontal_initiation_permission(),0)

    def test_front_can_release_actual_parcels_when_warm_origin_is_closed(self):
        for edition in ['astra','sol']:
            m=self.model(edition);self.front(m)
            m.time=12*3600;m.next_genesis_check=m.time+3600
            m.next_diagnostic=m.time+3600;m.genesis_closed=True
            m.lfc.fill(150);m.mu_lfc[:]=Z[m.mu['start_index']]+150
            m.synoptic_lift.fill(1000);m.cape_capacity.fill(2400)
            m.sb['cape'].fill(1500);m.mu['cape'].fill(2400)
            m.step(m.time+1)
            self.assertGreater(float(m.initiation.max()),.1)
            self.assertTrue(m.genesis_closed,'frontal initiation must not reopen the old warm origin')

    def test_warm_pattern_uses_calibrated_motion_without_rewriting_wind_arrays(self):
        for edition in ['astra','sol']:
            m=self.model(edition);u,v=m.winds();original_u=u.copy();original_v=v.copy()
            raw_u,raw_v=m.steering(u,v);cu,cv=m.storm_motion(u,v)
            warm=m.air<.1
            np.testing.assert_allclose(cu[warm],raw_u[warm]*m.WARM_PATTERN_RETENTION)
            np.testing.assert_allclose(cv[warm],raw_v[warm]*m.WARM_PATTERN_RETENTION)
            np.testing.assert_array_equal(u,original_u);np.testing.assert_array_equal(v,original_v)
            m.air.fill(1);a,b=m.storm_motion(u,v)
            np.testing.assert_array_equal(a,raw_u);np.testing.assert_array_equal(b,raw_v)
            # A downstream NE background is not a hard track constraint.
            # Locally southeastward flow must retain its sign, including
            # front-attached cells; only the warm-pattern speed is scaled.
            for air in [0,.3,1]:
                m.air.fill(air)
                for northward in [-6.,6.]:
                    a,b=m.storm_motion(np.full_like(u,15.),np.full_like(v,northward))
                    factor=m.WARM_PATTERN_RETENTION+(1-m.WARM_PATTERN_RETENTION)*np.clip((air-.1)/.4,0,1)
                    np.testing.assert_allclose(a,15*factor,rtol=1e-6)
                    np.testing.assert_allclose(b,northward*factor,rtol=1e-6)

    def test_flank_form_drag_is_stronger_than_leading_head_and_conserves_cold_mass(self):
        m=self.model();y,x=np.indices(m.shape);cx,cy=np.array(m.shape[::-1])/2
        m.cold_depth=600*np.exp(-((x-cx)**2+(y-cy)**2)/20)
        m.cold_content=m.cold_depth*3
        dx=x-cx;dy=y-cy;r=np.maximum(np.hypot(dx,dy),1)
        nx=dx/r;ny=dy/r
        m.cold_mx=m.cold_depth*(m.syn_u+15*nx);m.cold_my=m.cold_depth*(m.syn_v+15*ny)
        h=m.cold_depth.copy();q=m.cold_content.copy()
        before=np.hypot(15*nx,15*ny);m.cold_head_friction(90)
        u,v=velocity(m.cold_depth,m.cold_mx,m.cold_my)
        ratio=np.hypot(u-m.syn_u,v-m.syn_v)/np.maximum(before,1)
        u3,v3=m.winds();su,sv=m.steering(u3,v3)
        align=((su-m.syn_u)*nx+(sv-m.syn_v)*ny)/np.maximum(np.hypot(su-m.syn_u,sv-m.syn_v),1)
        ring=(r>2)&(r<5)
        self.assertLess(float(ratio[ring&(np.abs(align)<.2)].mean()),float(ratio[ring&(align>.9)].mean()))
        np.testing.assert_array_equal(m.cold_depth,h);np.testing.assert_array_equal(m.cold_content,q)

    def test_filtered_head_cannot_trigger_ahead_of_actual_cold_volume(self):
        for edition in ['astra','sol']:
            m=self.model(edition);head=np.full(m.shape,1000.);gradient=np.full(m.shape,.04)
            m.cold_depth.fill(0);np.testing.assert_array_equal(m.convective_head_edge(gradient,head),0)
            m.cold_depth.fill(1);thin=m.convective_head_edge(gradient,head)
            m.cold_depth.fill(150);arrived=m.convective_head_edge(gradient,head)
            # Mechanical work uses edge squared: a one-metre numerical tail
            # may receive <2.5% of head work, never the full neighbouring head.
            self.assertLess(float(thin.max())**2,float(arrived.min())**2*.025)
            np.testing.assert_array_equal(arrived,1)

    def test_oblique_heads_keep_connections_but_receding_side_stays_blocked(self):
        m=self.model()
        aligned=m.cold_head_balance(12,12,0,1,0)
        oblique=m.cold_head_balance(12,12,0,np.sqrt(.5),np.sqrt(.5))
        receding=m.cold_head_balance(12,12,0,-1,0)
        self.assertGreater(oblique,.6*aligned)
        self.assertLess(oblique,aligned)
        self.assertEqual(receding,0)

    def test_one_small_bow_does_not_close_the_mother_boundary(self):
        for edition in ['astra','sol']:
            m=self.model(edition);m.synoptic.genesis_half_length=110000
            mature=np.zeros(m.shape,bool);cy,cx=np.array(m.shape)//2
            mature[cy:cy+2,cx:cx+6]=True
            self.assertGreater(mature.sum()*m.dx**2,1000e6)
            self.assertFalse(m.mature_genesis_line(mature))
            partial=int(np.ceil(110000/m.dx))
            mature[cy-partial//2:cy-partial//2+partial,cx]=True
            self.assertFalse(m.mature_genesis_line(mature),'a half-length bow must not close the entire parent confluence')
            length=int(np.ceil(1.5*110000/m.dx))
            mature[cy-length//2:cy-length//2+length,cx]=True
            self.assertTrue(m.mature_genesis_line(mature))

    def test_pressure_response_tracks_frontal_crossing_time_not_cape(self):
        m=self.model();self.front(m);m.synoptic.genesis_center=None
        original=m.synoptic.speed
        m.synoptic.speed=lambda time:np.full(m.shape[1],1.)
        slow=m.synoptic_adjustment_rate()
        m.synoptic.speed=lambda time:np.full(m.shape[1],8.)
        fast=m.synoptic_adjustment_rate()
        belt=(m.air>.25)&(m.air<.75)
        self.assertGreater(float(fast[belt].mean()),float(slow[belt].mean())*2)
        m.synoptic.speed=lambda time:np.zeros(m.shape[1])
        np.testing.assert_array_equal(m.synoptic_adjustment_rate(),1/7200)
        m.synoptic.speed=original

    def favourable_finished_episode(self,m):
        m.time=10*3600;m.genesis_closed=True;m.activity.fill(0);m.last_rate.fill(0)
        m.air.fill(0);m.cape_deficit.fill(0);m.cape_capacity.fill(2400)
        m.mu['cape'].fill(2000);m.mu['cin'].fill(-20)
        m.mu_lfc[:]=Z[m.mu['start_index']]+600;m.background_w.fill(.02)

    def test_same_day_second_episode_needs_no_cape_or_water_reset(self):
        for edition in ['astra','sol']:
            m=self.model(edition);self.favourable_finished_episode(m)
            m.cape_deficit.fill(100)
            before={k:getattr(m,k).copy() for k in ['temp','q','cold_content','cape_deficit']}
            episode=m.synoptic.episode_index
            self.assertTrue(m.reconsider_genesis())
            self.assertEqual(m.synoptic.episode_index,episode+1)
            self.assertTrue(m.time+1800<m.synoptic.genesis_start<m.time+5400)
            self.assertLess(m.synoptic.genesis_start,86400)
            for key,value in before.items():np.testing.assert_array_equal(getattr(m,key),value)

    def test_new_episode_is_not_automatic_or_parallel_to_unfinished_line(self):
        for reason in ['ongoing','spent','stable','no_lift','cold_air']:
            m=self.model();self.favourable_finished_episode(m)
            if reason=='ongoing':m.activity.fill(.2);m.last_rate.fill(5)
            if reason=='spent':m.cape_deficit[:]=m.cape_capacity
            if reason=='stable':m.mu_lfc.fill(np.inf)
            if reason=='no_lift':m.background_w.fill(0)
            if reason=='cold_air':m.air.fill(1)
            self.assertFalse(m.reconsider_genesis(),reason)

    def test_day_change_does_not_replace_an_ongoing_system(self):
        m=self.model();m.time=86400;m.activity.fill(.3);m.last_rate.fill(5)
        m.genesis_closed=True
        episode=m.synoptic.episode_index;center=m.synoptic.genesis_center;start=m.synoptic.genesis_start
        m.step(m.time+1)
        self.assertEqual(m.synoptic.episode_index,episode)
        self.assertEqual(m.synoptic.genesis_center,center)
        self.assertEqual(m.synoptic.genesis_start,start)


if __name__=='__main__':unittest.main()
