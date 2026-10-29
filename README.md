# 深中气象 · StormSim 2.5

深圳中学气象社网站：深圳天气、一周预报、官方预警，以及华南强对流过程模拟。

[网站首页](https://06e-felicia.github.io/) · [Astra](https://06e-felicia.github.io/simulator.html) · [Sol](https://06e-felicia.github.io/simulator-sol.html)

## 功能

- 深圳天气、未来一周预报和预警信息由官方公开数据自动更新。
- 上游雷暴抵达估测：按预警发布时间、城市经线投影距离和 50 km/h 假定速度计算；仅供参考，不代替官方预警。
- **StormSim 2.5 Astra / Sol**：随机初始化华南春季天气，模拟锋面、冷池、对流、降水和阵风；支持雷达、分层风场、MUCAPE、多地图、观测点与过程回放。
- **Flightdat 航班精选（维护中）**：自动采集已暂停，页面显示维护提示；原有代码和数据保留。[整合与更新说明](flightdata/README.md)。

Astra 提供可选精细网格，Sol 使用 28 km 网格；两版均在访客浏览器本机计算，无需额外服务器、WRF 或 API key。模拟是降阶物理实验，**不是实况或业务预报**，不保证每个随机环境都产生同样的风暴。

## 本地运行

在项目目录执行：

```bash
python3 -m simulation.preview
```

打开终端提示的本机网址，保持终端运行。macOS 也可双击 `development/launchers/启动本地预览.command`。不要通过 `file://` 直接打开模拟器。

每次开始生成全新的种子和环境，初始化完成后自动展示过程，首轮结束后开放回看。

本次已完成的 Astra 测试可双击 `development/launchers/复现Astra测试.command` 直接回看，无需重新计算；说明见 [本机测试启动器](simulation/TEST_REPLAY.md)。

## GitHub Pages 部署

1. 上传完整项目，包括根目录隐藏文件 `.nojekyll`、`simulation/` 和 `assets/`；不要只替换 HTML。
2. 仓库 **Settings → Pages → Source** 选择 **GitHub Actions**。
3. 为 Actions 开启 **Read and write permissions**，手动运行一次 **自动更新天气数据** 工作流。

天气定时更新由 Actions 执行，调度可能延迟。雷暴估测的全站开关在该工作流的手动运行选项中，不提供网页访客开关。

## 配置与开发

- `config.json`：天气快照、预警及雷暴估测设置。
- `auto_update/`：官方天气数据抓取与更新。
- `simulation/`：Astra / Sol 共用的物理内核、测试说明与历史核验。
- `development/tests/`：物理、页面和浏览器回归测试。

[第一轮 bug 修复说明](development/docs/OPTIMIZATION.md)：天气加载容错、跨页面菜单修复、航班请求去重及验证方法。

[模拟器操作与技术说明](simulation/README.md) · [2.5 后侧输送与 Sol 实测](simulation/REAR_CIRCULATION_2_5.md) · [版本记录](simulation/STORMSIM.md)

保留地图、地形及数据来源的署名与许可；模拟结果和上游雷暴估测不能用于防灾决策。

## 放假模拟器与本地开发

[放假模拟器](Vacation.html) · [模型说明](VACATION.md) · [开发工具说明](development/README.md)。

本地启动器集中在 `development/launchers/`，脚本、测试和开发文档分别在其同级的 `scripts/`、`tests/`、`docs/`；网站运行资源保持在 `assets/`。
