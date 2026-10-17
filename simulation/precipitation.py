"""Conservative stochastic surface footprint, NOT extra resolved dynamics.

The column solver predicts cell-mean water. Point gauges sample a finite rain
shaft instead. Sixteen area quadratures split that SAME fallen water; their
mean equals the native flux at every step. Stratiform rain stays widespread.
Independent persistent noise does not change any meteorological RNG stream.
"""
import math
import numpy as np
from scipy.ndimage import gaussian_filter


class SurfaceRain:
    subdivisions=4

    def __init__(self,shape,seed):
        self.shape=shape;self.rng=np.random.default_rng(np.random.SeedSequence([int(seed),1207]))
        self.noise=self.draw();self.rank=self.ranks();self.next_noise=300.;self.time=0.
        self.total=np.zeros((shape[0]*4,shape[1]*4),dtype='float32')
        self.phase=np.zeros((2,*shape),dtype='float64')
        self.rate=np.zeros_like(self.total);self.history=[(0.,self.total.copy())]
        self.next_history=300.;self.max_five=0.;self.max_hour=0.

    def draw(self):
        return gaussian_filter(self.rng.standard_normal((self.shape[0]*4,self.shape[1]*4)),
                               .8,mode='reflect').astype('float32')

    def weights(self,area):
        # At least two quadratures represent a finite shaft. In particular we
        # never turn a numerical 1% area tail into a 100-fold point maximum.
        occupied=np.clip(area,2/16,1)*16
        water=np.clip(occupied[...,None]-self.rank,0,1)*16/occupied[...,None]
        # Smooth finite shafts instead of hard, permanently dry quadratures.
        # The filter wraps ONLY within each quadrature block and preserves
        # its exact mean; it transports no water between model grid cells.
        return gaussian_filter(water.reshape(*self.shape,4,4),(0,0,.45,.45),mode='wrap')

    def ranks(self):
        blocks=self.noise.reshape(self.shape[0],4,self.shape[1],4).transpose(0,2,1,3)
        return np.argsort(np.argsort(-blocks.reshape(*self.shape,16),axis=-1),axis=-1)

    def shifted_weights(self,weights,phase):
        # Periodic quadrature translation is a convex, exactly mean-preserving
        # interpolation, not a transfer of rain between native model cells.
        # Repeated global interpolation of the old noise erased small scales;
        # ranking its remaining smooth gradient then pinned the same dry/wet
        # corner to every cell despite an apparently moving texture.
        y,x=np.indices((4,4));yy=y-phase[0,...,None,None];xx=x-phase[1,...,None,None]
        iy=np.floor(yy).astype(int);ix=np.floor(xx).astype(int);fy=yy-iy;fx=xx-ix
        source=weights.reshape(*self.shape,16)
        def sample(dy,dx):
            indices=(((iy+dy)%4)*4+(ix+dx)%4).reshape(*self.shape,16)
            return np.take_along_axis(source,indices,axis=-1).reshape(*self.shape,4,4)
        return ((1-fy)*((1-fx)*sample(0,0)+fx*sample(0,1))
                +fy*((1-fx)*sample(1,0)+fx*sample(1,1)))

    def advance(self,time,dt,convective,background,area,velocity=None,dx=None):
        if self.time>=self.next_noise-1e-6:
            alpha=math.exp(-300/1800)
            self.noise=alpha*self.noise+math.sqrt(1-alpha*alpha)*self.draw()
            self.next_noise+=300
        phase=self.phase
        if velocity is not None:
            if dx is None or dx<=0:raise ValueError('Moving rain footprints need a positive grid spacing')
            u,v=velocity;increment=np.stack([v,u])*(dt*4/dx)
            phase=(self.phase+increment*.5)%4
            self.phase=(self.phase+increment)%4
        self.rank=self.ranks()
        weights=self.weights(area)
        if velocity is not None:weights=self.shifted_weights(weights,phase)
        water=background[...,None,None]+convective[...,None,None]*weights
        fine=water.transpose(0,2,1,3).reshape(self.total.shape)
        self.rate=(fine*3600/dt).astype('float32');self.total+=fine.astype('float32');self.time=time
        if time>=self.next_history-1e-6:
            self.history.append((time,self.total.copy()));self.next_history+=300
            while len(self.history)>2 and self.history[1][0]<=time-3600:self.history.pop(0)
            self.max_five=max(self.max_five,float(self.accumulation(300).max()))
            self.max_hour=max(self.max_hour,float(self.accumulation(3600).max()))

    def accumulation(self,seconds):
        target=max(0,self.time-seconds);before=self.history[0][1]
        points=self.history if self.history[-1][0]>=self.time-1e-6 else [*self.history,(self.time,self.total)]
        for (ta,a),(tb,b) in zip(points,points[1:]):
            if ta<=target<=tb:
                before=a+(b-a)*(target-ta)/max(tb-ta,1e-9);break
        return np.maximum(self.total-before,0)

    def grid(self,lon,lat):
        dx=float(lon[0,1]-lon[0,0]);dy=float(lat[1,0]-lat[0,0])
        return {'nx':self.total.shape[1],'ny':self.total.shape[0],
                'west':float(lon[0,0])-dx*.375,'south':float(lat[0,0])-dy*.375,
                'dlon':dx/4,'dlat':dy/4,'z_agl_m':[],
                'method':'conservative advected rain-shaft quadrature; bilinear gauge sampling; not resolved grid'}

    def fields(self):
        return {'point_rainrate':self.rate,'point_rain_total':self.total,
                'point_rain_hour':self.accumulation(3600),'point_rain5':self.accumulation(300)}
