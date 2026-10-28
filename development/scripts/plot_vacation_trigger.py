"""Plot immutable fields and actual cell IDs; no interpolation of weather."""
import argparse, json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle
from vacation_replay_data import load_manifest, read_frame


def plot(directory, output):
    p = Path(directory)
    m = load_manifest(p)
    a = json.loads((p / 'revision-analysis.json').read_text())
    w = a['regeneration'][0]
    g, eg, cg = (m['grids'][k] for k in ['radar', 'environment', 'coldPool'])
    extent = [0, g['width']/1000, 0, g['height']/1000]
    lim = [w['x']/1000-75, w['x']/1000+175, w['y']/1000-75, w['y']/1000+100]
    coast = [np.asarray(line)/1000+np.array([g['width'], g['height']])/2000
             for line in json.loads((Path(__file__).resolve().parents[2]/'assets/data/vacation-coastlines.json').read_text())['coordinates']]
    x = (np.arange(cg['nx'])+.5)*cg['dx']/1000
    y = (np.arange(cg['ny'])+.5)*cg['dx']/1000
    ex = (np.arange(eg['nx'])+.5)*eg['dx']/1000
    ey = (np.arange(eg['ny'])+.5)*eg['dx']/1000
    cmap = ListedColormap(['#d7eef4','#8acee7','#4caae0','#3bca73','#f1e744','#fca13b','#f34638','#cc1d7c','#9052ac'])
    norm = BoundaryNorm([5,15,25,35,40,45,50,55,60,70], 9)
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.6), layout='constrained', sharex=True, sharey=True)
    for j, t in enumerate([w['start'], (w['start']+w['end'])/2, w['end']]):
        e = min(m['frames'], key=lambda e: abs(e['simTime']-t))
        meta, f = read_frame(p, m, e)
        h = f['cold_depth']
        delta = np.divide(f['cold_heat'], h, out=np.zeros_like(h), where=h>0)
        for row in range(2):
            ax = axes[row, j]
            ax.imshow(f['z'], origin='lower', extent=extent, cmap='Greys', vmin=0, vmax=1800, alpha=.2)
            ax.contour(ex, ey, f['z'], levels=[200,500,1000], colors='#99947b', linewidths=.5, alpha=.5)
            ax.add_collection(LineCollection(coast, colors='#6a706d', linewidths=.7))
            ax.set(xlim=lim[:2], ylim=lim[2:], aspect='equal', xlabel='x (km)')
            ax.plot(w['x']/1000, w['y']/1000, '+', color='#151725', ms=12, mew=1.6)
        r = axes[0,j].imshow(np.ma.masked_less(f['reflectivity_composite'],5), origin='lower', extent=extent, cmap=cmap, norm=norm, interpolation='nearest')
        c = axes[1,j].imshow(np.ma.masked_where(h<5,delta), origin='lower', extent=extent, cmap='Blues', vmin=0, vmax=2.5, interpolation='nearest')
        axes[1,j].contour(x,y,h, levels=[40,150,400], colors='#283f5a', linewidths=[.6,.9,1.2])
        cells = [cell for cell in meta['cells'] if cell['id'] in w['birthIDs']]
        axes[0,j].scatter([c['x']/1000 for c in cells], [c['y']/1000 for c in cells], s=35, facecolors='none', edgecolors='black', linewidths=.8)
        axes[0,j].set_title(f'Radar  +{e["simTime"]/3600:.2f} h')
        axes[1,j].set_title(f'Cold pool  +{e["simTime"]/3600:.2f} h')
        if j == 0:
            inset = axes[0,j].inset_axes([.025,.66,.28,.31])
            inset.imshow(f['land'], origin='lower', extent=extent, cmap='Greys', alpha=.3)
            inset.imshow(np.ma.masked_less(f['reflectivity_composite'],5), origin='lower', extent=extent, cmap=cmap,norm=norm)
            inset.add_patch(Rectangle((lim[0],lim[2]),lim[1]-lim[0],lim[3]-lim[2],fill=False,ec='#a72e5b',lw=1))
            inset.set(xticks=[],yticks=[],title='Full domain')
    axes[0,0].set_ylabel('Radar / y (km)')
    axes[1,0].set_ylabel('Cold pool / y (km)')
    fig.colorbar(r, ax=axes[0,:], label='Reflectivity (dBZ)', shrink=.85)
    fig.colorbar(c, ax=axes[1,:], label='Temperature deficit (K)', shrink=.85)
    fig.suptitle(f'{m["model"]} | seed {m["config"]["seed"]} | actual production fields\n'
                 'Terrain contours: 200 / 500 / 1000 m; cold depth: 40 / 150 / 400 m\n'
                 '+ repeated passage location; circles: independently tracked cell IDs', fontsize=12)
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory');parser.add_argument('output')
    args=parser.parse_args();plot(args.directory,args.output)
