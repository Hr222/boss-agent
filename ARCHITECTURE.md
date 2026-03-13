# 项目架构说明

当前项目对外采用标准 MVC 命名：

- `src/models`
  - 负责核心业务模型与用例模型。
  - 包括 JD 匹配、招呼语生成、批量筛选、自动投递、岗位仓储、浏览器投递能力。

- `src/views`
  - 负责命令行展示与输入采集。
  - 当前主要是 `ConsoleView`。

- `src/controllers`
  - 负责把用户动作路由到对应 model。
  - 当前主入口是 `ConsoleController`。

## MVC 主链路

### 手动 JD 分析

`src/main.py`
-> `src/controllers/console_cli_controller.py`
-> `src/views/console_view.py`
-> `src/models/manual_job_model.py`
-> `src/models/job_matching_model.py`
-> LLM 生成匹配结果与招呼语

### 批量筛选岗位

`src/controllers/match_cli_controller.py`
-> `src/models/job_screening_model.py`
-> `src/models/job_repository.py`
-> `src/models/job_matching_model.py`
-> LLM 生成匹配结果与招呼语

### 自动投递岗位

`src/controllers/apply_cli_controller.py`
-> `src/models/job_apply_model.py`
-> `src/models/job_repository.py`
-> `src/models/boss_apply_browser.py`
-> nodriver 打开详情页 / 立即沟通 / 输入或发送招呼语

### 岗位抓取链路

`src/controllers/search_cli_controller.py`
-> `src/models/job_search_model.py`
-> `src/infrastructure/browser/boss_search_client.py`
-> `src/models/job_repository.py`
-> SQLite 落库

## 内部实现说明

当前仓库保留的内部实现目录主要是 `src/infrastructure`：

- `src/models` 是对外统一业务入口。
- `src/views` 是对外统一交互入口。
- `src/controllers` 是对外统一流程入口。
- `src/infrastructure` 负责 AI、SQLite、简历文件、浏览器自动化等外部依赖适配。

也就是说，后续继续开发时，应优先在 MVC 三层下扩展；业务逻辑进入 `src/models`，交互进入 `src/views`，流程编排进入 `src/controllers`。
