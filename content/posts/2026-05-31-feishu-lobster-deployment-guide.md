---
title: "30 人部门 AI 助理部署方案：飞书入口、一人一实例、Mac Studio 承载"
date: 2026-05-31
updated: 2026-05-31
version: "0.2.0"
status: "implementation-plan"
summary: "面向 30 人部门的 AI 助理部署方案：以飞书作为员工入口，后端为每个人分配独立 Hermes profile/gateway，统一经 DeepSeek Proxy 调用 DeepSeek V4，并配套自动化开通、权限隔离、token 统计、默认 skills、培训和运维机制。"
tags: ["公司端 AI", "飞书", "小龙虾", "Hermes", "DeepSeek", "Mac Studio"]
cover: "/assets/img/posts/feishu-lobster-deployment/feishu-message-api.png"
draft: false
changelog: ["0.2.0 - 重写为正式部署规划，版本号改为文章头部标签，补充飞书端用户流程、后端服务、自动化开通、目录/端口/配置、权限和运维细节。", "0.1.0 - 第一版，改为飞书主入口，加入 Mac Studio 采购、自动化部署、权限、token 排行、skills 和培训规划。"]
---

## 目标和边界

目标是在 30 人左右的部门内提供一套可治理的个人 AI 助理服务。员工不需要接触 CLI，不需要理解 agent、gateway、profile、API key 等概念，只需要在飞书里像联系同事一样使用自己的 AI 助理。

服务形态可以概括为：

```text
飞书里的一个部门 AI 助理
  每位员工对应一个独立后端实例
  每位员工有独立记忆、知识库、任务队列、文件空间和 token 统计
  所有模型请求统一经过部门 DeepSeek Proxy
  管理员可以开通、停用、限额、审计和维护
```

这套系统不处理涉密资料。客户、合同、财务、人事、密钥、日志、未公开战略、未批准内部代码等内容，默认不进入外部模型。第一版以非敏感资料整理、公开信息追踪、个人知识沉淀、会议纪要、写作辅助、流程模板化为主要场景。

## 员工实际拿到什么

上线后，每位员工会在飞书里看到一个名为“部门小龙虾”的机器人或联系人。员工无需安装本地软件，也不用登录 Mac Studio。个人服务包包括六部分：

1. 私聊入口：员工可以在飞书私聊里提问、发送非敏感材料、查看个人任务。
2. 群聊入口：在部门群里 `@部门小龙虾`，机器人只处理被明确提及的消息。
3. 个人知识库：员工可以把一次有效回答保存成个人知识条目，后续通过 `/kb search` 查询。
4. 信息追踪：员工可以订阅公开网页、公开 RSS、公开 GitHub 仓库或指定关键词，系统按日生成 briefing。
5. 用量面板：员工可以用 `/tokens me` 查看当天、本周、本月 token 和任务数。
6. 默认 skills：系统预装低权限 skills，用于摘要、纪要、复盘、写作、知识沉淀和成本提醒。

从用户视角看，这不是“给每个人一套命令行工具”，而是给每个人一个飞书里的个人 AI 助理账号。后端的 profile、gateway、端口、日志、目录和模型 key 都由管理员维护。

## 选型结论

第一版建议以 Hermes 作为个人 agent 底座，OpenClaw 作为后续扩展候选。

Hermes 的 profile 机制更符合“一人一实例”的部署模型。官方文档里，profile 是独立 home directory，每个 profile 有自己的 `config.yaml`、`.env`、memory、sessions、skills、cron jobs 和 state database。这一点对 30 人部署很关键，因为个人记忆、任务历史和技能配置不能混在同一个状态目录里。

![Hermes Agent GitHub 仓库截图：第一版底座围绕 Hermes 的 profile 与 gateway 能力设计。](/assets/img/posts/feishu-lobster-deployment/hermes-github.png)

![Hermes profile 文档截图：每个 profile 有独立 config、API keys、memory、sessions、skills 和 gateway state。](/assets/img/posts/feishu-lobster-deployment/hermes-profiles.png)

