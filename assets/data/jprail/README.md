# JPRail 数据

页面为根目录 `JPRail.html`，依赖项目自带 Leaflet，无需 npm 构建。

- `network.geojson`：597 个运营商/线路组，地理几何来自日本国土交通省 [N02-25](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-2025.html)，基准日期 2025-12-31，CC BY 4.0。合并同运营商、线路、种别并简化。
- `grades.json`：等级来源与匹配依据，来自 [Geofabrik Japan OSM extract](https://download.geofabrik.de/asia/japan.html) 的命名铁路标签。按标准化运营方/线路名归并；缺标签或有明显冲突时保留未分类。新干线还使用 N02 的新干线种别。它是线路级参考，不是逐股道或 JR 票价制度的干线/地方交通线分类。包含 OSM 衍生的等级数据库按 ODbL 提供。
- `japan.geojson`：日本地理轮廓，来源 [Natural Earth 1:50m](https://www.naturalearthdata.com/about/terms-of-use/)，公有领域。不含任何铁路，确保隐藏线路不会从地理底图透出。
- `stations.json`：N02 同源 9,482 个车站位置记录，同名但不同运营公司/线路可能保留多条。
- `passes.json`：截至 2026-11-08 的 54 个产品记录，49 个现行产品、5 个停售/季节结束记录，附时长、资格、售用期、列车限制及官方链接。目录并非国家统一票券数据库，不能保证穷尽新增、临时和渠道限定产品；未明确的条件不作确定推断。

## 显示与过滤

Pass 为单选，选择另一张后替换原选择；只渲染其匹配范围。等级和运营方筛选在这个范围内继续取交集；不选 Pass 时筛选全国客运线。可选六家 JR、全部 JR、私铁/第三部门/公营汇总以及各具体运营方。空结果显示空图，不退回全国线路。

线路按 OpenRailwayMap 标准颜色绘制：高速红 `#ff0c00`，主干橙 `#ff8100`，支线黄绿 `#c4b600`，工业/专用棕 `#87491d`，地铁蓝 `#0300c3`，轻轨绿 `#00bd14`，路面电车粉 `#d877b8`。未分类深灰。高亮不使用 Pass 专属颜色，不叠加全网参考线。

在线详细设施原图是 [OpenRailwayMap 标准瓦片](https://wiki.openstreetmap.org/wiki/OpenRailwayMap/API)，按当前视野加载、不批量下载，仅在无 Pass、无线路筛选时可开启。筛选时关闭并禁用该图层，防止不匹配的线路透出。原图设施完整性和运营状态依赖 OSM 实际收录及更新，地图版权归 OpenStreetMap 贡献者，适用 [ODbL](https://www.openstreetmap.org/copyright)。

## Pass 范围精度

按用户确认，Pass 选区仍为**示意**：按运营方、线名、种别与区域框筛选/裁切 N02 几何。不能据此推断每站、每种列车、座席、直通公司和进出次数均适用。部分第三部门特例未绘制；附带地铁、巴士、轮渡只作文字说明。数据中的明确截止日期只在已核实官方信息时填写。

## 更新与验证

原始下载包及中间文件应置于每次任务独有的系统临时目录，生成后删除，不进入项目。

```sh
python3 development/scripts/build_jprail_network.py /临时路径/N02-25_GML/UTF-8
python3 development/scripts/enrich_jprail_grades.py /临时路径/japan.osm.pbf
python3 development/tests/test_jprail.py -v
```

生成脚本需要 Shapely/pyosmium；网页本身不需要。页面通过 HTTP/HTTPS 访问（GitHub Pages 或本地预览），不要求离线运行。更新票券时覆盖当前 JSON 并核对官方产品页与售停公告。
