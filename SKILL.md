---
name: expert-skill
description: "企业专家知识蒸馏引擎——将领域专家的隐性知识（诊断直觉、设计启发、判断框架）凝练为可复用的 Expert Skill"
argument-hint: "[expert-name-or-slug]"
version: "1.0.0"
user-invocable: true
allowed-tools: Read, Write, Edit, Bash
---

> **Language**: 本 Skill 支持中文和英文。根据用户第一条消息的语言全程使用同一语言回复。

> **Execution Root**: 所有 `Bash` 命令都在当前 `SKILL.md` 所在目录执行。`tools/...` 和 `prompts/...` 均为相对于 skill 根目录的相对路径。

---

# 企业专家 Skill 创建器

## 触发条件

当用户说以下内容时启动：
- `/expert-skill`
- "帮我创建一个专家 skill"
- "我想蒸馏一个专家的知识"
- "把 XX 的专业知识做成 skill"
- "做一个 XX 专家的 skill"

## 核心理念

本 Skill 不做人格模拟，只蒸馏**专业知识**。

蒸馏的是一个专家的：
- 判断框架：他遇到问题时怎么想、怎么看、怎么查
- 决策模式：他做技术决策时优先考虑什么、红线在哪里
- 经验规则：他踩过的坑、验证过的结论、可复用的启发式
- 知识结构：按专长类型组织的方法论和操作流程

不蒸馏的是：
- 他的性格、MBTI、星座、脾气
- 他的沟通风格、话术习惯
- 他的人际行为

**产出的 Skill 会说："基于 XX 专家的方法论，你应该先检查 Y"，而不是模仿某个人的语气说话。**

---

## 专长类型

企业专家的专业能力分为工程与医疗两组类型。医疗类型是独立的一等类型，不映射为工程类型。

用户不需要提前选择或导入专家模板。先收集专家描述和材料，再生成专家能力蓝图；如果蓝图与内置类型高度匹配，则复用对应类型；否则使用 `custom` 通用专家结构。

| 类型 | 标识 | 知识形态 | 典型产出 |
|------|------|---------|---------|
| 诊断专家 | `troubleshooter` | 决策树 | 故障模式库、诊断路径、嗅觉检查项 |
| 架构专家 | `architect` | 设计原则 | 设计哲学、技术选型矩阵、反模式清单 |
| 审核专家 | `reviewer` | 检查清单 | 缺陷模式库、Review 检查项、风险等级 |
| 决策专家 | `decision_maker` | 决策框架 | 评估维度、风险评估、优先级方法 |
| 运维专家 | `operator` | Runbook | 监控指标、SOP、升级规则 |
| 临床照护管理专家 | `clinical_care_manager` | 临床照护框架 | 关键指标、风险分层、干预路径、升级医生规则 |
| 照护运营专家 | `care_operation_specialist` | 照护运营 Runbook | 随访 SOP、患者教育、依从性管理、任务升级 |
| 医疗安全审核专家 | `medical_safety_reviewer` | 医疗安全清单 | 红旗症状、用药风险、禁忌建议、转诊/急诊边界 |
| 通用蓝图专家 | `custom` | 蓝图驱动 | 未知领域、低匹配度类型、跨领域专家 |

---

## 生成模式

本 Skill 支持两种生成模式，用户确认 Step 1 后选择：

| 模式 | 适用场景 | 产出差异 |
|------|---------|---------|
| **standard**（标准） | 快速蒸馏，材料充足 | expertise.md / heuristics.json / knowledge_graph.md |
| **discovery**（发现） | 深度挖掘，需要访谈 | 以上 + latent_report.md / interview_transcript.md + 隐性知识增强 |

选择 standard 模式 → 按现有主流程 Step 1-5 进行。
选择 discovery 模式 → 先完成 standard Step 1-5，再按下方 discovery 流程补充。

---

## 主流程

### Step 1: 基础信息录入

使用 `prompts/intake.md` 引导用户录入：

1. **专家称呼**（必填）
2. **基本信息**：公司、职级、职位、专业领域（一句话，可跳过）
3. **专长类型**：可跳过；后续专家能力蓝图会推断内置类型或回退到 `custom`
4. **专业描述**：他擅长什么、判断框架是什么、什么时候别人会想到他（2-3 句话，可选但推荐）

收集完后汇总确认。

### Step 2: 原材料导入

```
原材料怎么提供？

  [A] 飞书自动采集（推荐）
  [B] 钉钉自动采集
  [C] 飞书链接
  [D] 上传文件（PDF / 图片 / 飞书导出 JSON / 邮件 .eml）
  [E] 直接粘贴内容

可以混用，也可以跳过（仅凭手动信息生成）。
```