OpenClaw 的 Control UI、WebChat 和 gateway 能力更丰富，但它不适合作为“30 人共用一个 gateway”的第一版方案。OpenClaw 的安全文档明确提醒，gateway 不应被当作互不信任多用户之间的安全边界。因此第一版不把普通员工流量混进同一个 OpenClaw gateway；如果后续要使用 OpenClaw，建议为特定高权限场景单独部署、单独审批、单独审计。

![OpenClaw security 文档截图：第一版应避免把一个 gateway 当作跨用户安全边界。](/assets/img/posts/feishu-lobster-deployment/openclaw-security.png)

![OpenClaw Control UI 文档截图：控制台适合管理员和受控试点，不适合作为普通员工主入口。](/assets/img/posts/feishu-lobster-deployment/openclaw-control-ui.png)

## 总体架构

推荐架构如下：

```text
飞书用户
  -> 飞书 Bot / 消息事件 / 交互卡片
  -> Lobster Router
  -> Identity & Policy Service
  -> Job Queue
  -> Hermes Gateway Pool
  -> DeepSeek Proxy
  -> DeepSeek V4 API

旁路系统：
  Profile Store
  Upload Store
  Knowledge Index
  Metrics Store
  Audit Log
  Admin Console
```

各组件职责如下：

1. 飞书 Bot：接收私聊、群聊 `@`、文件转发、卡片按钮点击，向用户发送结果。
2. Lobster Router：解析飞书事件，根据 `open_id` 找到员工 profile，生成任务并写入队列。
3. Identity & Policy Service：判断员工身份、角色、部门、配额、允许的 skills 和数据边界。
4. Job Queue：把对话任务、文件摘要、信息追踪、知识库索引分成不同队列，避免一个长任务阻塞所有人。
5. Hermes Gateway Pool：每个员工一个 profile/gateway，端口只绑定 localhost。
6. DeepSeek Proxy：统一持有 DeepSeek key，记录 token 和费用，不把 key 下发给个人 profile。
7. Metrics Store：记录 token、任务数、模型、错误、延迟、员工活跃度。
8. Admin Console：管理员查看健康状态、异常任务、配额、员工启停和 skills 审批。

第一版不需要 Kubernetes。Mac Studio 单机加 `launchd` 或 `supervisord` 就可以完成 30 人规模的稳定运行。关键不是容器编排，而是身份、目录、端口、配额、日志和备份设计清楚。

## 飞书端怎么操作

飞书端要尽量产品化。普通员工不应该看到 gateway、profile、API key、模型参数和命令行日志。

### 第一次启用

员工在飞书里搜索“部门小龙虾”，发送：

```text
/start
```

系统返回一张初始化卡片：

```text
部门小龙虾已开通

姓名：张三
个人空间：20GB
本周 token 预算：1,000,000
默认模型：自动选择
可用能力：资料摘要、会议纪要、个人知识库、信息追踪、写作审阅

[查看使用边界] [创建每日 briefing] [查看我的用量]
```

如果用户不在白名单内，系统返回：

```text
当前飞书账号未开通部门小龙虾服务。请联系管理员加入 users.csv 后再启用。
```

### 日常提问

员工可以直接在私聊里输入：

```text
帮我把这段公开资料整理成 5 条结论、3 个待办和 2 个风险点。
```

返回内容应包含结构化结果和操作按钮：

```text
摘要
...

行动项
1. ...
2. ...
3. ...

风险点
1. ...
2. ...

[保存到知识库] [生成待办] [改写成周报] [继续追问]
```

按钮动作必须写入员工自己的 profile，不写入公共空间。

### 文件处理

员工转发文件给机器人后，机器人先做数据分类确认，不直接处理：

```text
请确认这份文件的数据类型

[公开资料]
[公司内部但允许 AI 处理]
[包含客户/合同/财务/员工/密钥等敏感信息]
```

选择“公开资料”或“公司内部但允许 AI 处理”后，系统才进入摘要流程。选择敏感信息后，系统不调用模型，只返回脱敏建议：

```text
该文件不进入模型处理。可先提取不含客户、合同金额、员工信息和密钥的结构化摘要，再提交给小龙虾处理。
```

### 信息追踪

员工可以创建公开信息追踪任务：

