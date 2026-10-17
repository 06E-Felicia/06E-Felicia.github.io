"""Render saved verification fields only; never performs weather steps."""
import argparse
import json
from pathlib import Path
import numpy as np


def main():
    ap=argparse.ArgumentParser();ap.add_argument('report');ap.add_argument('--output',required=True);args=ap.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap,BoundaryNorm
    report=json.loads(Path(args.report).read_text());data=np.load(args.report+'.npz')
    lon,lat=data['lon'],data['lat'];extent=[lon.min(),lon.max(),lat.min(),lat.max()]
    from .experiment import random_environment
    from .run import terrain_for
    cfg=random_environment(report['seed'],{'grid_km':report['grid_km']},grid_limit=max(12,report['grid_km']))
    terrain,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    colors=['#36a9f2','#2690d0','#1ccc70','#33b52c','#d0d82e','#f2d12b','#ed9725','#ec4b21','#cd213a','#b02063','#a151c4']
    cmap=ListedColormap(colors);cmap.set_bad((0,0,0,0));norm=BoundaryNorm(np.arange(5,65,5),len(colors))
    fig,axes=plt.subplots(2,3,figsize=(16,7.9),layout='constrained',facecolor='#f3f4fa')
    hours=[6,12,24,36,48,72]
    for ax,hour in zip(axes.ravel(),hours):
        echo=data[f'h{hour}_composite'];air=data[f'h{hour}_coldair'];u=data[f'h{hour}_u500'];v=data[f'h{hour}_v500']
        ax.imshow(terrain,origin='lower',extent=extent,cmap='gist_earth',vmin=-150,vmax=2500,alpha=.55)
        im=ax.imshow(np.ma.masked_less(echo,5),origin='lower',extent=extent,cmap=cmap,norm=norm,alpha=.83)
        if air.min()<.5<air.max():ax.contour(lon,lat,air,levels=[.5],colors=['#374766'],linewidths=1.5)
        sample=(slice(None,None,8),slice(None,None,10))
        ax.quiver(lon[sample],lat[sample],u[sample],v[sample],color='#26334e',scale=370,width=.003,alpha=.7)
        ax.set_title(f'{hour} h | radar + 500 hPa wind',color='#303d5b',fontsize=11)
        ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);ax.set_aspect(1/np.cos(np.radians(23.5)))
        ax.set_xlabel('Longitude E');ax.set_ylabel('Latitude N');ax.grid(alpha=.18)
    fig.colorbar(im,ax=axes.ravel().tolist(),label='Composite reflectivity (dBZ)',shrink=.85,pad=.015)
    fig.suptitle(f"StormSim 1.2 {report['edition'].title()} | {report['grid_km']} km / 72 h | seed {report['seed']}\nActual terrain; solid line = transported cold front; arrows = evolving 500 hPa flow",fontsize=13,color='#293a55')
    fig.savefig(args.output,dpi=155);plt.close(fig)


if __name__=='__main__':main()
