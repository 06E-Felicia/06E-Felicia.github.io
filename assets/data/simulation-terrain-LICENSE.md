# 地形数据来源与处理

本项目的 `simulation-terrain.npz` 和 `simulation-terrain-detail.npz` 缓存、重采样自 Mapzen / Tilezen 的公开 Terrarium 高程瓦片，经 AWS Open Data 获取：

`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`

原始全球数据的来源署名包括：SRTM / GMTED2010 — U.S. Geological Survey（USGS）；ETOPO1 — NOAA。区域瓦片是混合数据产品，本项目没有逐像素识别全部底层来源。完整来源、许可及署名说明以 [Tilezen / Joerd attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) 为准。

新增珠江口缓存范围为 112.9°–114.7°E、21.95°–22.95°N，zoom 10，规则采样间隔 0.25 km。运行时聚合为模型格内平均高程、高程标准差、峰值、陆地比例及高于 50 m 的面积比例。未把格内峰值替换成覆盖整个网格的高墙；这些处理不是原始数据提供机构的产品或认证。

地形数据不用于导航、实况监测或业务天气预报。
