---
title: "30 人部门 AI 助理部署手册：飞书入口、Hermes 实例、Mac Studio 承载"
date: 2026-05-31
updated: 2026-05-31
version: "0.3.0"
status: "deployment-handbook"
summary: "一份面向部署人员和普通员工的部门 AI 助理手册：机器采购建议、Hermes 安装、30 人批量开通、飞书机器人接入、权限隔离、token 统计、业务截图案例和用户上手流程。"
tags: ["公司端 AI", "飞书", "小龙虾", "Hermes", "DeepSeek", "Mac Studio"]
cover: "/assets/img/posts/feishu-lobster-deployment/case-start.png"
draft: false
changelog: ["0.3.0 - 改为部署手册和用户手册合一版本，补充 Hermes 安装、批量开通、飞书上手流程、业务案例截图和图片放大交互。", "0.2.0 - 重写为正式部署规划，补充飞书端用户流程、后端服务、自动化开通、目录/端口/配置、权限和运维细节。", "0.1.0 - 第一版，确定飞书主入口和一人一 Hermes profile/gateway 的方向。"]
---

## 交付目标

这套方案面向 30 人左右的部门。最终交付物不是一台装了 agent 的机器，而是一套员工可以直接在飞书里使用、管理员可以持续维护的个人 AI 助理服务。

部署完成后，每位员工会获得：

1. 一个飞书里的“部门小龙虾”机器人入口。
2. 一个独立 Hermes profile/gateway。
3. 20GB 左右个人文件与知识库空间。
4. 独立会话历史、个人知识库、信息追踪任务和 token 用量统计。
5. 一组低权限默认 skills，用于摘要、纪要、briefing、知识沉淀、写作审阅和任务复盘。

部署人员照着本文应能完成第一版环境搭建；普通员工照着本文应能完成第一次登录、第一次提问、第一次保存知识、第一次查看 token 用量。

## 采购配置

第一版机器推荐：

```text
Mac Studio
芯片：M4 Max，14 核中央处理器，32 核图形处理器
内存：36GB 统一内存
硬盘：2TB SSD
官方价格：RMB 20,999
```

![Apple 中国 Mac Studio 购买页截图：M4 Max、36GB 统一内存、2TB SSD，页面显示 RMB 20,999。](/assets/img/posts/feishu-lobster-deployment/mac-studio-buy-m4max-36gb-2tb.png)

这个配置的依据是：DeepSeek V4 在云端推理，Mac Studio 主要承担飞书接入、Hermes gateway、任务队列、文件索引、知识库、日志、token 统计和备份，不承担 30 人同时本地跑大模型的负载。

第一版资源策略：

```text
全局对话并发：6 到 8 个活跃任务
后台任务并发：2 到 3 个索引或信息追踪任务
单人并发：1 个对话任务 + 1 个后台任务
单人空间：20GB
机器内置 SSD：2TB
外置备份盘：建议 4TB 到 8TB，单独采购
```

如果后续要在本机跑 embedding、大批量 OCR、本地模型或更高并发，再评估 64GB 以上内存和更高容量 SSD。

## 总体架构

