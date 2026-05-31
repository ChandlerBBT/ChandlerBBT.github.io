---
title: "30 人部门 AI 助理部署手册：飞书入口、Hermes 实例、Mac Studio 承载"
date: 2026-05-31
updated: 2026-05-31
version: "0.6.0"
status: "deployment-and-knowledge-base-handbook"
summary: "一份面向部署人员和普通员工的部门 AI 助理手册：机器采购建议、Hermes 安装、飞书部署工作台、Excel 批量开通、部门知识库素材上传、权限隔离、token 统计、业务截图案例和用户上手流程。"
tags: ["公司端 AI", "飞书", "小龙虾", "Hermes", "DeepSeek", "知识库", "Mac Studio"]
cover: "/assets/img/posts/feishu-lobster-deployment/case-user-home-actions.png"
draft: false
changelog: ["0.6.0 - 明确飞书同时作为部署工作台和员工入口，重写企业研究分析 skills。", "0.5.0 - 补充飞书接入联调、Excel 批量开通、知识库上传向导、用户飞书截图路径和技能库分层。", "0.4.0 - 补充部门知识库、开源模型兜底方案、机器配置档位和悬浮目录。", "0.3.0 - 改为部署手册和用户手册合一版本，补充 Hermes 安装、批量开通、飞书上手流程、业务案例截图和图片放大交互。", "0.2.0 - 重写为正式部署规划，补充飞书端用户流程、后端服务、自动化开通、目录/端口/配置、权限和运维细节。", "0.1.0 - 第一版，确定飞书主入口和一人一 Hermes profile/gateway 的方向。"]
---

## 交付目标

这套方案面向 30 人左右的部门。最终交付物不是一台装了 agent 的机器，而是一套员工可以直接在飞书里使用、管理员可以持续维护的个人 AI 助理服务。

部署完成后，系统只有一个统一入口：飞书。普通员工看到的是“部门小龙虾”私聊、群聊和交互卡片；部署人员看到的是飞书里的部署工作台，包括管理员群、应用主页、表单、多维表格和任务状态卡片。

每位员工会获得：

1. 一个飞书里的“部门小龙虾”机器人入口。
2. 一个独立 Hermes profile/gateway。
3. 20GB 左右个人文件与知识库空间。
4. 独立会话历史、个人知识库、信息追踪任务和 token 用量统计。
5. 受权限控制的部门知识库入口，用于检索历史研究报告、用户调研材料和复用型结论。
6. 一组低权限默认 skills，用于摘要、纪要、briefing、知识沉淀、写作审阅和任务复盘。

部署人员照着本文应能完成第一版环境搭建和联调；普通员工只阅读飞书使用路径，不需要理解命令行、端口、profile 或模型网关。

## 部署和机器选购

### 采购结论

如果公司内网大模型 API 能按安全要求对接，第一版机器推荐保持在这档：

```text
Mac Studio
芯片：M4 Max，14 核中央处理器，32 核图形处理器
内存：36GB 统一内存
硬盘：2TB SSD
官方价格：RMB 20,999
```

![Apple 中国 Mac Studio 购买页截图：M4 Max、36GB 统一内存、2TB SSD，页面显示 RMB 20,999。](/assets/img/posts/feishu-lobster-deployment/mac-studio-buy-m4max-36gb-2tb.png)

这个配置的依据是：大模型推理走公司内网 API 或经过审批的外部非涉密模型通道，Mac Studio 主要承担飞书接入、Hermes gateway、任务队列、文件索引、部门知识库、日志、token 统计和备份，不承担 30 人同时本地跑大模型的负载。

如果公司内网大模型 API 谈不下来，机器建议上调到下面两档之一：

```text
实用离线兜底档
Mac Studio
芯片：M4 Max，16 核中央处理器，40 核图形处理器
内存：64GB 统一内存
硬盘：4TB SSD
官方价格：RMB 30,749
定位：可以承载 Qwen3-30B-A3B 的 4-bit 本地推理、部门知识库索引、30 人 Hermes gateway 和常规后台任务。

重度本地模型档
Mac Studio
芯片：M3 Ultra，28 核中央处理器，60 核图形处理器
内存：96GB 统一内存
硬盘：2TB SSD
官方价格：RMB 35,999
定位：适合把本地模型作为知识库主力底座，并把 DeepSeek-R1-Distill-Qwen-32B 这类 32B 推理模型用于离线报告合成任务。
如果历史材料很多，建议把内置 SSD 升到 4TB，按 Apple 配置器存储差价估算约 RMB 40,499，采购前复核最终价格。
```

![Apple 中国 Mac Studio 购买页截图：M4 Max、64GB 统一内存、4TB SSD，页面显示 RMB 30,749。](/assets/img/posts/feishu-lobster-deployment/mac-studio-buy-m4max-64gb-4tb.png)

![Apple 中国 Mac Studio 购买页截图：M3 Ultra、96GB 统一内存、2TB SSD，页面显示 RMB 35,999。](/assets/img/posts/feishu-lobster-deployment/mac-studio-buy-m3ultra-96gb-2tb.png)

### 不按人硬切 CPU 和内存

