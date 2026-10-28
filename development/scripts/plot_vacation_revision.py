"""Plot actual member-cell tracks, band-centroid lineages and process-source ledgers."""
import argparse,json,os,sys
from pathlib import Path
extra=Path(os.environ.get('VACATION_REPLAY_DEPS',str(Path.home()/'.cache/vacation-replay/python')))
if extra.is_dir():sys.path.insert(0,str(extra))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def plot(directory):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text());tracks={};samples=[]
    for entry in manifest['frames']:
        meta=json.loads((directory/entry['data']).read_text());samples.append(meta)
        for cell in meta['cells']:tracks.setdefault(cell['id'],[]).append((meta['simTime']/3600,cell['x']/1000,cell['y']/1000,cell['source']))
    fig,axs=plt.subplots(3,1,figsize=(13,13),dpi=130)
    for track in tracks.values():
        a=np.array([v[:3] for v in track]);color='#bf597c' if track[0][3]=='coldPool' else '#4e8195';axs[0].plot(a[:,0],a[:,1]-manifest['config']['width']/2000,color=color,alpha=.28,lw=.7)
    axs[0].set(title='Actual individual cell trajectories (all IDs; east coordinate)',ylabel='East from domain center (km)')
    if (directory/'structure-tracks.json').is_file():
        data=json.loads((directory/'structure-tracks.json').read_text())
        for key,track in data['tracks'].items():
            a=sorted(track,key=lambda v:v['t']);axs[1].plot([v['t']/3600 for v in a],[v['centroid'][0]/1000-manifest['config']['width']/2000 for v in a],lw=1 if any(v['band'] for v in a) else .4,alpha=.8 if any(v['band'] for v in a) else .2)
    axs[1].set(title='Raw >=35 dBZ object centroids; advected matching; thick lines have band geometry',ylabel='East from domain center (km)')
    hours=[s['simTime']/3600 for s in samples]
    for key in ['environmentCondensed','cellCondensed','coreGround','detrainedGround']:
        axs[2].plot(hours,[s['stats'].get('sources',{}).get(key,0)/1e9 for s in samples],label=key)
    axs[2].set(title='Cumulative process/source fluxes; environmental cloud is nonprecipitating',ylabel='10^9 kg',xlabel='Simulation hour');axs[2].legend()
    for ax in axs:ax.grid(alpha=.2)
    fig.suptitle(f"Vacation {manifest['model']} | seed {manifest['config']['seed']} | {manifest['config'].get('scenarioGroup')} | synthetic case")
    fig.tight_layout();fig.savefig(directory/'lineage-time-distance.png');plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args();plot(a.directory)
