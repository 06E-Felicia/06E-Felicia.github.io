"""Read and verify native Vacation replay fields; never run the integrator."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np


def local_file(directory, relative):
    directory = Path(directory).resolve()
    target = (directory / relative).resolve()
    if not target.is_relative_to(directory):
        raise ValueError('Archive path escapes the replay folder')
    return target


def load_manifest(directory, complete=True):
    manifest = json.loads((Path(directory) / 'manifest.json').read_text())
    if manifest.get('schema') != 'vacation-replay-v1':
        raise ValueError('Unsupported replay schema')
    if complete and manifest.get('status') != 'complete':
        raise ValueError('Simulation is incomplete')
    frames = manifest['frames']
    if not frames or frames[0]['simTime'] != 0:
        raise ValueError('Missing initial frame')
    times = [f['simTime'] for f in frames]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('Non-monotonic archive')
    if complete and times[-1] != manifest['config']['hours'] * 3600:
        raise ValueError('Missing final frame')
    return manifest


def read_frame(directory, manifest, entry):
    compressed = local_file(directory, entry['raw']).read_bytes()
    if hashlib.sha256(compressed).hexdigest() != entry['sha256']:
        raise ValueError('Frame checksum mismatch: ' + entry['raw'])
    metadata_raw = local_file(directory, entry['data']).read_bytes()
    if entry.get('metadataSha256') and hashlib.sha256(metadata_raw).hexdigest() != entry['metadataSha256']:
        raise ValueError('Frame metadata checksum mismatch')
    codec = manifest.get('metadataCodec', 'json')
    if codec == 'gzip-json':
        metadata_raw = gzip.decompress(metadata_raw)
    elif codec != 'json':
        raise ValueError('Unsupported frame metadata codec: ' + str(codec))
    metadata = json.loads(metadata_raw)
    raw = gzip.decompress(compressed)
    if len(raw) != metadata['uncompressedBytes'] or metadata['simTime'] != entry['simTime']:
        raise ValueError('Frame size/time mismatch')
    fields = {}
    for key, spec in metadata['fields'].items():
        grid = manifest['grids'][spec['grid']]
        dtype = np.dtype(spec['dtype'])
        count = grid['nx'] * grid['ny']
        if spec['bytes'] != count * dtype.itemsize or spec['offset'] + spec['bytes'] > len(raw):
            raise ValueError('Invalid field layout: ' + key)
        encoded = np.frombuffer(raw, dtype=dtype, count=count, offset=spec['offset']).reshape(grid['ny'], grid['nx'])
        decoded = encoded.astype(np.float64) * spec['scale'] + spec['addOffset']
        if spec['noData'] is not None:
            decoded[encoded == spec['noData']] = np.nan
        fields[key] = decoded
    return metadata, fields