```text
/watch add https://example.com/rss 每天 09:00 生成 5 条摘要
```

系统返回：

```text
已创建追踪任务
来源：https://example.com/rss
频率：每天 09:00
输出：5 条摘要 + 影响判断 + 建议行动

[暂停] [修改频率] [查看所有追踪]
```

### 个人知识库

员工保存一条回答后，可以用：

```text
/kb search DeepSeek V4
```

系统只搜索该员工自己的知识库，返回来源、摘要和可继续追问的按钮：

```text
找到 3 条相关记录

1. DeepSeek V4 模型接入策略
来源：2026-05-31 部署规划
摘要：日常任务走 flash，复杂任务走 pro，全部经 DeepSeek Proxy 记录 token。

[展开] [继续追问] [生成 SOP]
```

### 用量查看

员工查看个人用量：

```text
/tokens me
```

返回：

```text
本周用量
总 token：386,420 / 1,000,000
任务数：27
高成本任务：3
最常用能力：资料摘要、写作审阅、知识库查询

[查看明细] [导出周报]
```

部门群里每周可以发布汇总，但不建议只按 token 排名。更合理的是同时展示任务数、沉淀条目数和可复用产物数。

![飞书开放平台发送消息 API 截图：第一版用机器人消息、事件回调和交互卡片承接员工入口。](/assets/img/posts/feishu-lobster-deployment/feishu-message-api.png)

## Mac Studio 配置建议

DeepSeek V4 在云端运行，Mac Studio 不承担大模型推理主负载。它主要负责飞书接入、任务调度、Hermes gateway、文件索引、知识库、日志、token 统计和备份。因此不应按“每人固定几颗 CPU 核、几 GB 内存”来切分机器。

更合理的资源策略是：

1. 全局并发池：同时最多 12 到 16 个对话任务。
2. 后台任务池：同时最多 4 个信息追踪或文件索引任务。
3. 单人并发限制：每人最多 2 个对话任务、1 个后台长任务。
4. 任务优先级：人工对话优先于定时追踪，摘要优先于批量索引。
5. 预算限制：按人设置日预算、周预算和单次高成本确认。

截至 2026-05-31，Apple Mac Studio 官方规格页展示 M4 Max 和 M3 Ultra 两条配置线。30 人部门生产环境建议优先选 M3 Ultra 档位，原因是 CPU/GPU、统一内存上限、内存带宽和 SSD 扩展余量更适合常驻服务。

![Apple Mac Studio 技术规格截图：30 人部门生产环境建议优先考虑 M3 Ultra 档位。](/assets/img/posts/feishu-lobster-deployment/mac-studio-specs.png)

推荐采购：

1. 试点环境，5 到 10 人：M4 Max，64GB 或 128GB 统一内存，2TB SSD。
2. 30 人第一版生产环境：M3 Ultra，256GB 统一内存，4TB SSD。
3. 两年周期更稳的配置：M3 Ultra，512GB 统一内存，8TB SSD。

存储空间估算：

```text
个人空间：30 人 x 20GB = 600GB
索引和缓存：约 300GB 到 600GB
会话与任务日志：约 100GB 到 300GB/年
截图、培训材料、公开资料缓存：约 100GB 到 300GB
系统、依赖、备份缓冲：至少保留 30% 到 40% 空闲空间
```

因此不建议 1TB SSD 作为生产起步配置。4TB 是比较稳妥的下限，8TB 会显著降低后续清理和迁移压力。另配一块 8TB 以上外置备份盘或网络备份空间，用于 nightly backup。

## 部署拓扑和端口规划

Mac Studio 上建议创建一个专用系统用户：

```text
user: lobster
home: /Users/lobster
data root: /Users/Shared/lobster
```

目录结构：

```text
/Users/Shared/lobster/
  config/
    users.csv
    policy.yml
    skills-allowlist.yml
    model-routing.yml
  profiles/
    u001/
      hermes-home/
      memory/
      sessions/
      uploads/
      knowledge/
      logs/
    u002/
      ...
  services/
    router/
    ai-proxy/
    metrics/
    admin/
  backups/
  run/
```

端口规划：

