---
title: "部门小龙虾第一版部署规划：飞书入口、一人一只、统一跑在 Mac Studio 上"
date: 2026-05-31
updated: 2026-05-31
version: "0.1.0"
status: "first-public-draft"
summary: "把 30 人部门的 AI agent 部署方案先压成一版可讨论的规划：飞书作为主入口，后端一人一 Hermes profile/gateway，DeepSeek V4 作为模型层，并配套权限、token 统计、skills、培训和版本管理。"
tags: ["公司端 AI", "飞书", "小龙虾", "Hermes", "DeepSeek", "Mac Studio"]
cover: "/assets/img/posts/feishu-lobster-deployment/feishu-message-api.png"
draft: false
changelog: ["0.1.0 - 第一版，改为飞书主入口，加入 Mac Studio 采购、自动化部署、权限、token 排行、skills 和培训规划。"]
---

## 版本说明

这是第一版公开草案，版本号是 `v0.1.0`。它的目标不是直接替代 IT 实施文档，而是先把部门内“养龙虾”的架构、采购、权限和培训口径摆清楚，方便后续反复讨论、试点、补截图、改命令。

后续每次修改都沿用这篇文章更新，至少维护四件事：

1. front matter 里的 `version`、`updated`、`status`。
2. 文末的版本记录。
3. 截图目录 `assets/img/posts/feishu-lobster-deployment/`。
4. Git commit message 里写清楚本次改了采购、部署、权限、培训还是截图。

本篇截图抓取时间是 2026-05-31 09:28，均来自公开网页或本地博客构建环境，不包含公司内部资料。真正上线后的飞书聊天截图、管理员后台截图和 token 排行榜截图，需要在试点环境搭好后补拍。

## 一句话方案

主入口从“部门内部网页门户”改成“飞书”。其他原则不变：

飞书 Bot 负责承接同事的日常使用，后端调度服务按飞书身份把请求路由到对应员工自己的 Hermes profile 或 gateway。DeepSeek V4 作为默认大模型。Mac Studio 负责承载 agent 进程、个人目录、索引、日志、定时任务和统计服务。

我建议第一版不要把 OpenClaw 作为 30 人共用的主底座。OpenClaw 很适合做能力丰富的个人网关、WebChat 或管理控制台，但它的安全文档明确提醒：一个 gateway 不应被当成互不信任多租户之间的安全边界。部门场景里，权限交叉一旦发生，后续会很难解释。

Hermes 更适合第一版，因为它的 profile 模型天然接近“一人一只小龙虾”：每个 profile 可以有自己的配置、API key、memory、sessions、skills、cron jobs 和 state database。

![Hermes Agent GitHub 仓库截图：第一版底座建议围绕 Hermes 的 profile 与 gateway 能力设计。](/assets/img/posts/feishu-lobster-deployment/hermes-github.png)

![Hermes profile 文档截图：每个 profile 有独立 config、API keys、memory、sessions、skills 和 gateway state。](/assets/img/posts/feishu-lobster-deployment/hermes-profiles.png)

## 总体架构

第一版架构可以先这样落：

```text
飞书用户
  -> 飞书 Bot / 事件订阅 / 消息 API
  -> 部门 Lobster Router
  -> 用户身份映射与权限判断
  -> 对应员工的 Hermes profile / gateway
  -> 内部 DeepSeek Proxy
  -> DeepSeek V4 API
  -> token 日志 / 知识库 / 任务日志 / 飞书回复
```

这里有两个关键点。

第一，飞书只是入口，不直接承载所有状态。用户在飞书里发消息、上传允许范围内的文件、点击消息卡片，但长期记忆、个人知识库、任务历史、skills 配置都落在后端的个人 profile 目录里。

第二，所有模型调用都经过内部 DeepSeek Proxy。不要让每个 agent 直接拿 DeepSeek key 去请求模型。只有这样才能稳定记录每个人的 token、模型、任务类型、费用估算和异常请求。

![飞书开放平台发送消息 API 截图：第一版可用机器人消息作为用户入口。](/assets/img/posts/feishu-lobster-deployment/feishu-message-api.png)

## 为什么不是先做网页门户

网页门户更适合做复杂界面，但对没有编程基础的同事来说，飞书更接近日常动作。大家已经知道怎么发消息、转发文件、点卡片、看群通知。第一版最重要的不是把功能做满，而是让 30 人真正用起来。

所以入口分三层：

1. 飞书主入口：日常提问、文件摘要、信息追踪、任务提醒、日报周报、排行榜。
2. 管理后台入口：只给管理员和维护者看，用来排错、查看 profile 健康状态和审计日志。
3. 备选聊天入口：未来再接企业微信、Teams 或 Slack。这个是“其他不变”的第二入口，不抢第一版焦点。

