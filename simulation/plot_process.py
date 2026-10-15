"""Static scientific QA figure from real saved process arrays, not an echo mockup."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.font_manager import FontProperties
from .core import settings
from .run import terrain_for


def project(lon,lat):
    return 6371*np.radians(lon),6371*np.log(np.tan(np.pi/4+np.radians(lat)/2))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('snapshot');parser.add_argument('--output',required=True)
    parser.add_argument('--seed',required=True,type=int);parser.add_argument('--grid-km',required=True,type=float)
    parser.add_argument('--hour',required=True,type=float);parser.add_argument('--font')
    args=parser.parse_args()
    if args.font:
        from matplotlib import font_manager
        font_manager.fontManager.addfont(args.font)
        plt.rcParams['font.family']=FontProperties(fname=args.font).get_name()
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':11,'axes.titlesize':13})
    with np.load(args.snapshot,allow_pickle=False) as source:a={key:source[key] for key in source.files}
    lon,lat=a['lon'],a['lat'];x,y=project(lon,lat)
    cfg=settings({'seed':args.seed,'grid_km':args.grid_km})
    height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    if height.shape!=lon.shape:raise ValueError('Terrain/snapshot grid mismatch')
    stations=json.loads(Path('assets/data/simulator-stations.json').read_text())['stations']
    names={'59431':'南宁','59046':'柳州','59265':'梧州','59287':'广州','59493':'深圳','59663':'阳江','59658':'湛江','59280':'清远'}
    colors=['#a8dcff','#469afa','#00cfdd','#36c84c','#069622','#8ac80f','#e4e600','#ffbd00','#ff7900','#ee2520','#b80038','#e900cc','#9d29ad']
    levels=np.arange(5,75,5);radar_cmap=ListedColormap(colors)
    fig=plt.figure(figsize=(16,9),facecolor='white')
    grid=fig.add_gridspec(2,3,width_ratios=[1.05,1.05,1.05],hspace=.27,wspace=.16)
    radar=fig.add_subplot(grid[:,0:2]);cold=fig.add_subplot(grid[0,2]);birth=fig.add_subplot(grid[1,2])

    def background(ax,labels=False):
        ax.set_facecolor('#eaf3f8')
        ax.pcolormesh(x,y,np.ma.masked_where(height<=0,height),cmap='Greys',vmin=-500,vmax=4500,shading='nearest',rasterized=True)
        ax.contour(x,y,height,levels=[0],colors='#829294',linewidths=.45)
        ax.set_xlim(x.min(),x.max());ax.set_ylim(y.min(),y.max());ax.set_aspect('equal')
        longitude=np.arange(106,119,2);latitude=np.arange(20,27,2)
        ax.set_xticks(project(longitude,np.zeros_like(longitude))[0],labels=[f'{v}°E' for v in longitude])
        ax.set_yticks(project(np.zeros_like(latitude),latitude)[1],labels=[f'{v}°N' for v in latitude])
        ax.tick_params(labelsize=10)
        for spine in ax.spines.values():spine.set_color('#c5cdd2')
        if labels:
            for station in stations:
                if station['id'] not in names:continue
                xx,yy=project(station['lon'],station['lat'])
                ax.scatter([xx],[yy],s=9,color='#33434f',zorder=7)
                ax.annotate(names[station['id']],(xx,yy),xytext=(4,4),textcoords='offset points',fontsize=10,
                            color='#24343f',bbox={'facecolor':'white','edgecolor':'none','alpha':.77,'pad':.7},zorder=8)

    for ax in [radar,cold,birth]:background(ax)
    reflection=radar.pcolormesh(x,y,np.ma.masked_less(a['composite'],5),cmap=radar_cmap,
                              norm=BoundaryNorm(levels,len(colors)),shading='nearest',rasterized=True)
    # These overlays annotate ACTUAL density/air-mass fields; no data altered.
    pool=np.minimum(a['cold'],a['cold_depth']/100)
    radar.contour(x,y,a['air'],levels=[.5],colors='#52516e',linewidths=1.)
    radar.contour(x,y,pool,levels=[1],colors='#197b93',linewidths=1.,linestyles='--')
    for station in stations:
        if station['id'] not in names:continue
        xx,yy=project(station['lon'],station['lat'])
        radar.scatter([xx],[yy],s=10,color='#33434f',zorder=7)
        radar.annotate(names[station['id']],(xx,yy),xytext=(4,4),textcoords='offset points',fontsize=10,
                       color='#24343f',bbox={'facecolor':'white','edgecolor':'none','alpha':.8,'pad':.7},zorder=8)
    radar.set_title('合成雷达回波 · dBZ',loc='left',pad=10)
    bar=fig.colorbar(reflection,ax=radar,location='bottom',pad=.065,shrink=.85,aspect=45,ticks=np.arange(10,71,10))
    bar.set_label('反射率（模拟）；实线：冷锋，青色虚线：冷池边界')
    image=cold.pcolormesh(x,y,np.ma.masked_less(a['cold'],.15),cmap='Blues',vmin=0,vmax=8,shading='nearest',rasterized=True)
    cold.set_title('冷池虚温亏损 · K',loc='left')
    fig.colorbar(image,ax=cold,location='bottom',pad=.1,aspect=30,ticks=[0,2,4,6,8])
    image=birth.pcolormesh(x,y,np.ma.masked_less(a['initiation'],.1),cmap='magma',vmin=0,vmax=1,shading='nearest',rasterized=True)
    birth.contour(x,y,pool,levels=[1],colors='#197b93',linewidths=.7,linestyles='--')
    birth.set_title('当前新生对流触发 · 0–1',loc='left')
    fig.colorbar(image,ax=birth,location='bottom',pad=.1,aspect=30,ticks=[0,.5,1])
    hour=8+args.hour;clock=f'第 {int(hour//24)+1} 天 {int(hour%24):02d}:{int(round(hour%1*60)):02d}'
    fig.suptitle(f'强对流过程验收图  |  {clock}  |  {args.grid_km:g} km  |  种子 {args.seed}',fontsize=17,x=.055,ha='left',y=.995)
    fig.text(.055,.935,'真实积分结果 · 地形为缓存 DEM · 仅用于机制检验，非实况 / 非业务预报',fontsize=11,color='#58636c')
    fig.text(.055,.025,f'当前格点雨强峰值 {a["rainrate"].max():.1f} mm/h   ·   累计峰值 {a["rain_total"].max():.1f} mm   ·   冷池虚温亏损峰值 {a["cold"].max():.1f} K',fontsize=11,color='#33414a')
    fig.subplots_adjust(top=.89,bottom=.1,left=.055,right=.98)
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(target,dpi=150,metadata={'Description':f'Simulation only; input {args.snapshot}; seed {args.seed}; {args.grid_km} km; hour {args.hour}'})
    plt.close(fig)
    print(json.dumps({'output':str(target),'seed':args.seed,'hour':args.hour,'grid_km':args.grid_km,
                      'max_dbz':float(a['composite'].max()),'max_rainrate':float(a['rainrate'].max()),'max_cold':float(a['cold'].max())}))


if __name__=='__main__':main()
