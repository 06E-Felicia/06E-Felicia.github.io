# JPRail 数据

页面为根目录 `JPRail.html`，依赖项目自带 Leaflet、MapLibre GL JS 5.24.0 和 maplibre-gl-leaflet 0.1.3，无需 npm 构建。依赖版本和许可随 `assets/vendor/` 保存。

- `network.geojson`：597 个运营商/线路组，地理几何来自日本国土交通省 [N02-25](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-2025.html)，基准日期 2025-12-31，CC BY 4.0。合并同运营商、线路、种别并简化。
- `network-detail.geojson`：同样 597 组的原始精细轨迹，约 8.6 MB；不作几何简化，不用曲线插值补造轨迹。10 级起按需加载并缓存，低于 10 级恢复概览；精细模式仅渲染视野及周边的线路组。坐标保留七位小数不代表实测精度。近铁奈良线的坐标数由概览的 90 个恢复至 474 个，避免放大概览简化误差。
- `grades.json`：等级来源与匹配依据，来自 [Geofabrik Japan OSM extract](https://download.geofabrik.de/asia/japan.html) 的命名铁路标签。按标准化运营方/线路名归并；缺标签或有明显冲突时保留未分类。新干线还使用 N02 的新干线种别。它是线路级参考，不是逐股道或 JR 票价制度的干线/地方交通线分类。包含 OSM 衍生的等级数据库按 ODbL 提供。
- `japan.geojson`：日本地理轮廓，来源 [Natural Earth 1:50m](https://www.naturalearthdata.com/about/terms-of-use/)，公有领域。不含任何铁路，确保隐藏线路不会从地理底图透出。
- `streets-style.json`：白色街道底图的本地样式，基于 OpenMapTiles Positron 修改，许可见 `STREETS-LICENSE.txt`。在线加载 [OpenFreeMap](https://openfreemap.org/) 矢量瓦片、字形及 OSM 地名；删除铁路／公共交通线条、车站符号与底图铁路标注，防止未匹配铁路从底图透出。地理轮廓仅在底图尚未就绪或连接失败时作为后备。底图状态与重试入口在地图左下方。
- `stations.json`：N02 同源 9,482 个车站位置记录，同名但不同运营公司/线路可能保留多条。
- `passes.json`：截至 2026-11-08 的 54 个产品记录，50 个现行产品、4 个停售/季节结束记录，附时长、资格、售用期、列车限制、成人普通车厢日元票价及官方链接。所有现行产品覆盖其全部有效天数／小时类型；52 个产品有核实金额，两款停售产品注明无可核实的现行售价，不以零元代替。价格含核查日期及来源；JR 全国、北海道和九州的购买渠道价差另注。关西 LITE 已更新为 2026 冬季发售版本。目录并非国家统一票券数据库，不能保证穷尽新增、临时和渠道限定产品；未明确的条件不作确定推断。

## 显示与过滤

未选择 Pass 时隐藏右侧详情栏，桌面地图延伸至页面右侧；选择 Pass 后恢复详情栏与原三列布局，再按当前地图尺寸定位范围。清除选择或收起详情后恢复宽图，可点已选票券重新打开。平板和手机沿用侧边／底部详情浮层。

Pass 为单选，选择另一张后替换原选择；只渲染其匹配范围。等级和运营方筛选在这个范围内继续取交集；不选 Pass 时筛选全国客运线。可选六家 JR、全部 JR、私铁/第三部门/公营汇总以及各具体运营方。空结果显示空图，不退回全国线路。

线路按 OpenRailwayMap 标准颜色绘制：高速红 `#ff0c00`，主干橙 `#ff8100`，支线黄绿 `#c4b600`，工业/专用棕 `#87491d`，地铁蓝 `#0300c3`，轻轨绿 `#00bd14`，路面电车粉 `#d877b8`。未分类深灰。高亮不使用 Pass 专属颜色，不叠加全网参考线。筛选图普通线路宽 3 px，高速线路宽 4 px；比此前的 2.5 / 3.4 px 略加粗。

在线详细设施原图是 [OpenRailwayMap 标准瓦片](https://wiki.openstreetmap.org/wiki/OpenRailwayMap/API)，按当前视野加载、不批量下载，仅在无 Pass、无线路筛选时可开启。全国视野保留客运参考线，放大至 6 级以上时由设施原图替换，避免低缩放级别无瓦片而空白。筛选时关闭并禁用该图层，防止不匹配的线路透出。原图设施完整性和运营状态依赖 OSM 实际收录及更新，地图版权归 OpenStreetMap 贡献者，适用 [ODbL](https://www.openstreetmap.org/copyright)。

## Pass 范围精度

按用户确认，Pass 选区仍为**示意**：按运营方、线名、种别与区域框筛选/裁切 N02 几何。不能据此推断每站、每种列车、座席、直通公司和进出次数均适用。部分第三部门特例未绘制；附带地铁、巴士、轮渡只作文字说明。数据中的明确截止日期只在已核实官方信息时填写。

近铁 1 日券、札幌－登别、札幌－富良野及富士山－静冈券另保存 `railSections` 起讫区间；`pass-ranges.json` 和 `pass-ranges-detail.json` 沿铁路图寻路，分别配合两档几何，避免用区域框代替已核实的指定区间。仍不代替官方完整票券条件。

`passes.json` 中的 `stationPins` 保存官方范围来源及关键站。`boundary` 用于明确边界／起讫站（地图与按钮只显示站名），`restriction`（限）用于重要限制站，`gateway`（关）仅为区域门户／换乘提示，不把门户站推定为适用边界。选中 Pass 后这些站名在进入视野时不受缩放级别和普通站名密度限制；它们不是完整边界站清单，详情提供官方范围链接。

## 更新与验证

原始下载包及中间文件应置于每次任务独有的系统临时目录，生成后删除，不进入项目。

```sh
python3 development/scripts/build_jprail_network.py /临时路径/N02-25_GML/UTF-8
python3 development/scripts/enrich_jprail_grades.py /临时路径/japan.osm.pbf
python3 development/scripts/build_jprail_detail.py /临时路径/N02-25_GML.zip
python3 development/scripts/build_jprail_pass_ranges.py
python3 development/scripts/build_jprail_pass_ranges.py --network assets/data/jprail/network-detail.geojson --output assets/data/jprail/pass-ranges-detail.json
python3 development/tests/test_jprail.py -v
```

生成脚本需要 Shapely、NetworkX，等级脚本还需要 pyosmium；网页本身不需要。页面通过 HTTP/HTTPS 访问（GitHub Pages 或本地预览），不要求离线运行。更新票券时覆盖当前 JSON 并核对官方产品页与售停公告。

## 地图操作与车站名

初始视野紧贴北海道、本州、四国、九州，采用分数缩放，减少整数级别取景的多余留白。不提供单独冲绳按钮；冲绳可拖动或搜索车站定位。`jprail-camera.js` 使用连续的 0.5 级以内动画，滚轮目标最多领先当前视图 1 级，避免快速触控板输入堆积长队列；按钮每次缩放 0.5 级。定位与范围请求会等当前动画结束执行，遵循系统减少动态效果设置。

`jprail-stations.js` 使用 Canvas 绘制站点和名称，缓存排序及文字宽度；缩放期间沿用画布变换，结束后重绘，减少整库排序带来的卡顿。站名候选位置同时避让其他文字与当前匹配铁路的实际线段，避免白色描边和关键站名底框遮住轨迹、产生假断线；远移标注用细引线对应站点。全国概览优先显示人工整理的主要城市门户与换乘枢纽（不是客流量排名），区域视野按文字碰撞逐步增加车站；16 级起显示视野内全部本地客运站名。与 Pass、等级及运营方筛选保持一致，同名近邻位置避免重复文字；上述常驻关键站另作优先显示。数据仍以 N02 记录为准，不能代替实时运营公告。