```text
员工飞书客户端
  -> 飞书自建应用 Bot
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

关键原则：

1. 飞书是员工入口，不承载长期状态。
2. Hermes 是个人 agent 底座，每个员工一个独立 profile。
3. DeepSeek key 只放在 DeepSeek Proxy，不写进个人 profile。
4. Hermes gateway 只绑定 `127.0.0.1`，不暴露给员工和公网。
5. 普通员工只使用飞书；管理员使用命令行和管理后台。

Hermes 的 profile 机制适合“一人一实例”。官方文档里，每个 profile 都有自己的 config、API keys、memory、sessions、skills、cron jobs 和 state database。

![Hermes Agent GitHub 仓库截图：第一版底座围绕 Hermes 的 profile 与 gateway 能力设计。](/assets/img/posts/feishu-lobster-deployment/hermes-github.png)

![Hermes profile 文档截图：每个 profile 有独立 config、API keys、memory、sessions、skills 和 gateway state。](/assets/img/posts/feishu-lobster-deployment/hermes-profiles.png)

OpenClaw 保留为后续扩展，不作为第一版 30 人共用主底座。原因是 OpenClaw gateway 不适合直接当作跨用户安全边界。

![OpenClaw security 文档截图：第一版应避免把一个 gateway 当作跨用户安全边界。](/assets/img/posts/feishu-lobster-deployment/openclaw-security.png)

## 部署人员手册

以下步骤以 macOS、zsh、专用系统用户 `lobster` 为例。真实部署前请先完成公司 IT、安全和外部模型使用审批。

### 1. 初始化 Mac Studio

创建专用账号和数据目录：

```bash
sudo dscl . -create /Users/lobster
sudo dscl . -create /Users/lobster UserShell /bin/zsh
sudo dscl . -create /Users/lobster RealName "Lobster Service"
sudo dscl . -create /Users/lobster UniqueID 510
sudo dscl . -create /Users/lobster PrimaryGroupID 20
sudo dscl . -create /Users/lobster NFSHomeDirectory /Users/lobster
sudo createhomedir -c -u lobster

sudo mkdir -p /Users/Shared/lobster/{config,profiles,services,backups,run}
sudo chown -R lobster:staff /Users/Shared/lobster
```

建议目录结构：

```text
/Users/Shared/lobster/
  config/
    users.csv
    policy.yml
    skills-allowlist.yml
    model-routing.yml
    feishu.yml
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

### 2. 安装系统依赖

安装 Homebrew、Python、Node.js 和常用运行依赖：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12 node sqlite git jq ripgrep
python3.12 -m pip install --upgrade pip uv
node --version
python3.12 --version
```

如公司已有统一软件源，按公司源安装，不直接走公网脚本。

### 3. 安装 Hermes

建议先在 `lobster` 用户下安装和验证：

```bash
sudo -iu lobster
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent
```

按 Hermes 当前仓库说明安装依赖。第一版可以采用仓库自带的 Python/Node 安装方式；如果官方安装命令更新，以仓库 README 为准。安装后验证：

```bash
hermes --help
hermes profile --help
hermes gateway --help
```

如果 `hermes` 命令未进入 PATH，把 Hermes 可执行文件或启动脚本加入 `~/.zprofile`：

```bash
echo 'export PATH="$HOME/apps/hermes-agent/bin:$PATH"' >> ~/.zprofile
source ~/.zprofile
```

### 4. 创建 DeepSeek Proxy

DeepSeek Proxy 是部门内部模型入口。它负责三件事：

1. 保存 DeepSeek API key。
2. 兼容 OpenAI 风格 `/v1/chat/completions`。
3. 记录员工、profile、任务、模型、token、费用和错误。

配置示例：

```yaml
server:
  host: 127.0.0.1
  port: 8081

deepseek:
  api_base: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY

routes:
  default: deepseek-v4-flash
  long_reasoning: deepseek-v4-pro
  weekly_report: deepseek-v4-pro

limits:
  require_confirm_above_tokens: 100000
  weekly_default_budget_tokens: 1000000
