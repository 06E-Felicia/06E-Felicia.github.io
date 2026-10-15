"""Same-seed radar comparison and causal trailing-water diagnostics."""
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
from .plot_process import project


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--before',required=True);ap.add_argument('--after',required=True)
    ap.add_argument('--output',required=True);ap.add_argument('--font',required=True)
    ap.add_argument('--seed',type=int,required=True);ap.add_argument('--grid-km',type=float,required=True)
    ap.add_argument('--hour',type=float,required=True);args=ap.parse_args()
    from matplotlib import font_manager
    font_manager.fontManager.addfont(args.font)
    plt.rcParams.update({'font.family':FontProperties(fname=args.font).get_name(),'axes.unicode_minus':False,
                         'font.size':11,'axes.titlesize':13})
    with np.load(args.before,allow_pickle=False) as f:old={key:f[key] for key in f.files}
    with np.load(args.after,allow_pickle=False) as f:new={key:f[key] for key in f.files}
    np.testing.assert_array_equal(old['lon'],new['lon']);np.testing.assert_array_equal(old['lat'],new['lat'])
    lon,lat=new['lon'],new['lat'];x,y=project(lon,lat)
    cfg=settings({'seed':args.seed,'grid_km':args.grid_km})
    height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    if height.shape!=lon.shape:raise ValueError('Terrain/snapshot mismatch')
    stations=json.loads(Path('assets/data/simulator-stations.json').read_text())['stations']
    names={'59431':'南宁','59265':'梧州','59287':'广州','59493':'深圳','59663':'阳江','59658':'湛江','59280':'清远'}
    colors=['#a8dcff','#469afa','#00cfdd','#36c84c','#069622','#8ac80f','#e4e600','#ffbd00','#ff7900','#ee2520','#b80038','#e900cc','#9d29ad']
    levels=np.arange(5,75,5);cmap=ListedColormap(colors)
    fig,axes=plt.subplots(2,2,figsize=(15,11),facecolor='white')
    for ax in axes.ravel():
        ax.set_facecolor('#edf4f7')
        ax.pcolormesh(x,y,np.ma.masked_where(height<=0,height),cmap='Greys',vmin=-500,vmax=4500,shading='nearest',rasterized=True)
        ax.contour(x,y,height,levels=[0],colors='#809497',linewidths=.45)
        ax.set_xlim(*project(np.array([106.5,116.5]),np.zeros(2))[0])
        ax.set_ylim(*project(np.zeros(2),np.array([20.4,25.8]))[1]);ax.set_aspect('equal')
        xx=np.arange(108,117,2);yy=np.arange(21,26)
        ax.set_xticks(project(xx,np.zeros_like(xx))[0],labels=[f'{v}°E' for v in xx])
        ax.set_yticks(project(np.zeros_like(yy),yy)[1],labels=[f'{v}°N' for v in yy]);ax.tick_params(labelsize=10)
        for s in stations:
            if s['id'] not in names:continue
            point=project(s['lon'],s['lat']);ax.plot(*point,'.',color='#33434f',ms=3,zorder=8)
            ax.annotate(names[s['id']],point,xytext=(3,3),textcoords='offset points',fontsize=9,
                        color='#253745',bbox={'facecolor':'white','edgecolor':'none','alpha':.75,'pad':.5},zorder=8)
    for ax,a,title in zip(axes[0],[old,new],['修正前 · 合成回波','修正后 · 合成回波']):
        im=ax.pcolormesh(x,y,np.ma.masked_less(a['composite'],5),cmap=cmap,norm=BoundaryNorm(levels,len(colors)),shading='nearest',rasterized=True)
        ax.contour(x,y,a['air'],levels=[.5],colors='#52516e',linewidths=.8)
        pool=np.minimum(a['cold'],a['cold_depth']/100)
        if np.max(pool)>1:ax.contour(x,y,pool,levels=[1],colors='#197b93',linewidths=.8,linestyles='--')
        ax.set_title(title,loc='left',pad=9)
        fig.colorbar(im,ax=ax,location='bottom',pad=.08,shrink=.9,aspect=35,ticks=np.arange(10,71,10)).set_label('dBZ · 实线冷锋 / 虚线冷池边界')
    ax=axes[1,0]
    im=ax.pcolormesh(x,y,np.ma.masked_less(new['anvil_column'],.01),cmap='Blues',vmin=0,vmax=max(.5,float(np.nanpercentile(new['anvil_column'],99.7))),shading='nearest',rasterized=True)
    ax.set_title('实际冰相凝结水柱含量',loc='left',pad=9)
    fig.colorbar(im,ax=ax,location='bottom',pad=.08,shrink=.9,aspect=35).set_label('kg/m² · 不能由冷池温差直接生成')
    ax=axes[1,1]
    im=ax.pcolormesh(x,y,np.ma.masked_less(new['stratiform_rainrate'],.1),cmap='YlGnBu',vmin=.1,vmax=max(2,float(np.nanpercentile(new['stratiform_rainrate'],99.7))),shading='nearest',rasterized=True)
    ax.set_title('冰相融化来源的地面降水',loc='left',pad=9)
    fig.colorbar(im,ax=ax,location='bottom',pad=.08,shrink=.9,aspect=35).set_label('mm/h · 示踪子集，非额外添加一份雨量')
    hour=8+args.hour;clock=f'第 {int(hour//24)+1} 天 {int(hour%24):02d}:{int(round(hour%1*60)):02d}'
    fig.suptitle(f'后部层状云雨检验  |  {clock}  |  {args.grid_km:g} km  |  种子 {args.seed}',x=.055,ha='left',y=.99,fontsize=17)
    fig.text(.055,.945,'相同初始设置、独立真实积分 · 同一雷达色标 · 无贴图 / 无回波增益 · 非实况、非业务预报',fontsize=11,color='#58636c')
    fig.subplots_adjust(left=.055,right=.98,top=.905,bottom=.06,hspace=.32,wspace=.13)
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(target,dpi=150,metadata={'Description':f'Actual model arrays, seed {args.seed}, hour {args.hour}; before {args.before}; after {args.after}'})
    plt.close(fig)
    print(json.dumps({'output':str(target),'seed':args.seed,'hour':args.hour,'ice_column_max':float(new['anvil_column'].max()),'stratiform_rainrate_max':float(new['stratiform_rainrate'].max())}))


if __name__=='__main__':main()