具体操作方式与 dot-skill 兼容：飞书采集、钉钉采集、文件解析等工具均可用。

#### 方式 A：飞书自动采集

```bash
# 首次配置
python3 tools/feishu_auto_collector.py --setup

# 群聊采集
python3 tools/feishu_auto_collector.py \
  --name "{name}" \
  --output-dir ./knowledge/{slug} \
  --msg-limit 1000 \
  --doc-limit 20

# 私聊采集（需 user_access_token + chat_id）
python3 tools/feishu_auto_collector.py \
  --open-id {open_id} \
  --p2p-chat-id {chat_id} \
  --user-token {user_access_token} \
  --name "{name}" \
  --output-dir ./knowledge/{slug} \
  --msg-limit 1000
```

#### 方式 B：钉钉自动采集

```bash
python3 tools/dingtalk_auto_collector.py \
  --name "{name}" \
  --output-dir ./knowledge/{slug} \
  --msg-limit 500 \
  --doc-limit 20
```

#### 方式 C：飞书链接

```bash
# 浏览器方案
python3 tools/feishu_browser.py --url "{url}" --target "{name}" --output /tmp/feishu_doc.txt

# MCP 方案
python3 tools/feishu_mcp_client.py --url "{url}" --output /tmp/feishu_doc.txt
```

#### 方式 D：上传文件

- PDF / 图片 → `Read` 工具直接读取
- 飞书消息 JSON 导出 → `python3 tools/feishu_parser.py --file {path} --target "{name}"`
- 邮件 .eml → `python3 tools/email_parser.py --file {path} --target "{name}"`

#### 方式 E：直接粘贴

用户粘贴的内容直接作为原材料。

如果用户跳过原材料，仅凭 Step 1 的手动信息生成。

### Step 3: 分析原材料

根据专长类型加载对应 prompt：

| 专长类型 | Intake | Analyzer | Builder |
|---------|--------|----------|---------|
| troubleshooter | `prompts/expertise/troubleshooter/intake.md` | `prompts/expertise/troubleshooter/analyzer.md` | `prompts/expertise/troubleshooter/builder.md` |
| architect | `prompts/expertise/architect/intake.md` | `prompts/expertise/architect/analyzer.md` | `prompts/expertise/architect/builder.md` |
| reviewer | `prompts/expertise/reviewer/intake.md` | `prompts/expertise/reviewer/analyzer.md` | `prompts/expertise/reviewer/builder.md` |
| decision_maker | `prompts/expertise/decision_maker/intake.md` | `prompts/expertise/decision_maker/analyzer.md` | `prompts/expertise/decision_maker/builder.md` |
| operator | `prompts/expertise/operator/intake.md` | `prompts/expertise/operator/analyzer.md` | `prompts/expertise/operator/builder.md` |
| clinical_care_manager | `prompts/expertise/medical/clinical_care_manager/intake.md` | `prompts/expertise/medical/clinical_care_manager/analyzer.md` | `prompts/expertise/medical/clinical_care_manager/builder.md` |
| care_operation_specialist | `prompts/expertise/medical/care_operation_specialist/intake.md` | `prompts/expertise/medical/care_operation_specialist/analyzer.md` | `prompts/expertise/medical/care_operation_specialist/builder.md` |
| medical_safety_reviewer | `prompts/expertise/medical/medical_safety_reviewer/intake.md` | `prompts/expertise/medical/medical_safety_reviewer/analyzer.md` | `prompts/expertise/medical/medical_safety_reviewer/builder.md` |

**分析流程：**

1. 读取专长类型对应的 intake.md，追问专业方法论、核心工具、经典案例
2. 使用通用的 `prompts/expertise_analyzer.md` 做初步提取
3. 使用专长类型对应的 analyzer.md 做类型专项提取
4. 整合两份分析结果，生成结构化的专业知识摘要

**分析摘要包含：**
- 专业领域与职责边界
- 判断框架与核心启发式
- 决策模式与技术红线
- 按专长类型组织的方法论结构
- 经验知识库

### Step 4: 生成并预览

使用 `prompts/expertise_builder.md` + 专长类型的 builder.md 生成专业知识内容。

向用户展示摘要（5-8 行）：

```
专家知识摘要：
  - 专长类型：{type}
  - 专业领域：{domain}
  - 核心判断框架：{key heuristics}
  - 技术红线：{red lines}
  - 经验规则数：{N} 条
  ...

确认生成？还是需要调整？
```

### Step 5: 写入文件

用户确认后：

1. 将专业知识内容写入 `/tmp/expert_{slug}_expertise.md`
2. 准备 meta.json 写入 `/tmp/expert_{slug}_meta.json`
3. 调用 writer：

