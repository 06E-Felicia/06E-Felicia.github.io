"""Human-readable Actions evidence, with public counts only."""
import os
from .collect import DATA, STATUS, read_json


def summary(status):
    lines = ['## 飞常准实际数据覆盖', '',
             '保存成功不等于字段齐全；下表为本轮实际快照。图片还会按注册号在访客浏览器按需读取，不使用 MCP Key。', '',
             '| 机场 | 记录 | 注册号 | 机型 | 已预取图片 |', '| --- | ---: | ---: | ---: | ---: |']
    for code,state in (status.get('airports') or {}).items():
        c = state.get('detail_coverage') or {}
        lines.append('| %s | %d | %d | %d | %d |' % (code,c.get('total',0),c.get('registration',0),c.get('aircraft_type',0),c.get('photo',0)))
    stats = (status.get('enrichment') or {}).get('details') or {}
    lines += ['', '详情请求：%d 次批量调用，包含 %d 条航线，匹配 %d 班；待查询航线 %d 条。' % (
        stats.get('route_calls',0),stats.get('batch_routes',0),stats.get('matched',0),stats.get('pending_routes',0)),
        '自动采集每天北京时间12:00一次；手动运行立即执行，会使用积分。']
    if status.get('metadata_failed'):
        lines.append('\n**详情未取得注册号，本轮不能认定资料补齐成功。**')
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    output = summary(read_json(STATUS,{}))
    print(output)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write(output)
