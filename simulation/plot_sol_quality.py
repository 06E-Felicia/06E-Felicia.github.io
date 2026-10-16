"""Three actual Sol snapshots, not painted/guaranteed squall-line geometry."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.font_manager import FontProperties
from .run import terrain_for


def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--output',required=True);parser.add_argument('--font')
    args=parser.parse_args();directory=Path(args.directory);report=json.loads((directory/'process.json').read_text())
    if args.font:
        from matplotlib import font_manager
        font_manager.fontManager.addfont(args.font)
        plt.rcParams['font.family']=FontProperties(fname=args.font).get_name()
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':10})
    height,_=terrain_for(report['config'],'assets/data/simulation-terrain.npz')
    fig,axes=plt.subplots(3,3,figsize=(15,11),sharex=True,sharey=True,layout='constrained')
    radar=ListedColormap(['#a8dcff','#469afa','#00cfdd','#36c84c','#069622','#8ac80f','#e4e600','#ffbd00','#ff7900','#ee2520','#b80038','#e900cc','#9d29ad'])
    for column,hour in enumerate([6,30,54]):
        with np.load(directory/('%d.npz'%hour)) as source:a={k:source[k] for k in source.files}
        lon,lat=a['lon'],a['lat']
        panels=[('雷达回波 · dBZ',a['composite'],radar,BoundaryNorm(np.arange(5,75,5),13)),
                ('格点平均雨强 · mm/h',a['rainrate'],'YlGnBu',plt.Normalize(0,40)),
                ('冷池虚温亏损 · K',a['coldpool'],'Blues',plt.Normalize(0,8))]
        for row,(name,data,cmap,norm) in enumerate(panels):
            ax=axes[row,column];ax.set_facecolor('#e9f3f8')
            ax.pcolormesh(lon,lat,np.ma.masked_where(height<=0,height),cmap='Greys',vmin=-500,vmax=4500,shading='nearest')
            shown=np.ma.masked_less(data,[5,.1,.15][row])
            artist=ax.pcolormesh(lon,lat,shown,cmap=cmap,norm=norm,shading='nearest')
            ax.contour(lon,lat,a['coldair'],levels=[.5],colors='#625a7a',linewidths=.8)
            if row==0:ax.contour(lon,lat,a['coldpool'],levels=[1],colors='#176879',linewidths=.6,linestyles='--')
            ax.set_title('%d h · %s'%(hour,name));ax.set_aspect(1/np.cos(np.radians(23)))
            ax.set_xlim(104.3,118);ax.set_ylim(19.8,26.7)
            fig.colorbar(artist,ax=ax,shrink=.77,pad=.02)
            for city,x,y in [('广州',113.26,23.13),('深圳',114.06,22.54),('南宁',108.32,22.82)]:
                ax.plot(x,y,'.',color='#353047',markersize=3)
                if row==0:ax.annotate(city,(x,y),xytext=(3,3),textcoords='offset points',fontsize=8)
            if row==2:ax.set_xlabel('经度 °E')
            if column==0:ax.set_ylabel('纬度 °N')
    fig.suptitle('StormSim 1.1 Sol · 真实积分演变 · %s\n种子 %d / %g km；灰色为缓存 DEM，非实况；虚线冷池仅用于验收图'%(report['engine'],report['config']['seed'],report['config']['grid_km']),fontsize=14)
    fig.savefig(args.output,dpi=130);plt.close(fig)
    print(args.output)


if __name__=='__main__':main()
