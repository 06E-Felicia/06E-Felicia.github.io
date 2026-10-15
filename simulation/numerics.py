"""Reusable face geometry for the unchanged minmod MUSCL / SSP-RK2 scheme.

Share wind faces across tracers; use slices rather than pad / transpose each
entire volume twice. An operator owns no field state, and returned arrays
never alias its scratch storage or another tracer.
"""
import numpy as np

_accelerator=None


def install_accelerator(callback):
    """Optional zero-copy browser implementation of this EXACT float64 flux."""
    global _accelerator
    _accelerator=callback


class Advection:
    def __init__(self,u,v,dx):
        self.dx=dx
        self.ux=np.concatenate((u[...,:1],(u[...,:-1]+u[...,1:])*.5,u[...,-1:]),axis=-1)
        self.vy=np.concatenate((v[...,:1,:],(v[...,:-1,:]+v[...,1:,:])*.5,v[...,-1:,:]),axis=-2)
        self.upx=self.ux>=0;self.upy=self.vy>=0
        self.divergence=(np.diff(self.ux,axis=-1)+np.diff(self.vy,axis=-2))/dx

    def __call__(self,a,dt,boundary=None,conservative=False):
        if (_accelerator is not None and a.dtype==np.float64 and a.flags.c_contiguous
                and (boundary is None or np.ndim(boundary)==0
                     or (np.shape(boundary)==a.shape and np.asarray(boundary).flags.c_contiguous))):
            out=np.empty_like(a)
            _accelerator(a,self.ux,self.vy,self.divergence,out,dt,self.dx,
                         boundary,conservative,a.shape[-1],a.shape[-2])
            return out
        outside=None if boundary is None else np.broadcast_to(boundary,a.shape)

        def tendency(field):
            fx=self._flux(field,self.ux,self.upx,-1,outside)
            fy=self._flux(field,self.vy,self.upy,-2,outside)
            return -(np.diff(fx,axis=-1)+np.diff(fy,axis=-2))/self.dx+(0 if conservative else field*self.divergence)

        first=a+dt*tendency(a)
        return .5*(a+first+dt*tendency(first))

    def carry(self,carrier,moments,dt):
        """MUSCL carrier with mass-consistent signed passive moments.

        Reconstruct the WATER flux once, then multiply each face flux by its
        donor's moment/water ratio. Independently limiting signed moments can
        put a finite source speed in an almost empty cloud cell and generate
        unbounded diagnosed winds. This consistent first-order colour flux
        keeps source ratios bounded without clipping velocities or painting
        water. The carrier retains the original second-order SSP-RK2 flux.
        Open-boundary inflow is zero water/zero moment, outflow is free.
        """
        zero=np.zeros_like(carrier)

        def tendency(a,m):
            fx=self._flux(a,self.ux,self.upx,-1,zero)
            fy=self._flux(a,self.vy,self.upy,-2,zero)
            ratio=np.divide(m,a[None],out=np.zeros_like(m),where=a[None]>0)
            rx=np.concatenate((np.zeros_like(ratio[...,:1]),ratio,np.zeros_like(ratio[...,:1])),axis=-1)
            ry=np.concatenate((np.zeros_like(ratio[...,:1,:]),ratio,np.zeros_like(ratio[...,:1,:])),axis=-2)
            mx=fx[None]*np.where(self.upx[None],rx[...,:-1],rx[...,1:])
            my=fy[None]*np.where(self.upy[None],ry[...,:-1,:],ry[...,1:,:])
            return (-(np.diff(fx,axis=-1)+np.diff(fy,axis=-2))/self.dx,
                    -(np.diff(mx,axis=-1)+np.diff(my,axis=-2))/self.dx)

        da,dm=tendency(carrier,moments)
        first=carrier+dt*da;first_m=moments+dt*dm
        da,dm=tendency(first,first_m)
        return .5*(carrier+first+dt*da),.5*(moments+first_m+dt*dm)

    @staticmethod
    def _flux(field,wind,positive,axis,outside):
        # moveaxis returns a view; no padded or reconstructed full volume.
        a=np.moveaxis(field,axis,-1)
        b=a if outside is None else np.moveaxis(outside,axis,-1)
        # Match concatenate's promotion in the reference scheme. In
        # particular float32 water plus an integer zero ghost becomes float64;
        # silently retaining float32 changes threshold-sensitive initiation.
        dtype=np.result_type(a,b)
        a=np.asarray(a,dtype=dtype);b=np.asarray(b,dtype=dtype)
        w=np.moveaxis(wind,axis,-1);sign=np.moveaxis(positive,axis,-1)
        left=np.empty_like(a);right=np.empty_like(a)
        left[...,1:]=a[...,1:]-a[...,:-1];left[...,:1]=a[...,:1]-b[...,:1]
        right[...,:-1]=a[...,1:]-a[...,:-1];right[...,-1:]=b[...,-1:]-a[...,-1:]
        slope=np.where(left*right>0,np.where(left>0,np.minimum(left,right),np.maximum(left,right)),0)
        flux=np.empty(np.broadcast_shapes(a.shape[:-1]+(a.shape[-1]+1,),w.shape),dtype=np.result_type(a,w))
        flux[...,1:-1]=w[...,1:-1]*np.where(sign[...,1:-1],a[...,:-1]+slope[...,:-1]*.5,a[...,1:]-slope[...,1:]*.5)
        flux[...,:1]=w[...,:1]*np.where(sign[...,:1],b[...,:1],a[...,:1]-slope[...,:1]*.5)
        flux[...,-1:]=w[...,-1:]*np.where(sign[...,-1:],a[...,-1:]+slope[...,-1:]*.5,b[...,-1:])
        return np.moveaxis(flux,-1,axis)
