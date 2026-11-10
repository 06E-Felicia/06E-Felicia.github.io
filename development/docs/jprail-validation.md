# JPRail 当前验证摘要

## 本次：触控板捏合与响应式布局（2026-11-10）

- 用户确认 Mac 操作为双指捏合。Chromium 的 Ctrl+wheel 捏合单独使用 8 倍于普通滚轮的级别增量，保留连续目标／单 RAF、反向、小增量和上下限；普通滚轮仍为 100 px = 0.125 级。桌面 Safari 原生 gesture 事件按相邻 scale 比例处理，并选择单一输入路径，防止同一手势又被 wheel 重复执行。手机原有触摸缩放继续由 Leaflet 处理。
- 桌面顶栏 108→68 px，筛选条 73→42 px，页脚 42→26 px；站名与线路颜色说明收紧。1680×1050、选中北陆券的同一场景中，地图高度约 625→794 px，增加约 169 px。
- 手机／窄屏（≤960 px）详情改为地图下方的普通文档区域，独立滚动且可收起；选择 Pass 后回到地图顶部。取消固定底部浮层，地图保持原高度。961–1180 px 的桌面详情也使用独立列，不再浮在地图之上。
- 联网 Chrome 检查白色底图正常；390×844 手机地图约 414 px 高，详情从其下方开始，未覆盖地图。当前正式审核图更新为 [手机实测图](jprail-map-review.png)。