```bash
python3 tools/skill_writer.py \
  --action create \
  --slug {slug} \
  --name "{name}" \
  --expertise-type {type} \
  --expertise-content /tmp/expert_{slug}_expertise.md \
  --meta /tmp/expert_{slug}_meta.json \
  --domain-summary "{domain_summary}" \
  --base-dir ./skills/expert
```

生成的文件结构：

```
skills/expert/{slug}/
  ├── SKILL.md             # 完整 Skill（可直接运行）
  ├── expertise.md          # 专业知识文档
  ├── knowledge_graph.md    # 知识图谱（结构化的知识关联）
  ├── heuristics.json       # 启发式规则（程序化使用）
  ├── meta.json             # 元数据
  ├── manifest.json         # 安装/分发清单
  └── versions/             # 历史版本
```

如需安装到 Claude Code：
```bash
python3 tools/skill_writer.py ... --install-claude-skill
```

---

## 进化模式：追加材料

用户提供新文件时：

1. 按 Step 2 方法读取新内容
2. 用 `Read` 读取现有 `skills/expert/{slug}/expertise.md`
3. 归档当前版本：
   ```bash
   python3 tools/version_manager.py --action backup --slug {slug} --base-dir ./skills/expert
   ```
4. 分析增量内容，合并到专业知识中
5. 写入更新后的 expertise.md 并重建 SKILL.md：
   ```bash
   python3 tools/skill_writer.py \
     --action update \
     --slug {slug} \
     --expertise-content /tmp/expert_{slug}_expertise_updated.md \
     --base-dir ./skills/expert
   ```

---

## Discovery 模式：隐性知识挖掘增强

在 standard 模式生成的 Skill 基础上，通过结构化访谈挖掘专家的隐性知识。

### P2：前置研究

组装专家画像 prompt，由 AI 推断已知决策模式和疑似知识盲区：

```bash
python3 tools/pre_researcher.py \
  --slug {slug} \
  --name "{expert_name}" \
  --expertise-type troubleshooter \
  --base-dir ./skills/expert \
  [--title "{title}"] \
  [--domain "{domain}"] \
  [--years "{years}"] \
  [--expertise-description "{description}"] \
  [--domain-background "{background}"] \
  [--materials ./knowledge/{slug}/file1.md ./knowledge/{slug}/file2.md] \
  [--open-research ./knowledge/{slug}/open_research.md]
```

AI 分析完成后，保存输出到文件，解析并写入：
```bash
python3 tools/pre_researcher.py \
  --slug {slug} \
  --name "{expert_name}" \
  --expertise-type troubleshooter \
  --base-dir ./skills/expert \
  --parse-output /tmp/{slug}_expert_profile.json
```

注意：`pre_researcher.py` 当前没有 `--materials-dir` 参数；如需导入原材料，必须用 `--materials` 显式传入一个或多个文件路径。

### P2.5：专家能力蓝图

基于专家画像和用户描述，推断专家知识形态、内置类型匹配度和生成策略：

```bash
python3 tools/blueprint_builder.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --user-description "{description}"
```

AI 分析完成后，保存输出到文件，解析并写入：
```bash
python3 tools/blueprint_builder.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --parse-output /tmp/{slug}_expert_blueprint.json
```

成功后会得到 `discovery/expert_blueprint.json`，并把 `meta.discovery.status` 更新为 `blueprint_ready`。如果匹配度不足，后续 P7 会使用 `custom` 通用专家蓝图生成。

### P3：隐性变量候选

基于专家画像和专家能力蓝图，推断可能存在的隐性变量候选：

```bash
python3 tools/latent_variable_builder.py \
  --slug {slug} \
  --base-dir ./skills/expert

# 解析 AI 输出：
python3 tools/latent_variable_builder.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --parse-output /tmp/{slug}_latent_vars.json
```

### P4：三联体问题生成

为高优先级候选生成 A/B/C 三联体访谈问题：

```bash
python3 tools/triplet_generator.py \
  --slug {slug} \
  --base-dir ./skills/expert

# 解析 AI 输出：
python3 tools/triplet_generator.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --parse-output /tmp/{slug}_triplets.json
```

### P5：实时访谈记录

按 A→B→C 协议进行结构化访谈并记录。P5 开始前，agent 必须询问用户是否开启摄像头辅助；默认不启用摄像头，只有用户明确同意后，才可以调用本机摄像头。

必须使用以下同意文本：

```text
P5 访谈可以选择开启摄像头辅助。开启后，访谈过程中会调用本机摄像头，在专家回答期间定时采集临时帧，并由当前 agent 的多模态模型分析非语言信号，用于提示可能的追问。临时图片只用于实时分析，不保存到 skill 目录或 transcript。是否开启？
```