```text
8080  Lobster Router，对飞书事件回调开放，经 HTTPS 反向代理暴露
8081  DeepSeek Proxy，仅内网访问
8082  Metrics API，仅管理员访问
8090  Admin Console，仅管理员访问
31001-31030  Hermes user gateways，只绑定 127.0.0.1
```

外部只暴露一个 HTTPS 域名：

```text
https://lobster.company.com/feishu/events
```

Hermes gateway 端口不对员工、不对公网、不对飞书开放。飞书只访问 Router，Router 再在本机调用对应员工的 gateway。

## 飞书应用配置

飞书侧需要创建一个企业自建应用，并启用机器人能力。

最低配置包括：

1. 开启机器人能力。
2. 配置事件订阅 URL：`https://lobster.company.com/feishu/events`。
3. 订阅私聊消息、群聊 `@` 消息、文件消息和卡片回调事件。
4. 申请发送消息、读取机器人可见消息、获取用户 open_id 等必要权限。
5. 保存 App ID、App Secret、Verification Token、Encrypt Key 到 Mac Studio 的 secret store。

建议配置文件：

```yaml
feishu:
  app_id: ${FEISHU_APP_ID}
  app_secret: ${FEISHU_APP_SECRET}
  verification_token: ${FEISHU_VERIFICATION_TOKEN}
  encrypt_key: ${FEISHU_ENCRYPT_KEY}
  event_path: /feishu/events
  bot_name: 部门小龙虾
```

App Secret 不写入任何员工 profile，也不放进 Git 仓库。生产环境可放 macOS Keychain、1Password CLI、Vault，或只允许 `lobster` 用户读取的 `.env` 文件。

## 自动化开通 30 个员工实例

员工名单是部署入口。示例：

```csv
employee_id,feishu_open_id,name,department,role,quota_gb,weekly_token_budget
u001,ou_xxx,张三,研究部,user,20,1000000
u002,ou_yyy,李四,研究部,pilot,20,1500000
u003,ou_zzz,王五,研究部,admin,20,2000000
```

内部维护一个 `lobsterctl` 脚本，负责把员工名单变成可运行实例：

```text
./lobsterctl bootstrap \
  --users /Users/Shared/lobster/config/users.csv \
  --policy /Users/Shared/lobster/config/policy.yml \
  --skills /Users/Shared/lobster/config/skills-allowlist.yml
```

每个员工执行的动作：

```text
1. 创建 /Users/Shared/lobster/profiles/{employee_id}
2. 创建 Hermes profile：lobster-{employee_id}
3. 写入 profile 专用 config.yaml
4. 写入只指向 DeepSeek Proxy 的模型配置
5. 安装默认 skills allowlist
6. 分配 localhost gateway 端口
7. 登记 feishu_open_id -> profile_name -> gateway_port
8. 创建 launchd service
9. 运行 health check
10. 向管理员飞书群发送开通报告
```

Hermes profile 创建可以使用类似流程：

```text
hermes profile create lobster-u001
lobster-u001 setup
lobster-u001 gateway start --host 127.0.0.1 --port 31001
```

最终需要由 `lobsterctl` 包装这些命令，避免管理员手工执行 30 次。员工新增、离职、调岗也通过同一套脚本处理：

```text
./lobsterctl add-user --employee-id u031
./lobsterctl suspend-user --employee-id u009
./lobsterctl rotate-profile --employee-id u014
./lobsterctl quota set --employee-id u017 --gb 30
```

## DeepSeek Proxy 和 token 统计

所有模型调用统一走 DeepSeek Proxy：

```text
Hermes gateway
  -> http://127.0.0.1:8081/v1/chat/completions
  -> DeepSeek Proxy 记录用量
  -> DeepSeek API
```

Proxy 要兼容 OpenAI 风格接口，这样 Hermes/OpenClaw 之类的 agent 不需要知道真实 provider 细节。模型路由由 Proxy 决定：

```yaml
routes:
  default: deepseek-v4-flash
  long_reasoning: deepseek-v4-pro
  writing_review: deepseek-v4-flash
  weekly_report: deepseek-v4-pro
limits:
  single_request_soft_limit_tokens: 60000
  require_confirm_above_tokens: 100000
```

