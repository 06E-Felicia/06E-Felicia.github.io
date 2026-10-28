"""Verify replay endpoints, all native fields, source/image hashes and the decoded MP4."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import sys
extra=Path(os.environ.get('VACATION_REPLAY_DEPS',str(Path.home()/'.cache/vacation-replay/python')))
if extra.is_dir():sys.path.insert(0,str(extra))
if Path('/tmp/vacation-replay-tools').is_dir():sys.path.insert(0,'/tmp/vacation-replay-tools')
from PIL import Image
import numpy as np
from vacation_replay_data import load_manifest,read_frame,local_file


def verify(directory,video=True):
    directory=Path(directory).resolve();manifest=load_manifest(directory)
    if manifest.get('renderStatus')!='complete':raise ValueError('Images/video incomplete')
    report=json.loads((directory/'report.json').read_text())
    if report['steps']*manifest['physicsStepSeconds']!=manifest['config']['hours']*3600:raise ValueError('Physical steps do not cover complete duration')
    previous=-1
    for entry in manifest['frames']:
        metadata,fields=read_frame(directory,manifest,entry)
        if entry['simTime']<=previous:raise ValueError('Non-monotonic frames')
        if previous>=0 and entry['simTime']-previous>manifest['frameIntervalSeconds']:raise ValueError('Missing frame interval')
        previous=entry['simTime']
        for key in ['rain_rate','rain_total','cold_depth','cold_heat']:
            if not np.all(np.isfinite(fields[key])) or np.any(fields[key]<0):raise ValueError('Invalid native field '+key)
        raw=local_file(directory,entry['image']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['imageSha256']:raise ValueError('Image checksum mismatch')
        with Image.open(local_file(directory,entry['image'])) as image:image.verify()
    for spec in manifest['source'].values():
        if hashlib.sha256(local_file(directory,spec['path']).read_bytes()).hexdigest()!=spec['sha256']:raise ValueError('Source checksum mismatch')
    if hashlib.sha256((directory/manifest['visuals']['video']).read_bytes()).hexdigest()!=manifest['videoSha256']:raise ValueError('Video checksum mismatch')
    decoded=None
    if video:
        import imageio_ffmpeg
        stream=imageio_ffmpeg.read_frames(str(directory/manifest['visuals']['video']),pix_fmt='rgb24')
        info=next(stream);decoded=sum(1 for _ in stream)
        if decoded!=len(manifest['frames']):raise ValueError('Video frame count mismatch')
    result={'status':'complete','verifiedFrames':len(manifest['frames']),'decodedVideoFrames':decoded,'simulationHours':manifest['config']['hours'],'verifiedSourceFiles':len(manifest['source']),'waterResidual':report['audit']['relativeResidual']}
    (directory/'verification.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--no-video',action='store_true');a=p.parse_args()
    print(json.dumps(verify(a.directory,not a.no_video)))