不要把这台机器理解成“给 30 个人每人分几个 CPU 核、几 GB 内存”。Mac Studio 的统一内存和 CPU 更适合做共享资源池，由 Router、Job Queue 和模型网关控制并发。

第一版资源策略：

```text
全局对话并发：6 到 8 个活跃任务
后台任务并发：2 到 3 个索引或信息追踪任务
单人并发：1 个对话任务 + 1 个后台任务
单人空间：20GB
机器内置 SSD：2TB
外置备份盘：建议 4TB 到 8TB，单独采购
```

普通员工看不到 CPU、内存和端口，只看到飞书里的服务状态。管理员用三类阈值管资源：

1. 单人任务并发：避免一个人提交多个长任务占满队列。
2. 全局后台并发：OCR、索引、桌面研究报告生成排队执行。
3. 模型运行模式：外部/内网 API 可并发，本地模型只允许少量并发或批处理。

### 部门知识库新增负载

部门知识库不是每个人 20GB 个人空间的简单相加，它是一套共享资料资产。建议单独划出 `/Users/Shared/lobster/department-kb`：

```text
/Users/Shared/lobster/department-kb/
  raw/              原始报告、访谈纪要、调研表、PDF、PPT、DOCX
  extracted/        OCR 和文本抽取结果
  chunks/           分段后的文本块
  vectors/          向量索引
  metadata.sqlite   资料来源、权限、标签、日期、项目、作者
  reports/          生成的桌面研究报告草稿
  audit/            检索、引用和导出日志
```

容量估算：

```text
30 人个人空间：约 600GB
部门历史材料原文：先按 300GB 到 800GB 预留
抽取文本、缩略图、OCR 中间文件：原文的 20% 到 50%
向量索引和元数据：原文文本量的 5% 到 15%
运行日志、缓存、报告草稿：100GB 到 300GB
本地模型权重：10GB 到 70GB，取决于模型和量化精度
本地 Time Machine 或 rsync 备份：不建议占用内置盘，应放外置盘或 NAS
```

如果历史材料在 500GB 以内、知识库 LLM 走公司内网 API，2TB 内置盘可以启动第一版。如果历史材料接近 1TB，或准备常驻本地模型，建议直接买 4TB 内置 SSD。

### 知识库 LLM 底座

知识库的保密要求高于个人助理。模型路由按下面优先级设计：

1. 首选：公司内网大模型 API。部门历史报告、用户调研资料、研究报告合成只走内网模型。
2. 兜底：Mac Studio 本机离线开源模型。用 `llama.cpp` 或兼容 OpenAI API 的本地 server 暴露 `127.0.0.1:8090/v1`。
3. 禁止：部门知识库原文、检索片段、引用来源进入外部大模型。外部 DeepSeek 只用于经过审批的非涉密个人助理任务。

知识库链路：

```text
资料入库
  -> 权限和密级标注
  -> OCR / 文本抽取
  -> 分段 chunk
  -> embedding
  -> 向量索引
  -> 关键词索引
  -> rerank
  -> 内网 LLM 或本地 LLM 生成回答
  -> 返回引用来源和可追溯片段
```

embedding 和 rerank 可以优先选本地中文模型，例如 BGE-M3、bge-reranker-v2-m3 或公司统一提供的向量服务。它们比生成式大模型更容易本机部署，也更适合作为保密知识库的基础能力。

### 本地开源模型候选

以下内存和存储是工程估算，按常见 GGUF 4-bit / 8-bit 量化、Metal 推理、32K 到 64K 上下文做规划；实际占用会随量化版本、上下文长度、batch size、KV cache 和运行框架变化。

候选一：Qwen3-14B。

```text
参数规模：约 15B
官方特征：Qwen3 系列，支持 thinking / non-thinking 切换，Apache-2.0
模型存储：BF16 约 30GB；4-bit 约 8GB 到 10GB；8-bit 约 15GB 到 17GB
运行内存：4-bit 约 16GB 到 22GB；5-bit/6-bit 约 20GB 到 30GB
适合机器：36GB 可以作为应急本地模型；64GB 更稳
```

优点：最适合 20,999 元配置做离线兜底；中文、英文、工具调用和通用问答能力均衡；在不拉长上下文的情况下，能和 Hermes、飞书 Router、索引服务共存。

缺点：跨几十份资料写高质量桌面研究报告时会明显弱于 30B 以上模型；如果把上下文拉到 100K 以上，36GB 机器会被 KV cache 挤压，不适合作为长期知识库主力。

![Qwen3-14B Hugging Face 模型页截图：页面显示 Qwen3-14B、约 15B 参数和 Apache-2.0 许可。](/assets/img/posts/feishu-lobster-deployment/qwen3-14b-model-card.png)

候选二：Qwen3-30B-A3B-Instruct-2507。

```text
参数规模：约 31B，总参数 30B 级，MoE 每 token 激活约 3B 级参数
官方特征：Instruct 2507，non-thinking mode，256K long-context understanding，Apache-2.0
模型存储：BF16 约 62GB；4-bit 约 18GB 到 22GB；8-bit 约 32GB 到 36GB
运行内存：4-bit 约 32GB 到 44GB；上下文拉长后建议 64GB 起步，96GB 更稳
适合机器：64GB/4TB 是实用起点；96GB 适合把它作为知识库主力
```

