"""Plot native model radar/cold fields and real IDs from a fixed birth box."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Rectangle
import numpy as np
from pyproj import Transformer
from vacation_replay_data import load_manifest, read_frame

parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--output');parser.add_argument('--source-near',nargs=2,type=float,metavar=('LON','LAT'));parser.add_argument('--start-hours',type=float);args=parser.parse_args()
root=Path(args.directory);manifest=load_manifest(root);analysis=json.loads((root/'birth-cycle-analysis.json').read_text())
sources=analysis['repeatedSources']
if not sources: raise SystemExit('No qualifying fixed birth region; do not fabricate a training diagram.')
source=next((s for s in sources if s['environmentBirths']>=3 and s['terrainRiseMedianM']>=50),sources[0])
if args.source_near:
    tx,ty=Transformer.from_crs('EPSG:4326',manifest['projection'],always_xy=True).transform(*args.source_near)
    origin=manifest['grids']['environment']['origin'];tx-=origin[0];ty-=origin[1]
    source=min(sources,key=lambda s:np.hypot((s['boxM'][0]+s['boxM'][2])/2-tx,(s['boxM'][1]+s['boxM'][3])/2-ty))
box=np.array(source['boxM'])/1000;ids=set(source['ids'])
start=source['firstBirth'];end=manifest['frames'][-1]['simTime']
targets=[min(end,round(((args.start_hours if args.start_hours is not None else start/3600+1)+d)*6)/6*3600) for d in (0,1,2)]
entries=[min(manifest['frames'],key=lambda e:abs(e['simTime']-t)) for t in targets]
colors=['#2754a3','#2385c2','#29b4d9','#26baa0','#32b745','#7aca4a','#dfdd38','#f4bc32','#f58b26','#eb5535','#d32b50','#b72873']
bounds=list(range(5,70,5));cmap=ListedColormap(colors);norm=BoundaryNorm(bounds,len(colors));cmap.set_bad((0,0,0,0))
g=manifest['grids'];extent=lambda name:(0,g[name]['width']/1000,0,g[name]['height']/1000)
xlim=(max(0,box[0]-90),min(g['radar']['width']/1000,box[2]+140));ylim=(max(0,box[1]-100),min(g['radar']['height']/1000,box[3]+100))
fig,axes=plt.subplots(2,3,figsize=(14,8.5),layout='constrained')
to_xy=Transformer.from_crs('EPSG:4326',manifest['projection'],always_xy=True)
cities=[('Shiwan Mts',107.8,21.9),('Chongzuo',107.36,22.42),('Fangchenggang',108.39,21.67),('Qinzhou',108.62,21.96),('Yangjiang',111.98,21.86),('Guangzhou',113.26,23.13),('Shenzhen',114.00,22.54),('Shanwei',115.36,22.78),('Shantou',116.68,23.35)]
for col,entry in enumerate(entries):
    md,f=read_frame(root,manifest,entry)
    for row in range(2):
        ax=axes[row,col];ax.imshow(f['z'],origin='lower',extent=extent('environment'),cmap='Greys',vmin=0,vmax=1000,alpha=.35,interpolation='nearest')
        if row==0:
            image=ax.imshow(np.ma.masked_less(f['reflectivity_composite'],5),origin='lower',extent=extent('radar'),cmap=cmap,norm=norm,interpolation='nearest',alpha=.95)
        else:
            h=f['cold_depth'];delta=np.divide(f['cold_heat'],h,out=np.zeros_like(h),where=h>0)
            cold_image=ax.imshow(np.ma.masked_where(h<10,delta),origin='lower',extent=extent('coldPool'),cmap='PuBu',vmin=0,vmax=2.5,interpolation='nearest',alpha=.9)
        eg=g['environment'];xs=(np.arange(eg['nx'])+.5)*eg['dx']/1000;ys=(np.arange(eg['ny'])+.5)*eg['dx']/1000
        ax.contour(xs,ys,f['land'],levels=[.5],colors=['#626776'],linewidths=.5)
        ax.add_patch(Rectangle((box[0],box[1]),20,20,fill=False,edgecolor='#d2187d',linewidth=2))
        cells=[c for c in md['cells'] if c['id'] in ids and c['a']>=.1]
        if cells: ax.scatter([c['x']/1000 for c in cells],[c['y']/1000 for c in cells],s=42,facecolors='none',edgecolors='black',linewidths=1)
        for name,lon,lat in cities:
            x,y=to_xy.transform(lon,lat);x=(x-eg['origin'][0])/1000;y=(y-eg['origin'][1])/1000
            if xlim[0]<x<xlim[1] and ylim[0]<y<ylim[1]:
                ax.plot(x,y,'.',color='#393348',ms=3);right=x>xlim[1]-55
                ax.text(x-2 if right else x+2,y+2,name,ha='right' if right else 'left',fontsize=7,color='#393348')
        ax.set(xlim=xlim,ylim=ylim,aspect='equal');ax.tick_params(labelsize=8)
        ax.set_title(('Radar' if row==0 else 'Cold pool')+f" | t={entry['simTime']/3600:.1f} h",fontsize=11)
        if row==1:ax.set_xlabel('Model easting (km)')
        if col==0:ax.set_ylabel('Model northing (km)')
fig.colorbar(image,ax=axes[0,:],shrink=.8,pad=.02,label='Reflectivity (dBZ)',ticks=[5,15,25,35,45,55,65])
fig.colorbar(cold_image,ax=axes[1,:],shrink=.8,pad=.02,label='Cold-pool temperature deficit (K)')
fig.suptitle(f"{manifest['model']} | {root.name} | 600 s physical step\nPink: fixed 20 km birth region; rings: its mobile active cell IDs. Native fields; no synthetic radar shapes.",fontsize=12)
out=Path(args.output) if args.output else root/'birth-cycles.png';fig.savefig(out,dpi=160);out.with_suffix('.json').write_text(json.dumps({'source':source,'timesSeconds':[e['simTime'] for e in entries],'selectionNearLonLat':args.source_near},indent=2));print(out)
