# Feimadat · 深圳航班精选

Feimadat 当前暂停开放：网站入口已隐藏，访问 `Feimadat.html` 自动转到 Flightdat。代码和快照保留，方便将来恢复；Flightdat 保持七机场及自己的 FR24 采集逻辑。

## 更新与额度

- 工作流 `.github/workflows/feimadata.yml` 已移除全部定时触发，仅保留手动运行。不会再每天自动调用飞常准。
- 手动任务共用**每日最多200次详情请求**，不是每次200。批量、精选缺号单班补查、失败尝试都计数；缓存命中不计数。现有额度规则仍为14时前最多100次，14时后可使用全天剩余额度。日期按北京时间重置。
- 手动运行也受相同日额度限制。额度在请求前写入独立缓存及公开状态，不因重启或正常失败重置。新规则启用后开始记账；历史版本未记录的调用无法追溯。
- 大屏每轮只请求深圳到达、出发各一次；大屏调用与详情调用为不同工具，上述200次是详情上限，不等同于账号积分。实际计费以飞常准规则为准。
- 照片元数据每轮服务器最多预取60个注册号；其余可在浏览器按需读取，不消耗飞常准积分。网页刷新只读取快照，不启动采集。

## 筛选与字段补全

列表仅收录已识别的彩绘、宽体、四发、货机或外航；普通窄体机和未识别记录不显示。货运、外航等接口缺少可靠属性时保持未知，不猜测。计数、搜索、历史展开使用相同精选条件，只计当前至当日结束。

大屏接口常不提供普通航班机号与机型。使用 `getFlightStatus` 补充，严格匹配**航班号、起飞日期、起降机场、计划起飞钟点**；不按数组顺序或单独航班号关联，不借用历史机号。航线批次最多合并8个机场、只固定一侧端点为深圳；服务超时在预算内拆小重试一次，401/403/429停止，不绕过限流。

部分批量结果只有机型摘要；对当日精选缺号记录增加单班补查，优先未来航班。已实测 JL325 批量摘要缺号，单班详情能返回注册号，但不能据此保证所有航班均有数据。达到额度、时间限制或源站仍缺字段时保留空缺，Actions 摘要显示真实覆盖率，不把任务成功冒充资料全部齐全。

## 图片

所有图片（包括彩绘机）仅用 **PlaneSpotters.net 同注册号资料照**，附摄影师、来源链接与“非本航班实拍”说明。不再使用飞常准主题图，旧快照主题图也会被网页拒绝。找不到照片就留空。

可只读复用网站已有、带署名和来源的 P 网照片缓存，但不引入其他页面的航班、机型或注册号数据。照片按注册号隔离，换机后不复用旧飞机图片；成功缓存30天，无照片缓存7天。浏览器限制并发，遭拒绝或限流时停止，不循环请求。

## 配置与本地使用

1. 双击 `development/launchers/配置飞常准.command`，隐藏输入 MCP Key。macOS 密钥在当前用户 `Library/Application Support/Feimadat/mcp-key`，目录700、文件600，不在项目或网页目录。
2. 双击 `development/launchers/更新飞常准.command`，确认额度消耗后仅更新深圳；或运行 `python3 -B -m feimadata.collect --airports SZX`。
3. 页面当前暂停开放；如需恢复，先撤除 `Feimadat.html` 中标记的暂停区块，再恢复导航入口。恢复页面不会自动恢复 Actions 定时任务。

GitHub 仓库 Secret 为 `VARIFLIGHT_MCP_KEY`。密钥只在 Header 发送到官方固定主机，不跟随重定向，不进入网页、URL、公开JSON、日志或聊天。公开快照发布前进行隐私检查，私有缓存不进入 Pages。

`python3 -B -m feimadata.collect --enrich-only --detail-limit 0 --photo-limit 0` 仅复用已核验缓存，不新增接口请求，也不伪造大屏采集时间或云端运行来源。

## 数据与测试

配置在 `data/index.json`，深圳快照在 `data/szx.json`，状态及日额度在 `data/status.json`。其他机场旧快照保留但不查询、不提供页面入口。新一天清除前一天累计；同日失败保留此前可用记录。不宣称接口包含当天全部航班；未提供的字段不作推测。

两页保留“显示之前时刻”与手动定位按钮。列表时间统一为北京时间，实际时间优先于预计时间；每日快照不能保证反映之后的临时换机，实际运行以机场、航司为准。

离线回归：`python3 -B -m unittest discover -s tests -p 'test_feimadata.py' -v`；界面回归：`node development/tests/test_feimadat_browser.cjs` 与 `node development/tests/test_flightdata_browser.cjs`（需本机 Playwright/Chrome）。测试不调用收费接口。

官方文档：[机场大屏](https://cmcp.variflight.com/zh/tools/#getAirportFlightBoard)、[航班详情](https://cmcp.variflight.com/zh/tools/#getFlightStatus)。
