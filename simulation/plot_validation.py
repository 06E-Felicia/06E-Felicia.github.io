"""Optional scientific QA rendering of real saved process snapshots."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from .run import terrain_for


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--report',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('--hours',type=int,nargs='+',default=[6,12]);args=ap.parse_args()
    report=json.loads(Path(args.report).read_text());height,_=terrain_for(report['config'],'assets/data/simulation-terrain.npz')
    fig,axes=plt.subplots(2,len(args.hours),figsize=(7*len(args.hours),9),squeeze=False,constrained_layout=True)
    cmap=ListedColormap(['#2868c1','#27cbb7','#43b94d','#dfdb31','#eda543','#de542e','#c52665','#ae77d5'])
    norm=BoundaryNorm([5,15,25,30,35,40,45,50,65],cmap.N)
    for column,hour in enumerate(args.hours):
        with np.load(args.report+'.'+str(hour)+'.npz') as data:
            lon,lat=data['lon'],data['lat']
            for row,key in enumerate(['composite','cold']):
                ax=axes[row,column];ax.pcolormesh(lon,lat,height,cmap='Greys',vmin=0,vmax=2500,shading='auto',alpha=.35)
                values=data[key];valid=values>=5 if row==0 else values>=.2
                plotted=ax.pcolormesh(lon,lat,np.ma.masked_where(~valid,values),cmap=cmap if row==0 else 'Blues',norm=norm if row==0 else None,vmin=None if row==0 else 0,vmax=None if row==0 else 8,shading='auto')
                ax.contour(lon,lat,data['air'],levels=[.5],colors=['#4160b0'],linewidths=.8)
                ax.set(title=f'+{hour:02d} h / '+('Radar composite' if row==0 else 'Rain-cooled outflow'),xlabel='Longitude',ylabel='Latitude')
                ax.set_aspect(1/np.cos(np.deg2rad(23)));ax.grid(alpha=.15)
                fig.colorbar(plotted,ax=ax,label='dBZ' if row==0 else 'K',shrink=.8)
    cfg=report['config'];fig.suptitle(f"Calculated process / seed {cfg['seed']} / {cfg['grid_km']:g} km / longest tracked line {report['longest_tracked_line_hours']:g} h\nTerrain: real DEM; contours: synoptic cold-air boundary; parameterized experiment",fontsize=14)
    fig.savefig(args.output,dpi=150);plt.close(fig)


if __name__=='__main__':main()
