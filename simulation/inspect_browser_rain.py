"""Postprocess already saved browser fields; never starts a simulation."""
import argparse
import base64
import gzip
import json
import numpy as np


def unpack(packet):
    return np.frombuffer(base64.b64decode(packet['data']),dtype='<i2').reshape(packet['shape'])*packet['scale']+packet['offset']


def main():
    ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('--plot',required=True);args=ap.parse_args()
    opener=gzip.open if args.input.endswith('.gz') else open
    with opener(args.input,'rt') as file:raw=json.load(file)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap,BoundaryNorm
    colors=['#42a9f4','#23a4df','#1ecc67','#2fba34','#d3dd2d','#f3d32f','#f29127','#ee4c24','#ce243b','#b32765','#a65aaa']
    cmap=ListedColormap(colors);cmap.set_bad((0,0,0,0));norm=BoundaryNorm(np.arange(5,65,5),len(colors))
    g=raw['manifest']['grid'];extent=[g['west'],g['west']+(g['nx']-1)*g['dlon'],g['south'],g['south']+(g['ny']-1)*g['dlat']]
    fig,axes=plt.subplots(2,3,figsize=(15,7),layout='constrained')
    rows={round(f['hour']):f['fields'] for f in raw['fields']}
    for j,hour in enumerate([6,36,60]):
        z=unpack(rows[hour]['composite']);rain=unpack(rows[hour]['rainrate'])
        for ax in axes[:,j]:ax.set_facecolor('#e9eef4');ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);ax.grid(alpha=.2)
        image=axes[0,j].imshow(np.ma.masked_less(z,5),origin='lower',extent=extent,cmap=cmap,norm=norm,aspect='auto');axes[0,j].set_title(f'{hour} h · composite dBZ')
        rate=axes[1,j].imshow(np.ma.masked_less(rain,.1),origin='lower',extent=extent,cmap='turbo',vmin=0,vmax=25,aspect='auto');axes[1,j].set_title(f'{hour} h · native mean mm/h')
    fig.colorbar(image,ax=axes[0,:],label='dBZ');fig.colorbar(rate,ax=axes[1,:],label='mm/h')
    fig.suptitle('StormSim 1.2 Sol · actual 72-hour browser integration · boundary audit (no new run)')
    fig.savefig(args.plot,dpi=140);plt.close(fig)


if __name__=='__main__':main()
