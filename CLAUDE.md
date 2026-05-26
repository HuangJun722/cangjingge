# 藏经阁项目规则

## 定位

`藏经阁` 是中文副业机会私人看板，只做线上静态看板，不生成周报文档。

目标不是追热点，而是筛出值得用 3-7 天低成本亲自验证的小机会。

## 目录约定

- `data/sources.json`：自动采集信源配置。
- `data/manual_seeds.json`：人工观察种子。
- `data/opportunities.json`：脚本生成的机会库。
- `scripts/fetch_opportunities.py`：采集、清洗、评分。
- `scripts/generate_site.py`：静态页面生成。
- `scripts/template.html`：页面模板。
- `docs/index.html`：GitHub Pages 输出。

## 工程规则

- 修改采集口径时，先更新信源或评分规则，再生成数据和页面。
- 不把登录态、Cookie、token、账号密码写进仓库。
- 不硬抓强反爬平台；优先使用 RSS、公开搜索页、官方榜单、公开网页摘要。
- 机会必须带证据类型，不能只靠标题关键词判断。
- 低质资讯只能进入观察池，不能直接进入可试机会。

## 验证命令

```powershell
py -3 -m py_compile scripts\fetch_opportunities.py scripts\generate_site.py
py -3 scripts\fetch_opportunities.py
py -3 scripts\generate_site.py
```

涉及 `git push`、workflow、部署配置、删除文件、密钥配置时，先问用户。
