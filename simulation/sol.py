"""Sol-only closure for initiation below the horizontal grid scale.

The shared Astra model and its thresholds are deliberately left unchanged.
"""
import numpy as np
from .core import Model


class SolModel(Model):
    def frontal_lifting(self,syn_convergence,convergence,uphill,trough_ascent):
        restoring=super().frontal_lifting(syn_convergence,convergence,uphill,trough_ascent)
        # A 28-km cell averages over the narrow confluence that initiates the
        # mother system. Recover its unresolved plume-scale ascent from the
        # ACTUAL positive convergence, only in this episode's finite fresh
        # warm-sector footprint. No extra CAPE/water or automatic storm is
        # supplied; parcels still have to clear their LFC and CIN.
        scale=np.clip(self.dx/12000-1,0,1.5)
        if scale and not self.genesis_closed:
            _,permission=self.synoptic.genesis(self.time)
            extra=1000*scale*np.maximum(syn_convergence,0)*permission*self.fresh_initiation_air()
            self.background_w=np.clip(self.background_w+extra,-.4,.8)
            self.w=np.clip(self.w+extra,-.4,.8)
        return restoring
