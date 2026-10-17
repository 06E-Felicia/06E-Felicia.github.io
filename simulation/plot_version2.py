"""Plot existing Astra diagnostics; never computes a weather step."""
import argparse
import json
import numpy as np
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('report');ap.add_argument('--output',required=True)
    args=ap.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    report=json.loads(Path(args.report).read_text());data=np.load(args.report+'.npz')
    lon,lat=data['lon'],data['lat'];extent=[lon.min(),lon.max(),lat.min(),lat.max()]
    colors=['#319bf2','#1ba2b2','#22c75e','#38a631','#c1cf35','#f0ce36','#ed9e2c','#eb592a','#ca243e','#a52569','#ac65be']
    cmap=ListedColormap(colors);cmap.set_bad((0,0,0,0));norm=BoundaryNorm(np.arange(5,65,5),len(colors))
    hours=[0,6,12,24,48,72]
    fig,axes=plt.subplots(3,6,figsize=(19,8.6),layout='constrained',facecolor='#f4f3fa')
    for column,hour in enumerate(hours):
        for row,(key,title,palette,low,high) in enumerate([
            ('radar','Radar / dBZ',cmap,None,None),('cape','Effective MUCAPE / J kg-1','YlOrRd',0,6000),
            ('cold','Convective cold-pool deficit / K','Blues',0,5)]):
            ax=axes[row,column];values=data[f'h{hour}_{key}'];air=data[f'h{hour}_air']
            ax.set_facecolor('#e8ecf2')
            im=ax.imshow(np.ma.masked_less(values,5) if key=='radar' else values,origin='lower',extent=extent,
                         cmap=palette,**({'norm':norm} if key=='radar' else {'vmin':low,'vmax':high}))
            if air.min()<.5<air.max():ax.contour(lon,lat,air,levels=[.5],colors=['#465470'],linewidths=.8)
            if row==0:ax.set_title(f'{hour} h',fontsize=11)
            if column==0:ax.set_ylabel(title+'\nLatitude N',fontsize=9)
            if row==2:ax.set_xlabel('Longitude E',fontsize=9)
            ax.set_aspect(1/np.cos(np.radians(23.5)));ax.tick_params(labelsize=7)
            if column==5:fig.colorbar(im,ax=axes[row,:],shrink=.75,pad=.008)
    fig.suptitle(f"StormSim 2 Astra | {report['grid_km']} km | seed {report['config']['seed']}\nSaved process diagnostics; line = transported cold front, not a radar mask",fontsize=13)
    fig.savefig(args.output,dpi=150);plt.close(fig)


if __name__=='__main__':main()
