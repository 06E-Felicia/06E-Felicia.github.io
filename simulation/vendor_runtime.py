"""Vendor a pinned Pyodide runtime and exactly the NumPy/SciPy dependency set.

Static assets only; no package manager execution, no arbitrary wheel install.
Package SHA-256 is verified against the pinned upstream lockfile.
"""
import hashlib
import json
from pathlib import Path
import time
import urllib.request

BASE='https://cdn.jsdelivr.net/pyodide/v0.28.3/full/'
LICENSE_BASE='https://cdn.jsdelivr.net/gh/pyodide/pyodide@0.28.3/'
DEST=Path('assets/vendor/pyodide')


def fetch(name, digest=None, source=BASE):
    if '/' in name or name.startswith('.'):raise ValueError('Unsafe runtime asset name')
    target=DEST/name
    if target.exists() and digest and hashlib.sha256(target.read_bytes()).hexdigest()==digest:return
    for attempt in range(3):
        try:
            with urllib.request.urlopen(source+name,timeout=30) as response:data=response.read()
            if digest and hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Runtime checksum mismatch: '+name)
            target.write_bytes(data);print(name,len(data),flush=True);return
        except Exception:
            if attempt==2:raise
            time.sleep(1+attempt)


def main():
    DEST.mkdir(parents=True,exist_ok=True)
    fetch('pyodide-lock.json')
    lock=json.loads((DEST/'pyodide-lock.json').read_text());packages=lock['packages'];done=set()
    def package(name):
        if name in done:return
        item=packages[name]
        for dependency in item.get('depends',[]):package(dependency)
        fetch(item['file_name'],item['sha256']);done.add(name)
    for name in ['pyodide.js','pyodide.asm.js','pyodide.asm.wasm','python_stdlib.zip']:fetch(name)
    package('numpy');package('scipy')
    fetch('LICENSE',source=LICENSE_BASE)
    manifest={'version':'0.28.3','source':BASE,'packages':sorted(done),
              'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DEST.iterdir()) if p.is_file() and p.name!='checksums.json'}}
    (DEST/'checksums.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
