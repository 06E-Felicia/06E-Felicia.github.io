"""Sol-only closure for initiation below the horizontal grid scale.

The shared Astra model and its thresholds are deliberately left unchanged.
"""
import numpy as np
from .core import Model


class SolModel(Model):
    # The coarse-grid regeneration hops need slightly stronger translation
    # damping than Astra; retain the shared physical flow and cold-head work.
    WARM_PATTERN_RETENTION=.65

    def frontal_lifting(self,syn_convergence,convergence,uphill,trough_ascent):
        restoring=super().frontal_lifting(syn_convergence,convergence,uphill,trough_ascent)
        # A 28-km cell averages over the narrow confluence that initiates the
        # mother system. Recover its unresolved plume-scale ascent from the
        # ACTUAL positive convergence, only in this episode's finite fresh
        # warm-sector footprint. No extra CAPE/water or automatic storm is
        # supplied; parcels still have to clear their LFC and CIN.
        scale=1.15*np.clip(self.dx/12000-1,0,1.5)
        if scale and not self.genesis_closed:
            _,permission=self.synoptic.genesis(self.time)
            # A zero-capacity column has zero debt too, but is not an
            # unstable fresh reservoir. The wider footprint exposed such a
            # column; do not add the unresolved plume lift without energy.
            unstable=self.available_cape(self.mu['cape'])>150
            extra=1000*scale*np.maximum(syn_convergence,0)*permission*self.fresh_initiation_air()*unstable
            self.background_w=np.clip(self.background_w+extra,-.4,.8)
            self.w=np.clip(self.w+extra,-.4,.8)
        return restoring