优点：这是本方案的离线主推模型。它在中文理解、指令跟随、工具调用、长上下文和开放式总结上更适合部门知识库；MoE 结构让计算压力比同规模 dense 模型友好一些，适合“常驻问答 + 少量报告生成”的组合。

缺点：MoE 只降低每 token 计算量，不代表只占 3B 模型内存，权重仍要加载；64GB 机器上必须限制上下文和并发；如果同时跑 OCR、索引、30 个 gateway 和长报告生成，仍需要排队。

![Qwen3-30B-A3B-Instruct-2507 Hugging Face 模型页截图：页面显示约 31B 参数、256K long-context understanding 和 Apache-2.0 许可。](/assets/img/posts/feishu-lobster-deployment/qwen3-30b-a3b-model-card.png)

候选三：DeepSeek-R1-Distill-Qwen-32B。

```text
参数规模：约 33B
官方特征：DeepSeek-R1 蒸馏模型，基于 Qwen 32B，MIT 许可
模型存储：BF16 约 66GB；4-bit 约 19GB 到 24GB；8-bit 约 34GB 到 38GB
运行内存：4-bit 约 36GB 到 52GB；建议 96GB 机器用于批处理
适合机器：不建议放在 36GB 机器；64GB 可测试；96GB 才适合作为报告合成 batch 模型
```

优点：适合复杂推理、冲突材料分析、假设拆解和研究报告大纲生成。它不需要把资料发到外部 DeepSeek 服务，只在本机离线运行时使用本地权重。

缺点：推理模型更慢，输出更容易冗长；日常知识库问答体验不如 Qwen3-30B-A3B 轻快；如果 30 人 Hermes 服务也在同一台机器上，必须把它限制为 `/desk-research` 之类的后台批处理任务。

![DeepSeek-R1-Distill-Qwen-32B Hugging Face 模型页截图：页面显示约 33B 参数和 MIT 许可。](/assets/img/posts/feishu-lobster-deployment/deepseek-r1-distill-qwen-32b-model-card.png)

技术选型建议：

1. 内网大模型 API 能上线：买 RMB 20,999 的 36GB/2TB 版本即可启动，部门知识库生成环节走内网 API，本机只做索引、权限、队列和缓存。
2. 内网 API 不确定，但希望第一版就有离线可用能力：买 RMB 30,749 的 64GB/4TB 版本，默认本地模型选 Qwen3-30B-A3B-Instruct-2507 4-bit，Qwen3-14B 作为低资源备用。
3. 内网 API 短期无法落地，且桌面研究报告是高频场景：预算提高到 RMB 35,999 到 RMB 40,499，选 M3 Ultra 96GB，常驻 Qwen3-30B-A3B，DeepSeek-R1-Distill-Qwen-32B 只跑后台报告合成。

## 总体架构

```text
员工飞书前台
  -> 部门小龙虾 Bot
  -> 私聊 / 群聊 @ / 交互卡片
  -> Lobster Router
  -> Identity & Policy Service
  -> Job Queue
  -> Hermes Gateway Pool
  -> Model Gateway

部署者飞书工作台
  -> 管理员群 / 应用主页 / 表单 / 多维表格 / 文件上传 / 状态卡片
  -> Admin Event Handler
  -> Provisioning Worker
  -> Knowledge Import Worker
  -> Model Gateway Config Worker

Model Gateway：
  非涉密个人助理任务 -> DeepSeek Proxy 或其他审批通过的外部模型
  部门知识库任务 -> 公司内网大模型 API
  内网 API 不可用 -> Local LLM Server

旁路系统：
  Profile Store
  Upload Store
  Personal Knowledge Index
  Department Knowledge Index
  Vector Store
  Reranker
  Metrics Store
  Audit Log
  Feishu Admin Tables
```

关键原则：

1. 飞书同时是员工前台和部署者工作台，提供登录、身份、消息、表单、多维表格、文件上传和卡片交互。
2. Hermes 是个人 agent 底座，每个员工一个独立 profile。
3. 外部模型 key 只放在 Model Gateway，不写进个人 profile。
4. Hermes gateway 只绑定 `127.0.0.1`，不暴露给员工和公网。
5. 部门知识库和个人知识库物理目录、索引、权限、审计日志分开。
6. 飞书不承载长期业务状态；长期状态仍在 Mac Studio 上的数据库、索引、文件目录和审计日志里。
7. 普通员工只使用飞书；部署者使用飞书部署工作台完成开通、联调、知识库上传，命令行只作为底层排障手段。

Hermes 的 profile 机制适合“一人一实例”。官方文档里，每个 profile 都有自己的 config、API keys、memory、sessions、skills、cron jobs 和 state database。

![Hermes Agent GitHub 仓库截图：第一版底座围绕 Hermes 的 profile 与 gateway 能力设计。](/assets/img/posts/feishu-lobster-deployment/hermes-github.png)

![Hermes profile 文档截图：每个 profile 有独立 config、API keys、memory、sessions、skills 和 gateway state。](/assets/img/posts/feishu-lobster-deployment/hermes-profiles.png)

OpenClaw 保留为后续扩展，不作为第一版 30 人共用主底座。原因是 OpenClaw gateway 不适合直接当作跨用户安全边界。

