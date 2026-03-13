# Job Agent

基于 `Python + SQLite + nodriver + LLM` 的闭环求职 Agent。

当前主能力：

- 打开 Boss 直聘搜索页并复用本地浏览器登录态
- 抓取岗位列表并写入 `SQLite`
- 用 `LLM` 按策略做岗位匹配
- 为匹配岗位生成打招呼语
- 自动打开职位详情页并发送招呼语
- 发送成功后归档 JD 与打招呼语，便于后续复盘

## 目录结构

```text
src/
  main.py
  config/
  controllers/
  infrastructure/
  models/
  views/
data/
  resume.json
  boss_jobs.sqlite3
  greetings/
  boss_debug/
```

## 环境准备

1. 创建并激活虚拟环境
2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 复制环境变量模板并填写自己的配置

```bash
cp .env.example .env
```

最小必填项：

```env
ZAI_API_KEY=your_api_key_here
```

当前项目实际相关的常用变量：

```env
ZAI_API_KEY=your_api_key_here
ZAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
BOSS_DEBUG=0
BOSS_USER_DATA_DIR=.nodriver_user_data\\boss
```

说明：

- `.env` 已在 `.gitignore` 中，不应提交真实密钥
- 示例配置见 [.env.example](/mnt/c/pycharm/pythonproject/.env.example)

## 运行方式

主交互入口：

```bash
python -m src.main
```

抓取 Boss 岗位并落库：

```bash
python -m src.controllers.search_cli_controller --keyword "Python开发" --city "深圳" --limit 20 --require-login
```

批量匹配岗位库：

```bash
python -m src.controllers.match_cli_controller --db data/boss_jobs.sqlite3 --limit 10 --threshold 75
```

自动投递已入队岗位：

```bash
python -m src.controllers.apply_cli_controller --db data/boss_jobs.sqlite3 --limit 15 --require-login
```

闭环求职 Agent：

```bash
python -m src.controllers.agent_cli_controller \
  --db data/boss_jobs.sqlite3 \
  --keyword "Python开发" \
  --city "深圳" \
  --target-apply-count 15 \
  --batch-size 5 \
  --threshold 75 \
  --require-login
```

单岗位预览填充：

```bash
python -m src.controllers.apply_cli_controller \
  --require-login \
  --job-url "https://www.zhipin.com/job_detail/xxx.html" \
  --fill-only \
  --greeting-file "data/test_greeting.txt"
```

## 当前主链路

1. 打开 Boss 搜索页，用户手动登录并确认筛选条件
2. 抓取岗位列表并写入 `data/boss_jobs.sqlite3`
3. 用 `LLM` 做岗位匹配，满足阈值的岗位进入待投递队列
4. 自动打开详情页并发送招呼语
5. 发送成功后归档到 `data/greetings`
6. 若累计实际发送仍未满足目标，则继续抓取下一轮

## 当前行为说明

- 闭环 Agent 的收口标准是“累计实际发送数”，不是“已沟通/继续沟通数”
- 每轮一旦匹配出待投递岗位，会优先把“本轮已入队岗位”全部发送完
- 因此最终 `累计实际发送` 可能大于用户输入的目标值，这是当前设计行为
- 历史公司过滤默认从简历里的历史任职公司或 `excluded_company_names` 读取
- `每轮最小匹配数量` 支持用户输入，实际范围被钳制在 `5-10`

## 招呼语与归档

- 招呼语会结合 JD 与简历证据生成，强调岗位主轴，不再使用统一长尾模板
- 会附带一段能力说明，表明消息由你编写的求职 Agent 自动发送，后续由本人真人沟通
- 归档文件只在“真实发送成功”后生成
- 当前归档文件名格式为：

```text
公司 - 岗位.txt
```

- 归档正文包含：
  - 公司
  - 岗位
  - 城市
  - 链接
  - 清洗后的 JD 内容
  - 实际发送的打招呼语

## 运行产物

这些内容属于本地运行数据，不建议提交：

- `.env`
- `.nodriver_user_data/`
- `data/greetings/`
- `data/boss_debug/`
- `*.sqlite3`
- `*.db`

项目已在 `.gitignore` 中忽略大部分运行产物。

## 说明

- 当前主策略包含：
  - `backend_ai`
  - `frontend`
  - `legal`
  - `auto`
- 简历主文件为 [data/resume.json](/mnt/c/pycharm/pythonproject/data/resume.json)
- 环境变量与路径统一按项目根目录解析，避免从 `src/` 启动时写到错误位置
