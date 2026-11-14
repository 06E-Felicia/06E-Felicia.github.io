# JPRail 当前验证摘要

2026-11-14，本次提交包括局界符号统一、全目录范围复核与灰线调整。按用户授权上传 GitHub；保留既有发布工作流，上传后不追加 Actions 或线上检查，不将推送成功等同于部署确认。

## 局界符号统一（本次提交）

- 普通运营交接、跨局 Pass 的内部局界、Pass 止于公司局界，全部采用同一种实线蓝色菱形。取消旧虚圈及局界处叠加的主要站双圈；保留普通站点中心、非局界的绿色边界圈和铁路端点细圈。是否属于本券适用边界仍由站点提示与详情说明，不改变票券范围。
- 图例、无障碍说明、详情、README 和缓存版本同步更新。局界菱形及内点仍在同一个 Canvas 上使用同一坐标与缩放变换；点击区域保持透明。
- 在最新 origin/main 的隔离工作树执行 16 项检查，108.269 秒全部通过。包含全部 55 券的 137 个实际局界符号：直接捕获 Canvas 的多边形、虚线和圆弧描边，确认每个局界恰有一个实线菱形、没有外部虚圈或枢纽双圈。额外覆盖辰野这种只有明确票券公司边界、没有接口目录记录的情况，以及普通非局界边界仍用圆圈。
- 普通边界／端点缩放和拖动检查 147 帧，内外圈偏移最大 0；触控板路径、桌面高度、手机详情、全部线路复位、55 券最终概览、范围回归和 3 项发布保护检查通过。联网预览白色底图 ready，无脚本异常，旧局界虚圈图例数量为 0。
- 本次只提交 16 个 JPRail 相关代码、数据、测试及当前文档／审核图文件；天气、航班、模拟器和发布工作流保持最新远端版本。此前范围复核的 4 项证据缺口继续保留。

## 范围复核与修正

目录 55 条产品（51 条现行／已公布、4 条历史／当季结束）全部逐项重新读取发行方资料。**51 条资料对照完成，4 条仍有明确证据缺口**。本轮仅复核铁路适用范围和相关限制；票价保留其原核查日期。“完成”表示已对照取得的官方资料，不是发行方认证或零错误保证。

- 北陆拱桥：2026-10-20 起现行日文产品仍附 2026-03-14 起版范围图。大糸线松本—南小谷—糸鱼川全线可用，改为完整保留两家公司原始线路，避免在内部交接站按站心裁切；补小滨／舞鹤全线、山阴京都—绫部。删除南小谷／龟冈／千叶的票券边界，南小谷保留独立公司交接标记；补绫部、佐仓、辰野的对应方向限制。
- 北陆拱桥及东日本・南北海道：总武线补千叶—佐仓，连接已有成田机场路线；东日本・南北海道另补鹤见—羽泽横滨国大支路。JR 东日本全域券补辰野饭田线方向边界说明。
- 关西迷你：补入官方范围图中的片町线京桥—木津，不把它误当范围外私铁。
- 所有命名区间均由实际详细网络拓扑重建概览／精细两档，不扩大矩形框、不作直线补接。小滨／舞鹤／大糸四个公司线路组合的完整原始轨迹另有回归。
- 非匹配线路改为 **#7A828A、80% 不透明度**。与同类匹配线路共用线宽：普通铁路 3 px、新干线 4 px。实际 Canvas 像素检查 RGB(122,130,138)、alpha 约 204；参考层仍低于彩色轨迹、不参与权限或数量计算。都市圈中新干线仍作为非匹配灰线保留。

## 尚未完成的证据项

- **东日本・南北海道周游券**：南北海道官方简图未给札幌东侧函馆线逐站边界；保留连接千岁线所需白石，不把白石宣称为已证实票券边界。；新潟西南支线尚缺可读的完整逐站边界表，已核对2026主图与东京插图，但不能宣称全券零漏线。
- **东北・南北海道周游券**：南北海道示意图未列札幌东侧函馆线逐站边界；地图接入千岁线需经白石，不能据此宣称白石是已核实票券边界。
- **福冈广域手机周游券**：手机版简图标为唐津，未找到西唐津是否包含的明确逐站条款，唐津端点暂按简图，尚不能宣称已完全核实。
- **南海全线 2 日券（停售）**：发行方遗留页未写停售日或泉北并入前后的版本日期；按销售方明确排除泉北的历史范围绘制，仍缺发行方带日期的完整历史条款。

