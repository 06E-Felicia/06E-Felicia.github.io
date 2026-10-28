# 放假模拟器：静态地形与环境几何

`vacation-terrain.bin`、`vacation-terrain.json`、`vacation-coastlines.json` 由
`scripts/prepare_vacation_terrain.py` 生成，遵循 `WARM_SECTOR_ENVIRONMENT_V1_2.md`。

## 来源与署名

- 复用本仓库 `simulation-terrain.npz`：4 km 网格；原始 Terrarium zoom 7。
- 珠江口覆盖区域复用 `simulation-terrain-detail.npz`：0.25 km 网格；原始 Terrarium zoom 10。
- 两个旧缓存实际节点范围以外的区域，从 AWS Open Data 的 Mapzen / Tilezen Terrarium
  zoom 8 瓦片补齐，URL：
  `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`。
- SRTM 与 GMTED2010 地形数据 courtesy of the U.S. Geological Survey (USGS)。
- ETOPO1 全球地形数据：DOC/NOAA/NESDIS/NCEI, National Centers for Environmental Information,
  NESDIS, NOAA, U.S. Department of Commerce。

完整上游来源与许可说明保存在相邻文件
`vacation-terrain-UPSTREAM-ATTRIBUTION.md`，来源为
[Tilezen / Joerd attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)。
全球 Terrarium 是混合数据产品，本项目未逐像素反推全部底层来源。美国政府材料在美国境内
不主张版权；境外权利及其他底层产品以该上游声明为准。保留以上署名与原始说明。

## 处理与边界

采用 WGS84 椭球方位等距投影，中心 113°E、22.5°N。正式域 960 × 720 km，2.5 km
共同网格；四边各有 150 km 数据外扩。所有主域与外扩区的抽样都有实际 DEM 数据覆盖；
下载失败会中断生成，不把缺测转成海洋。

每个投影格采用 4 × 4 等面积抽样，缓存内双线性插值；珠江口高分辨率缓存优先。
地面平均高程使用 `max(DEM, 0)` 的格平均。**海陆面积比例使用 DEM 高程大于零的比例代理**，
不是专业水文海岸线：内陆湖泊等水面可能被归为陆地；零高程低地可能有相反误差。
平滑海岸线也继承该限制。4 km 缓存重采样没有增加真实地形分辨率。

静态海岸向量、平滑地形、坡向、急流增强系数与绕流系数按照配套环境规则生成。
这些是理想化天气模型的工程输入，不是观测分析、天气预报、导航或测绘产品，数据提供方
未审定这些派生场。元数据记录源缓存与新瓦片 SHA-256、覆盖掩膜、处理尺度及投影尺度误差。

## 二进制读取

`Float32` little endian，连续场块；每块行从南向北、列从西向东，单元中心采样。
`metadata.fields` 为正式域，`metadata.extendedFields` 为带外扩区的同名字段。
字段的 `offsetBytes`、`count` 和 `units` 可直接用于 `Float32Array(buffer, offsetBytes, count)`。
`coverage` 为有效数据覆盖（当前全部 1）；`sourceMask` 是位掩膜：1 旧 4 km、2 旧 0.25 km、
4 新补 Terrarium；同格多个来源时按位或。

浏览器投影库 `assets/vendor/proj4/proj4.js` 固定为 proj4js 2.15.0，MIT 许可见相邻 LICENSE.md；
其版本独立于本地 Python 预处理所用 PROJ。应使用椭球 AEQD 定义并做正反投影核对。