![OpenClaw security 文档截图：第一版应避免把一个 gateway 当作跨用户安全边界。](/assets/img/posts/feishu-lobster-deployment/openclaw-security.png)

## 部署人员手册

以下步骤以 macOS、zsh、专用系统用户 `lobster` 为例。真实部署前请先完成公司 IT、安全和外部模型使用审批。

这一版不再建议单独做一个完整网页后台。部署者的日常后台放在飞书自建应用里：管理员在飞书看到“飞书部署工作台”，通过表单、多维表格、文件附件和交互卡片完成开通、配置、导入和联调；Mac Studio 上只跑事件接收、任务执行、数据库和索引服务。

这不是飞书原生一键生成的后台，也不需要从零写一套完整 Web 管理系统。需要开发和部署的是一个轻量后端 `lobster-admin-backend`：接收飞书事件、校验操作者权限、读取表单/多维表格/附件、执行开通和导入任务，再把状态写回飞书卡片和多维表格。

部署者日常只需要走五个飞书向导：

1. 飞书接入：填 App ID、App Secret、Encrypt Key、Verification Token，并复制事件回调地址到飞书开放平台。
2. 员工开通：上传 Excel，字段为工号、姓名、存储空间容量、每月Token容量额度。
3. 模型配置：选择公司内网大模型 API，或选择本机开源模型兜底。
4. 知识库上传：上传原始 PPT、PDF、Word、Excel、图片、录音等素材。
5. 联调检查：验证飞书 challenge、消息接收、卡片按钮、个人 profile 路由和 token 统计。

这条路径的目标是让部署人员尽量少碰底层命令。下面的命令和配置用于首次安装、自动化脚本开发和排障；正式上线后，开通员工、接入飞书和导入知识库都应该在飞书部署工作台里完成。

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

### 4. 创建 Model Gateway

Model Gateway 是部门内部模型入口。它负责五件事：

1. 保存 DeepSeek、公司内网模型和本地模型的访问配置。
2. 兼容 OpenAI 风格 `/v1/chat/completions`。
3. 按任务密级路由：个人非涉密任务可走审批通过的外部模型，部门知识库任务只走公司内网 API 或本机离线模型。
4. 记录员工、profile、任务、模型、token、费用和错误。
5. 拦截未经授权的资料、超预算请求和长上下文任务。

配置示例：

```yaml
server:
  host: 127.0.0.1
  port: 8081

providers:
  deepseek_public:
    api_base: https://api.deepseek.com
    api_key_env: DEEPSEEK_API_KEY
    allowed_data_class: public_or_approved
  company_llm:
    api_base: https://llm.internal.company/v1
    api_key_env: COMPANY_LLM_API_KEY
    allowed_data_class: internal_kb
  local_llm:
    api_base: http://127.0.0.1:8090/v1
    allowed_data_class: internal_kb

routes:
  personal_default: deepseek_public
  department_kb_default: company_llm
  department_kb_fallback: local_llm
  desk_research: company_llm

limits:
  require_confirm_above_tokens: 100000
  weekly_default_budget_tokens: 1000000
```

模型名、价格、上下文长度上线前复核对应供应方文档。部门知识库材料不进入外部模型通道。

![DeepSeek 模型列表文档截图：模型名、价格、上下文等信息上线前必须复核。](/assets/img/posts/feishu-lobster-deployment/deepseek-models.png)

部署者在飞书部署工作台里看到的是模型配置卡片。选择“公司内网大模型 API”后，只需要填写 API Base、API Key、默认模型名和最大上下文；选择“本机离线模型”后，只需要选择已下载模型和上下文长度。后端会把密钥加密保存到 Mac Studio，不写入飞书多维表格明文字段。保存前必须点“测试连接”，测试通过后才允许导入部门知识库素材。

![模型配置向导截图：部署者选择公司内网 API 或本机模型，测试通过后保存为知识库默认模型。](/assets/img/posts/feishu-lobster-deployment/admin-model-config.png)

### 5. 用 Excel 准备员工开通表

部署者只准备一份 Excel，并在飞书部署工作台的“员工开通”卡片里上传。部署者不需要填写端口、open_id、profile 名称或系统路径。第一版必填四列：

```text
工号
姓名
存储空间容量
每月Token容量额度
```

示例：

```text
工号    姓名    存储空间容量    每月Token容量额度
U001    张三    20GB            100万
U002    李四    20GB            150万
U003    王五    30GB            200万
```

上传后，飞书会把文件作为附件交给 `lobster-admin-backend`。后端读取 Excel，写入“员工开通表”多维表格，并做四类校验：

1. 工号是否能在飞书通讯录里匹配到员工。
2. 姓名是否与通讯录一致，不一致时进入待确认。
3. 存储空间容量是否超过机器剩余可分配空间。
4. 每月Token容量额度是否超过部门总预算。

![员工 Excel 一键开通截图：部署者上传包含工号、姓名、存储空间容量、每月Token容量额度的 Excel，系统自动校验并预览。](/assets/img/posts/feishu-lobster-deployment/admin-excel-import.png)