```

模型名、价格、上下文长度上线前复核 DeepSeek 官方文档。

![DeepSeek 模型列表文档截图：模型名、价格、上下文等信息上线前必须复核。](/assets/img/posts/feishu-lobster-deployment/deepseek-models.png)

### 5. 准备员工名单

`/Users/Shared/lobster/config/users.csv`：

```csv
employee_id,feishu_open_id,name,department,role,quota_gb,weekly_token_budget,gateway_port
u001,ou_xxx,张三,研究部,user,20,1000000,31001
u002,ou_yyy,李四,研究部,pilot,20,1500000,31002
u003,ou_zzz,王五,研究部,admin,20,2000000,31003
```

`feishu_open_id` 由飞书开放平台事件或通讯录接口获得。不要用员工姓名做权限判断，姓名只能作为展示字段。

### 6. 批量创建员工 Hermes profile

部署脚本 `lobsterctl bootstrap` 的目标是让管理员不需要手动创建 30 次。脚本逻辑如下：

```text
读取 users.csv
为每位员工创建 profile 目录
创建 Hermes profile：lobster-{employee_id}
写入 config.yaml，只指向 DeepSeek Proxy
写入 skills allowlist
分配 gateway_port
生成 launchd plist
启动 gateway
运行 health check
写入 profile_registry.sqlite
```

单个员工的等价手工流程：

```bash
export EMPLOYEE_ID=u001
export PROFILE=lobster-u001
export PORT=31001
export ROOT=/Users/Shared/lobster/profiles/$EMPLOYEE_ID

mkdir -p "$ROOT"/{hermes-home,memory,sessions,uploads,knowledge,logs}
hermes profile create "$PROFILE"

cat > "$ROOT/hermes-home/config.yaml" <<EOF
profile: $PROFILE
home: $ROOT/hermes-home
model:
  provider: openai-compatible
  base_url: http://127.0.0.1:8081/v1
  default_model: auto
storage:
  memory_dir: $ROOT/memory
  sessions_dir: $ROOT/sessions
  uploads_dir: $ROOT/uploads
  knowledge_dir: $ROOT/knowledge
permissions:
  filesystem_root: $ROOT
  shell: false
  browser_cookies: false
EOF

hermes gateway start \
  --profile "$PROFILE" \
  --host 127.0.0.1 \
  --port "$PORT"
```

批量部署时不要让 gateway 监听 `0.0.0.0`。所有员工 gateway 只允许 Router 在本机调用。

### 7. 用 launchd 托管 gateway

每位员工一个 `plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.company.lobster.u001</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/lobster/apps/hermes-agent/bin/hermes</string>
    <string>gateway</string>
    <string>start</string>
    <string>--profile</string>
    <string>lobster-u001</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>31001</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/Shared/lobster/profiles/u001/logs/gateway.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/Shared/lobster/profiles/u001/logs/gateway.err.log</string>
</dict>
</plist>
```

加载服务：

```bash
launchctl bootstrap gui/$(id -u lobster) /Users/Shared/lobster/run/com.company.lobster.u001.plist
launchctl print gui/$(id -u lobster)/com.company.lobster.u001
curl http://127.0.0.1:31001/health
```

### 8. 接入飞书自建应用

飞书侧创建企业自建应用，启用机器人能力，配置事件订阅：

```text
事件回调地址：https://lobster.company.com/feishu/events
接收事件：私聊消息、群聊 @ 消息、文件消息、卡片按钮回调
发送能力：机器人发送文本、富文本、交互卡片
权限：获取 open_id、发送消息、读取机器人可见消息
```

![飞书开放平台发送消息 API 截图：第一版用机器人消息、事件回调和交互卡片承接员工入口。](/assets/img/posts/feishu-lobster-deployment/feishu-message-api.png)

Router 配置：

```yaml
feishu:
  app_id: ${FEISHU_APP_ID}
  app_secret: ${FEISHU_APP_SECRET}
  verification_token: ${FEISHU_VERIFICATION_TOKEN}
  encrypt_key: ${FEISHU_ENCRYPT_KEY}
  event_path: /feishu/events

router:
  host: 127.0.0.1
  port: 8080
  profile_registry: /Users/Shared/lobster/services/router/profile_registry.sqlite