验证：本次 6 项浏览器／数据回归通过（24.887 秒）；覆盖普通滚轮与捏合增量、连续／反向／惯性、停止后无额外跳变、原生 Chromium 合成捏合、Safari 事件路径去重，以及桌面 961／1100／1440／1680 和窄屏 320／390／768／844／960 的布局、横屏、详情开关、地图命中与无横向溢出。Chromium 原生 1.5 倍捏合输入实际改变约 0.405 级，输入逐个取消浏览器默认行为，页面自身未被缩放。Safari 使用事件能力模拟回归，没有宣称完成物理触控板人工验收。

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest development.tests.test_jprail_touch_layout development.tests.test_jprail -v
```

本次部署：待提交后确认 Actions 与实际 Pages 文件。保留已有发布重试和真实 30 分钟步骤／40 分钟任务时限。

## 已有范围审查与发布记录（上一轮，本次未重新逐券核实官方条款）

核对日期：2026-11-10（Asia/Shanghai）。本次为 02:10 定时任务的一次执行，基于最新 `origin/main` 的隔离工作树，覆盖替换此前的局部验证摘要。

54 张产品均逐券查阅来源并实际选择绘图检查，其中 **50 张范围／主要使用条款来源核验完成，4 张仍有证据缺口**。绘图检查通过不等于尚未证实的官方适用范围也正确；不能据此宣称全目录无错标、无漏标或零错误。票价继续使用详情中标注的原有核查日期（2026-11-08），本次不宣称重新核实全部票价。线路几何仍来自 N02-25，属于适用范围示意，未验证每条轨道的实时营运状态。

### 修正内容

- 滚轮改为一个连续目标和一个 RAF，按输入增量累计，而不是把整段手势锁成一次。100 CSS px 约 0.125 级，按钮／键盘每次 0.25 级；保留小幅惯性输入与反向操作。删除首段收集、尾部丢弃和离散动画排队，输入停止后不再跳到另一档。慢滚、快滚、持续滚、反向、惯性尾部、pixel／line／page deltaMode、上下限、双击按钮、键盘和系统减少动态效果均有回归。
- 只按每券官方范围白名单标注票券边界。删除“只显示公司接口一侧就自动推定为边界”的逻辑，分开粗圈适用边界、蓝色虚圈真实公司边界、细圈物理铁路端点和文字限制；站名本身没有“界／限／关”等后缀。同站涉及多条线路时在说明中写明具体限制，避免把某一线路边界解释成所有线路都止于该站。
- 官方命名起讫区间替代所有票券矩形裁切。补全漏掉的私铁、短支线和真正端点，删去超范围区间。北陆地区券新干线为敦贺—黑部宇奈月温泉，关西・北陆券为敦贺—上越妙高，两券独立核对。北陆拱型券另取得 2026 详细日文附图，纠正龟冈／园部及中央东线、筱之井线、东京短支线范围。
- 概览和精细范围使用同一详细拓扑生成，只简化坐标，不更换所选通路；保留实际平行线路、砂原路径、予赞海岸与内子路径。没有人为直线补接、放大范围框或跨不相连设施造线。缆车、非铁路交通或不同实际设施之间的换乘距离保留，不冒充绘图断线。
- 站点去重保留运营方和线路身份，从 9,482 条增至 10,234 条，解决共享站丢失新干线／第三部门身份及定位错误。站名避开控件、其他常驻名称和线路白底遮挡；普通站名只在附近排布，避免被远移到别处并产生蜘蛛状引线。精细图按有重叠端点的原始坐标段做视野索引，省去视野外投影；标签避让仅做亚像素碰撞简化，实际轨迹不降精度。区域视图提前疏开普通站名，近距离仍显示全部。缩放过程中同步变换，在长手势中刷新绘图视野，并扩大真实 Canvas 绘制余量，消除缩小过程中曾出现的约 34 px 边缘空洞（回归逐帧检查实际 Canvas 的覆盖范围）。
- 修复详情栏改变宽度后 MapLibre 底图可能保留旧绘制视图的问题：同步底图视口、公开相机 API 并主动重绘，防止海岸线与铁路错位。允许带 padding 的 GL 视图跨日期变更线，避免全国缩小时 GL 自动夹紧中心而产生约 69 px 的错位。除投影对齐外，联网截图还检查金泽车站实际落在陆地，涵盖三种桌面宽度及详情关闭／重开。
- 保留路线略加粗、按等级着色、单券选择、等级／运营方筛选、未选券时收起详情和桌面整屏布局。

### 自动与真实绘图检查

最终本地联合回归：5 项测试通过（323.149 秒）。54 张逐一选择，合计 **2,218 个实际视图、686 个关键站配置访问、344,899 个实际绘制铁路采样点**。

每券检查全国、区域、近距离视图；对每个运营方／线路组定位到真实铁路坐标并读取实际 Canvas 截图像素，检查覆盖层中线路确实可见（至少 96% 的采样邻域存在预期线路颜色）；逐个关键站近距离访问，并检查视野内常驻边界名称未被控件／其他关键站名遮住。逐券操作等级、全部实际运营方、拖动、详情关闭／重开。无 JavaScript 页面异常。图层层级、视野保留、概览／精细端点和站点集合相同另有检查。这些是有限的实际视图／像素检查，不是对无限缩放位置的穷举证明。

另以真实 Chrome 原生鼠标 wheel、模拟触控板连续输入和在线 OpenFreeMap 瓦片检查：100 px 输入改变 0.125 级；持续 40 次 × 30 px 输入改变 1.5 级，60 Hz 环境帧时长中位／P95 为 16.7／16.8 ms，输入结束稳定后额外变化 0。全国模式东京精细图的同类手势，本机采样 P95 从约 83 ms 降至约 33 ms（中位 16.7 ms）；重场景仍可出现短暂帧延迟，未声称所有硬件均固定 60 fps。桌面 660／1440／1800 高度无外层底部空白，窄屏滚动／详情保留。最终正式审核图覆盖保存为 [jprail-map-review.png](jprail-map-review.png)。

复用回归命令（环境中需 Playwright、Chrome、Pillow；构建几何另需 Shapely、networkx）：

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest development.tests.test_jprail development.tests.test_jprail_audit -v
```

### 仍未完成的具体项

- **东日本・南北海道周游券** (`east-hokkaido`)：南北海道示意图未列札幌东侧函馆线逐站边界；地图接入千岁线需经白石，不能据此宣称白石是已核实票券边界。；新潟西南支线与东京近郊插图之间的详细可用站表未获取，当前线路范围仍需进一步核实，不能据图推定全券无漏线。；该券东京近郊范围不是东京广域券；已移除房总全线等无依据高亮，尚待取得可读的完整逐站边界表。 页面已显示“范围待核”，详情提前列出证据缺口。

