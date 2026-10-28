# StormSim 1.2 首阶段验收记录（3.10 历史）

日期：2026-10-16。产品 Astra / Sol 1.2；Python 内核 `3.10.0-surface-rain`；前端/Worker `4.3.0`。

本阶段随后发现近中性冷池残层的厚度/动量消退不充分，历史问题见 [首轮后冷池检查](COLDPOOL_1_2_CHECK.md)。用户授权后已继续修正至 `3.11.0-friction-wake`，当前结果见 [最新风与冷池验收](WIND_WAKE_1_2.md)；以下 `3.10` 的数字保留原样，不冒充新内核重测。

## Safari 初始化

此前首帧保存必须等待 IndexedDB 完成，打开/事务无超时；这一路径可因挂起而永久停在 0%。本轮用故障注入重现“无 success、无 error”的等待，加入启动前读写预检、8 秒限时、事务中止、CacheStorage 备用存储和压缩兼容。真实问题来自 iPhone Safari，但未连接用户的实体 iPhone，不能声称已在该真机复现唯一原因。WebKit 也有[待决 IDB 请求的历史记录](https://bugs.webkit.org/show_bug.cgi?id=226547)，仅用于兼容性设计参考，不将旧缺陷当作本机问题的证明。

使用 Playwright WebKit 26.5 / iPhone 13 视口，真实同站 Pyodide、NumPy、SciPy、DEM 和 Python 源码：

- Astra：手机默认 12 km / 节省内存 / 30 分钟输出，首帧保存成功，进度前进到 2.5% 后主动停止；没有跑 Astra 72 h 或 6 km 验证。
- Sol：首帧保存成功、进度前进；一小时过程完成，自动播放能够回读压缩帧并解码新增点降水。
- Chrome / WebKit 分别检查正常存储、打开请求永久挂起、被占用、事务挂起、缺少 gzip。校验回退后读写相等、删除本轮而保留其他轮次。加载阶段有真实阶段文字，计算阶段显示实际模拟时间比例与 ETA，不伪造百分比。
- 仍需使用较新 Safari，实体设备内存限制、后台暂停和省电模式未由桌面 WebKit 仿真覆盖。运行时最低浏览器要求见 [Pyodide 官方说明](https://pyodide.org/en/stable/usage/index.html)。

## 降水口径与结果

原 `rainrate/rain_total/rain_hour` 保留原生格点平均和物理预算。新增 `point_*` 是守恒雨区的亚格点估测：每格 16 个等面积积分点，有限对流雨柱至少占其中两个；点雨量的面积平均与每步实际落地水量相等。独立种子流保留持续相关性；没有硬加 20 mm 雨量下限、没有把雨强显示值统一乘倍数。层状雨不放大。细分用于统计降水足迹，不代表解析 1 km 对流。

近五分钟与近一小时雨量由累计水量差得到，历史按实际积分的 300 秒事件保存；不是瞬时雨强乘时长。Sol 仍逐小时保存展示帧，不能展示每一次短时峰值；过程审计在内部五分钟事件持续记录峰值。

受控 15 分钟雨柱案例：原格平均 15 mm/h，核心点五分钟 10 mm、事件总量 20–30 mm；干燥后五分钟/小时累计归零而总量保留。每步通量和累计面积平均守恒，均匀 2 mm/h 层状雨不被增幅。

实际浏览器 Sol 整轮：种子 `20260423`，28 km，14 层，72 h / 73 帧。从点击到全部保存 **291.364 秒**，包含载入、实际积分、编码、压缩与持久保存，不是原生 Python 时间或推算。外部在线底图被测试拦截，以隔离网络耗时。

| 指标 | 实测 |
| --- | --- |
| 全过程五分钟点雨量峰值 | 15.0438 mm / 5 min |
| 前两小时点累计峰值 | 36.6894 mm |
| 全过程点一小时累计峰值 | 57.8607 mm |
| 72 h 最大点累计 | 115.2440 mm |
| 原生格点最大累计 | 81.0892 mm |
| 最大水量相对残差 | 1.1441×10⁻⁷ |
| 模式平流 CFL | 每帧 ≤ 0.450001 |

前两小时累计峰值不是每个站点都达到该值的承诺；72 h 总量包含多轮过程，不把它当成单条飑线雨量。随机种子、是否命中核心和背景供给均影响实际雨量。五分钟以内仅是本台测试设备实测，不保证手机耗时。

原始记录：[浏览器审计](validation/sol-1.2-browser.json)、[逐小时原生字段](validation/sol-1.2-browser-fields.json.gz)。保存的字段用于复核边界和形态，点峰值来自每个快照所带的过程审计；不声称该字段文件含所有五分钟点栅格。物理源码散列与本轮基准一致。

## 边界及地图

冷池求解器曾将整个外部永远置干，冷池触边时即使内部均匀也会建立虚假的密度差。本轮改为零梯度开放出流，并禁止外部冷池质量/示踪量流入，静水压力单独保留。受控均匀静止冷池在全部边缘积分 30 分钟后深度、浮力和动量不变；向外运动的冷池可离开，质量变化等于开放边界通量。不是将地图边缘一圈涂透明来掩盖模拟错误。

实际 Sol 72 h 原生雷达/雨强抽帧图：[边界检查图](validation/sol-1.2-boundaries.png)。由已存结果后处理，不额外模拟；边缘仍可能存在从域内移动而来的合法降水，不要求边缘永远无雨。

地图回归检查：最小华南全域向四个方向连续拖动，中心保持固定；放大后可拖动；双图/四图同步、无硬重置、延迟底图下九点覆盖、快速反向缩放、透明边界及内部真实小雨显示均通过。旧帧没有新增雨量字段时仍可读取。

## 复核命令

最终 Python 测试集 **160 项通过**（包括五项需要回环端口的预览测试）；受控物理案例不等同于 Astra 全域整轮天气验证。

```sh
python -m unittest discover -s development/tests -p 'test_*.py'
node development/tests/test_frame_storage.cjs
node development/tests/test_safari_startup.cjs
node development/tests/test_stormsim_editions.cjs
node development/tests/test_simulation_raster_edges.cjs
SIM_TEST_RUN=/path/to/completed/fixture TEST_BROWSER_CHANNEL=chrome node development/tests/test_simulation_v2_browser.cjs
SIM_TEST_RUN=/path/to/completed/fixture TEST_BROWSER_CHANNEL=chrome node development/tests/test_simulation_zoom.cjs
SOL_BENCH_SEED=20260423 SOL_BENCH_OUTPUT=/tmp/sol.json node development/tests/benchmark_stormsim_sol.cjs
```

浏览器检查需本机 Playwright、Chrome 与 WebKit。完整 Python 测试包含本机回环预览服务，需要允许绑定本机端口。`.nojekyll` 已在根目录且被 Git 跟踪。新增 `simulation/precipitation.py`、两版 HTML、Python/前端脚本需一起上传，不能只更新页面文件。
