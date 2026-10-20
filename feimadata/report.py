"""Human-readable Actions evidence, with public counts only."""
import os
from .collect import DATA, STATUS, read_json


def summary(status):
    lines = ['## 飞常准实际数据覆盖', '',
             '保存成功不等于字段齐全；下表为本轮实际快照。图片还会按注册号在访客浏览器按需读取，不使用 MCP Key。', '',
             '| 机场 | 记录 | 注册号 | 机型 | 已预取图片 | 当日已识别精选机号 |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for code,state in (status.get('airports') or {}).items():
        c = state.get('detail_coverage') or {}
        lines.append('| %s | %d | %d | %d | %d | %d/%d |' % (code,c.get('total',0),c.get('registration',0),c.get('aircraft_type',0),c.get('photo',0),c.get('selected_registration',0),c.get('selected_total',0)))
    stats = (status.get('enrichment') or {}).get('details') or {}
    lines += ['', '详情请求：共 %d 次（含 %d 次精选缺号单班补查），批量包含 %d 条航线，匹配 %d 班；待查询航线 %d 条。' % (
        stats.get('route_calls',0),stats.get('single_calls',0),stats.get('batch_routes',0),stats.get('matched',0),stats.get('pending_routes',0)),
        '仅深圳；北京时间每天06:00、14:00更新。手动运行同样受每日共享额度限制。']
    budget = status.get('daily_detail_budget') or {}
    if budget:
        lines.append('当日详情已使用 %d/%d 次，剩余 %d 次（批量、单班、失败请求共计）。' % (
            budget.get('used',0),budget.get('limit',200),budget.get('remaining',0)))
    if status.get('metadata_failed'):
        lines.append('\n**详情未取得注册号，本轮不能认定资料补齐成功。**')
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    output = summary(read_json(STATUS,{}))
    print(output)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write(output)