Excel 导入通过后，飞书部署工作台会显示预览和差异提醒；确认后，后端生成内部 `users.csv` 和 profile registry。内部表会补齐 `feishu_open_id`、`employee_id`、`gateway_port`、`profile_name`、`quota_gb` 和 `monthly_token_budget` 等字段，但这些字段不要求部署者手工维护。

### 6. 一键创建员工 Hermes profile

点击“确认并开通”后，部署脚本 `lobsterctl bootstrap` 会批量执行，不需要管理员手动创建 30 次。脚本逻辑如下：

```text
读取 Excel 导入后的员工表
按工号匹配飞书通讯录 open_id
为每位员工创建 profile 目录
创建 Hermes profile：lobster-{employee_id}
写入 config.yaml，只指向 Model Gateway
写入 skills allowlist
自动分配 gateway_port
写入存储空间 quota 和每月 token 额度
生成 launchd plist
启动 gateway
运行 health check
写入 profile_registry.sqlite
```

单个员工的底层等价流程如下，日常部署不需要逐个执行：

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

飞书接入分两边配置：飞书开放平台创建自建应用，Mac Studio 上的后端保存应用密钥和回调参数。部署人员应该先在飞书部署工作台打开“飞书接入”向导，再去飞书开放平台操作。

同一个飞书自建应用承接两类入口：

1. 员工前台：员工与“部门小龙虾”机器人私聊、在群里 @ 机器人、点击机器人发出的交互卡片。
2. 部署工作台：部署人员进入管理员群或应用主页，通过表单、多维表格、附件上传和状态卡片管理开通、模型、知识库和联调。

飞书部署工作台需要填写：

```text
App ID
App Secret
Encrypt Key
Verification Token
事件回调地址：https://lobster.company.com/feishu/events
```

![飞书接入向导截图：部署者把飞书应用参数填入飞书部署工作台，并复制事件回调地址到飞书开放平台。](/assets/img/posts/feishu-lobster-deployment/admin-feishu-wizard.png)

飞书开放平台侧按下面顺序配置：

1. 进入飞书开放平台，创建“企业自建应用”，应用名建议为“部门小龙虾”。
2. 启用机器人能力，头像和简介使用部门内部统一口径。
3. 在事件订阅里填写飞书部署工作台给出的事件回调地址，保存后飞书会发送 challenge，工作台应显示“challenge 通过”。
4. 订阅消息事件：私聊消息、群聊 @ 消息、文件消息。
5. 订阅卡片按钮回调：保存到知识库、生成桌面研究、查看引用、确认资料类型、确认批量开通。
6. 开通发送消息能力：机器人发送文本、富文本、交互卡片。
7. 开通通讯录读取能力：用员工工号匹配飞书 open_id。只读取开通所需字段，不同步无关人事信息。
8. 开通多维表格或表单相关能力：用于员工开通表、模型配置表、知识库批次表、任务状态表和审计日志表。
9. 发布应用版本，并安装到部门可见范围。第一轮先只安装给 3 到 5 个试点用户和 1 到 2 名部署人员。

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

部署工作台里的多维表格建议固定为五张：

```text
员工开通表：工号、姓名、容量、月 token 额度、开通状态、失败原因
模型配置表：供应商、API Base、模型名、用途、测试状态、最后测试时间
知识库批次表：批次名、资料密级、可访问角色、导入状态、验收问题
任务状态表：任务 ID、任务类型、进度、操作者、开始时间、结束时间
审计日志表：操作者、动作、对象、结果、错误码、追踪 ID
```

调通标准不是“配置保存成功”，而是下面 8 项全部通过：飞书 challenge、私聊消息事件、机器人发送消息、卡片按钮回调、工号到 open_id 的映射、员工 Excel 写入多维表格、知识库附件读取、个人 profile 路由。

![飞书联调检查截图：逐项验证 challenge、消息接收、卡片按钮、个人路由和 token 统计。](/assets/img/posts/feishu-lobster-deployment/admin-debug-checklist.png)

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
Model Gateway、公司内网模型 API 或本地模型 server 是否可用
每个 gateway 是否能完成最小对话
每个 profile 是否只能写入自己的目录
token 日志是否入库
uploads 是否受 20GB 配额限制
department-kb 是否只暴露给授权角色
backup 是否完成一次 dry-run
```

管理员每日会收到类似健康检查卡片：

![管理员健康检查业务截图：展示实例、队列、磁盘和异常任务，示例数据用于培训演示。](/assets/img/posts/feishu-lobster-deployment/case-admin.png)

### 11. 部署部门知识库服务

部门知识库和个人知识库分开部署。个人知识库服务于员工自己的复用；部门知识库服务于部门级研究资产，必须有统一权限、统一元数据和统一引用记录。

部署者在飞书部署工作台里只需要完成三件事：

1. 在“模型配置”里选择知识库 LLM：公司内网大模型 API，或本机离线模型。
2. 在“知识库”里填写资料批次信息：批次名称、资料密级、可访问角色、资料来源说明。
3. 直接上传原始素材：PPT/PPTX、PDF、Word、Excel、Markdown、图片、录音 m4a/mp3/wav。

![知识库素材上传截图：部署者上传原始研究资料，系统自动进入转写、OCR、切分、索引和验收流程。](/assets/img/posts/feishu-lobster-deployment/admin-kb-upload.png)

上传后，飞书只负责承接附件和触发事件；Mac Studio 上的 Knowledge Import Worker 自动处理下游环节：

```text
文件指纹去重
  -> 格式识别
  -> PDF / PPT / Word / Excel 文本抽取
  -> 图片 OCR
  -> 录音 ASR 转写
  -> 按标题、章节、表格、访谈对象、时间戳切块
  -> 生成 embedding
  -> 建立向量索引和关键词索引
  -> rerank 测试
  -> 抽样生成引用
  -> 输出导入报告