![DeepSeek 模型列表文档截图：模型名、价格、上下文等信息上线前必须复核。](/assets/img/posts/feishu-lobster-deployment/deepseek-models.png)

用量表建议从第一天就建：

```sql
create table model_calls (
  id text primary key,
  created_at timestamp not null,
  employee_id text not null,
  feishu_open_id text not null,
  profile_name text not null,
  task_id text not null,
  task_type text not null,
  model text not null,
  prompt_tokens integer not null default 0,
  completion_tokens integer not null default 0,
  total_tokens integer not null default 0,
  estimated_cost numeric not null default 0,
  status text not null,
  error_code text
);
```

每天生成三类报表：

1. 个人用量：员工通过 `/tokens me` 查看。
2. 管理用量：管理员查看部门总量、异常任务、预算接近上限的员工。
3. 部门周报：在部门群发布聚合数据，不展示敏感 prompt 和完整会话内容。

部门榜单建议使用综合指标：

```text
使用活跃度 = 活跃天数 + 任务数
知识沉淀 = 保存到知识库的条目数
产出复用 = 被转为 SOP、周报、纪要、briefing 的数量
成本意识 = 高成本任务确认率和无效重试率
```

这样可以避免把 token 消耗误读成效率提升。

## 权限和数据隔离

权限模型分为四层：

1. 飞书身份层：确认消息来自哪个 `open_id`。
2. 员工映射层：`open_id` 映射到 `employee_id` 和 profile。
3. 策略层：决定该员工能用哪些 skills、模型、预算、文件类型。
4. 系统层：目录、端口、进程、secret 和日志隔离。

角色建议：

```yaml
roles:
  user:
    skills: default
    max_background_jobs: 1
    can_view_admin: false
  pilot:
    skills: default_plus_beta
    max_background_jobs: 2
    can_view_admin: false
  maintainer:
    skills: default_plus_ops
    can_view_health: true
    can_view_content: false
  admin:
    can_manage_users: true
    can_manage_quotas: true
    can_publish_skills: true
```

默认禁止：

1. 一个 profile 读取另一个 profile 的目录。
2. 普通员工直接访问 gateway 端口。
3. skills 默认执行 shell。
4. skills 默认读取全盘文件。
5. 复制浏览器 Cookie、token、个人账号登录态。
6. 把 DeepSeek key 写进员工 profile。
7. 将敏感资料发给未批准模型或外部服务。

文件上传策略：

```text
公开资料：允许处理，保留来源。
公司内部但允许 AI 处理：允许处理，记录员工确认。
敏感资料：拒绝处理，返回脱敏模板。
不确定：按敏感资料处理。
```

## 默认 skills

第一版默认 skills 应该低权限、可复核、能沉淀，不追求全能。

建议默认启用：

1. Personal Briefing Builder：公开信息追踪和每日 briefing。
2. Source Distiller：网页、文章、会议材料摘要。
3. Meeting Notes Builder：会议纪要、行动项、风险点。
4. PKM Compounder：把有效回答沉淀为个人知识库条目。
5. Company-Safe Adapter：把个人 AI 用法改写成公司可用流程。
6. Chinese Writing Quality Reviewer：审阅中文表达和结构。
7. Cost-Aware Task Router：在高 token 任务前提醒确认。
8. Model Snapshot Checker：复核模型、价格和配置变化。
9. Workflow Packager：把成功任务打包成 SOP。
10. Skill Discovery Log：记录候选 skills，不直接全员启用。

默认不启用：

1. 浏览器登录态自动化。
2. Cookie 抓取。
3. 任意 shell 命令执行。
4. 全盘文件读取。
5. 未审批外部 MCP server。

高权限 skills 采用申请制。申请记录进入管理员飞书群，由管理员批准后只对特定员工或试点组开放。

## 员工培训

培训目标是让员工掌握三件事：适合交给 AI 的任务、不能提交的数据、如何把一次回答沉淀成可复用资产。

建议分四个阶段：

第一阶段，5 人试点，周期 5 个工作日。每位试点员工完成三个固定任务：一次公开资料摘要、一次会议纪要整理、一次个人知识库沉淀。管理员记录失败案例、权限误判、token 异常和飞书交互问题。