```

### 9. Router 如何把消息路由给个人 Hermes

飞书消息进入 Router 后执行：

```text
读取 feishu_open_id
查询 users.csv/profile_registry.sqlite
确认员工状态是 active
读取该员工 gateway_port
检查 token 和并发配额
把消息转发到 http://127.0.0.1:{gateway_port}
拿到 Hermes 返回结果
生成飞书文本或交互卡片
写入审计日志和 token 统计
```

未开通员工返回：

```text
当前账号未开通部门小龙虾服务。请联系管理员开通。
```

敏感文件返回：

```text
该文件不进入模型处理。请先提交脱敏摘要或结构化字段。
```

### 10. 健康检查

部署后运行：

```bash
lobsterctl doctor
```

检查项：

```text
30/30 gateway 是否运行
Router 是否能收到飞书 challenge
DeepSeek Proxy 是否可用
每个 gateway 是否能完成最小对话
每个 profile 是否只能写入自己的目录
token 日志是否入库
uploads 是否受 20GB 配额限制
backup 是否完成一次 dry-run
```

管理员每日会收到类似健康检查卡片：

![管理员健康检查业务截图：展示实例、队列、磁盘和异常任务，示例数据用于培训演示。](/assets/img/posts/feishu-lobster-deployment/case-admin.png)

## 用户上手手册

普通员工只需要使用飞书。可选入口有两个：

1. 飞书桌面端或移动端。
2. 飞书 Web 端：`https://www.feishu.cn/messenger/`

进入后搜索“部门小龙虾”，打开私聊窗口。

### 第一次登录

输入：

```text
/start
```

系统返回开通卡片，展示个人空间、token 预算、默认 skills 和使用边界。

![首次开通业务截图：员工在飞书私聊里发送 /start 后收到个人 AI 助理服务包。](/assets/img/posts/feishu-lobster-deployment/case-start.png)

如果没有开通权限，系统会提示联系管理员。员工不需要知道 Hermes profile 或 gateway 端口。

### 第一次处理文件

把公开资料或允许处理的非敏感文件转发给“部门小龙虾”，再输入：

```text
请整理成 5 条结论、3 个行动项和 2 个风险点。
```

机器人会先要求确认数据类型。选择“公开资料”或“公司内部但允许 AI 处理”后，才会进入摘要流程。

![文件摘要业务截图：上传前先确认数据类型，确认后返回结论、行动项和保存按钮。](/assets/img/posts/feishu-lobster-deployment/case-summary.png)

输出结果里常用按钮：

1. 保存到知识库：把结果写入个人知识库。
2. 生成待办：把行动项转为飞书待办或任务草稿。
3. 改写成周报：把摘要改写成部门周报风格。
4. 继续追问：基于当前上下文继续问。

### 创建每日信息追踪

输入：

```text
/watch add https://example.com/rss 每天 09:00 生成 5 条摘要
```

机器人会创建一个只针对公开来源的定时任务。每天到点后，自动推送 briefing。

![信息追踪业务截图：员工创建公开来源追踪任务后，每天收到 briefing。](/assets/img/posts/feishu-lobster-deployment/case-watch.png)

常用命令：

```text
/watch list
/watch pause 任务名
/watch resume 任务名
/watch delete 任务名
```

### 使用个人知识库

当某次回答有复用价值，点击“保存到知识库”。后续可以搜索：

```text
/kb search DeepSeek V4 部署
```

机器人只搜索该员工自己的知识库，不搜索其他员工内容。

![个人知识库业务截图：员工通过 /kb search 查询自己沉淀过的记录，并继续追问或生成 SOP。](/assets/img/posts/feishu-lobster-deployment/case-kb.png)

常用命令：

```text
/kb search 关键词
/kb save 当前回答
/kb list recent
/kb delete 条目ID
```

### 查看个人 token 用量

输入：

```text
/tokens me
```

系统返回本周 token、任务数、高成本任务和知识沉淀数量。

![用量统计业务截图：员工通过 /tokens me 查看个人 token、任务数、高成本任务和知识条目数。](/assets/img/posts/feishu-lobster-deployment/case-tokens.png)

token 多不等于效率高。部门复盘更关注：是否减少重复劳动、是否形成可复用知识条目、是否产出了 SOP、周报、纪要和 briefing。

## 用户可以做的具体事情

### 资料摘要

适合输入：

