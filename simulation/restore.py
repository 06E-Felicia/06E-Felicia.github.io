"""Restore latest successful simulation artifact before ANY Pages deployment.

Keeps large generated fields out of Git history. Uses GitHub's bundled `gh`
client for authenticated redirects, never logs tokens, validates zip paths.
"""
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


def restore(repository, destination):
    result=subprocess.run(['gh','api',f'repos/{repository}/actions/artifacts?name=simulation-results&per_page=30'],check=True,capture_output=True)
    artifacts=[a for a in json.loads(result.stdout)['artifacts'] if not a['expired']]
    if not artifacts:
        print('No retained simulation artifact; website will explicitly show no results.');return False
    artifact=max(artifacts,key=lambda a:a['created_at'])
    blob=subprocess.run(['gh','api',f"repos/{repository}/actions/artifacts/{artifact['id']}/zip"],check=True,capture_output=True).stdout
    dest=Path(destination)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names=archive.namelist()
        if 'manifest.json' not in names:raise ValueError('Simulation manifest missing from artifact')
        if sum(x.file_size for x in archive.infolist())>500*1024**2:raise ValueError('Artifact exceeds size limit')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('schema')!=2 or manifest.get('status')!='complete':raise ValueError('Incomplete/unsupported simulation')
        allowed={'manifest.json'}|{f['file'] for f in manifest['frames']}
        for name in names:
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or len(p.parts)!=1 or name not in allowed:raise ValueError('Unexpected artifact path')
        dest.mkdir(parents=True,exist_ok=True)
        for name in names:(dest/name).write_bytes(archive.read(name))
    print(f"Restored simulation artifact {artifact['id']} ({len(manifest['frames'])} frames)")
    return True


if __name__=='__main__':restore(os.environ['GITHUB_REPOSITORY'],'assets/simulation')