```

部署者需要看的只有导入报告：

```text
导入文件数
成功 / 失败文件数
录音转写成功率
OCR 成功率
已生成知识片段数
抽样引用是否能追溯到原文
无权限用户是否无法检索到该批资料
可直接复制到飞书的测试问题
```

知识库上线前必须完成 3 个验收问题：

1. 用管理员账号提问一个已知答案的问题，确认回答能引用到正确报告、页码或录音时间戳。
2. 用普通员工账号提问同一个问题，确认只能看到自己角色允许访问的资料。
3. 用无权限账号提问，确认系统不会泄露标题、片段或引用。

底层目录仍然按 `raw / extracted / chunks / vectors / reports / audit` 保存，方便备份和排障；但部署人员不需要手工创建目录、写 SQL 或执行导入命令。

## 用户上手手册

普通员工只需要使用飞书，不需要打开终端，不需要知道 Hermes、gateway、模型名或端口。可选入口有两个：

1. 飞书桌面端或移动端。
2. 飞书 Web 端：`https://www.feishu.cn/messenger/`

进入后搜索“部门小龙虾”，打开私聊窗口。

### 第一次登录

第一次打开后，系统返回个人首页卡片，展示个人空间、每月 token 额度、默认 skills 和可用按钮。员工不需要记任何命令，先点卡片里的按钮即可。

![个人首页业务截图：员工在飞书里看到个人空间、每月 token 额度、默认技能和常用按钮。](/assets/img/posts/feishu-lobster-deployment/case-user-home-actions.png)

如果没有开通权限，系统会提示联系管理员。员工不需要知道 Hermes profile 或 gateway 端口。

### 第一次处理文件

把公开资料或允许处理的非敏感文件转发给“部门小龙虾”，然后在输入框里直接写自然语言需求，例如“请整理成 5 条结论、3 个行动项和 2 个风险点”。机器人会先要求确认数据类型。选择“公开资料”或“公司内部但允许 AI 处理”后，才会进入摘要流程。

![文件摘要业务截图：上传前先确认数据类型，确认后返回结论、行动项和保存按钮。](/assets/img/posts/feishu-lobster-deployment/case-summary.png)

输出结果里常用按钮：

1. 保存到知识库：把结果写入个人知识库。
2. 生成待办：把行动项转为飞书待办或任务草稿。
3. 改写成周报：把摘要改写成部门周报风格。
4. 继续追问：基于当前上下文继续问。

### 创建每日信息追踪

点击“创建追踪”，在卡片里填公开来源链接、推送频率和输出格式。机器人会创建一个只针对公开来源的定时任务，每天到点后自动推送 briefing。

![信息追踪业务截图：员工通过飞书表单创建公开来源追踪任务，不需要记命令。](/assets/img/posts/feishu-lobster-deployment/case-watch-natural.png)

### 使用个人知识库

当某次回答有复用价值，点击“保存到知识库”。后续在“我的知识库”里输入关键词或问题，机器人只搜索该员工自己的知识库，不搜索其他员工内容。

![个人知识库业务截图：员工查询自己沉淀过的记录，并继续追问或生成 SOP。](/assets/img/posts/feishu-lobster-deployment/case-kb.png)

### 使用部门知识库

部门知识库用于查询已经入库、已授权的研究报告、用户调研材料、访谈纪要和复盘材料。它和个人知识库不同：个人知识库只看自己的沉淀，部门知识库会检索部门公共资料，并且每个结论都要带引用来源。

员工直接在输入框提问，例如“帮我查：过去 6 个月用户为什么放弃试用？”系统会返回结论、证据来源和操作按钮。

![部门知识库业务截图：员工用自然语言检索授权部门资料，回答附带来源和后续操作按钮。](/assets/img/posts/feishu-lobster-deployment/case-dept-kb.png)

需要形成新课题输入时，点击“生成桌面研究”，填写课题、范围和输出格式。系统会把多份授权材料合成为 briefing 草稿。

![桌面研究业务截图：员工通过飞书卡片把多份部门材料合成为 briefing 草稿。](/assets/img/posts/feishu-lobster-deployment/case-desk-research.png)

如果某条资料没有权限，系统会只返回“无权访问”或“结果中存在不可展示材料”，不会把未授权片段透出给用户。

### 查看个人 token 用量

点击“查看我的用量”，系统返回本周 token、任务数、高成本任务和知识沉淀数量。

![用量统计业务截图：员工查看个人 token、任务数、高成本任务和知识条目数。](/assets/img/posts/feishu-lobster-deployment/case-tokens.png)

token 多不等于效率高。部门复盘更关注：是否减少重复劳动、是否形成可复用知识条目、是否产出了 SOP、周报、纪要和 briefing。