- **东北・南北海道周游券** (`tohoku-hokkaido`)：南北海道示意图未列札幌东侧函馆线逐站边界；地图接入千岁线需经白石，不能据此宣称白石是已核实票券边界。 页面已显示“范围待核”，详情提前列出证据缺口。

- **福冈广域手机周游券** (`kyushu-mobile`)：手机版简图标为唐津，未找到西唐津是否包含的明确逐站条款，唐津端点暂按简图，尚不能宣称已完全核实。 页面已显示“范围待核”，详情提前列出证据缺口。

- **南海全线 2 日券（停售）** (`nankai-old`)：发行方遗留页未写停售日或泉北并入前后的版本日期；按销售方明确排除泉北的历史范围绘制，仍缺发行方带日期的完整历史条款。 页面已显示“范围待核”，详情提前列出证据缺口。

### 逐券来源记录

下表每张产品均对应独立核对记录，完整的边界白名单、明确排除的内部站、来源、版本、日期和未完成事项保存在生产数据 [pass-audit.json](../../assets/data/jprail/pass-audit.json)。核对日期全部为 2026-11-10。“完成”指对应产品版本的范围／主要限制来源核验，地图并非官方精确票券图。南海历史券补充的 HIS 销售方材料不能替代发行方带日期的历史条款，因此仍列待核。