第二阶段，部门启动培训，60 分钟。培训结构：

```text
10 分钟：服务边界和数据规则
15 分钟：飞书私聊、群聊、文件、卡片按钮演示
15 分钟：资料摘要、briefing、知识库三个案例
10 分钟：/tokens me、/kb search、/watch add 等常用命令
10 分钟：问题收集和试点安排
```

第三阶段，岗位模板训练。研究、运营、管理、行政、工程分别沉淀自己的 5 个高频任务模板。例如研究组重点做资料摘要和观点对比，管理组重点做会议纪要和周报，运营组重点做公开信息追踪和内容改写。

第四阶段，月度复盘。复盘不只看使用量，还看可复用成果：新增 SOP、知识库条目、briefing 质量、重复任务减少情况、人工复核发现的问题。

培训材料建议固定为三份：

1. 《飞书里如何使用部门小龙虾》
2. 《哪些资料不能提交给 AI》
3. 《高质量请求模板和岗位案例》

## 运维和维护节奏

每日检查：

1. 飞书事件回调成功率。
2. Router、Proxy、Hermes gateways 存活状态。
3. DeepSeek Proxy 错误率和平均延迟。
4. token 异常峰值。
5. 磁盘剩余空间和单人 quota。

每周检查：

1. 生成部门用量周报。
2. 抽查 5 条输出是否符合数据规则。
3. 清理失败任务和过期上传文件。
4. 审核新增 skills 申请。
5. 更新岗位模板。

每月检查：

1. 复核 DeepSeek 模型名、价格、上下文限制和弃用公告。
2. 复核 Hermes/OpenClaw 版本变化。
3. 检查备份恢复流程。
4. 复盘 token 成本和实际产出。
5. 更新本文版本记录和生产截图。

Hermes 的 Web Dashboard 可作为维护者排错界面，但普通员工不需要使用。

![Hermes dashboard 文档截图：适合作为维护者排错界面，普通员工仍以飞书为主入口。](/assets/img/posts/feishu-lobster-deployment/hermes-dashboard.png)

## 上线顺序

建议按 10 步上线：

1. 采购并初始化 Mac Studio，创建 `lobster` 系统用户和数据目录。
2. 配置 HTTPS 域名、反向代理、飞书事件回调地址。
3. 部署 DeepSeek Proxy，完成 token 记录和模型路由。
4. 部署 Hermes，创建 2 个测试 profile。
5. 部署 Lobster Router，实现飞书消息收发。
6. 接入 `users.csv`，完成飞书 `open_id` 到 profile 的映射。
7. 实现 `/start`、`/tokens me`、`/kb search`、`/watch add` 四个基础命令。
8. 接入默认 skills allowlist。
9. 5 人试点 5 个工作日，补齐真实飞书截图和失败案例。
10. 扩展到 30 人，开始周报和月度复盘。

## 参考资料

1. [Hermes Agent GitHub](https://github.com/NousResearch/hermes-agent)
2. [Hermes Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
3. [Hermes Web Dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)
4. [OpenClaw GitHub](https://github.com/openclaw/openclaw)
5. [OpenClaw Gateway Security](https://docs.openclaw.ai/gateway/security)
6. [OpenClaw Control UI](https://docs.openclaw.ai/web/control-ui)
7. [Apple Mac Studio Specs](https://www.apple.com/mac-studio/specs/)
8. [DeepSeek API Docs](https://api-docs.deepseek.com/)
9. [飞书开放平台发送消息 API](https://open.feishu.cn/document/server-docs/im-v1/message/create)

## 修订记录

`v0.2.0`，2026-05-31：重写为正式部署规划，删除自指草稿话术，把版本号移到文章头部标签；补充员工实际服务包、飞书端操作流程、服务拓扑、端口/目录规划、飞书应用配置、自动化开通、DeepSeek Proxy、权限策略、培训和运维细节。

`v0.1.0`，2026-05-31：第一版。将主入口改为飞书，保留“一人一 Hermes profile/gateway”，加入 Mac Studio 采购建议、自动部署、权限治理、token 排行、默认 skills、培训计划和公开截图。
