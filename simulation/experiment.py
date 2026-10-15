"""Seeded environment sampling. No preselected storms or guaranteed outcomes."""
import numpy as np
from .core import settings


def random_environment(seed, overrides=None):
    # A separate stream from the model's initial-field/evolution streams.
    rng=np.random.default_rng(np.random.SeedSequence([int(seed),8675309]))
    month=int(rng.integers(3,6))
    raw={'seed':int(seed),'month':month,
         'moisture':round(float(rng.uniform(.85,1.2)),3),
         'jet':round(float(rng.uniform(.7,1.4)),3),
         'shear':round(float(rng.uniform(.65,1.4)),3),
         'trough':round(float(rng.uniform(.5,1.4)),3),
         'cold_reservoir':round(float(rng.uniform(.65,1.4)),3),
         'sst_c':round(float(np.clip(22+(month-3)*1.8+rng.normal(0,.6),18,29)),2),
         'stochastic':round(float(rng.uniform(.35,1)),3)}
    # Numerical controls only; random environment is never silently overridden
    # by stale fields from the configuration form.
    for key,value in (overrides or {}).items():
        if key not in ('hours','grid_km','frame_minutes','terrain','compact_transport'):raise ValueError('Not a numerical control: '+key)
        raw[key]=value
    return settings(raw)