| 产品 | 版本 | 状态 | 官方依据／核对发现 |
| --- | --- | --- | --- |
| 日本全国铁路周游券 | 2026-11-10 现行条款 | 完成 | JR 六社内部交接不是票券边界；补入四项第三部门通过特例，Nozomi/Mizuho 是列车限制。 [来源1](https://japanrailpass.net/en/use/conditions-for-use/) |
| 北海道铁路周游券 | 2026-11-10 现行条款 | 完成 | 不含北海道新干线、道南渔火铁道；留萌线已于 2026-04-01 废止。 [来源1](https://www.jrhokkaido.co.jp/global/english/ticket/railpass/) · [来源2](https://www.jrhokkaido.co.jp/global/images/ticket/railpass/e-rail04.png) · [来源3](https://www.jrhokkaido.co.jp/CM/Info/press/pdf/20260318_KO_rumoi.pdf) |
| 札幌－登别区域周游券 | 2026-11-10 现行条款 | 完成 | 按官方每个分支起讫站逐段定位，排除图示不可用目的地；未用矩形边缘作为边界。 [来源1](https://www.jrhokkaido.co.jp/global/english/ticket/railpass/) · [来源2](https://www.jrhokkaido.co.jp/global/images/ticket/railpass/e-rail02.png) |
| 札幌－富良野区域周游券 | 2026-11-10 现行条款 | 完成 | 按官方每个分支起讫站逐段定位，排除图示不可用目的地；未用矩形边缘作为边界。 [来源1](https://www.jrhokkaido.co.jp/global/english/ticket/railpass/) · [来源2](https://www.jrhokkaido.co.jp/global/images/ticket/railpass/e-rail03.png) |
| JR 东日本铁路周游券 | 2026-11-10 现行条款 | 完成 | 2026 新版全 JR 东日本加列明七家私铁／第三部门；补上东武直通区间，新干线／普通线公司边界按线路说明。 [来源1](https://www.jreast.co.jp/en/multi/pass/eastpass.html) · [来源2](https://asset.japan.travel/image/upload/v1771574289/pdf/JR_East_20260220.pdf) |
| 东京广域周游券 | 2026-11-10 现行条款 | 完成 | 补 New Shuttle 与东武区间；西至小渊泽／小诸，HSR 佐久平，北至黑矶／那须盐原／日立／常陆大子；没有大宫整站边界。 [来源1](https://www.jreast.co.jp/en/multi/pass/tokyowidepass.html) · [来源2](https://www.jreast.co.jp/multi/pass/tokyowidepass_terms.html) · [来源3](https://asset.japan.travel/image/upload/v1771574289/pdf/JR_East_20260220.pdf) |
| 东日本・南北海道周游券 | 2026-11-10 现行条款 | **待核** | 删除错误的全 JR 东日本范围与长野／热海／大月标注；按官方主图与东京近郊插图拆分。 [来源1](https://www.jreast.co.jp/en/multi/pass/easthokkaido.html) · [来源2](https://www.jreast.co.jp/multi/pass/easthokkaido_terms.html) · [来源3](https://asset.japan.travel/image/upload/v1771574289/pdf/JR_East_20260220.pdf) |
| 东北・南北海道周游券 | 2026-11-10 现行条款 | **待核** | 纠正此前东北部分矩形漏线；边界是白坂、勿来、村上、小国、德泽、只见、矢祭山及新白河，不是县界。 [来源1](https://www.jreast.co.jp/en/multi/pass/tohokuhokkaido.html) · [来源2](https://www.jreast.co.jp/multi/pass/tohokuhokkaido_terms.html) · [来源3](https://asset.japan.travel/image/upload/v1771574289/pdf/JR_East_20260220.pdf) |
| 仙台区域周游券 | 2026-11-10 现行条款 | 完成 | JR 四方向、仙台机场线、阿武隈槻木—阿武隈；新干线与地铁未高亮。 [来源1](https://sendaitravelpass.jp/1day/en/) · [来源2](https://sendaitravelpass.jp/images/sendaiareapass_map.png) |
| 关西迷你周游券 | 2026-11-10 现行条款 | 完成 | 不含任何新干线；Haruka 等特急另购料金。范围按山科／舞子／宝塚／保津峡／木津而非城市矩形。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansaimini/) · [来源2](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/kansaimini_map.jpg) |
| 关西广域周游券 | 2026-11-10 现行条款 | 完成 | HSR 新大阪—冈山；由良、津山、总社、仓敷、柘植、米原、新宫；含智头、丹铁、和歌山电铁和高松方向。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai_wide/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=125000343&keyword=%E3%82%A8%E3%83%AA%E3%82%A2%E3%83%91%E3%82%B9) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20251029185510024&newwindow=true) |
| 关西・广岛周游券 | 2026-11-10 现行条款 | 完成 | HSR 新大阪—广岛；在来线至岩国／三次／府中／鸟取；不把广岛站误作所有线路边界。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai_hiroshima/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=123000473&keyword=%E3%82%A8%E3%83%AA%E3%82%A2%E3%83%91%E3%82%B9) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20240930132917632&newwindow=true) |
| 关西・山阴周游券 | 2026-11-10 现行条款 | 完成 | 不含高松／新宫；伯备、木次、因美、智头及丹铁按官方全区段，山口线至津和野。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai_sanin/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=124000015&keyword=%E3%82%A8%E3%83%AA%E3%82%A2%E3%83%91%E3%82%B9) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20240123162111667&newwindow=true) |
| 关西・北陆周游券 | 2026-11-10 现行条款 | 完成 | HSR 到上越妙高；不含高松、智头急行；猪谷／南小谷／新宫是真正局界边界，敦贺是内部换乘。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai_hokuriku/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=124000066&keyword=%E3%82%A8%E3%83%AA%E3%82%A2%E3%83%91%E3%82%B9) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20240123184022761&newwindow=true) |
| 鸟取・松江周游券 | 2026-11-10 现行条款 | 完成 | 山阴东滨—出云市，木次至木次、伯备至根雨、因美至郡家和境线。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/tottorimatsue/) · [来源2](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/tottorimatsue_map.jpg) |
| 山阳・山阴周游券 | 2026-11-10 现行条款 | 完成 | 含高松、智头、丹铁；不含博多南、北陆新干线、纪势和歌山以南；公司交接只标本券外缘。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/sanyo_sanin/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=123000474&keyword=%E3%82%A8%E3%83%AA%E3%82%A2%E3%83%91%E3%82%B9) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20240930125447620&newwindow=true) |
| 广岛・山口周游券 | 2026-11-10 现行条款 | 完成 | 山阳 HSR 博多—三原，在来线东至尾道；山阴至益田、艺备至三次，逐一分开地图边界。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/hiroshima_yamaguchi/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=125000089&keyword=%E3%82%A8%E3%83%AA%E3%82%A2%E3%83%91%E3%82%B9) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20240930123357617&newwindow=true) |
| 关西广域游览周游券 | 2026-11-10 现行条款 | 完成 | 独立读取游览券范围图，铁路区间与广域版一致；3 日、非日本护照不限签证类型。 [来源1](https://www.westjr.co.jp/global/en/ticket/pass/kansai_wide_excursion/) · [来源2](https://www.westjr.co.jp/global/en/ticket/pass/kansai_wide_excursion/images/kansai_wide_map.jpg) |
| 冈山・广岛・山口周游券 | 2026-11-10 现行条款 | 完成 | 山阳 HSR 博多—岡山，在来线东至岡山；山阴至益田、艺备至三次，逐一分开地图边界。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/okayama_hiroshima_yamaguchi/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=125000088&keyword=%E3%82%A8%E3%83%AA%E3%82%A2%E3%83%91%E3%82%B9) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20250131114227936&newwindow=true) |
| 北陆地区周游券 | 2026-11-10 现行条款 | 完成 | 新干线止于黑部宇奈月温泉；补齐越前铁路、万叶线和富山市内电车；不延长至上越妙高。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/hokuriku/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=125000081&keyword=%E3%82%A8%E3%83%AA%E3%82%A2%E3%83%91%E3%82%B9) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20240123192508774&newwindow=true) |
| JR 西日本全地区周游券 | 2026-11-10 现行条款 | 完成 | JR 西日本全区域加指定私铁；博多南与山阳、北陆分开；米原、龟山等局界使用官方网络外缘白名单。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/all/) · [来源2](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=124000071) · [来源3](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20240930115204607) |
| 北陆拱型铁路周游券 | 2026-11-10 现行条款 | 完成 | 以 2026-03-14 起版详细日文附图核实东京全支线：中央东线至盐尻并含辰野路径、筱之井线、八高八王子—高丽川、川越大宫—高丽川、羽泽横滨国大与京阪短支线；山阴线止龟冈而非园部。上越妙高／敦贺为内部衔接，不作整券边界。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/other/hokuriku-arch-pass/) · [来源2](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/other/hokuriku_arch_map_02.jpg) · [来源3](https://asset.japan.travel/image/upload/v1771574289/pdf/JR_East_20260220.pdf) · [来源4](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=126000196) · [来源5](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20260128091929024) |
| 濑户内地区周游券 | 2026-11-10 现行条款 | 完成 | 濑户内独立范围：四国至伊予大洲／琴平／栗林；京都至龟冈；不把广域区域框内山阴／北陆等线路混入。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/other/setouchi/) · [来源2](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/other/setouchi_map.jpg) |
| 山阳・山阴・北部九州周游券 | 2026-11-10 现行条款 | 完成 | 山阳／山阴加北九州逐段；下关、博多为券内衔接，非边界；北九州 HSR 至熊本，在来线至宇土／大分。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/other/ssnk/) · [来源2](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/other/ssnk_map.jpg) |
| 高山・北陆地区周游券 | 2026-11-10 现行条款 | 完成 | 高山全线含 JR 东海与西日本两段；北陆 HSR 敦贺—富山；大阪市内短支线独立补齐，不含东海道新干线。 [来源1](https://touristpass.jp/en/takayama_hokuriku/) · [来源2](https://touristpass.jp/assets/img/takayama_hokuriku/routemap_en.jpg) |
| 立山黑部・高山・松本地区周游券 | 2026-04-15 至 2026-11-10 使用季（2026-11-06 停售） | 完成 | 对应 2026-04-15—11-10 使用版；名古屋—富山与松本／信浓大町—名古屋，含富山地方铁道和钢索线；非铁路路段只文字说明。 [来源1](https://touristpass.jp/en/alpine/) · [来源2](https://touristpass.jp/assets/img/alpine/routemap_en.jpg) |
| 伊势・熊野・和歌山地区周游券 | 2026-11-10 现行条款 | 完成 | 纪势线两家公司全行程、关西线大阪—名古屋、参宫、伊势铁道、贵志川线；不含奈良线／和歌山线。 [来源1](https://touristpass.jp/en/ise_kumano/) · [来源2](https://touristpass.jp/assets/img/ise_kumano/routemap_en.jpg) |
| 富士山・静冈地区迷你周游券 | 2026-11-10 现行条款 | 完成 | 东海道热海—丰桥、御殿场沼津—松田、身延富士—下部温泉、骏豆三岛—修善寺；新干线完全不含。 [来源1](https://touristpass.jp/en/fuji_shizuoka/) · [来源2](https://touristpass.jp/assets/img/fuji_shizuoka/routemap_en.jpg) |
| 全九州铁路周游券 | 2026-11-10 现行条款 | 完成 | JR 九州全线至下关，含西九州 HSR；小仓—博多山阳 HSR 不属于 JR 九州，不用博多／小仓两个大站推导全站不可乘。 [来源1](https://www.jrkyushu.co.jp/english/railpass/railpass.html) · [来源2](https://www.jrkyushu.co.jp/lang/assets/img/railpass/common/img_all-kyushu.png) · [来源3](https://www.jrkyushu.co.jp/english/pdf/railpass_guidebook.pdf) |
| 北部九州铁路周游券 | 2026-11-10 现行条款 | 完成 | HSR 至熊本；在来线为宇土接三角支线、日丰止大分，完整包含丰肥线，不用南纬矩形截掉阿苏段。 [来源1](https://www.jrkyushu.co.jp/english/railpass/railpass.html) · [来源2](https://www.jrkyushu.co.jp/lang/assets/img/railpass/common/img_northern-kyushu.png) |
| 南部九州铁路周游券 | 2026-11-10 现行条款 | 完成 | 大分／熊本以南含三角及丰肥；鹿儿岛本线八代—川内属于第三部门，不造直线连接；肥萨线停运是运营状态。 [来源1](https://www.jrkyushu.co.jp/english/railpass/railpass.html) · [来源2](https://www.jrkyushu.co.jp/lang/assets/img/railpass/common/img_southern-kyushu.png) |
| 福冈广域手机周游券 | 2026-11-10 现行条款 | **待核** | 大牟田、行桥方向至图示边缘；不是只到久留米；仅自由席，不含任何新干线。 [来源1](https://www.jrkyushu.co.jp/english/railpass/mobilepass.html) · [来源2](https://www.jrkyushu.co.jp/lang/assets/img/railpass/mobile/img_fukuoka.png) |
| 四国铁路周游券 | 2026-11-10 现行条款 | 完成 | 2026-10-01 新版：3／7 日，移除小豆岛船／巴士；铁路按新版列明的五家公司，Sunrise Seto 不含。 [来源1](https://shikoku-railwaytrip.com/news/pdf/20260806_en_japan-rail-passes.pdf) |
| 大东京周游券 | 2026-11-10 现行条款 | 完成 | 移除误含江之电，补百合海鸥；地铁／巴士仅文字权益；成田 Sky Access 不误当北总线全线自由乘车。 [来源1](https://greater-tokyo-pass.jp/en/) · [来源2](https://greater-tokyo-pass.jp/en/rosen/index.html) · [来源3](https://greater-tokyo-pass.jp/assets/images/rosen/line.pdf) |
| 近铁铁路周游券 1 日 | 2026-11-10 现行条款 | 完成 | 四组指定区间；奈良线不借用地名矩形，生驹线不在一日券范围。 [来源1](https://www.kintetsu.co.jp/foreign/english/ticket/krp_1day.html) |
| 近铁铁路周游券 2 日 | 2026-11-10 现行条款 | 完成 | 大阪／奈良／京都全区域，东端三本松；补齐京阪奈缆车与短支线，非矩形包含名张。 [来源1](https://www.kintetsu.co.jp/foreign/english/ticket/krp_2day.html) · [来源2](https://www.kintetsu.co.jp/foreign/guidebook/english/pdf/krp_2day_2020_english.pdf) |
| 近铁铁路周游券 5 日 | 2026-11-10 现行条款 | 完成 | 近铁／伊贺全铁路含缆车；plus 额外权益是巴士，不扩大铁路范围。 [来源1](https://www.kintetsu.co.jp/foreign/english/ticket/krp_5day.html) |
| 近铁铁路周游券 5 日 plus | 2026-11-10 现行条款 | 完成 | 近铁／伊贺全铁路含缆车；plus 额外权益是巴士，不扩大铁路范围。 [来源1](https://www.kintetsu.co.jp/foreign/english/ticket/krp_5dayplus.html) |
| 日光全地区周游券 | 2026-11-10 现行条款 | 完成 | 两券铁路区间相同，巴士权益和天数不同；下今市是使用次数切换点，不是可乘铁路外边界。 [来源1](https://www.tobu.co.jp/en/ticket/nikko/all.html) |
| 日光世界遗产地区周游券 | 2026-11-10 现行条款 | 完成 | 两券铁路区间相同，巴士权益和天数不同；下今市是使用次数切换点，不是可乘铁路外边界。 [来源1](https://www.tobu.co.jp/en/ticket/nikko/city.html) |
| 川越优惠周游券 Premium | 2026-11-10 现行条款 | 完成 | 川越是不限次区间切换点，不能误作外边界；实际范围东上本线池袋—川越市。 [来源1](https://www.tobu.co.jp/en/ticket/kawagoe/premium.html) |
| 西武一日券 | 2026-11-10 现行条款 | 完成 | 不得把被排除的武藏境、是政标为券内边界。 [来源1](https://www.seiburailway.jp/en/ticket/seibu1daypass/) |
| 西武一日券＋长瀞 | 2026-11-10 现行条款 | 完成 | 长瀞是范围内车站，北侧真正边界是野上。 [来源1](https://www.seiburailway.jp/en/ticket/seibu1daypass/) |
| 箱根・镰仓周游券 | 2026-11-10 现行条款 | 完成 | 小田原、箱根汤本、强罗是范围内换乘，不应作为整券外边界；Romancecar 须另购特急票。 [来源1](https://www.odakyu.jp/english/passes/hakone_kamakura/) · [来源2](https://odakyu-global.com/passes/hakone-kamakura-pass/) |
| 京阪京都・大阪观光券 | 2026-11-10 现行条款 | 完成 | 本线系全区域含宇治、交野、男山缆车，不含大津；地铁／巴士和园区权益仅文字说明。 [来源1](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/kyoto-osaka.html) · [来源2](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Kyoto_Osaka_Validarea.pdf) |
| 京阪京都观光券 | 2026-11-10 现行条款 | 完成 | 石清水八幡宫—三条加鸭东、宇治、男山缆车；不再以京都矩形截断本线。 [来源1](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/kyoto-osaka.html) · [来源2](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Kyoto_Validarea.pdf) |
| 京阪京都・大阪＋鞍马贵船观光券 | 2026-11-10 现行条款 | 完成 | 京阪本线系全区域加叡山两线；不含叡山缆车。 [来源1](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/eizan-railway.html) · [来源2](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Validarea_Eizanrailway.pdf) |
| 京阪京都・大阪观光券（大阪 Metro 版） | 2026-11-10 现行条款 | 完成 | 本线系全区域含宇治、交野、男山缆车，不含大津；地铁／巴士和园区权益仅文字说明。 [来源1](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/osaka-subway.html) · [来源2](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Validarea_OsakaSubway.pdf) |
| 京阪大津观光券 | 2026-11-10 现行条款 | 完成 | 只含京津／石山坂本两线，区别于其他京阪观光券。 [来源1](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/otsu.html) · [来源2](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Validarea_Otsu.pdf) |
| 京阪京都・大阪观光券（枚方公园版） | 2026-11-10 现行条款 | 完成 | 本线系全区域含宇治、交野、男山缆车，不含大津；地铁／巴士和园区权益仅文字说明。 [来源1](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/hirakata-park.html) · [来源2](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Validarea_Hirakatapark.pdf) |
| 关西地区周游券（停售） | 截至 2026-09-30 停售的旧关西地区券（保留官方旧范围图） | 完成 | 历史券 JR 支线逐段到日吉／篠山口／伊贺上野等；另含指定一日京阪／阪急，不含任何新干线。 [来源1](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai/) · [来源2](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/kansai_map.jpg) |
| 关西铁路周游券 LITE | 2026-11-10 现行条款 | 完成 | 补叡山、阪堺、单轨、神户新交通；近铁按指定边界及排除支线；神户高速以实际运营公司的轨迹表示。 [来源1](https://www.surutto.com/kansai_rwpl/en/krp.html) · [来源2](https://www.surutto.com/kansai_rwpl/assets/pdf/areamap2026_en.pdf) |
| 南海全线 2 日券（停售） | 历史南海全线 2 日版；最终销售日及泉北合并前后版本未证实 | **待核** | 官方页面明确停售、全南海线含机场线；任意两日，指定席特急另付费。 [来源1](https://www.nankai.co.jp/en_railway/ticket/web-nankaiallline2daypass/) · [来源2](https://his-travel.co.id/nankai-all-line-pass/) |
| 香川迷你铁路・渡轮券（停售） | 截至 2026-09-30 停售的香川迷你 2 日版 | 完成 | 历史 2 日券：高松至观音寺／琴平／引田加琴电全线；2026-09-30 停售，不含本四备赞线去儿岛。 [来源1](https://shikoku-railwaytrip.com/news/pdf/202304_pricechange_en.pdf) · [来源2](https://shikoku-railwaytrip.com/news/pdf/20260806_en_japan-rail-passes.pdf) |

### 发布与清理

保留 `bfe9c85` 的默认分支检出、fetch/rebase 推送重试及发布任务 40 分钟保护；不强推，不回写主工作区的陈旧工作流。初次功能提交 `0f15fa6` 的 [Actions 42692795852](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42692795852) 在部署阶段超时，官方注释明确指出 `1800000` 被压回 `600000`。GitHub Pages [单次部署上限为 10 分钟](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)，[deploy-pages@v4 源码也限制为 600000](https://github.com/actions/deploy-pages/blob/v4/src/internal/deployment.js)。

修复两个发布入口：外层步骤设置真实的 `timeout-minutes: 30`；内部对同一上传产物最多尝试三次，每次 10 分钟，失败后短暂等待再试，成功后立即停止，第三次失败仍使任务失败。保留 40 分钟任务时限，并统一发布检出默认分支。3 项工作流回归通过，覆盖首次／第二次／第三次成功、全部失败、取消不重试、平台单次上限、实际外层时限及检出／推送保护。此配置提供有界重试，无法保证 GitHub 服务永不超时。

随后定时 [Actions 42729353640](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42729353640) 已成功发布包含本功能的版本；12 个修改前端／数据文件指纹一致。已在线再次逐券完成 54 张、108 个视图、11,212 个铁路像素采样点检查，无页面异常，原生 100 px 滚轮为 0.125 级，停止后额外变化为 0。

部署记录：功能提交 [`2c8a8ea`](https://github.com/06E-Felicia/06E-Felicia.github.io/commit/2c8a8eac32f10399f980bc861b63028c2e36578e)，由 [Actions 42732134206](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42732134206) 已成功（确认时间 2026-11-10 09:10:29（UTC+8），总耗时 11 分 9 秒）；上传与 Pages 发布均成功，超时后自动重试已在本次实际任务中生效。实际 [JPRail 页面](https://06e-felicia.github.io/JPRail.html) 的 14 个本次前端、数据及审核文件逐一 SHA-256 与功能提交相同，确认实际上线内容。此前 `b08ac3b` / Actions 42653355538 的局部通过不作为本次全目录结论。

线上再次逐券操作全部 54 张（含历史），108 个初始／近距离视图，11,212 个铁路实际像素采样点；每券等级／全部实际运营方筛选、详情收起／重开、唯一选择、关键站解析和桌面无空白检查通过。联网街道底图正常，金泽陆地实际像素与投影对齐检查通过；原生滚轮 100 px 为 0.125 级，稳定后额外缩放 0，无 JavaScript 页面异常。线上正式图覆盖同一张审核图。来源核验状态仍为 50 完成、4 待核，线上运行通过不补足官方证据缺口。

原始下载、PDF 展开、临时依赖、截图草稿、浏览器配置与机器检查 JSON 全在本任务独有系统临时目录，任务结束清理。仅保留生产数据／代码、复用测试、本摘要和一张正式审核图；没有生成完整模拟或回放，也未删除用户正式数据、其他任务文件或根目录 trash/。
