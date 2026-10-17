"""Causal Astra cloud-source shutdown, never a production forecast.

Loads ONLY trusted, self-generated local checkpoints; pickle is not an input
format for downloads, public uploads or arbitrary third-party model files.
"""
import argparse
import json
import pickle
import time
from pathlib import Path
import numpy as np
from .core import VERSION,source_digest


def main():
    ap=argparse.ArgumentParser();ap.add_argument('trusted_checkpoint');ap.add_argument('--hours',type=int,default=8);ap.add_argument('--output',required=True);args=ap.parse_args()
    with Path(args.trusted_checkpoint).open('rb') as file:m=pickle.load(file)
    inferred=not hasattr(m,'anvil_number')
    if inferred:m.anvil_number=m.anvil/(4/3*np.pi*300*.00015**3)
    start=m.time;started=time.monotonic();rows=[]
    def stop_plumes(cloud_gain,dt,u=None,v=None,air_flux=None,vapor_gain=None,source_inflow=None):
        return cloud_gain*0 if vapor_gain is None else (cloud_gain*0,vapor_gain*0)
    m.debit_plumes=stop_plumes
    for hour in range(args.hours+1):
        while m.time<start+hour*3600-1e-6:m.step(start+hour*3600)
        convective=np.sum(m.anvil_convective*m.mass,axis=0)
        environmental=np.sum(np.maximum(m.anvil-m.anvil_convective,0)*m.mass,axis=0)
        row={'hours_since_source_off':hour,'convective_ice_mass':float(convective.sum()),
             'convective_ice_column_max':float(convective.max()),'environmental_ice_mass':float(environmental.sum()),
             'convective_ice_columns_over_0_02':int((convective>.02).sum()),
             'new_convective_ice_source':m.convective_ice_source,'audit':m.audit_state()}
        rows.append(row)
        print(json.dumps({k:row[k] for k in ['hours_since_source_off','convective_ice_mass','convective_ice_column_max']}),flush=True)
    Path(args.output).write_text(json.dumps({'engine':VERSION,'source_sha256':source_digest('experiment.py','browser.py'),
        'grid_km':m.cfg['grid_km'],'seed':m.cfg['seed'],'checkpoint_hour':start/3600,
        'inferred_number_for_old_checkpoint':inferred,
        'limitation':'Astra causal source-off sensitivity, not a physically complete alternate forecast; environmental condensation, transport, phase changes and surface fluxes remain enabled',
        'elapsed_s':time.monotonic()-started,'samples':rows},indent=2))


if __name__=='__main__':main()