Hermes 自带 Web Dashboard，可以作为管理员排错和观察 agent 状态的辅助界面，但不建议直接暴露给普通同事使用。

![Hermes dashboard 文档截图：适合作为管理和排错界面，不建议第一版给普通用户直接使用。](/assets/img/posts/feishu-lobster-deployment/hermes-dashboard.png)

## Hermes 与 OpenClaw 的第一版取舍

我的建议是：

第一版主线用 Hermes。

OpenClaw 保留为扩展候选，用在三类场景：

1. 需要 OpenClaw 的 WebChat 或 Control UI 做专项演示。
2. 某些高权限工具需要单独 gateway、单独审批、单独审计。
3. 后续确认 OpenClaw 的多 gateway 隔离策略能满足公司要求，再作为高级用户工具。

OpenClaw 不是不能用，而是不应该在还没有权限治理和审计框架时，让 30 个人共用一个 gateway。

![OpenClaw security 文档截图：第一版要把 gateway 当成信任边界内的组件，而不是跨用户安全边界。](/assets/img/posts/feishu-lobster-deployment/openclaw-security.png)

![OpenClaw Control UI 文档截图：这类控制台更适合管理员或受控试点，而不是普通员工主入口。](/assets/img/posts/feishu-lobster-deployment/openclaw-control-ui.png)

## Mac Studio 应该怎么买

先说结论：不要按“每个人固定分几个 CPU 核、几 GB 内存”来理解这套系统。

因为大模型在 DeepSeek 云端跑，Mac Studio 主要承担的是编排、队列、文件索引、知识库、日志、定时任务和飞书集成。30 个人不会每秒都在同时跑重任务。更合理的方式是设置并发池和配额，而不是给每个人切一块固定硬件。

截至 2026-05-31，Apple 官方 Mac Studio 规格页显示当前线是 M4 Max 和 M3 Ultra。M3 Ultra 这一档更适合部门共用服务，因为 CPU/GPU、统一内存上限、内存带宽和存储扩展余量更大。

![Apple Mac Studio 技术规格截图：第一版建议优先看 M3 Ultra 档位，而不是只看最低配。](/assets/img/posts/feishu-lobster-deployment/mac-studio-specs.png)

我的采购建议：

1. 只做 5 到 10 人试点：M4 Max、64GB 或 128GB 统一内存、2TB SSD 可以先跑。
2. 30 人部门第一版生产：M3 Ultra、256GB 统一内存、4TB SSD 起步。
3. 希望少折腾两年：M3 Ultra、512GB 统一内存、8TB SSD 更稳。

为什么不建议 1TB SSD？你们已经计划每人给 20GB，30 人就是 600GB。再加上会话日志、上传附件、索引、缓存、向量库、备份、系统更新和未来截图资料，1TB 很快会变成运维焦虑。4TB 是比较理性的起步，8TB 是舒服很多的选择。

CPU 和内存建议这样管理：

1. 不给每个人固定切 CPU 核。
2. 设置全局并发，比如同时最多 8 到 12 个活跃重任务。
3. 设置个人并发，比如每人同时最多 1 个后台长任务。
4. 设置队列优先级，比如人工对话优先于定时信息追踪。
5. 设置每日 token 预算和高消耗任务确认。
6. 用进程监控发现异常 profile，而不是预先把机器切成 30 个小虚拟机。

如果未来要在 Mac Studio 上跑本地大模型、批量 embedding 或本地 OCR，内存和 SSD 需求还要再上调。第一版默认 DeepSeek V4 是远程模型，因此采购重点是稳定编排和留足数据空间。

## DeepSeek V4 接入方式

DeepSeek 当前 API 文档里已经能看到 V4 相关模型页。第一版建议默认：

1. 日常任务走 `deepseek-v4-flash`，追求速度和成本。
2. 复杂规划、长文改写、疑难分析走 `deepseek-v4-pro`。
3. 不把模型名写死在用户 prompt 里，而是由路由层按任务类型选择。
4. 上线前复核 DeepSeek 的模型名、价格、上下文长度和弃用公告，因为这些信息漂移很快。

![DeepSeek 模型列表文档截图：模型名和价格属于高漂移信息，上线前必须复核。](/assets/img/posts/feishu-lobster-deployment/deepseek-models.png)

后端最好放一层内部模型代理，哪怕第一版只是很薄的一层：

```text
Hermes/OpenClaw compatible request
  -> https://ai-proxy.internal/v1/chat/completions
  -> 记录 user_id、profile_id、task_id、model、tokens
  -> 转发到 DeepSeek API
  -> 写入用量库
  -> 返回给 agent
```

这样做的好处是：换模型、统计 token、设预算、拉排行榜、排查异常，都不需要改 30 个 agent。

