# JPRail 当前验证摘要

## 本轮：青函显示、独立局界、青春18、首页插画与预览入口（2026-11-13）

- 保留此前已完成的本地修改：青函共用区间统一按新干线红色／4 px 显示；14 个已知 JR 运营接口独立显示局界符号，不将内部局界自动变成票券边界；青春18默认列第二位，3日 ¥10,000／5日 ¥12,050，基础券不含新干线、海峡货运线与道南铁路。原始网络、车站及公司接口数据未改。依据：[JR北海道共用区间](https://www.jrhokkaido.co.jp/corporate/shinkansen/specificity.html)、[JR西日本青春18](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=126000037)、[JR北海道青春18](https://www.jrhokkaido.co.jp/CM/Otoku/007255/)、[2026新闻稿](https://www.jreast.co.jp/press/2025/20260205_ho02.pdf)。
- “启动本地预览.command”现在打开首页 index.html；模拟器启动器仍打开模拟器。首页启动不再要求先检查模拟器科学依赖；默认模块入口仍保留原模拟器行为。首页右侧介绍仅说明查询范围、价格、时间、限制与行程比较。
- 宣传图以用户最终提供的 1448×1086 插画为准，保留人物、标题、两张票卡、列车及接触网等内容。去掉所有站名框／引线，以及西北侧俄罗斯、朝鲜等境外陆地。旧示意线路由网页当前“全部线路”的真实截图替换：597／597 线路组，未选 Pass，无等级／公司筛选，仅日本轮廓；保留站点圆圈和局界符号，不含站名、底图、控件与境外地形。线路不是生成工具重画；在浏览器中按原构图合成为一张生产 WebP，不增加页面图层、监听器或地图逻辑。
- 最终文件：`assets/images/jprail-preview.webp`，1448×1086，335,878 字节。地图数据沿用 MLIT N02（加工）／OSM，轮廓来自 Natural Earth；宣传图不是实时轨道图，也不用于判断票券权限。生成工具原始输出保留在工具图库，项目只保留一张生产宣传图。
- 目录55条，新增青春181条官方核对；原54条两档范围记录结构相同。本轮未重新核实原54券全部最新条款；条款证据仍为51完成／4待核。绘图回归不代替这些证据缺口的核实。

### 本轮验证

- 从最新 origin/main 的隔离工作树测试：25项全部通过，114.965秒。覆盖本地预览入口、公司配色、全目录绘图、缩放与触控布局、票券数据及发布保护；118运营方、55券、228视图、14,082个真实铁路像素采样点；端点圆圈147帧最大相对偏移0。
- 最终单张宣传图替换后，1440×1000、390×844、320×640浏览器检查均成功加载1448×1086图像，无横向溢出。已人工查看最终合成图；人物、票卡、标题及列车未被日本地图遮盖，站名框／引线与境外陆地已移除。
- 青春18与青函／局界针对性回归，以及联网热海地图审核已完成；保留现有一张正式审核图 [jprail-map-review.png](jprail-map-review.png)。仅图片收尾后未重复整套地图回放。
- 发布准备只整理本任务文件；simulation/preview.py 和首页按任务差异合入最新远端，保留其他任务变更。工作流与发布重试 Action 无修改，保留默认分支检出、fetch/rebase重试、40分钟任务及30分钟Pages时限，不强推。按用户此前要求，上传后不做Actions／线上验收，因此不据推送结果宣称部署成功。
- 临时截图、统计及隔离工作树均位于本轮独有系统临时目录；任务收尾时停止本轮服务器并清理该目录。保留生产代码、可复用测试、本摘要和一张正式审核图，保护正式数据、其他任务文件与根目录 trash/。

### 最终插画处理提示词

使用内置 image_gen 编辑用户提供的原图；下方是最终底稿修订提示词。之后的实际线路截图与浏览器合成不交由生成工具重画。

```text
Precise compositing preparation edit of the supplied JPRail promotional image. Preserve ALL non-map content exactly: the purple-haired girl's identity, face, eyes, hair, clothing, pose and hands; camera; her booklet; both floating pass cards and every printed word on them; the JPRail logo and ALL existing headings/taglines; cherry blossoms, mountains, pagoda, train, viaduct, overhead contact wires and poles; overall palette, dimensions and composition. Change ONLY the geographical map artwork area. Remove all station-name callout boxes and their leader lines, including 新青森, 仙台, 東京, 名古屋, 新大阪, 広島 and 博多. Remove the northwest foreign mainland/coastline shapes representing Russia, China and the Korean peninsula and their boundary/road strokes. For accurate railway geometry, an exact transparent screenshot of Japan's real railway network will be overlaid afterward by the website: therefore clear the entire old Japanese map silhouette and all its old colored railway paths and station circles as well, leaving a clean seamless continuation of the existing pale blue-gray ocean/sky gradient in those map areas, with absolutely no replacement map or route invented by you. Do not remove, move, cover or change the floating pass cards that sit in front of the map. Do not alter the girl's extended hand or train where they meet the map area. No new text, no changed title, no new station names, no added dates. The result is the same original illustration with only the old geographic diagram and foreign land removed so a geographically exact label-free railway layer can be composited over it. Do not redesign the poster.
```

### 已应用的公司配色与来源

| 公司 | 实际颜色 | 依据 | 来源与限制 |
|---|---|---|---|
| IRいしかわ鉄道 | `#00A7E3` | 官网标识参考色 | [来源](https://www.ishikawa-railway.jp/assets/img/ir_logo_2.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| JR東海交通事業 | `#FF6B00` | 官网标识参考色 | [来源](https://tkj-i.co.jp/assets/images/logo.png)；城北线运营公司，属 JR 东海子公司；本表暂列独立运营主体，采用其 TKJ 标识橙，供审核。 |
| WILLER　TRAINS | `#E60012` | 官网标识参考色 | [来源](https://trains.willer.co.jp/corporate/profile/ci/img/willer.png)；采用官网 CI 页的企业标识红，不把京都丹后铁路昵称标识或车辆颜色代作企业色。 |
| あいの風とやま鉄道 | `#007AC6` | 官网标识参考色 | [来源](https://ainokaze.co.jp/common/images/logo.png)；多色标识，选用蓝；另含绿色。 |
| いすみ鉄道 | `#117C3B` | 官网标识参考色 | [来源](https://isumirail.co.jp/wp-content/uploads/2024/02/shiromoji.png)；官网标识绿色；原 PNG 半透明，取实色内容，不取白色抗锯齿。 |
| えちごトキめき鉄道 | `#3782BD` | 官方线路图参考色 | [来源](https://www.echigo-tokimeki.co.jp/img/img-line-guide.png)；官网范围图的日本海ひすいライン蓝；用于本页统一公司色，不冒充妙高はねうま等全部线路的官方统一色。 |
| えちぜん鉄道 | `#004097` | 官网标识参考色 | [来源](https://www.echizen-tetudo.co.jp/_assets/img/logo.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| くま川鉄道 | `#B08E42` | 官网标识参考色 | [来源](https://kumagawa-rail.com/wp-content/uploads/2025/06/kt-hp_logo.jpg)；官网金色标识为压缩／渐变图，#B08E42 是采用金色近似值，不是官方公布 RGB。 |
| しなの鉄道 | `#2A519F` | 官网标识参考色 | [来源](https://www.shinanorailway.co.jp/common/img/logo_footer.gif)；多色标识，选用蓝；另含金黄。 |
| のと鉄道 | `#00A0EA` | 官网标识参考色 | [来源](https://nototetsu.jp/wp-content/uploads/2022/09/logo.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| ひたちなか海浜鉄道 | `#FF9933` | 售票路线图参考色 | [来源](https://ticket.jorudan.co.jp/hitachinaka-rail/img/routemap01.png)；Jorudan 湊线售票路线图的线路橙色；原公司标识色仍未证实，此色用于地图参考。 |
| わたらせ渓谷鐵道 | `#651614` | 官网标识参考色 | [来源](https://www.watetsu.com/assets/img/logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| アイジーアールいわて銀河鉄道 | `#0F459B` | 官网标识参考色 | [来源](https://igr.jp/wp-content/themes/igr/assets/images/logo_igr.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| アルピコ交通 | `#2E3F99` | 官网标识参考色 | [来源](https://www.alpico.co.jp/traffic/files/images/header/img_logo.jpg)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| ハピラインふくい | `#E6378D` | 官网标识参考色 | [来源](https://www.hapi-line.co.jp/theme/default/img/common/logo/site_logo.svg)；多色标识，选用粉红；另含黄绿。 |
| 一畑電車 | `#DC000C` | 官网标识参考色 | [来源](https://railway.ichibata.co.jp/wp-content/media/f_logo_1.svg)；采用公司字标旁的红色标志，不选橙／黄的昵称宣传字。 |
| 三岐鉄道 | `#182D82` | 官网标识参考色 | [来源](https://sangirail.co.jp/images/images2022111617170283.jpg)；官网蓝色标识的代表色。 |
| 三陸鉄道 | `#0075C1` | 官方象征色的屏幕近似值 | [来源](https://www.sanrikutetsudou.com/三陸鉄道の車両のご紹介・列車ご利用のご案内/)；官方列车象征色包括蓝、红、白，蓝表示三陆海洋；本页选蓝色近似值，并非公布的企业 RGB 规范。 |
| 上信電鉄 | `#004999` | 官网铁路服务页参考色 | [来源](https://www.joshin-dentetsu.co.jp/wp/wp-content/themes/joshin-dentetsu/css/railway.css?ver=20190906)；官网 railway.css 的 .rosen_map li a 边框／文字蓝。 |
| 上毛電気鉄道 | `#46352B` | 官网标识参考色 | [来源](https://jomorailway.com/images/common/logo.png)；官网 JOMO 标志深棕色；按原图主要棕色像素取值。 |
| 上田電鉄 | `#E46018` | 官网标识参考色 | [来源](https://www.uedadentetsu.com/assets/themes/uedadentetsu_202003/imgs/common/header_sitetitle.png)；小尺寸 PNG 取标志橙色近似值。 |
| 井原鉄道 | `#759A31` | 官方线路图参考色 | [来源](https://www.ibara-railway.co.jp/wp-content/themes/child/image/contents/area/rail-map.jpg)；官网井原线站点／线路图的绿色，PNG 代表色。 |
| 京成電鉄 | `#77499C` | 地图辨识配色（本页调整） | [来源](https://www.keisei.co.jp/assets/images/common/head_logo.png)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #154F9E。采用 Liner Blue；另含 Liner Red。 |
| 京浜急行電鉄 | `#9D273C` | 地图辨识配色（本页调整） | [来源](https://www.keikyu.co.jp/company/outline.html)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #004098。官方公司概要展示蓝色 KEIKYU；#004098 是拟用屏幕近似值，未取得官方 RGB 规范。 |
| 京王電鉄 | `#C3428A` | 地图辨识配色（本页调整） | [来源](https://www.keio.co.jp/assets/img/common/icon_company_logo.svg)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #0F3675。多色标识，拟选蓝；另含京王红。 |
| 京阪電気鉄道 | `#E95504` | 官网标识参考色 | [来源](https://www.keihan.co.jp/app-files/img/cmn_logo01.svg)；多色标识，选用橙；另含蓝灰。仅本线系普通铁路部分。 |
| 仙台空港鉄道 | `#0A50A1` | 官网标识参考色 | [来源](https://www.senat.co.jp/wp-content/themes/mythemes/img/rogo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 伊予鉄道 | `#EA6000` | 官网标识参考色 | [来源](http://www.iyotetsu.co.jp/common/img/logo.png)；兼营公司只处理高浜、横河原、郡中三条郊外铁路；不处理市内电车和巴士。 |
| 伊勢鉄道 | `#036CE1` | 官网标识参考色 | [来源](https://isetetu.co.jp/js/header.js#inline-header-mark)；内联标志继承页面 CSS；取固定顶栏／页脚实际填色 #036CE1，不把白色版解析成默认黑。 |
| 伊豆急行 | `#0386CE` | 官网标识参考色 | [来源](https://www.izukyu.co.jp/assets/images/common/logo.jpg)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 伊豆箱根鉄道 | `#007A24` | 官网标识参考色 | [来源](http://www.izuhakone.co.jp/share/imgs/h-logo.png)；采用本公司绿色标志，不选同页的西武集团标识。 |
| 伊賀鉄道 | `#0767B1` | 官网标识参考色 | [来源](https://www.igatetsu.co.jp/igatetsu/wp-content/themes/igatetsuwp/images/logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 会津鉄道 | `#21701A` | 官网标识参考色 | [来源](https://aizutetsudo.jp/wp-content/themes/aizutetsudo/assets/images/common/logo.png)；多色标识，选用绿色；另含橙色。 |
| 信楽高原鐵道 | `#00A779` | 官网标识参考色 | [来源](https://koka-skr.co.jp/img/footer/footerLogo.jpg)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 北条鉄道 | `#8D512D` | 官网标识参考色 | [来源](http://www.hojorailway.jp/wp-content/themes/houjyostyle/images/rogo_e.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 北総鉄道 | `#6B819E` | 地图辨识配色（本页调整） | [来源](https://www.hokuso-railway.co.jp/images/common/header_logo01.svg)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #16379E。多色标识，拟选蓝色。 |
| 北越急行 | `#073190` | 官网标识参考色 | [来源](https://hokuhoku.co.jp/img/logo01.png)；多色标识，选用蓝；另含红。 |
| 北陸鉄道 | `#D74739` | 其他地图分类参考色 | [来源](https://tetsudozyoho.com/tetsudomap/)；参考铁道情報館全国铁路地图图例的私铁红色类别；HEX 为本页所选屏幕近似值，不是公司官方品牌色，也未复制该地图几何或宣称逐像素复刻。 |
| 南海電気鉄道 | `#E94E00` | 官网标识参考色 | [来源](https://www.nankai.co.jp/common/img/logo/nankai-logo.svg)；取当前官网标识朱橙；另含黄色。排除钢索线。 |
| 南阿蘇鉄道 | `#029178` | 官网标识参考色 | [来源](https://www.mt-torokko.com/img/common/header-logo.png)；多色标识，选用青绿；另含深绿及红。 |
| 叡山電鉄 | `#008663` | 官网标识参考色 | [来源](https://eizandensha.co.jp/files/img/common/logo_eiden.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 名古屋臨海高速鉄道 | `#4344A3` | 官网标识参考色 | [来源](https://www.aonamiline.co.jp/sys/wp-content/themes/aonami/assets/img/common/header_logo.svg)；多色标识，选用蓝紫；另含青蓝。 |
| 名古屋鉄道 | `#004DA0` | 官网标识参考色 | [来源](https://top.meitetsu.co.jp/img/header_identity_01.svg)；取得当前官网 SVG，修正此前 CSS 近似值 #004EA2 为实际标识蓝 #004DA0；不是车辆猩红。 |
| 和歌山電鐵 | `#CC3518` | 官网标识参考色 | [来源](https://wakayama-dentetsu.co.jp/wp-content/uploads/logo_a-1.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 四日市あすなろう鉄道 | `#00904C` | 官网标识参考色 | [来源](https://yar.co.jp/common/img/layout/footer/fLogo.gif)；采用公司标识绿；另含浅蓝。不因窄轨而排除，仍为普通铁路。 |
| 土佐くろしお鉄道 | `#00B0E7` | 官网标识参考色 | [来源](https://static.wixstatic.com/media/06d37b_32b04ee8d43546e685cc9d7165fea51b%7Emv2.png/v1/fill/w_192%2Ch_192%2Clg_1%2Cusm_0.66_1.00_0.01/06d37b_32b04ee8d43546e685cc9d7165fea51b%7Emv2.png)；官网图标及官方三社合作资料交叉确认浅蓝标识；PNG 代表色。 |
| 大井川鐵道 | `#2B3A60` | 官网铁路服务页参考色 | [来源](https://daitetsu.jp/wordpress/wp-content/themes/oigawa/style.css?20240711)；官网车站区块 .station-wrap 的边框蓝和铁路站点提示文字色；不是宣称本线／井川线统一官方线路色。 |
| 天竜浜名湖鉄道 | `#79A833` | 其他地图分类参考色 | [来源](https://tetsudozyoho.com/tetsudomap/)；参考铁道情報館全国铁路地图图例的第三部门黄绿色类别；HEX 为本页所选屏幕近似值，不是公司官方品牌色，也未复制该地图几何或宣称逐像素复刻。 |
| 富士山麓電気鉄道 | `#5A2200` | 官网标识参考色 | [来源](https://www.fujikyu-railway.jp/fujisanroku/images/logo_mark.png)；官网 FujiQ 标识不透明版为棕色；不取淡化透明版与白底混合后的浅色。 |
| 富山地方鉄道 | `#D74739` | 其他地图分类参考色 | [来源](https://tetsudozyoho.com/tetsudomap/)；参考铁道情報館全国铁路地图图例的私铁红色类别；HEX 为本页所选屏幕近似值，不是公司官方品牌色，也未复制该地图几何或宣称逐像素复刻。 |
| 小湊鐵道 | `#FF3700` | 官网铁路服务页参考色 | [来源](https://www.kominato.co.jp/wp-content/themes/html5blank-stable/common/css/station.css?mod=20230330040453)；官网车站栏目、站名标和车站菜单的朱红色。 |
| 小田急箱根 | `#EF4A00` | 官网标识参考色 | [来源](https://www.odakyu-hakone.jp/common/img/logo.gif?20240306)；官网当前公司字标橙色；仅鉄道線，不含钢索线／索道。 |
| 小田急電鉄 | `#009CA7` | 地图辨识配色（本页调整） | [来源](https://www.odakyu.jp/common/img/logo.svg)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #004EA2。官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 山形鉄道 | `#3B3290` | 官网标识参考色 | [来源](https://flower-liner.jp/wp/wp-content/themes/yamatetsu/img/logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 山陽電気鉄道 | `#E31B13` | 官网标识参考色 | [来源](https://www.sanyo-railway.co.jp/assets/img/common/logo.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 岳南電車 | `#CF664D` | 官方线路图参考色 | [来源](https://www.gakutetsu.jp/a68089000000024f-img/rosenzu.png)；官网路線図中岳南本线的赤陶色；不取旁侧 JR 东海道线／新干线颜色。 |
| 島原鉄道 | `#112953` | 官方车站图参考色 | [来源](https://www.shimatetsu.co.jp/storage/content-page/1CO8acYwrxoeGk4653CQQrC32Thgv5nsZ30C26XX.png)；官网諫早—島原港站点图的深蓝站点／文字色；图中另有红点，本页选深蓝作为单一显示色。 |
| 嵯峨野観光鉄道 | `#8A2222` | 官网铁路服务页参考色 | [来源](https://www.sagano-kanko.co.jp/cms/wp-content/themes/saganokanko/assets/css/station.css?d=1769477525)；官网 station.css 的车站线路栏目／强调色深红，不把白色标志解释成无品牌色。 |
| 平成筑豊鉄道 | `#0065B2` | 官网标识参考色 | [来源](https://www.heichiku.net/wp-content/themes/heichiku2020/assets/img/logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 弘南鉄道 | `#1E9C43` | 官网标识参考色 | [来源](https://konantetsudo.jp/wp2/wp-content/uploads/tcd-w/logo.png?1794314024)；多色标识，选用绿；另含橙。 |
| 愛知環状鉄道 | `#0058A4` | 官网标识参考色 | [来源](https://www.aikanrailway.co.jp/images/logo.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 明知鉄道 | `#E73828` | 官网铁路服务页参考色 | [来源](https://www.aketetsu.co.jp/wp-content/themes/aketetsu/style.css?ver=20260521044335)；官网铁路与车站页面标题／站名样式的红色。 |
| 智頭急行 | `#004196` | 官网标识参考色 | [来源](https://www.chizukyu.co.jp/user/assets/img/common/logo.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 東京臨海高速鉄道 | `#205A48` | 地图辨识配色（本页调整） | [来源](https://www.twr.co.jp/Portals/0/Skins/TWR/images/logo.png)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #00418E。官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 東急電鉄 | `#D65026` | 地图辨识配色（本页调整） | [来源](https://www.tokyu.co.jp/#inline-logo)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #E83817。取得官网内联 SVG 实值，修正此前近似值 #E60012 为 #E83817；排除世田谷线。 |
| 東武鉄道 | `#1D77B4` | 地图辨识配色（本页调整） | [来源](https://www.tobu.co.jp/_assets/images/common/logo_tobu.png)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #0950A7。蓝色渐变标识，选代表值；并非唯一 RGB 规范。 |
| 東葉高速鉄道 | `#5AB55C` | 官方线路图参考色 | [来源](https://www.toyokosoku.co.jp/wp/images/route_jpn_2504.png)；官网线路图的东叶高速线为绿色；不取同图东京 Metro 东西线蓝或银座线橙。 |
| 松浦鉄道 | `#E70012` | 官网标识参考色 | [来源](https://matutetu.com/files/libs/3797/202203220939373300.png?1647909577)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 樽見鉄道 | `#D0B46A` | 官网标识参考色 | [来源](https://tarumi-railway.com/images/common/logo_txt.svg)；SVG 金色实值；浅色，后续实际绘图需检查白色底图对比度。 |
| 水島臨海鉄道 | `#007BBD` | 官网标识参考色 | [来源](https://www.mizurin.co.jp/img/logo1.png)；多色标识，选用深蓝；另含浅蓝。 |
| 水間鉄道 | `#5AC13E` | 官网标识参考色 | [来源](https://www.suitetsu.com/image/top/logo.jpg)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 江ノ島電鉄 | `#00A943` | 官网标识参考色 | [来源](http://www.enoden.co.jp/common/images/top/logo_2026_05_only.png)；公司官网沿革另明确企业绿色；虽有短距离街面段，仍纳入普通铁路。 |
| 津軽鉄道 | `#FF6600` | 官方车站图参考色 | [来源](https://tsutetsu.com/tsutetsu/wp-content/uploads/2015/09/rosenzu-01.png)；官网线路与沿线指南的橙色站点标识；用于本页公司色，不称为官方统一线色规范。 |
| 流鉄 | `#5D8354` | 官网标识参考色 | [来源](http://ryutetsu.jp/img/logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 熊本電気鉄道 | `#750124` | 官网标识参考色 | [来源](https://www.kumamotodentetsu.co.jp/shared/img/common/head_logo.jpg)；官方页眉 CSS 标志深红代表色；不取巴士招聘、商店周年或社交图标。 |
| 甘木鉄道 | `#CD1402` | 官网标识参考色 | [来源](https://www.amatetsu.jp/share/head_left.gif)；从官方 header.js 确认公司红色标志资源，不取 LINE 绿色；采用近似红。 |
| 由利高原鉄道 | `#009D72` | 官网标识参考色 | [来源](https://www.obako5.com/wp-content/uploads/2022/03/topbanner.png)；采用官网主字标中的绿色近似值，不选辅助俱乐部／广告／社交网站图标。 |
| 相模鉄道 | `#303B77` | 地图辨识配色（本页调整） | [来源](https://www.sotetsu.co.jp/_nuxt/group_logo.C0rwaJfS.svg)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #243C98。官方 CI 解释确认 SOTETSU 蓝／橙；取当前官方 SVG 蓝 #243C98。 |
| 真岡鐵道 | `#003149` | 官网标识参考色 | [来源](https://www.moka-railway.co.jp/wp-content/uploads/2019/11/moka_logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 神戸電鉄 | `#94283D` | 官网标识参考色 | [来源](https://www.shintetsu.co.jp/cms/wp-content/themes/original/dist/images/site_logo.webp)；小尺寸／有抗锯齿 PNG，采用标志深红近似值。 |
| 福島交通 | `#E5001E` | 官网标识参考色 | [来源](http://www.fukushima-koutu.co.jp/images/logo-index.svg)；多色公司标识，选用红；另含绿、蓝、黄。只处理饭坂线。 |
| 秋田内陸縦貫鉄道 | `#E60012` | 官网标识参考色 | [来源](https://www.akita-nairiku.com/images/common/header_logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 秩父鉄道 | `#01479D` | 官网标识参考色 | [来源](https://www.chichibu-railway.co.jp/wp-content/themes/tpl_chichibu/images/logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 紀州鉄道 | `#004599` | 官网标识参考色 | [来源](https://kitetsu.jp/cms/wp-content/uploads/job-logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 肥薩おれんじ鉄道 | `#FCC800` | 官网标识参考色 | [来源](https://www.hs-orange.com/common/images/top1/ologo.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 能勢電鉄 | `#A4223E` | 官网标识参考色 | [来源](https://noseden.hankyu.co.jp/img/common/logo_j.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 芝山鉄道 | `#DF032E` | 官网标识参考色 | [来源](https://www.sibatetu.co.jp/images/logo.png)；多色标识，选用红；另含绿。 |
| 若桜鉄道 | `#266DB6` | 官网标识参考色 | [来源](https://wakatetsu.co.jp/wp/wp-content/themes/wakatesu/img/logo-3.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 西日本鉄道 | `#154B97` | 官网标识参考色 | [来源](https://www.nishitetsu.jp/assets/images/common/header_logo.png)；选用标识蓝；另含红、橙。只处理铁路，不处理巴士业务。 |
| 西武鉄道 | `#5A8421` | 地图辨识配色（本页调整） | [来源](https://www.seiburailway.jp/assets/images/header/logo.svg)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #3366CC。拟选铁路公司标识蓝；另含浅蓝、绿。排除山口线新交通系统。 |
| 豊橋鉄道 | `#F3D823` | 官网标识参考色 | [来源](https://www.toyotetsu.com/assets/img/common/logo-header.svg)；取当前 Much MORE! 公司标识黄；仅渥美线，不处理东田本线／市内线。 |
| 近江鉄道 | `#FCCD32` | 官网标识参考色 | [来源](https://www.ohmitetudo.co.jp/assets/images/header/logo_ohmigroup_kodo.png)；取本公司集团标识黄，不选同页西武集团标识或通用列车图标；PNG 代表色。 |
| 近畿日本鉄道 | `#0068B7` | 官网标识参考色 | [来源](https://www.kintetsu.co.jp/common/rn/image/header/header_logo.svg)；取官网 SVG 蓝；本次排除钢索及けいはんな地铁型线路部分。 |
| 道南いさりび鉄道 | `#008CCF` | 官网标识参考色 | [来源](https://www.shr-isaribi.jp/wp-content/themes/isaribi/images/header/header_title.png)；渐变蓝标识，选中蓝代表色；另含橙黄装饰。 |
| 遠州鉄道 | `#0081CC` | 官网标识参考色 | [来源](https://train.entetsu.co.jp/images/logo.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 野岩鉄道 | `#204581` | 官网标识参考色 | [来源](https://www.yagan.co.jp/assets/img/common/logo-yagan.svg)；官网公司字标蓝的采用近似值。 |
| 銚子電気鉄道 | `#D74739` | 其他地图分类参考色 | [来源](https://tetsudozyoho.com/tetsudomap/)；参考铁道情報館全国铁路地图图例的私铁红色类别；HEX 为本页所选屏幕近似值，不是公司官方品牌色，也未复制该地图几何或宣称逐像素复刻。 |
| 錦川鉄道 | `#E60010` | 官网标识参考色 | [来源](https://nishikigawa.com/wp-content/uploads/logo-white-main.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 長良川鉄道 | `#1C499E` | 官网标识参考色 | [来源](https://www.nagatetsu.co.jp/img/common/logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 長野電鉄 | `#CE000D` | 官网标识参考色 | [来源](https://www.nagaden-net.co.jp/hubfs/nagaden2024/img/logo.png)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 関東鉄道 | `#1D2088` | 官网标识参考色 | [来源](https://www.kantetsu.co.jp/cms/wp-content/themes/kr/img/common/logo.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 阪急電鉄 | `#A60030` | 官网标识参考色 | [来源](https://www.hankyu.co.jp/common/img/logo.svg)；取企业标识红，不把车辆栗色冒充标识色。 |
| 阪神電気鉄道 | `#38ACB5` | 官网标识参考色 | [来源](https://www.hanshin.co.jp/image/common/logo_taisetsu_gr.svg)；官网公司标识 SVG 取色；未宣称为唯一企业色规范。 |
| 阿佐海岸鉄道 | `#16439F` | 官网标识参考色 | [来源](https://asatetu.com/dmv/wp-content/uploads/2021/11/logo.png)；只处理 DMV 的铁路区段，巴士区段不纳入铁路上色；选用企业标识蓝。 |
| 阿武隈急行 | `#019EE4` | 官网标识参考色 | [来源](https://www.abukyu.co.jp/wp-content/themes/abu/dist/img/webp/common/logo.webp)；官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 青い森鉄道 | `#2CBADC` | 其他路线资料参考色 | [来源](https://w.atwiki.jp/traininformation/pages/1786.html)；铁道情報wiki 的青い森铁道线明确列出 #2CBADC；属于第三方参考，官方 CI 标志色仍未证实。 |
| 静岡鉄道 | `#E40038` | 官网标识参考色 | [来源](https://train.shizutetsu.co.jp/wp-content/themes/shizutetsu/images/head-logo.svg)；多色标识，选用红；另含浅蓝。 |
| 養老鉄道 | `#009944` | 官网标识参考色 | [来源](https://www.yororailway.co.jp/wp-content/themes/yororailway/img/webp/logo.webp)；多色标识，选用绿；另含黄绿。 |
| 首都圏新都市鉄道 | `#8C711E` | 地图辨识配色（本页调整） | [来源](https://www.mir.co.jp/common/img/hdr_logo01.png)；为区分东京及近郊相邻私铁而选用的本页显示色，并非公司官方色；原参考色 #003B83。官网公司标识取代表色；未查得单一官方 RGB 规范。 |
| 高松琴平電気鉄道 | `#1D2089` | 官网标识参考色 | [来源](https://www.kotoden.co.jp/image/kotodengrouprogo.jpg)；取ことでん公司集团标识深蓝，不取带颜色的“电车”导航按钮。 |
| 鹿島臨海鉄道 | `#79A833` | 其他地图分类参考色 | [来源](https://tetsudozyoho.com/tetsudomap/)；参考铁道情報館全国铁路地图图例的第三部门黄绿色类别；HEX 为本页所选屏幕近似值，不是公司官方品牌色，也未复制该地图几何或宣称逐像素复刻。 |
| 黒部峡谷鉄道 | `#EE7700` | 官网标识参考色 | [来源](https://www.kurotetu.co.jp/img/logo_top_sp.png)；普通黏着式窄轨铁路，不是钢索缆车；取官网铁路标识橙。 |

### 发布与产物管理

用户最新指示已授权上传本轮修改（取代此前“暂不上传”）。从最新 `origin/main` 建立隔离工作树，只整理本任务文件；保留已有默认分支检出、fetch/rebase 推送重试、40 分钟任务、30 分钟 Pages 步骤与三次有界重试。不回写主工作区陈旧工作流、不强推。3 项发布保护回归通过（0.032 秒），隔离工作树中两份工作流和发布重试 Action 均未修改。功能提交 [`b1df4e1`](https://github.com/06E-Felicia/06E-Felicia.github.io/commit/b1df4e18656cb5633c13a0e3afa553823b66d548) 已上传主分支；[Actions 42842435151](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42842435151) 与 Pages 均成功，部署状态确认于北京时间 2026-11-10 23:39:56。线上 12 个本轮发布文件的 SHA-256 与该提交全部一致。

补充线上自动检查中，4 项完成、2 项在页面导航／等待初始化时超时，线上逐券自动检查未完成，不宣称线上全目录验收通过；此前本地逐券 54 张检查和联网底图审核已通过。用户确认上传与发布成功，并要求清理后结束，因此不再追加检查或推送。本段为本地收尾记录。

本轮临时官网下载、失败下载片段、截图草稿、运行日志与浏览器检查统计均放在唯一系统临时目录，隔离工作树已移除；现已完成清理。只保留生产代码／颜色数据、可复用测试、本摘要和一张正式审核图；不删除正式数据、其他任务文件或根目录 `trash/`。

## 已发布历史：触控板捏合与响应式布局（2026-11-10）

- 用户确认 Mac 操作为双指捏合。Chromium 的 Ctrl+wheel 捏合单独使用 8 倍于普通滚轮的级别增量，保留连续目标／单 RAF、反向、小增量和上下限；普通滚轮仍为 100 px = 0.125 级。桌面 Safari 原生 gesture 事件按相邻 scale 比例处理，并选择单一输入路径，防止同一手势又被 wheel 重复执行。手机原有触摸缩放继续由 Leaflet 处理。
- 桌面顶栏 108→68 px，筛选条 73→42 px，页脚 42→26 px；站名与线路颜色说明收紧。1680×1050、选中北陆券的同一场景中，地图高度约 625→794 px，增加约 169 px。
- 手机／窄屏（≤960 px）详情改为地图下方的普通文档区域，独立滚动且可收起；选择 Pass 后回到地图顶部。取消固定底部浮层，地图保持原高度。961–1180 px 的桌面详情也使用独立列，不再浮在地图之上。
- 联网 Chrome 检查白色底图正常；390×844 手机地图约 414 px 高，详情从其下方开始，未覆盖地图。当时保存过手机实测审核图；按单图管理要求，现已由上方当前配色审核图覆盖。

验证：本次 6 项浏览器／数据回归通过（24.887 秒）；覆盖普通滚轮与捏合增量、连续／反向／惯性、停止后无额外跳变、原生 Chromium 合成捏合、Safari 事件路径去重，以及桌面 961／1100／1440／1680 和窄屏 320／390／768／844／960 的布局、横屏、详情开关、地图命中与无横向溢出。Chromium 原生 1.5 倍捏合输入实际改变约 0.405 级，输入逐个取消浏览器默认行为，页面自身未被缩放。Safari 使用事件能力模拟回归，没有宣称完成物理触控板人工验收。

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest development.tests.test_jprail_touch_layout development.tests.test_jprail -v
```

本次代码提交：`456ed9a`；发布与使用说明提交：`4bf6424`。首次 [Actions 42737337378](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42737337378) 的构建／制品上传完成，但 Pages 在 `deployment_queued`／`syncing_files` 超时，整次运行 30 分 44 秒后失败。最新主分支的第二次 [Actions 42741902694](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42741902694) 已成功，任务耗时 11 分 10 秒，GitHub Pages 部署状态于北京时间 2026-11-10 10:30:15 确认为 `success`。保留默认分支检出、推送 fetch/rebase 重试、三次 Pages 尝试及真实 30 分钟步骤／40 分钟任务时限；本次未回写工作流。

上线验收：6 个实际 Pages 文件（HTML、camera／主脚本、CSS、报告与审核图）的 SHA-256 均与 `4bf6424` 一致。随后对真实线上页面执行本轮 4 项浏览器回归，48.209 秒全部通过。另在在线 1680×1050 与 390×844 场景检查真实白色底图均为 `ready`，无页面脚本错误；桌面地图 794.234 px 高、详情为独立右列，手机地图 413.547 px 高、详情起点在地图底部下方。补充使用说明中的捏合／手机详情位置，纠正旧版矩形裁切说明。当前摘要的部署结果以本段为准；下方范围审查属于上一轮，未借本次布局验收扩大其结论。

```sh
JPRAIL_BASE_URL=https://06e-felicia.github.io JPRAIL_LIVE_BASEMAP=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest development.tests.test_jprail_touch_layout -v
```

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
| 青春18车票 | 2026春夏冬版本，冬季11/27开售 | 完成 | 连续3／5日、基础券不含新干线；四项第三部门通过区间单独提取，接续／限制站不当作全国券边界。[JR西日本](https://tickets.jr-odekake.net/shohindb/view/consumer/tokutoku/detail.html?shnId=126000037) · [JR北海道](https://www.jrhokkaido.co.jp/CM/Otoku/007255/) |
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

### 历史发布与清理

保留 `bfe9c85` 的默认分支检出、fetch/rebase 推送重试及发布任务 40 分钟保护；不强推，不回写主工作区的陈旧工作流。初次功能提交 `0f15fa6` 的 [Actions 42692795852](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42692795852) 在部署阶段超时，官方注释明确指出 `1800000` 被压回 `600000`。GitHub Pages [单次部署上限为 10 分钟](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)，[deploy-pages@v4 源码也限制为 600000](https://github.com/actions/deploy-pages/blob/v4/src/internal/deployment.js)。

修复两个发布入口：外层步骤设置真实的 `timeout-minutes: 30`；内部对同一上传产物最多尝试三次，每次 10 分钟，失败后短暂等待再试，成功后立即停止，第三次失败仍使任务失败。保留 40 分钟任务时限，并统一发布检出默认分支。3 项工作流回归通过，覆盖首次／第二次／第三次成功、全部失败、取消不重试、平台单次上限、实际外层时限及检出／推送保护。此配置提供有界重试，无法保证 GitHub 服务永不超时。

随后定时 [Actions 42729353640](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42729353640) 已成功发布包含本功能的版本；12 个修改前端／数据文件指纹一致。已在线再次逐券完成 54 张、108 个视图、11,212 个铁路像素采样点检查，无页面异常，原生 100 px 滚轮为 0.125 级，停止后额外变化为 0。

部署记录：功能提交 [`2c8a8ea`](https://github.com/06E-Felicia/06E-Felicia.github.io/commit/2c8a8eac32f10399f980bc861b63028c2e36578e)，由 [Actions 42732134206](https://github.com/06E-Felicia/06E-Felicia.github.io/actions/runs/42732134206) 已成功（确认时间 2026-11-10 09:10:29（UTC+8），总耗时 11 分 9 秒）；上传与 Pages 发布均成功，超时后自动重试已在本次实际任务中生效。实际 [JPRail 页面](https://06e-felicia.github.io/JPRail.html) 的 14 个本次前端、数据及审核文件逐一 SHA-256 与功能提交相同，确认实际上线内容。此前 `b08ac3b` / Actions 42653355538 的局部通过不作为本次全目录结论。

线上再次逐券操作全部 54 张（含历史），108 个初始／近距离视图，11,212 个铁路实际像素采样点；每券等级／全部实际运营方筛选、详情收起／重开、唯一选择、关键站解析和桌面无空白检查通过。联网街道底图正常，金泽陆地实际像素与投影对齐检查通过；原生滚轮 100 px 为 0.125 级，稳定后额外缩放 0，无 JavaScript 页面异常。线上正式图覆盖同一张审核图。来源核验状态仍为 50 完成、4 待核，线上运行通过不补足官方证据缺口。

原始下载、PDF 展开、临时依赖、截图草稿、浏览器配置与机器检查 JSON 全在本任务独有系统临时目录，任务结束清理。仅保留生产数据／代码、复用测试、本摘要和一张正式审核图；没有生成完整模拟或回放，也未删除用户正式数据、其他任务文件或根目录 trash/。