## 用户可以做的具体事情

### 资料摘要

适合场景：把公开资料、已批准处理的内部材料整理成结论、行动项、风险点和周报素材。员工在飞书输入框里直接写：“请基于这份公开资料输出 5 条结论、3 个行动项、2 个风险点，以及一段可以写入周报的话。”

### 会议纪要

适合场景：把会议记录整理成决策事项、待办事项、负责人、截止时间和需要复核的问题。会议涉及敏感客户、合同、财务或人事信息时，不进入外部模型通道。

### 周报草稿

适合场景：把本周事项整理成“本周进展 / 风险问题 / 下周计划”。建议要求它“简洁、事实优先、少形容词”，输出后再由员工人工确认。

### 个人知识沉淀

适合场景：把一次有效回答保存成个人知识库条目。推荐结构包括标题、适用场景、步骤、注意事项、下次复用提示词。

### 部门资料检索

适合场景：基于授权的历史研究报告和用户调研材料提问。推荐问法：“请基于 2025 年以来的用户调研材料，总结用户首次试用失败的前三个原因、对应证据来源，以及下次访谈可以继续验证的问题。”

### 桌面研究报告

适合场景：为新课题快速准备输入材料。员工填写课题、资料范围和输出格式，系统生成一页 briefing、关键洞察、证据引用和需要补充调研的问题。

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
策略控制：skills、模型、预算、文件类型、知识库范围、并发数
系统隔离：目录、端口、secret、日志和备份
```

角色配置：

```yaml
roles:
  user:
    skills: default
    max_chat_jobs: 1
    max_background_jobs: 1
    kb_scopes: personal,department_public
  pilot:
    skills: default_plus_beta
    max_chat_jobs: 2
    max_background_jobs: 2
    kb_scopes: personal,department_public,department_pilot
  maintainer:
    can_view_health: true
    can_view_content: false
    can_rebuild_index: true
  admin:
    can_manage_users: true
    can_manage_quotas: true
    can_publish_skills: true
    can_manage_kb_permissions: true
