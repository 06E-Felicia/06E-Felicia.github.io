"""Plot saved numerical diagnostics only; does not advance a simulation."""
import argparse
import json
import numpy as np


def main():
    ap=argparse.ArgumentParser();ap.add_argument('report');ap.add_argument('--output',required=True)
    ap.add_argument('--hours',nargs='+',type=float,default=[4,6,8]);args=ap.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap,BoundaryNorm
    with open(args.report) as file:report=json.load(file)
    data=np.load(args.report+'.npz');lon,lat=data['lon'],data['lat']
    extent=[lon.min(),lon.max(),lat.min(),lat.max()]
    cmap=ListedColormap(['#3c91e5','#2aa9c7','#23bf78','#36bc35','#a4ce34','#ecdc35','#f8b039','#ee6730','#dc2942','#b42672','#b164c4'])
    cmap.set_bad((0,0,0,0));norm=BoundaryNorm(np.arange(5,65,5),len(cmap.colors))
    fig,axes=plt.subplots(3,len(args.hours),figsize=(5*len(args.hours),9),squeeze=False,layout='constrained')
    for column,hour in enumerate(args.hours):
        for row,(key,title,palette,high) in enumerate([
            ('radar','Composite / dBZ',cmap,None),('cold','Rain-cooled air / K','Blues',4),
            ('rain_total','Actual grid-mean rain / mm','YlGnBu',40)]):
            stored=f'h{hour:g}_{key}'
            if key=='rain_total' and stored not in data:stored=f'h{hour:g}_grid_total'
            a=data[stored];ax=axes[row,column];ax.set_facecolor('#edf0f5')
            im=ax.imshow(np.ma.masked_less(a,5) if key=='radar' else a,origin='lower',extent=extent,cmap=palette,
                         **({'norm':norm} if key=='radar' else {'vmin':0,'vmax':high}))
            if key=='cold':
                depth=data[f'h{hour:g}_depth']
                if depth.max()>100:ax.contour(lon,lat,depth,levels=[100],colors=['#64758b'],linewidths=.5)
            ax.set_aspect(1/np.cos(np.radians(23.5)));ax.grid(alpha=.16);ax.tick_params(labelsize=8)
            if row==0:ax.set_title(f'{hour} h')
            if column==0:ax.set_ylabel(title+'\nLatitude N')
            if row==2:ax.set_xlabel('Longitude E')
            if column==len(args.hours)-1:fig.colorbar(im,ax=axes[row,:],shrink=.7,pad=.01)
    fig.suptitle(f"StormSim 2 Astra | {report['grid_km']} km | seed {report['config']['seed']}\nActual saved fields; no synthetic radar/cold-pool masks")
    fig.savefig(args.output,dpi=130);plt.close(fig)


if __name__=='__main__':main()
