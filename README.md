# 深中气象

深圳中学气象社的网站项目，集成深圳天气与预警展示、华南强对流模拟、暖区暴雨互动游戏，以及保留中的航班数据页面。网站使用 GitHub Pages 发布；天气快照由 GitHub Actions 更新，模拟器在访客浏览器中计算。

[网站首页](https://06e-felicia.github.io/) · [放假模拟器](https://06e-felicia.github.io/Vacation.html) · [StormSim Astra](https://06e-felicia.github.io/simulator.html) · [StormSim Sol](https://06e-felicia.github.io/simulator-sol.html)

## 页面与功能

| 页面 | 内容 |
| --- | --- |
| [index.html](index.html) | 深圳当前天气、网站导航、上游雷暴抵达估测 |
| [forecast.html](forecast.html) | 一周天气预报 |
| [warnings.html](warnings.html) | 官方预警快照与官方查询入口 |
| [Vacation.html](Vacation.html) | 放假模拟器：暖区暴雨、列车回波、深圳模拟预警与三天作业决策游戏 |
| [simulator.html](simulator.html) | StormSim 2.5 Astra，较精细的华南强对流过程模拟 |
| [simulator-sol.html](simulator-sol.html) | StormSim 2.5 Sol，28 km 网格版本 |
| [VacationReplay.html](VacationReplay.html) | 已生成的放假模拟器离线回放查看器 |
| [Flightdat.html](Flightdat.html) | 航班精选，当前处于维护状态，自动采集已暂停 |
| [Feimadat.html](Feimadat.html) | 保留的飞常准页面与数据工具，非默认公开入口，采集工作流仅手动运行 |
| [agent.html](agent.html) | 智能体跳转入口 |

天气页展示公开来源的数据快照，与模拟器生成的天气互相独立。上游雷暴抵达时间采用发布时间、位置与假定传播速度估算，并不是实际雷达外推。真实预警与停课安排请以气象部门及学校通知为准。

## 放假模拟器

当前模型版本：**vacation-1.43.0**。这是面向华南暖区暴雨的参数化模拟和互动游戏，不是业务天气预报，也不保证每个随机环境都产生暴雨。

### 模拟过程

- 每轮从前一日 20:00 开始，运行 72 小时。主物理步长为 10 分钟；守恒输送和冷池传播在必要时使用稳定数值子循环。
- 每轮随机生成环境；季风在三天内沿固定方向缓慢转向，急流与减速区连续变化。背景季风约 10–13 m/s，急流约 13–15 m/s。
- 地形、急流减速、湿度、抬升与冷池暖侧共同决定新生。起爆点环境持续合适时补生新单体，移动单体随风输送；这与把整条雨带固定绘制在地图上不同。
- 地形迎风/背风关系及山脉与风向的夹角参与触发和维持。南北向列车向南接续受最南侧山地限制，偏东西向列车可沿合格冷池前缘向海上发展。
- 对流凝结、降水沉降、蒸发、冷池和层状回波共享有限水量预算。核心降水设有 100 mm/h 上限，超额水量留在降水库中；弱降水不会被强行提升至 50 mm/h。
- 午后增温与水汽交换会改变湿度，暖湿供给不足时源和单体衰减。风向、地形和随机环境会使不同轮次的触发区域与过程长度不同。

1.43 调整了列车源附近的早期上升气流尺度，使强核更快在起爆点附近形成；下游供给随离源距离及横穿山脉而衰减，避免移走后在更北侧重新获得无限供给。恩平与珠海北侧的源区范围收紧，相对横穿有组织山脉的风向也会抑制已有源的持续补生。单体寿命与强核延伸适当缩短；已生成的层状云雨仍按原方程输送。

模型区域为 1280 × 800 km。环境网格 5 km、冷池网格 2.5 km、降水网格 2 km、雨量账网格 1 km；这些是数值分辨率，不表示同等尺度的真实预报能力。画质影响显示产品，不改变主物理网格。

### 地图、观测与回放

| 地图 | 图层顺序 |
| --- | --- |
| 区域大地图 | 雷达、西南季风、1h 降水、24h 降水、累计降水 |
| 深圳小地图 | 雷达、街道预警、1h 降水、24h 降水、累计降水 |

左右地图独立浏览，支持缩放、拖动和自选观测点。观测值随当前显示时刻同步。回放覆盖本轮已经计算出的完整时间段；滑动降水与过程累计分别计算。保存和恢复使用浏览器本地存储，不会上传个人进度。模型版本更新后，旧检查点可能无法续算，需要新开一轮。

### 深圳预警与三天决策

游戏使用 **74 个街道模拟代表点**，不是已核实站址的真实自动气象站。每个点独立采样模型雨量；地图显示点位预警，不把近邻关系冒充真实街道行政边界。

当前游戏规则采用滑动 1/3/6 小时雨量和近期降雨持续性判断黄、橙、红预警。橙色达标点向邻点联动黄色；红色达标点向第一圈联动橙色、第二圈联动黄色。降级需连续至少一小时不达标，中途重新达标会重置计时。详细阈值与来源说明见 [VACATION.md](VACATION.md) 和 [街道点位数据](assets/data/vacation-warning-stations.json)。这些阈值是游戏实现说明，不代表实时官方预警发布。

三天各有两次可能的决策：

1. **21:00**：写作业或不写。选择写作业后，当晚不再出现第二次决策。
2. **00:00**：此前选择不写，可选择补作业、睡觉或熬夜。
3. 熬夜期间可以点击右侧醒目的“回头是岸”补作业。
4. 每日最晚 **07:30** 结算。00:00–07:30 内任一街道出现模拟红暴，可提前结算当天停课结果。

| 选择与结果 | 当日得分 |
| --- | --- |
| 21:00 写作业，未停课 | 1000 |
| 不写作业并睡觉或继续熬夜，停课 | 1000 |
| 00:00 补作业，未停课 | 667 |
| 熬夜后补作业，未停课 | `round(667 × (1 − 已熬夜分钟数 / 450))` |
| 判断错误，包括补作业后停课 | 0 |

每日最高 1000 分，三天总分 3000。07:30 得 0 分且未写作业的情况下，若在之后至 16:30（含）才出现红暴，会额外显示“在功亏一篑中屈服”，分数不补发。决策时计算暂停在对应时刻，回放不会反复触发计分。

## StormSim Astra / Sol

StormSim 与放假模拟器使用不同的模型。Astra / Sol 在浏览器 Worker 中通过 Pyodide 运行 Python、NumPy、SciPy 内核，模拟分层风、温湿场、锋面、对流、降水、冷池与阵风。支持雷达、分层风场、MUCAPE、观测点和过程回放。

Astra 默认 6 km 网格并提供其他分辨率选项；Sol 使用 28 km 网格以降低计算成本。两者都不需要访客配置 WRF、计算服务器或 API key。首次访问需下载运行时和地形，计算时间及存储需求随设备、网格和过程长度变化。操作、技术细节与既有核验范围见 [simulation/README.md](simulation/README.md)。

## 本地运行

需要 Python 3。完整项目下载后，在项目根目录执行：

```sh
python3 -m simulation.preview
```

保持终端运行，在浏览器打开终端给出的地址。只预览放假模拟器也可以使用：

```sh
python3 development/scripts/preview_vacation.py
```

macOS 双击入口集中在 [development/launchers](development/launchers)，包括“启动本地预览.command”和“启动放假模拟器.command”。不要直接通过 `file://` 打开模拟器：Worker、地形与二进制资源需要 HTTP 环境。

网页使用预构建资源，没有必须执行的 npm 打包步骤。地形和模拟代码在项目中；在线底图、外部运行时或来源链接仍可能需要网络。底图加载失败时，页面可继续显示已计算的模拟产品。

## 项目结构与计算流程

| 路径 | 职责 |
| --- | --- |
| 根目录 HTML | 网站与各模拟器入口 |
| `assets/scripts/`、`assets/styles/` | 页面逻辑、样式与前端模块 |
| `assets/scripts/vacation-model.js` | 暖区模拟主模型、触发、单体生命周期、水量收支 |
| `vacation-worker.js`、`vacation-wasm.js`（位于上述脚本目录） | 后台计算、数值内核适配 |
| `vacation-game.js`、`vacation-warning.js` | 作业决策、每日评分与街道模拟预警 |
| `vacation-store.js`、`vacation-resource.js` | 本地进度、资源加载与兼容性处理 |
| `assets/data/`、`assets/wasm/`、`assets/vendor/` | 地形、站点、数值二进制及前端依赖 |
| `simulation/` | Astra / Sol 的 Python 模型、浏览器预览和说明 |
| `config.json`、`auto_update/` | 天气快照与更新程序 |
| `flightdata/`、`feimadata/` | 保留的航班采集、快照和说明 |
| `development/` | 启动器、可复用测试、统计工具、当前验证摘要 |
| `.github/workflows/` | 天气更新、Pages 发布与手动模拟/航班任务 |

放假模拟器的计算链为：加载地形与版本 → Worker 初始化随机环境 → 每步输送、冷池、环境诊断、触发和单体演化 → 降水产品与雨量账 → 街道预警和游戏事件 → 页面显示与本地回放。显示速度不改变 10 分钟主物理步长。

## GitHub Pages 发布

1. 保留完整入口、`assets/`、`simulation/` 和 `.nojekyll`，不要仅上传 HTML。特别是放假模拟器必须同时发布版本脚本、Worker、WASM、地形元数据和压缩/原始地形资源。
2. 在仓库 **Settings → Pages** 中选择 **GitHub Actions**，并允许项目工作流写入仓库、创建 Pages 部署。
3. 修改模拟器相关文件后推送 `main` 会触发现有天气更新/全站发布工作流；也可手动运行“自动更新天气数据”。只修改 README 不一定触发该路径过滤器。
4. 在 Actions 中检查更新与 Pages 部署结果。天气更新可能另行提交 `config.json`；推送前先同步这些提交，不覆盖它们。

天气调度有季节开关与频率检查，GitHub 的定时执行可能延迟。航班相关工作流目前只有手动入口，不应按历史文档中的旧定时说明理解。访客点击网页刷新不会启动后台抓取。

## 开发与验证

暖区模型的常规定向检查使用 Node.js，无需生成完整回放：

```sh
node development/tests/test_vacation_source_support.cjs
node development/tests/test_vacation_marine_initiation.cjs
node development/tests/test_vacation_windward_front.cjs
node development/tests/test_vacation_core_rate.cjs
```

短程统计使用 `development/scripts/summarize_vacation_run.cjs`，输入配置可通过 `validationHours` 缩短检查，保留 `hours: 72` 的生产背景变化。需要浏览器验证时，现有 Playwright 测试可检查初始化、地图、决策暂停和存档恢复；运行前需安装对应测试依赖及 Chrome。

本次验证范围与结果见 [当前验证摘要](development/docs/vacation-validation.md)。定向测试通过并不等同于验证全部随机种子或完整三天天气过程。

调试遵守 [AGENTS.md](AGENTS.md)：临时配置、截图、缓存与试算放入任务专用系统临时目录，结束时删除；不默认保存全量格点、逐帧回放或检查点。仅保留可复用测试与一份当前验证摘要。不要提交账号状态、`.env`、浏览器认证数据、数据库或本地历史归档；用户保留的 `trash/` 也不作为自动清理对象。

## 数据来源与说明

保留底图、地形、站点以及第三方运行时的署名和许可。地形来源与许可分别见 [暖区地形许可](assets/data/vacation-terrain-LICENSE.md)、[上游署名](assets/data/vacation-terrain-UPSTREAM-ATTRIBUTION.md) 和 [StormSim 地形许可](assets/data/simulation-terrain-LICENSE.md)。各组件遵守各自许可，不将整个仓库笼统声明为同一许可证。

进一步阅读：[暖区模型与玩法](VACATION.md) · [开发工具](development/README.md) · [StormSim](simulation/README.md) · [Flightdat](flightdata/README.md) · [Feimadat](feimadata/README.md)。