页面详情保留“尚有未核实项目”提示；不以绘图检查通过将上述产品升级为完整核实。原始几何来自 N02-25，不将票券范围图当成列车实时运行证明。

## 验证

本轮检查结果：

- 13 项范围／筛选回归正常结束，53.956 秒通过；最终数据上的 5 项范围／概览复查，23.146 秒通过。55 条产品各有一条区间内和一条区间外的独立官方对照，未用证据不足的泉北历史版本或札幌东侧端点作为确定预期。
- 55 张券深度绘图专项通过，428.742 秒：2,416 个全国／区域／近距离视图，705 个关键站配置访问，460,318 个实际绘制铁路采样点。逐券检查各线路组、边界／端点、标签遮挡、原色与参考层级、缩放／拖动、等级／实际运营方和详情开关；未记录 JavaScript 页面异常。
- 收尾核对恢复既有概览简化精度（0.00045），未改券的派生范围记录与任务前逐项相等，仅东日本・南北海道及北陆拱桥的两档范围记录变化。最终精度再逐券检查 55 张、110 个概览视图：每券实际线路 Canvas 均有彩色铁路像素（合计 329,630 像素），可避开站名与控件的 214 个线路段采样通过。短私铁在区域视野可能全被站名盖住，使用实际线路缓冲区检查，不将零个可采样点当成已完成像素检查。
- 全部命名区间两档的站名集合、路径分支与首尾一致；大糸线两家公司全线、小滨与舞鹤全线的原始轨迹完整性回归通过，不用站点抽样代替整段轨迹比较。
- 独立联网 Chrome 预览：白色底图 ready，北陆拱桥显示 JR 东／西日本两段大糸线，南小谷不在票券边界名单；参考线与同类彩色线宽相等，无页面脚本异常。[当前正式审核图](jprail-map-review.png)。
- 测试收尾曾出现 Chrome 最后 Browser.close 确认挂住；改为停止本测试专属 Playwright 驱动并回收浏览器，13 项复跑正常结束。未操作用户浏览器。

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest development.tests.test_jprail_scope development.tests.test_jprail_filters development.tests.test_jprail_audit.FareRegressions -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest development.tests.test_jprail_audit.RenderedCatalogue -v
```

上述范围检查来自本轮前段；局界符号变更后的检查见上方。均未据此宣称尚缺官方证据的 4 券完整、全目录零错误或已经确认上线。

## 逐券核对记录

核对日期均为 2026-11-14，历史版日期在对应行标明。完整来源集合、明确边界及非边界名单保存在 [pass-audit.json](../../assets/data/jprail/pass-audit.json)。下表按官方图例判读，灰色参考站／公司交接点不自动视为票券边界。

| 产品 | 版本／状态 | 本轮独立核对要点与官方依据 |
|---|---|---|
| 日本全国铁路周游券 | 现行版；资料对照完成 | 重读全国券运输条件：JR六社客运线及东京单轨，青森／IR／爱之风／Hapi四项通过特例分别保留；JR内部交接不是全国券范围边界。 [官方产品／条款](https://japanrailpass.net/en/use/conditions-for-use/) |
| 青春18车票 | 现行版；资料对照完成 | 核对2026版日文条款：仅JR普通／快速；北陆三公司通过区间与全国JRPass不同，保留倶利伽罗跨公司接续及指定JR发着条件；新干线加购权益不混入基础图。 [官方产品／条款](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=126000037) |
| 北海道铁路周游券 | 现行版；资料对照完成 | 官方全域图及排除条款：北海道在来线，不含新干线与道南；留萌废止线不作可乘高亮，富良野—新得已废止段不补连。 [官方产品／条款](https://www.jrhokkaido.co.jp/global/english/ticket/railpass/) |
| 札幌－登别区域周游券 | 现行版；资料对照完成 | 逐对照橙色官方区域图：小樽、北海道医疗大学、岩见泽、登别、新千岁机场为外端；千岁／室兰交会段完整，不延伸洞爷。 [官方产品／条款](https://www.jrhokkaido.co.jp/global/english/ticket/railpass/) |
| 札幌－富良野区域周游券 | 现行版；资料对照完成 | 逐对照紫色官方区域图：小樽—旭川、旭川—富良野—泷川环路及新千岁机场；不含石胜线／Tomamu或札沼支线。 [官方产品／条款](https://www.jrhokkaido.co.jp/global/english/ticket/railpass/) |
| JR 东日本铁路周游券 | 现行版；资料对照完成 | 2026整合版官方条款确认全JR东日本、三陆／北越等指定公司及直江津—新井；东武仅指定直通和下今市以北区间，补辰野的饭田线方向限制。 [官方产品／条款](https://www.jreast.co.jp/en/multi/pass/eastpass.html) |
| 东京广域周游券 | 现行版；资料对照完成 | 核对官方2026区域图：普速到小淵泽／越后汤泽／黑矶／日立／常陆大子，新干线分别到佐久平／那须盐原；含小海全线、房总、伊豆急、富士急、上信及指定东武直通。 [官方产品／条款](https://www.jreast.co.jp/en/multi/pass/tokyowidepass.html) |
| 东日本・南北海道周游券 | 现行版；仍有待核项 | 重读2026官方主图及东京插图，确认中央至八王子、东海道至大船、常磐至取手；补千叶—佐仓连接成田机场和鹤见—羽泽横滨国大支路，不借图扩大成东京广域券。 [官方产品／条款](https://www.jreast.co.jp/en/multi/pass/easthokkaido.html) |
| 东北・南北海道周游券 | 现行版；仍有待核项 | 官方2026图南缘分别为白坂、勿来、矢祭山、新白河，西缘村上、小国、德泽、只见；不含东京与长野方向。南北海道细节证据仍不充分。 [官方产品／条款](https://www.jreast.co.jp/en/multi/pass/tohokuhokkaido.html) |
| 仙台区域周游券 | 现行版；资料对照完成 | 发行方明确白石—松岛、仙台—山寺、青叶通—松岛海岸、仙台机场全线及槻木—阿武隈；不把仙台枢纽当外边界，不含新干线。 [官方产品／条款](https://sendaitravelpass.jp/1day/en/) · [官方范围图](https://sendaitravelpass.jp/images/sendaiareapass_map.png) |
| 关西迷你周游券 | 现行版；资料对照完成 | 逐查官方粉色图，发现漏收片町线，补入京桥—木津连接；外缘山科、保津峡、宝冢、舞子、日根野，含奈良／宇治／关西机场支路，排除新干线。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansaimini/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/kansaimini_map.jpg) |
| 关西广域周游券 | 现行版；资料对照完成 | 官方蓝色图：山阴到由良、山阳到仓敷、姬新到津山、伯备到总社；含智头急行、京都丹后、和歌山电铁及高松，山阳新干线新大阪—冈山。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai_wide/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/kansai_wide_map.jpg) |
| 关西・广岛周游券 | 现行版；资料对照完成 | 官方红图：山阴至鸟取、山阳至岩国、福盐至府中、艺备至三次；高松、纪势至新宫及丹后／和歌山电铁在内，智头急行未列，山阳新干线止广岛。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai_hiroshima/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/kansai_hiroshima_map.jpg) |
| 关西・山阴周游券 | 现行版；资料对照完成 | 官方紫图：山阴至萩、山口至津和野、木次至备后落合；山阳至仓敷、姬新至津山；纪势仅和歌山—和歌山市，新干线新大阪—冈山。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai_sanin/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/kansai_sanin_map.jpg) |
| 关西・北陆周游券 | 现行版；资料对照完成 | 官方蓝绿图：北陆新干线至上越妙高，大糸仅JR西日本侧至南小谷；高山至猪谷、纪势至新宫；不含高松或智头急行，保留三项第三部门通过特例。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai_hokuriku/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/kansai_hokuriku_map.jpg) |
| 鸟取・松江周游券 | 现行版；资料对照完成 | 逐线核对官方浅蓝图：东滨—出云市、伯耆大山—根雨、宍道—木次、鸟取—郡家和境线全线；不把松江／米子误标外边界。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/tottorimatsue/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/tottorimatsue_map.jpg) |
| 山阳・山阴周游券 | 现行版；资料对照完成 | 官方绿图：关西／山阴／山阳至下关与博多新干线，含高松／智头／丹后；北陆在来线止敦贺、关西止柘植、纪势不越过和歌山南下，不含博多南线。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/sanyo_sanin/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/sanyo_sanin_map.jpg) |
| 广岛・山口周游券 | 现行版；资料对照完成 | 官方浅绿图：山阳普速至尾道，新干线博多—三原；艺备至三次、山阴至益田，含山口／美祢／宇部／小野田／岩德／吴／可部，不含九州在来线。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/hiroshima_yamaguchi/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/hiroshima_yamaguchi_map.jpg) |
| 关西广域游览周游券 | 现行版；资料对照完成 | 独立核对本券官网蓝图，与关西广域当前铁路范围一致：由良／津山／总社／仓敷／高松／新宫及指定私铁；不据资格相似自动复制范围。 [官方产品／条款](https://www.westjr.co.jp/global/en/ticket/pass/kansai_wide_excursion/) · [官方范围图](https://www.westjr.co.jp/global/en/ticket/pass/kansai_wide_excursion/images/kansai_wide_map.jpg) |
| 冈山・广岛・山口周游券 | 现行版；资料对照完成 | 官方黄图：冈山—下关、新干线冈山—博多；高松、总社、津山、府中、三次、益田各支路独立收尾，不含关西。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/okayama_hiroshima_yamaguchi/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/okayama_hiroshima_yamaguchi_map.jpg) |
| 北陆地区周游券 | 现行版；资料对照完成 | 官方图及条款：新干线敦贺—黑部宇奈月温泉、小滨线止小滨、高山止猪谷；七尾至和仓、越美北全线，爱之风／IR／Hapi仅指定通过段；不含大糸线。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/hokuriku/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/hokuriku_map.jpg) |
| JR 西日本全地区周游券 | 现行版；资料对照完成 | 官方全域图及公司范围：JR西日本全线含博多南，关西至龟山；另含丹后／智头／和歌山电铁及指定三公司通过段、能登七尾—和仓；不含JR四国到高松。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/all/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/all_map.jpg) |
| 北陆拱型铁路周游券 | 现行版；资料对照完成 | 重读2026-10-20现行产品所附日文图：补大糸线南小谷—松本、小滨／舞鹤全线、山阴京都—绫部和千叶—佐仓。移除南小谷／龟冈／千叶的错误票券边界，保留内部公司交接；补绫部、佐仓及辰野的方向限制。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/other/hokuriku-arch-pass/) · [官方范围图](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/download.html?fileId=20260128091929024&newwindow=true) |
| 濑户内地区周游券 | 现行版；资料对照完成 | 官方红图：新干线新大阪—博多；普速京都／龟冈、奈良／关西机场，山阳至下关；四国含高松—伊予大洲两条予赞通路及内子、琴平、栗林，不扩大到宇和岛。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/other/setouchi/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/other/setouchi_map.jpg) |
| 山阳・山阴・北部九州周游券 | 现行版；资料对照完成 | 独立对照粉色官方图：JR西山阳山阴同图范围加北九州至大分／宇土、新干线至熊本与西九州新干线；博多／下关为内部接续，不是本券外边界。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/other/ssnk/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/other/ssnk_map.jpg) |
| 高山・北陆地区周游券 | 现行版；资料对照完成 | 官方线路条文及大阪市内插图：名古屋—岐阜—高山—富山，新干线富山—敦贺，经湖西至京都／大阪市内／关西机场；不含米原绕行或东海道新干线。 [官方产品／条款](https://touristpass.jp/en/takayama_hokuriku/) · [官方范围图](https://touristpass.jp/assets/img/takayama_hokuriku/routemap_en.jpg) |
| 立山黑部・高山・松本地区周游券 | 2026-04-15 至 2026-11-10 使用季（2026-11-06 停售）；资料对照完成 | 按已结束的2026-04-15—11-10使用季核对：名古屋经高山到富山、经中央／松本到信浓大町，富山地方铁道电铁富山—立山；不把立山黑部非普通铁路交通画为普通铁路。 [官方产品／条款](https://touristpass.jp/en/alpine/) · [官方范围图](https://touristpass.jp/assets/img/alpine/routemap_en.jpg) |
| 伊势・熊野・和歌山地区周游券 | 现行版；资料对照完成 | 官方逐线条文：名古屋经关西／伊势铁道／纪势绕纪伊至大阪及关西机场，含参宫、和歌山电铁、JR关西木津路线和大阪市内插图；新宫／龟山为内部接续。 [官方产品／条款](https://touristpass.jp/en/ise_kumano/) · [官方范围图](https://touristpass.jp/assets/img/ise_kumano/routemap_en.jpg) |
| 富士山・静冈地区迷你周游券 | 现行版；资料对照完成 | 发行方逐线列明热海—丰桥、沼津—松田、富士—下部温泉、三岛—修善寺；巴士连接河口湖不冒充可乘富士急铁路，新干线不含。 [官方产品／条款](https://touristpass.jp/en/fuji_shizuoka/) · [官方范围图](https://touristpass.jp/assets/img/fuji_shizuoka/routemap_en.jpg) |
| 全九州铁路周游券 | 现行版；资料对照完成 | 官方全九州图与条款包含JR九州全线及下关、九州／西九州新干线，排除山阳新干线小仓—博多及所有其他公司；停运铁路并不表示可搭车。 [官方产品／条款](https://www.jrkyushu.co.jp/english/railpass/railpass.html) |
| 北部九州铁路周游券 | 现行版；资料对照完成 | 官方北九州图：普速到宇土／三角／大分，新干线到熊本，含西九州；熊本不能被错误用作鹿儿岛普速线边界，不含南阿苏／岛原等私铁。 [官方产品／条款](https://www.jrkyushu.co.jp/english/railpass/railpass.html) |
| 南部九州铁路周游券 | 现行版；资料对照完成 | 官方南九州图：熊本／大分以南JR九州，含三角、丰肥、肥萨、吉都、日南等；九州新干线熊本—鹿儿岛中央，不含肥萨橙铁道。 [官方产品／条款](https://www.jrkyushu.co.jp/english/railpass/railpass.html) |
| 福冈广域手机周游券 | 现行版；仍有待核项 | 现行手机版官方图：门司港—大牟田、小仓—行桥、筑丰／篠栗／香椎／后藤寺及姪滨—唐津；自由席及普通列车，无任何新干线；西唐津端仍待证实。 [官方产品／条款](https://www.jrkyushu.co.jp/english/railpass/mobilepass.html) |
| 四国铁路周游券 | 现行版；资料对照完成 | 2026-10-01新版官方附录明确JR四国／土佐黑潮全线，阿佐海岸DMV及琴电等；JR侧至儿岛，Sunrise不适用；移除的是小豆岛船／巴士，非铁路范围不扩缩。 [官方产品／条款](https://shikoku-railwaytrip.com/news/pdf/20260806_en_japan-rail-passes.pdf) |
| 大东京周游券 | 现行版；资料对照完成 | 官网及官方线网图13公司范围复核：普通铁路的九家私铁全部指定线路，JR／东京单轨／江之电／临海线不含；成田SkyAccess不等同北总全线自由上下车。 [官方产品／条款](https://greater-tokyo-pass.jp/en/) · [官方范围图](https://greater-tokyo-pass.jp/assets/images/rosen/line.pdf) |
| 近铁铁路周游券 1 日 | 现行版；资料对照完成 | 官方明文及区域图：大阪难波—近铁奈良、京都—筒井、长田—生驹及生驹钢索；不含生驹以东的京阪奈线、平端或生驹线菜畑。 [官方产品／条款](https://www.kintetsu.co.jp/foreign/english/ticket/krp_1day.html) |
| 近铁铁路周游券 2 日 | 现行版；资料对照完成 | 官方大阪／奈良／京都府县图逐线核对：大阪线至三本松，吉野全线与奈良各支线包含；不跨到赤目口／名张，列车特急费另付。 [官方产品／条款](https://www.kintetsu.co.jp/foreign/english/ticket/krp_2day.html) |
| 近铁铁路周游券 5 日 | 现行版；资料对照完成 | 本产品官网明确近铁全线及伊贺铁道，非5day plus的巴士权益；不含索道，乘特急另购特急券。 [官方产品／条款](https://www.kintetsu.co.jp/foreign/english/ticket/krp_5day.html) |
| 近铁铁路周游券 5 日 plus | 现行版；资料对照完成 | 本产品官网明确铁路同近铁全线及伊贺铁道，plus增加指定巴士；未据名称扩大到养老铁道或名铁。 [官方产品／条款](https://www.kintetsu.co.jp/foreign/english/ticket/krp_5dayplus.html) |
| 日光全地区周游券 | 现行版；资料对照完成 | 本券官网明确浅草—下今市一次往返，下今市—东武日光／新藤原自由乘车；不含野岩铁道到会津高原尾濑口，巴士／船权益另列。 [官方产品／条款](https://www.tobu.co.jp/en/ticket/nikko/all.html) |
| 日光世界遗产地区周游券 | 现行版；资料对照完成 | 独立核对本券官网：铁路同浅草接续及下今市—东武日光／新藤原，世界遗产区域是巴士差异，不应把鬼怒川支路删除；下今市是次数限制点。 [官方产品／条款](https://www.tobu.co.jp/en/ticket/nikko/city.html) |
| 川越优惠周游券 Premium | 现行版；资料对照完成 | 官网明确池袋—川越／川越市往返，川越—川越市可自由乘车；不延伸霞关，川越不是外端。 [官方产品／条款](https://www.tobu.co.jp/en/ticket/kawagoe/premium.html) |
| 西武一日券 | 现行版；资料对照完成 | 官网本券明确西武全线但排除多摩川线，特急／指定席另付；不包含秩父铁道，轨道以外的新交通按本页铁路显示口径排除。 [官方产品／条款](https://www.seiburailway.jp/en/ticket/seibu1daypass/) |
| 西武一日券＋长瀞 | 现行版；资料对照完成 | 官网本券在西武排除多摩川线之外，加秩父铁道野上／长瀞—三峰口；野上以北皆野方向不含，长瀞是内部站。 [官方产品／条款](https://www.seiburailway.jp/en/ticket/seibu1daypass/) |
| 箱根・镰仓周游券 | 现行版；资料对照完成 | 当前官方全小田急及箱根铁路／江之电权益复核：小田原、箱根汤本、强罗不是因换乘而成为票券范围外端；缆车、索道和巴士仅文字列出。 [官方产品／条款](https://www.odakyu.jp/english/passes/hakone_kamakura/) |
| 京阪京都・大阪观光券 | 现行版；资料对照完成 | 2026-04京阪官方金色图：京阪本线系、鸭东、中之岛、交野、宇治及钢索权益，不含京津／石山坂本或叡山；非JR权益。 [官方产品／条款](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/kyoto-osaka.html) · [官方范围图](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Kyoto_Osaka_Validarea.pdf) |
| 京阪京都观光券 | 现行版；资料对照完成 | 2026-04官方橙图：京阪本线石清水八幡宫—三条、鸭东至出町柳、宇治及钢索；交野和大阪方向灰线不可用。 [官方产品／条款](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/kyoto-osaka.html) · [官方范围图](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Kyoto_Validarea.pdf) |
| 京阪京都・大阪＋鞍马贵船观光券 | 现行版；资料对照完成 | 2026-04官方绿图：京阪本线系及叡山的鞍马／八濑两分支；不含大津线及叡山缆车，不把出町柳公司接续标作范围边界。 [官方产品／条款](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/eizan-railway.html) · [官方范围图](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Validarea_Eizanrailway.pdf) |
| 京阪京都・大阪观光券（大阪 Metro 版） | 现行版；资料对照完成 | 2026-04官方蓝图：京阪本线系铁路同京都大阪版，另附大阪Metro／巴士权益；未把灰色JR或叡山线路误纳铁路高亮。 [官方产品／条款](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/osaka-subway.html) · [官方范围图](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Validarea_OsakaSubway.pdf) |
| 京阪大津观光券 | 现行版；资料对照完成 | 2026-04官方紫图：仅京津线御陵—琵琶湖滨大津及石山坂本线石山寺—坂本比叡山口，不含京都市营地铁往三条京阪。 [官方产品／条款](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/otsu.html) · [官方范围图](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Validarea_Otsu.pdf) |
| 京阪京都・大阪观光券（枚方公园版） | 现行版；资料对照完成 | 2026-04官方青图：包含整段京阪本线系、宇治、交野及钢索权益，并非只可乘到枚方公园；不含大津或叡山。 [官方产品／条款](https://www.keihan.co.jp/travel/en/trains/passes-for-visitors-to-japan/hirakata-park.html) · [官方范围图](https://www.keihan.co.jp/travel/en/pdf/trains/passes-for-visitors-to-japan/Validarea_Hirakatapark.pdf) |
| 关西地区周游券（停售） | 截至 2026-09-30 停售的旧关西地区券（保留官方旧范围图）；资料对照完成 | 发行方停售遗留页及旧橙色图复核：JR上郡／播州赤穗／本龙野／篠山口／日吉／伊贺上野／敦贺／米原／和歌山，另含旧指定京阪和阪急一日权益；不含新干线。 [官方产品／条款](https://www.westjr.co.jp/travel-information/en/tickets-passes/jrwest-rail-pass/kansai/) · [官方范围图](https://www.westjr.co.jp/travel-information/en/assets/img/tickets-passes/jrwest-rail-pass/kansai_map.jpg) |
| 关西铁路周游券 LITE | 现行版；资料对照完成 | 发行方2026官方大图与注脚复核：参与私铁含近铁大阪线至青山町、吉野线至壶阪山；明确排除道明寺／田原本／西信贵及京阪大津、岚电和JR，不误补灰色参考线。 [官方产品／条款](https://www.surutto.com/kansai_rwpl/en/krp.html) |
| 南海全线 2 日券（停售） | 历史南海全线 2 日版；最终销售日及泉北合并前后版本未证实；仍有待核项 | 发行方停售遗留页确认全南海含机场线、任意2日、特急指定席另付；原销售期及泉北并入前后版本仍未找到带日期的发行方条款，不升级完整核实。 [官方产品／条款](https://www.nankai.co.jp/en_railway/ticket/web-nankaiallline2daypass/) |
| 香川迷你铁路・渡轮券（停售） | 截至 2026-09-30 停售的香川迷你 2 日版；资料对照完成 | 重读官方2023附录3范围图：高松—观音寺／琴平／引田及琴电全线，不含本四备赞至儿岛；2026-08停售公告确认9/30停售，作为历史版保留。 [官方产品／条款](https://shikoku-railwaytrip.com/news/pdf/20260806_en_japan-rail-passes.pdf) |

## 产物管理

保留生产修改、可复用测试、本摘要和一张正式审核图。官方原始下载、PDF 渲染、脚本草稿、浏览器截图草稿、日志及测试运行缓存均置于各自任务独有的系统临时目录，提交上传前完成清理。正式数据、其他任务文件及根目录 trash/ 不在清理范围。
