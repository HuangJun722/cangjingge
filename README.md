# 藏经阁

副业机会观测与试验看板，私人版。

目标不是追热点，而是筛出值得用 3-7 天低成本亲自验证的小机会。

## 当前定位

- 中文为主。
- 只做线上看板，不生成周报文档。
- 优先找低成本可验证机会，而不是最热话题。
- `localStorage`、登录态平台、强反爬平台暂不作为 V1 自动化核心。

## 看板结构

- 可试机会 TOP 5
- 观察池
- 避坑册
- 全阁索引
- 赛道分布

## 数据流

```text
data/manual_seeds.json
data/sources.json
        ↓
scripts/fetch_opportunities.py
        ↓
data/opportunities.json
        ↓
scripts/generate_site.py
        ↓
docs/index.html
```

## 本地运行

```powershell
Set-Location -LiteralPath 'D:\共享文件\AI协作工作区\01_工作文件区\副业项目\藏经阁'
py -3 -m pip install -r requirements.txt
py -3 scripts\fetch_opportunities.py
py -3 scripts\generate_site.py
```

然后打开：

```text
docs/index.html
```

## 评分原则

总分更偏向：

- 需求真实性
- 付费证据
- 低成本验证
- 可沉淀资产

扣分项：

- 供给拥挤
- 平台风险
- 灰产/割韭菜风险

## 信源策略

当前分三层补信号：

- 人工观察：直接写入 `data/manual_seeds.json`
- 垂直/市场 RSS：配置在 `data/sources.json`
- 搜索/社媒公开摘要：通过公开搜索 RSS 抽样，只作为需求信号
- 二次筛选：先用规则复核，未来可接 `DEEPSEEK_API_KEY` 做 AI 复核

小红书、闲鱼、抖音等登录态/强反爬平台不硬抓，不写 Cookie，不把账号态放进自动化。

## 发布

如果作为独立 GitHub Pages 项目发布：

1. 将本目录初始化为 Git 仓库。
2. 推送到 GitHub。
3. 开启 GitHub Pages，目录选择 `docs/`。
4. GitHub Actions 会每天北京时间 09:20 自动更新。
