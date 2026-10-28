"""Plot archived physical radar and cold fields; no weather synthesis or smoothing."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.collections import LineCollection
from vacation_replay_data import load_manifest,read_frame

def plot(directory,out):
 p=Path(directory);m=load_manifest(p);r=json.loads((p/'revision-analysis.json').read_text())
 evidence=(r['regeneration'] or r['persistentBands']);start=evidence[0]['start'] if evidence else 7200
 times=[start+i*1800 for i in range(4)]
 fig,axs=plt.subplots(2,4,figsize=(16,8),layout='constrained',sharex=True,sharey=True)
 colors=['#d7eef4','#8acee7','#4caae0','#3bca73','#f1e744','#fca13b','#f34638','#cc1d7c','#9052ac'];bounds=[5,15,25,35,40,45,50,55,60,70]
 cmap=ListedColormap(colors);norm=BoundaryNorm(bounds,cmap.N)
 cg=m['grids']['coldPool'];g=m['grids']['radar'];extent=[0,g['width']/1000,0,g['height']/1000];x=(np.arange(cg['nx'])+.5)*cg['dx']/1000;y=(np.arange(cg['ny'])+.5)*cg['dx']/1000
 coast=[]
 if m['config']['geography']=='real':
  coast=[np.asarray(line)/1000+np.array([g['width'],g['height']])/2000 for line in json.loads((Path(__file__).resolve().parents[2]/'assets/data/vacation-coastlines.json').read_text())['coordinates']]
 for j,t in enumerate(times):
  e=min(m['frames'],key=lambda e:abs(e['simTime']-t));meta,f=read_frame(p,m,e);h=f['cold_depth'];q=f['cold_heat'];delta=np.divide(q,h,out=np.zeros_like(q),where=h>0)
  z=axs[0,j].imshow(np.ma.masked_less(f['reflectivity_composite'],5),origin='lower',extent=extent,cmap=cmap,norm=norm,interpolation='nearest')
  c=axs[1,j].imshow(np.ma.masked_where(h<5,delta),origin='lower',extent=extent,cmap='Blues',vmin=0,vmax=2.5,interpolation='nearest')
  for row in [0,1]:
   ax=axs[row,j];ax.contour(x,y,h,levels=[40,150,400],colors=['#17365d'],linewidths=[.6,.9,1.2],alpha=.65);ax.set_aspect('equal');ax.set_xlabel('x (km)')
   if coast:ax.add_collection(LineCollection(coast,colors='#8c8172',linewidths=.55,alpha=.75));ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:])
  axs[0,j].set_title(f'{e["simTime"]/3600:.2f} h')
  if r['regeneration']:
   point=r['regeneration'][0]
   for row in [0,1]:axs[row,j].plot(point['x']/1000,point['y']/1000,'+',color='black',ms=9,mew=1.5)
  axs[1,j].text(.02,.02,f'h max {h.max():.0f} m\nA(h >= 40 m) {(h>=40).sum()*6.25:.0f} km²',transform=axs[1,j].transAxes,fontsize=8,bbox=dict(facecolor='white',alpha=.75,edgecolor='none'))
 axs[0,0].set_ylabel('Radar / y (km)');axs[1,0].set_ylabel('Cold deficit / y (km)')
 fig.colorbar(z,ax=axs[0,:],label='Composite reflectivity (dBZ)',shrink=.8);fig.colorbar(c,ax=axs[1,:],label='Cold temperature deficit (K)',shrink=.8)
 fig.suptitle(f'Physical fields — seed {m["config"]["seed"]}, {m["config"]["geography"]}\nContours: cold depth 40 / 150 / 400 m; + first independently verified training location',fontsize=13)
 fig.savefig(out,dpi=140);plt.close(fig)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('directory');a.add_argument('output');args=a.parse_args();plot(args.directory,args.output)
