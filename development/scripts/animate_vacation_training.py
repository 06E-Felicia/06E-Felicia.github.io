"""Render a verified 90-minute window directly from immutable production fields."""
import argparse,io,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.collections import LineCollection
from PIL import Image
from vacation_replay_data import load_manifest,read_frame

def render(directory,out):
 p=Path(directory);m=load_manifest(p);r=json.loads((p/'revision-analysis.json').read_text());w=r['regeneration'][0]
 tracks=json.loads((p/'structure-tracks.json').read_text());obj=next(o for f in tracks['frames'] for o in f['objects'] if o['objectId']==w['objectId'])
 g=m['grids']['radar'];cg=m['grids']['coldPool'];xx=np.array(obj['pixels'])%g['nx']*g['dx']/1000;yy=np.array(obj['pixels'])//g['nx']*g['dx']/1000
 ext=[0,g['width']/1000,0,g['height']/1000];lims=[max(0,xx.min()-35),min(ext[1],xx.max()+60),max(0,yy.min()-60),min(ext[3],yy.max()+35)]
 x=(np.arange(cg['nx'])+.5)*2.5;y=(np.arange(cg['ny'])+.5)*2.5
 fig,ax=plt.subplots(1,2,figsize=(11,5),layout='constrained');frames=[]
 cmap=ListedColormap(['#d7eef4','#8acee7','#4caae0','#3bca73','#f1e744','#fca13b','#f34638','#cc1d7c','#9052ac']);norm=BoundaryNorm([5,15,25,35,40,45,50,55,60,70],9)
 for e in m['frames']:
  if not w['start']<=e['simTime']<=w['end']:continue
  meta,f=read_frame(p,m,e);h=f['cold_depth'];delta=np.divide(f['cold_heat'],h,out=np.zeros_like(h),where=h>0)
  for a in ax:a.clear();a.set(xlim=lims[:2],ylim=lims[2:],xlabel='x (km)',ylabel='y (km)',aspect='equal');a.set_facecolor('#f5f7fa')
  ax[0].imshow(np.ma.masked_less(f['reflectivity_composite'],5),origin='lower',extent=ext,cmap=cmap,norm=norm,interpolation='nearest');ax[0].set_title('Composite radar | green ≥35, orange ≥45 dBZ')
  ax[1].imshow(np.ma.masked_where(h<5,delta),origin='lower',extent=ext,cmap='Blues',vmin=0,vmax=2.5,interpolation='nearest');ax[1].set_title('Cold deficit | white 0 → blue 2.5 K')
  for a in ax:
   a.contour(x,y,h,levels=[40,150,400],colors='#253858',linewidths=[.6,.9,1.2],alpha=.6);a.plot(w['x']/1000,w['y']/1000,'+',color='black',ms=12,mew=2)
  cells=[c for c in meta['cells'] if c['id'] in w['birthIDs']]
  if cells:ax[0].scatter([c['x']/1000 for c in cells],[c['y']/1000 for c in cells],s=30,facecolors='none',edgecolors='black',linewidths=.8)
  fig.suptitle(f'Seed {m["config"]["seed"]} — actual production fields — +{e["simTime"]/3600:.2f} h\nContours: cold depth 40/150/400 m; + passage location; circles: verified cell IDs',fontsize=12)
  buf=io.BytesIO();fig.savefig(buf,format='png',dpi=90);buf.seek(0);frames.append(Image.open(buf).convert('RGB'))
 frames[0].save(out,save_all=True,append_images=frames[1:],duration=160,loop=0);plt.close(fig)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('directory');a.add_argument('output');args=a.parse_args();render(args.directory,args.output)