默认访谈命令：

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert
```

开启摄像头辅助：

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --camera-assist
```

开启摄像头辅助并使用流式回答输入：

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --camera-assist \
  --answer-input stream
```

摄像头辅助只生成候选追问信号；`signals_observed` 仍然只记录已确认信号，P6 不能仅依据摄像头建议生成隐性知识发现。

```bash
# 中断后恢复：
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --resume

# 仅完成特定三联体：
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --triplet-id tg_001
```

### P6：访谈分析

由 AI 分析访谈记录，提取隐性知识发现：

```bash
python3 tools/interview_analyzer.py \
  --slug {slug} \
  --base-dir ./skills/expert

# 解析 AI 分析输出：
python3 tools/interview_analyzer.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --parse-output /tmp/{slug}_analysis.json
```

### P7：融合写入

将隐性知识融合到 Skill 产物中：

```bash
# 先备份当前版本
python3 tools/version_manager.py \
  --action backup \
  --slug {slug} \
  --base-dir ./skills/expert

# 融合写入（增强已有 Skill）
python3 tools/skill_writer.py \
  --action update \
  --slug {slug} \
  --base-dir ./skills/expert \
  --latent-report ./skills/expert/{slug}/discovery/latent_report.md \
  --interview-transcript ./skills/expert/{slug}/discovery/interview_transcript.md \
  --blueprint ./skills/expert/{slug}/discovery/expert_blueprint.json \
  --discovery-meta ./skills/expert/{slug}/discovery/interview_analysis.json
```

### 跳过访谈（可选）

如果不需要访谈，不能直接把 P3 的 `latent_variables.json` 传给 P7。当前 `skill_writer.py --discovery-meta` 读取的是 P6 `interview_analysis.json` 结构（`triplet_analyses` + `cross_analysis`），用于生成 `heuristics.json` 的 `latent_variables`、`priority_rules`、`boundary_conditions` 三类增强字段。

因此 V1 的安全路径是：

1. 若要融合隐性知识增强，必须先完成 P5/P6，或人工整理一个符合 P6 schema 的 `interview_analysis.json`。
2. 若只想保留 P2-P4 产物，不执行 P7；这些文件留在 `{slug}/discovery/` 中作为候选池和访谈设计草稿。
3. 后续若实现 `latent_variables.json → discovery_meta` 的转换器，再补充免访谈融合命令。

免访谈融合不属于当前 Step 8 的实现范围；不要在 smoke test 中断言 P3 数据可直接写入 P7 latent 字段。

---

## Discovery 中断恢复策略

每个 Phase 完成后 `meta.json` 中的 `discovery.status` 会自动更新。中途中断时：

| discovery.status | 含义 | 重新启动点 |
|-----------------|------|---------|
| `not_started` | 尚未开始 | 从 P2 开始 |
| `profile_ready` | P2 完成 | 从 P2.5 开始 |
| `blueprint_ready` | P2.5 完成 | 从 P3 开始 |
| `variables_ready` | P3 完成 | 从 P4 开始 |
| `triplets_ready` | P4 完成 | 从 P5 开始 |
| `interview_in_progress` | P5 进行中 | `--resume` 从中断点继续 |
| `interview_completed` | P5 完成，访谈记录已生成 | 从 P6 开始 |
| `analysis_ready` | P6 完成 | 从 P7 开始 |
| `merged` | P7 完成 | discovery 已归档 |
| `aborted` | discovery 被放弃 | 清理 `{slug}/discovery/` 或保留备查 |

**清理未合并产物**：若放弃当前 discovery，直接删除 `{slug}/discovery/` 目录即可。

**回滚已合并产物**：若 P7 已写入，必须通过 version_manager 回滚：
```bash
python3 tools/version_manager.py \
  --action rollback \
  --slug {slug} \
  --version v{N-1} \
  --base-dir ./skills/expert
```

注意：当前 `skill_writer.py` 在写入 discovery 增强后会启用 `meta.discovery.enabled=True`，但不会自动把 `discovery.status` 改为 `merged`。若需要归档状态，P7 完成后由流程控制代码或测试手动将状态设为 `merged`，并验证该值存在于 `DISCOVERY_STATUSES`。

---

## 管理操作

列出所有专家 Skill：
```bash
python3 tools/skill_writer.py --action list --base-dir ./skills/expert
```

列出可用专长类型：
```bash
python3 tools/skill_writer.py --list-types
```

回滚版本：
```bash
python3 tools/version_manager.py --action rollback --slug {slug} --version v2 --base-dir ./skills/expert
```

删除专家 Skill：
```bash
rm -rf skills/expert/{slug}
```
