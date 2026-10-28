"""Record a complete process, then render and publish its offline AI replay."""
import argparse
from datetime import datetime
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours',type=float,default=72);parser.add_argument('--minutes',type=int,default=10)
    parser.add_argument('--quality',choices=['low','standard','high'],default='low');parser.add_argument('--seed',type=int)
    args=parser.parse_args()
    node=shutil.which('node') or str(RUNTIME/'node/bin/node')
    python=os.environ.get('VACATION_REPLAY_PYTHON') or (str(RUNTIME/'python/bin/python3') if (RUNTIME/'python/bin/python3').is_file() else sys.executable)
    if not Path(node).is_file():parser.exit(1,'需要 Node.js 或 Codex 工作区运行时。\n')
    env=os.environ.copy();extra=Path(env.get('VACATION_REPLAY_DEPS',str(Path.home()/'.cache/vacation-replay/python')))
    paths=[str(extra),'/tmp/vacation-replay-tools',env.get('PYTHONPATH','')];env['PYTHONPATH']=os.pathsep.join(paths)
    check=subprocess.run([python,'-c','import numpy, matplotlib, PIL, imageio_ffmpeg'],env=env,capture_output=True)
    if check.returncode:parser.exit(1,'缺少渲染依赖。请按 VACATION.md 安装 development/scripts/requirements-vacation-replay.txt。\n')
    name=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')
    output=ROOT/'simulation/vacation-replays'/name
    command=[node,str(ROOT/'development/scripts/record_vacation_replay.cjs'),'--output='+str(output),'--hours='+str(args.hours),'--minutes='+str(args.minutes),'--quality='+args.quality]
    if args.seed is not None:command.append('--seed='+str(args.seed))
    subprocess.run(command,cwd=ROOT,env=env,check=True)
    subprocess.run([python,str(ROOT/'development/scripts/render_vacation_replay.py'),str(output)],cwd=ROOT,env=env,check=True)
    print('回放已完成：'+str(output/'index.html'),flush=True)


if __name__=='__main__':main()