```text
请基于这份公开资料输出：
1. 5 条结论
2. 3 个行动项
3. 2 个风险点
4. 可以写入周报的一段话
```

### 会议纪要

适合输入：

```text
请把这段会议记录整理成：
1. 决策事项
2. 待办事项
3. 负责人
4. 截止时间
5. 需要复核的问题
```

### 周报草稿

适合输入：

```text
请把以下本周事项整理成部门周报：
风格：简洁、事实优先、少形容词
结构：本周进展 / 风险问题 / 下周计划
```

### 个人知识沉淀

适合输入：

```text
请把这次回答沉淀成知识库条目：
标题：
适用场景：
步骤：
注意事项：
下次复用提示词：
```

### 不适合输入

不要输入：

1. 客户名单、合同金额、财务数据。
2. 员工个人信息、人事资料。
3. API key、token、Cookie、登录态。
4. 未公开战略、未批准内部代码。
5. 无法确认授权范围的文档原文。

## 权限和用量治理

权限分四层：

```text
飞书身份：确认消息来自哪个 open_id
员工映射：open_id -> employee_id -> Hermes profile
策略控制：skills、模型、预算、文件类型、并发数
系统隔离：目录、端口、secret、日志和备份
```

角色配置：

```yaml
roles:
  user:
    skills: default
    max_chat_jobs: 1
    max_background_jobs: 1
  pilot:
    skills: default_plus_beta
    max_chat_jobs: 2
    max_background_jobs: 2
  maintainer:
    can_view_health: true
    can_view_content: false
  admin:
    can_manage_users: true
    can_manage_quotas: true
    can_publish_skills: true
```

模型调用日志：

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

## 默认 skills

默认启用低权限 skills：

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

## 运维节奏

每日：

1. 检查飞书回调成功率。
2. 检查 Router、DeepSeek Proxy、Hermes gateways 存活状态。
3. 检查 token 异常峰值。
4. 检查磁盘剩余和单人 quota。
5. 处理失败任务。

每周：

1. 发布部门用量和案例周报。
2. 审核新增 skills 申请。
3. 清理过期上传文件。
4. 抽查输出是否符合数据规则。
5. 更新岗位模板。

每月：

1. 复核 DeepSeek 模型、价格、上下文限制和弃用公告。
2. 复核 Hermes/OpenClaw 版本变化。
3. 做一次备份恢复演练。
4. 复盘 token 成本和实际产出。
5. 更新本文版本和生产截图。

Hermes Web Dashboard 可作为维护者排错入口，不作为普通员工入口。

![Hermes dashboard 文档截图：适合作为维护者排错界面，普通员工仍以飞书为主入口。](/assets/img/posts/feishu-lobster-deployment/hermes-dashboard.png)

## 参考资料

1. [Hermes Agent GitHub](https://github.com/NousResearch/hermes-agent)
2. [Hermes Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
3. [Hermes Web Dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)
4. [OpenClaw GitHub](https://github.com/openclaw/openclaw)
5. [OpenClaw Gateway Security](https://docs.openclaw.ai/gateway/security)
6. [Apple 中国 Mac Studio 购买页](https://www.apple.com.cn/shop/buy-mac/mac-studio/m4-max-chip-14-core-cpu-32-core-gpu-36gb-memory-2tb-storage)
7. [DeepSeek API Docs](https://api-docs.deepseek.com/)
8. [飞书开放平台发送消息 API](https://open.feishu.cn/document/server-docs/im-v1/message/create)

## 修订记录

`v0.3.0`，2026-05-31：扩展为部署手册和用户手册合一版本，加入机器配置费用、Hermes 部署流程、批量开通、飞书使用案例和图片放大交互。

`v0.2.0`，2026-05-31：调整为正式部署规划，补充员工服务包、飞书端流程、服务拓扑、权限策略和运维机制。

`v0.1.0`，2026-05-31：确定飞书主入口和一人一 Hermes profile/gateway 的方案方向。