## 自动部署 30 人，不要手工点 30 次

第一版要把“员工名单”作为唯一输入，而不是一个人一个人手动装。

准备一个 `users.csv`：

```text
employee_id,feishu_open_id,name,department,role,quota_gb,daily_token_budget
u001,ou_xxx,张三,研究部,user,20,200000
u002,ou_yyy,李四,研究部,pilot,20,300000
```

部署脚本做这些事：

1. 为每个人创建 profile 目录，比如 `/Users/Shared/lobster/profiles/u001`。
2. 创建 Hermes profile，比如 `lobster-u001`。
3. 写入个人配置，只允许访问自己的 memory、sessions、uploads、workspace。
4. 安装默认 skills allowlist。
5. 在数据库登记飞书 `open_id` 与 profile 的映射。
6. 为每个 profile 分配 gateway 端口或本地 socket。
7. 注册到进程管理器，例如 `launchd`、`supervisord` 或 `pm2`。
8. 跑一次健康检查，并把结果发给管理员飞书群。

伪代码大概是这样：

```text
load users.csv
for each user:
  create profile directory
  create hermes profile lobster-{employee_id}
  write config with ai-proxy base_url
  install approved skills
  register feishu_open_id -> profile_name
  create launch service
  run health check
send rollout report to Feishu admin group
```

第一版先不要追求 Kubernetes 或复杂容器化。Mac Studio 单机服务可以很稳定，前提是目录、进程、日志、备份和限流先做好。

## 权限怎么管

权限管理的核心原则是：飞书身份只决定“这个人是谁”，后端 router 才决定“他能访问哪只小龙虾、哪些文件、哪些 skills、哪些模型和多少预算”。

建议角色分四类：

1. 普通用户：只能使用自己的 profile、自己的历史和默认 skills。
2. 试点用户：可以使用 beta skills，但不能访问他人数据。
3. 维护者：可以看健康状态和错误日志，但默认不能看用户完整会话内容。
4. 管理员：可以调整配额、停用 profile、发布 skills，但关键操作要留审计日志。

必须禁止的默认行为：

1. 一个 profile 读取另一个 profile 的目录。
2. 普通用户直接访问 gateway 端口。
3. skills 默认拥有 shell、浏览器 Cookie、公司系统登录态或全盘文件权限。
4. DeepSeek key 分发到个人配置里。
5. 把客户、合同、财务、员工、未公开战略、密钥、日志原文发给未批准的外部服务。

比较稳的目录结构：

```text
/Users/Shared/lobster/
  profiles/
    u001/
      config/
      memory/
      sessions/
      uploads/
      skills/
      logs/
    u002/
      ...
  router/
  ai-proxy/
  metrics/
  backups/
```

20GB 存储配额可以先用应用层 quota checker 实现，每天扫描一次每个 profile 的目录大小，超过 80% 提醒用户，超过 100% 暂停大文件上传和索引任务。如果公司 IT 熟悉 APFS volume quota，也可以给每个人独立 APFS volume，但 30 个 volume 会增加运维复杂度。

## token 统计和部门排行

token 排行不要从 DeepSeek 控制台手工抄。正确做法是让所有模型调用都经过内部代理，并写入结构化日志。

每条模型调用至少记录：

1. `timestamp`
2. `feishu_open_id`
3. `employee_id`
4. `profile_name`
5. `task_type`
6. `model`
7. `prompt_tokens`
8. `completion_tokens`
9. `total_tokens`
10. `estimated_cost`
11. `request_status`

排行榜可以每天或每周由飞书 Bot 发到部门群：

```text
本周小龙虾使用榜
1. 张三  1,240,000 tokens  18 个任务
2. 李四    980,000 tokens  22 个任务
3. 王五    760,000 tokens   9 个任务

异常提醒
- 2 个任务超过单次 token 阈值
- 1 个用户接近本周预算上限
```

但要注意：token 多不等于效率高。更好的内部指标是三类并列：

1. 使用投入：token、任务数、活跃天数。
2. 交付产出：沉淀了多少 briefing、纪要、SOP、研究摘要。
3. 复利资产：个人知识库新增多少可复用条目、多少任务被复用。

否则排行榜很容易变成刷量游戏。

## 默认安装哪些 skills

第一版默认 skills 不要贪多。给所有人统一安装一套“低权限、可复核、能沉淀”的基础包。

建议默认包：

