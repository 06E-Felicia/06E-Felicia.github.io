import json
import os
import sys
from pathlib import Path

data=json.loads(Path(sys.argv[1]).read_text())
text='## 强对流模拟完成\n\n'
text+=f"模型 `{data['engine']}`；网格 {data['grid']['nominal_km']} km；主种子 {data['config']['seed']}。\n\n"
text+=f"模拟 {data['config']['hours']} 小时，输出 {len(data['frames'])} 帧，计算耗时 {data['elapsed_seconds']:.0f} 秒。\n\n"
text+='```json\n'+json.dumps(data['audit'],ensure_ascii=False,indent=2)+'\n```\n\n'
text+='简化物理过程实验，非业务数值预报；不保证出现两轮飑线。结果存档保留 90 天，过期后请重新运行。\n'
print(text)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf8') as f:f.write(text)