```

部门知识库权限不要靠“资料放在哪个文件夹”来判断，必须落到元数据和检索过滤上。检索前先按 `employee_id`、`role`、`kb_scopes` 过滤文档集合，再做向量召回和 rerank；检索后再次过滤引用片段，防止模型答案里混入未授权材料。

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
  kb_scope text,
  data_class text not null default 'public_or_approved',
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

技能库按企业白领的真实工作维护：研究与洞察、数据分析、办公产出、知识沉淀、质量与合规。部署完成后先全员启用低风险技能；涉及浏览器登录态、网页自动化、外部账号、敏感资料和文件系统扩大权限的技能，需要申请后按角色开放。

![技能库配置截图：面向研究、分析、办公产出和知识沉淀的企业 skills，按岗位启用并做审计。](/assets/img/posts/feishu-lobster-deployment/admin-skill-pack.png)

第一组，全员默认启用：

1. Agent Reach：公开信息检索、网页资料追踪、RSS 订阅和公开来源监测，默认只允许公开来源。
2. Department KB Searcher：按权限检索部门研究报告、用户调研、复盘材料，并强制返回引用来源。
3. Research Report Distiller：把 PDF、PPT、Word 和网页资料整理成结论、证据、待验证假设和行动项。
4. User Interview / VOC Synthesizer：整理访谈记录、客服反馈、开放题和用户原话，输出主题聚类、代表性引文和洞察假设。
5. Survey & Spreadsheet Analyst：读取 Excel/CSV，做描述统计、交叉分析、异常值提示和图表建议。
6. Data Visualization Reporter：把数据分析结果转成适合汇报的图表说明、口径解释和风险提示。
7. Meeting Notes & Action Tracker：把会议录音、纪要和聊天记录整理成决议、负责人、截止时间和待追踪问题。
8. Executive Briefing Builder：把长材料压缩成管理层 briefing，包括背景、关键结论、影响、建议和下一步。
9. Humanizer-zh：优化中文商业表达，减少生硬的 AI 味，适合周报、调研结论、方案说明和邮件。
10. Citation & Evidence Guard：检查回答是否有来源、是否过度推断、是否混入无权限资料。
11. Cost-Aware Task Router：在高 token、长上下文、批量报告生成任务前提醒确认预算和数据等级。

第二组，按岗位或项目审批启用：

1. NotebookLM Skill：把授权资料整理成可追问的笔记本，适合专题研究、竞品梳理和材料复盘。
2. bb-browser：带登录态浏览器自动化，默认不全员启用，只给通过审批的岗位，用于内部系统取数或重复网页操作。
3. Playwright MCP：网页交互验证、流程截图和批量检查，只给维护者、数据运营或需要网页验证的研究人员。
4. Documents / Report Writer：生成 Word 型研究纪要、调研报告、访谈总结和项目复盘。
5. Presentations / Slide Brief Builder：把研究结论整理成汇报页结构和讲稿。
6. Spreadsheets：用于较复杂的数据清洗、透视表、公式校验和可复用分析模板。
7. Zotero / Source Manager：管理文献、报告来源和引用信息，适合行业研究、政策研究和技术研究岗位。
8. skill-creator：把稳定流程沉淀成可复用 skill，默认只给维护者和流程 owner。
9. find-skills：帮助维护者发现更合适的 skill，作为技能库治理入口。
10. office-hours：用于市场判断、业务假设和研究结论的结构化质询，不作为内容发布工具。

建议优先自研或定制的部门技能：

1. Industry Radar：按公开来源追踪行业政策、公司公告、竞品动态和关键人物观点，输出每日或每周 briefing。
2. Desk Research Composer：把多份授权材料合成为桌面研究草稿，并把每条结论绑定来源。
3. Insight Backlog Builder：把调研发现、未验证假设、证据强度和后续问题沉淀成可追踪 backlog。
4. Privacy Redactor：在员工上传材料前提示疑似敏感字段、个人信息和不应进入模型的内容。
5. Department Glossary Keeper：维护部门术语、项目代号、指标口径和常见问答，减少新课题启动成本。

默认不启用：

1. 未审批的浏览器登录态自动化。
2. Cookie 抓取。
3. 任意 shell 命令执行。
4. 全盘文件读取。
5. 未审批外部 MCP server。

## 运维节奏

每日：

1. 检查飞书回调成功率。
2. 检查 Router、Model Gateway、Hermes gateways 存活状态。
3. 检查 token 异常峰值。
4. 检查磁盘剩余和单人 quota。
5. 检查部门知识库索引队列和失败导入任务。
6. 处理失败任务。

每周：

1. 发布部门用量和案例周报。
2. 审核新增 skills 申请。
3. 清理过期上传文件。
4. 抽查输出是否符合数据规则。
5. 抽查部门知识库回答是否带引用、是否越权。
6. 更新岗位模板。

每月：

1. 复核 DeepSeek 模型、价格、上下文限制和弃用公告。
2. 复核 Hermes/OpenClaw 版本变化。
3. 做一次备份恢复演练。
4. 复盘 token 成本和实际产出。
5. 复核知识库模型路由、embedding/rerank 模型和索引质量。
6. 更新本文版本和生产截图。

Hermes Web Dashboard 可作为维护者排错入口，不作为普通员工入口。

![Hermes dashboard 文档截图：适合作为维护者排错界面，普通员工仍以飞书为主入口。](/assets/img/posts/feishu-lobster-deployment/hermes-dashboard.png)

## 参考资料

1. [Hermes Agent GitHub](https://github.com/NousResearch/hermes-agent)
2. [Hermes Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
3. [Hermes Web Dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard)
4. [OpenClaw GitHub](https://github.com/openclaw/openclaw)
5. [OpenClaw Gateway Security](https://docs.openclaw.ai/gateway/security)
6. [Apple 中国 Mac Studio：M4 Max 36GB/2TB](https://www.apple.com.cn/shop/buy-mac/mac-studio/m4-max-chip-14-core-cpu-32-core-gpu-36gb-memory-2tb-storage)
7. [Apple 中国 Mac Studio：M4 Max 64GB/4TB](https://www.apple.com.cn/shop/buy-mac/mac-studio/m4-max-chip-16-core-cpu-40-core-gpu-64gb-memory-4tb-storage)
8. [Apple 中国 Mac Studio：M3 Ultra 96GB/2TB](https://www.apple.com.cn/shop/buy-mac/mac-studio/m3-ultra-chip-28-core-cpu-60-core-gpu-96gb-memory-2tb-storage)
9. [Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B)
10. [Qwen3-30B-A3B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507)
11. [DeepSeek-R1-Distill-Qwen-32B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B)
12. [DeepSeek API Docs](https://api-docs.deepseek.com/)
13. [飞书开放平台发送消息 API](https://open.feishu.cn/document/server-docs/im-v1/message/create)
14. [飞书开放平台事件订阅](https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case)
15. [飞书开放平台机器人能力](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)
16. [飞书开放平台多维表格 API](https://open.feishu.cn/document/server-docs/docs/bitable-v1/bitable-overview)
17. [Microsoft 2025 Work Trend Index](https://www.microsoft.com/en-us/worklab/work-trend-index/2025-the-year-the-frontier-firm-is-born)
18. [McKinsey State of AI 2025](https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai)
19. [Nielsen Norman Group：Common UX Tasks Performed by UX Professionals with Generative AI](https://media.nngroup.com/media/articles/attachments/Common-Tasks_AI-in-UX.pdf)

## 修订记录

`v0.6.0`，2026-05-31：明确飞书部署工作台方案，重写企业研究分析 skills。

`v0.5.0`，2026-05-31：补充飞书接入联调、Excel 批量开通、知识库上传向导、用户飞书截图路径和技能库分层。

`v0.4.0`，2026-05-31：补充部门知识库、模型兜底方案、机器配置档位和悬浮目录。

`v0.3.0`，2026-05-31：扩展为部署手册和用户手册合一版本，加入机器配置费用、Hermes 部署流程、批量开通、飞书使用案例和图片放大交互。

`v0.2.0`，2026-05-31：调整为正式部署规划，补充员工服务包、飞书端流程、服务拓扑、权限策略和运维机制。

`v0.1.0`，2026-05-31：确定飞书主入口和一人一 Hermes profile/gateway 的方案方向。