1. Personal Briefing Builder：每天追踪公开信息源，生成个人 briefing。
2. Source Distiller：把文章、网页、会议资料整理成摘要和行动项。
3. PKM Compounder：把一次性问答沉淀进个人知识库。
4. Meeting Notes Builder：整理飞书会议纪要、待办和风险点。
5. Company-Safe Adapter：把个人 AI 用法改写成公司可用的安全版本。
6. Chinese Writing Quality Reviewer：审阅中文表达，减少 AI 味。
7. Cost-Aware Task Router：提醒用户任务是否值得调用高成本模型。
8. Model Snapshot Checker：检查 DeepSeek 模型、价格和配置是否需要复核。
9. Workflow Packager：把一次成功任务整理成可复用 SOP。
10. Skill Discovery Log：记录候选 skills，不允许直接全员安装。

不建议默认启用：

1. 浏览器 Cookie 抓取。
2. 自动登录个人账号。
3. 默认 shell 执行。
4. 默认读取全盘文件。
5. 未经过审批的外部 MCP server。

skills 的原则很简单：先给同事稳定的低权限能力，再把高权限能力做成申请制。

## 同事在飞书里怎么用

普通同事看到的应该是一个飞书联系人或群机器人，而不是命令行。

推荐支持这些自然入口：

```text
@部门小龙虾 帮我把这篇文章整理成 5 条结论和 3 个行动项

@部门小龙虾 以后每天 9 点追踪这 5 个公开来源，给我一段 briefing

@部门小龙虾 把刚才这段讨论沉淀成我的知识库条目

@部门小龙虾 这份非敏感材料帮我改成部门周报风格
```

同时保留少量 slash 命令，给熟练用户提高效率：

```text
/briefing today
/kb search "DeepSeek V4"
/todo this-week
/tokens me
/skills list
/help safe-data
```

飞书消息卡片应该承担更多按钮动作，比如：

1. 保存到我的知识库。
2. 生成待办。
3. 改写成周报。
4. 继续追问。
5. 标记为有用或无用。
6. 申请高权限 skill。

部署后需要补拍这些真实截图：

1. 员工第一次在飞书里唤醒小龙虾。
2. 飞书消息卡片上的“保存到知识库”和“生成待办”按钮。
3. `/tokens me` 返回个人用量。
4. 部门周榜自动推送。
5. 管理员收到健康检查报告。

## 培训怎么做

不要只发一个“大家开始用吧”的通知。30 人部门上线这种工具，要把培训做成习惯迁移。

建议四步：

第一周，5 人试点。

每个人只跑三个任务：每日 briefing、一次资料整理、一次知识库沉淀。目标是发现权限、口径、token 统计和飞书交互问题。

第二周，部门 60 分钟启动培训。

只讲三件事：能做什么、不能放什么资料、怎么让输出可复核。现场演示飞书里发 3 个问题，给大家看结果如何保存和复用。

第三周，岗位小组训练。

研究、运营、管理、行政、工程同事的高频任务不同。每个小组各自沉淀 5 个 prompt 模板和 3 个禁用场景。

第四周，复盘和排行榜。

不要只公布 token 榜。要展示 3 个真实案例：节省了什么时间、沉淀了什么资产、哪里还必须人工判断。

培训材料可以固定成三张卡：

1. 小龙虾能做什么。
2. 什么资料不能给小龙虾。
3. 一个好请求长什么样。

## 日常维护

上线后维护比安装更重要。

每日维护：

1. 检查 gateway 存活。
2. 检查 DeepSeek Proxy 错误率。
3. 检查 token 异常峰值。
4. 检查磁盘剩余空间。
5. 备份 profile 元数据和配置。

每周维护：

1. 发布部门 token 和案例周报。
2. 审核新增 skills 申请。
3. 清理失败任务和过期附件。
4. 抽查 3 条输出是否有敏感资料误用。

每月维护：

1. 复核 DeepSeek 模型、价格和上下文限制。
2. 复核 Hermes/OpenClaw 版本变化。
3. 更新默认 skills。
4. 更新培训材料。
5. 更新这篇博客和版本记录。

## 第一版上线顺序

我会按这个顺序推进：

1. 准备 Mac Studio、系统账号、磁盘目录和备份策略。
2. 部署 DeepSeek Proxy，只让后端通过它调用模型。
3. 部署 Hermes，并用 2 个测试 profile 验证隔离。
4. 接飞书 Bot，实现最小消息收发。
5. 接用户映射表，实现“谁问就路由到谁的 profile”。
6. 接 token 日志和 `/tokens me`。
7. 安装默认 skills。
8. 5 人试点一周。
9. 补拍飞书端真实截图。
10. 扩到 30 人。

这套方案的关键不是“装一个 agent”，而是把 agent 变成部门可治理的生产力基础设施：入口友好、权限清楚、成本可见、知识能沉淀、出了问题能追。

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

## 版本记录

`v0.1.0`，2026-05-31：第一版。将主入口改为飞书，保留“一人一 Hermes profile/gateway”，加入 Mac Studio 采购建议、自动部署、权限治理、token 排行、默认 skills、培训计划和公开截图。
