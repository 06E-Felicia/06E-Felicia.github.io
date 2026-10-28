# 开发工具

网站入口和运行资源位于项目根目录与 `assets/`。本目录集中保留可复用的本地工具。

- `launchers/`：macOS 双击启动器。打开 [启动放假模拟器.command](launchers/启动放假模拟器.command) 会从项目根目录启动本机服务器；移动整个项目后仍可使用。
- `scripts/`：地形准备、短程统计、回放生成与读取工具。
- `tests/`：物理与页面回归测试；`results/` 保留当前小型验证摘要。
- `tools/vacation-wasm/`：数值内核源码与构建脚本。
- `docs/`：模型规格、开发说明和当前验证说明。
- `archive/`：本机保留的历史开发资料，不上传 GitHub。

以下命令均从项目根目录运行，需要 Python 3 / Node.js：

```sh
python3 development/scripts/preview_vacation.py
node development/tests/test_vacation_western_slope.cjs
node development/tests/test_weather_data.cjs
```

回放渲染依赖见 `scripts/requirements-vacation-replay.txt`。常规排查优先使用 `scripts/summarize_vacation_run.cjs` 的小型统计，不默认生成完整回放。临时试算应写入任务专用临时目录并在结束时删除；需要保留的本地材料可放在已忽略的 `development/local/`。不要提交数据库、账号资料、完整模拟或浏览器缓存。
