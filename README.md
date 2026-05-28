# Enterprise Expert Skill (企业专家 Skill)

把企业专家的显性知识和隐性判断框架整理成可复用的 LLM Skill。

这个项目不做人格模仿，重点是把专家在真实工作里使用的判断逻辑沉淀下来，例如：

- 遇到故障时先看什么、后看什么
- 什么时候该止血，什么时候该等
- 哪些阈值、例外、边界条件是文档里没写但实际天天在用的

项目支持两条路径：

- `standard`：快速蒸馏显性知识，生成基础 Skill
- `discovery`：在基础 Skill 上继续做前置研究、三联体访谈和分析，补出隐性知识

## 项目定位

和 `dot-skill` 相比，这个仓库更像“专家方法论提炼器”，而不是“人格/语气模拟器”。

| 维度 | dot-skill | expert-skill |
|------|-----------|--------------|
| 蒸馏目标 | Persona + Work Skill | 专业知识和判断框架 |
| 关注点 | 这个人怎么说话、怎么做事 | 这个领域应该怎么判断和行动 |
| 角色类型 | colleague / relationship / celebrity | troubleshooter / architect / reviewer / decision_maker / operator |
| 是否模拟人格 | 是 | 否 |
| 核心产物 | `SKILL.md` | `SKILL.md` / `expertise.md` / `heuristics.json` / `knowledge_graph.md` |

## 仓库到底做什么

这套工具链本质上是：

1. 读取原材料和已有中间产物
2. 组装 prompt
3. 校验并解析模型输出
4. 把结果写成结构化文件和最终 Skill 产物

它默认不直接调用云端模型。

也就是说，P2 / P3 / P4 / P6 的典型用法是：

1. 运行脚本，生成 prompt 文件
2. 把 prompt 粘到 Claude / ChatGPT / 你自己的模型里
3. 把模型回复保存成 `json` 或 `yaml`
4. 再次运行同一个脚本，用 `--parse-output` 把回复落盘

P5 访谈记录阶段则是本地交互式工具，不需要模型参与。

## 适合什么专家

项目内置工程与医疗两组专长类型。工程类型用于技术组织里的诊断、架构、审核、决策和运维；医疗类型用于慢病管理、照护运营和医疗安全审核。

内置类型现在只是加速器，不再是创建专家的前置条件。创建流程可以先生成 `discovery/expert_blueprint.json`，根据材料判断是否匹配已有类型；匹配度不足时会使用 `custom` 通用专家蓝图继续生成。

| 类型 | 标识 | 知识形态 | 适用场景 |
|------|------|----------|----------|
| 诊断专家 | `troubleshooter` | 决策树 | 故障排查、性能诊断 |
| 架构专家 | `architect` | 设计原则 | 系统设计、技术评审 |
| 审核专家 | `reviewer` | 检查清单 | Code Review、方案审查 |
| 决策专家 | `decision_maker` | 决策框架 | 技术决策、资源分配 |
| 运维专家 | `operator` | Runbook | 运维保障、应急响应 |
| 临床照护管理专家 | `clinical_care_manager` | 临床照护框架 | 慢病指标判断、风险分层、干预路径、升级医生规则 |
| 照护运营专家 | `care_operation_specialist` | 照护运营 Runbook | 随访 SOP、饮食运动干预、患者教育、依从性管理 |
| 医疗安全审核专家 | `medical_safety_reviewer` | 医疗安全清单 | 红旗症状、用药风险、禁忌建议、转诊/急诊边界 |
| 通用蓝图专家 | `custom` | 蓝图驱动 | 未知领域、低匹配度类型、跨领域专家 |

## 输出产物

### Standard 模式

- `SKILL.md`：最终可被 LLM 直接使用的 Skill
- `expertise.md`：专家知识正文
- `heuristics.json`：结构化规则，适合程序消费
- `knowledge_graph.md`：知识图谱和关系摘要
- `meta.json`：元数据、状态、版本
- `manifest.json`：分发清单

### Discovery 模式额外增加

- `discovery/expert_profile.json`：P2 专家画像
- `discovery/expert_blueprint.json`：P2.5 专家能力蓝图，用于推断知识形态、类型匹配和 custom/generic 生成策略
- `discovery/latent_variables.json`：P3 隐性变量候选
- `discovery/triplet_groups.json`：P4 三联体问题
- `discovery/interview_script.md`：P4 访谈脚本草稿
- `discovery/interview_transcript.json` / `.md`：P5 访谈记录
- `discovery/interview_analysis.json`：P6 结构化分析
- `discovery/latent_findings.json`：P6 提取出的发现列表
- `discovery/latent_report.md`：P6 面向人阅读的分析报告

P7 融合后，`expertise.md` / `heuristics.json` / `knowledge_graph.md` 会被增强。

## 环境准备

下面所有命令都默认在仓库根目录执行。

```text
expert-skill/
```

建议环境：

- Python 3.10+
- `pytest`：运行测试时需要
- `PyYAML`：如果你希望把模型输出保存成 YAML，再让脚本解析，则需要

可选安装：

```bash
pip install pytest pyyaml
```

如果你只保存 JSON 输出，可以不安装 `PyYAML`。

建议自己准备一个临时目录，例如：

```text
./tmp/
```

文档里所有 `./tmp/...` 都只是示例路径，你换成任何本地路径都可以。

## 最快开始

### 路径 A：在 Claude / Codex / ChatGPT 里用 Skill 编排

如果你希望让一个智能体带着你走完整流程，使用仓库根目录的 [SKILL.md](./SKILL.md)。

触发词：

```text
/expert-skill
```

适合你已经在 Claude Code、Codex 或支持 Skill 的环境里工作，希望它代你：

- 追问专家背景
- 整理材料
- 决定走 `standard` 还是 `discovery`
- 组装每一步 prompt
- 执行写文件和状态更新

### 路径 B：纯 CLI 手动跑

如果你希望完全自己掌控每一步，就直接用 `tools/*.py`。

这条路尤其适合：

- 你要接自己的模型
- 你要把每一步 prompt 单独保存和复核
- 你要做可审计、可重跑的 discovery 过程

## Standard 模式：最短上手

`standard` 的输入是“已经整理好的专家知识正文”。

也就是说，仓库不会替你凭空写出 `expertise.md`；你通常会先用人工或模型把原材料整理成一份专业知识稿，再交给 `skill_writer.py` 生成正式产物。

### 第 1 步：准备一份专家知识正文

例如保存为：

```text
./tmp/expert_demo_expertise.md
```

### 第 2 步：创建基础 Skill

```bash
python tools/skill_writer.py \
  --action create \
  --slug demo-expert \
  --name "Demo Expert" \
  --expertise-type troubleshooter \
  --base-dir ./skills/expert \
  --expertise-content ./tmp/expert_demo_expertise.md \
  --domain-summary "分布式系统故障排查"
```

生成后目录大致是：

```text
skills/expert/demo-expert/
├── SKILL.md
├── expertise.md
├── heuristics.json
├── knowledge_graph.md
├── meta.json
├── manifest.json
└── versions/
```

### 第 3 步：查看或继续更新

列出已生成专家：

```bash
python tools/skill_writer.py --action list --base-dir ./skills/expert
```

用新增材料迭代：

```bash
python tools/version_manager.py --action backup --slug demo-expert --base-dir ./skills/expert

python tools/skill_writer.py \
  --action update \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --expertise-content ./tmp/expert_demo_expertise_v2.md
```

## Discovery 模式：完整隐性知识挖掘流程

### 先决条件

跑 discovery 前，建议你已经有一个基础 Skill，也就是已经完成 `standard` 产物。

目录会长这样：

```text
skills/expert/{slug}/
```

Discovery 中间产物会写到：

```text
skills/expert/{slug}/discovery/
```

### 一条很重要的操作规律

P2 / P3 / P4 / P6 基本都遵循同一个模式：

1. 先运行脚本，不带 `--parse-output`
2. 脚本会在 `discovery/` 下写 prompt 文件
3. 把 prompt 交给模型，让模型返回 JSON 或 YAML
4. 把模型原始输出保存到本地文件
5. 再运行同一个脚本，加 `--parse-output` 完成校验和落盘

你也可以用 `--dry-run` 只把 prompt 打到终端，不写任何文件。

注意：

- `--dry-run` 和 `--parse-output` 互斥
- 若保存的是 YAML，需要本地安装 `PyYAML`

### P2：前置研究

作用：

- 从已有材料中抽出可见知识、已知决策、领域冲突
- 最重要的是产出 `suspected_gaps`

#### 1. 生成 prompt

```bash
python tools/pre_researcher.py \
  --slug demo-expert \
  --name "Demo Expert" \
  --expertise-type troubleshooter \
  --title "分布式系统工程师" \
  --domain "分布式系统故障排查" \
  --years "8" \
  --expertise-description "擅长高压线上故障止血与容量判断" \
  --materials ./knowledge/demo/notes.md ./knowledge/demo/chat.json \
  --open-research ./knowledge/demo/open_research.md \
  --base-dir ./skills/expert
```

会生成：

```text
skills/expert/demo-expert/discovery/pre_research_prompt.md
```

注意：`pre_researcher.py` 没有 `--materials-dir` 参数，材料必须用 `--materials` 显式传文件列表。

#### 2. 保存模型输出并解析

```bash
python tools/pre_researcher.py \
  --slug demo-expert \
  --name "Demo Expert" \
  --expertise-type troubleshooter \
  --title "分布式系统工程师" \
  --domain "分布式系统故障排查" \
  --years "8" \
  --materials ./knowledge/demo/notes.md ./knowledge/demo/chat.json \
  --base-dir ./skills/expert \
  --parse-output ./tmp/demo_expert_profile.json
```

成功后会得到：

- `discovery/expert_profile.json`
- `meta.discovery.status = profile_ready`

### P2.5：专家能力蓝图

作用：

- 从 P2 专家画像和原始描述中推断专家的知识形态
- 判断是否高置信匹配内置类型
- 低匹配度或未知领域自动走 `custom` / `generic` 生成策略

#### 1. 生成 prompt

```bash
python tools/blueprint_builder.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --user-description "擅长高压线上故障止血与容量判断"
```

会生成：

```text
skills/expert/demo-expert/discovery/expert_blueprint_prompt.md
```

#### 2. 保存模型输出并解析

```bash
python tools/blueprint_builder.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --parse-output ./tmp/expert_blueprint_output.json
```

成功后会得到：

- `discovery/expert_blueprint.json`
- `meta.discovery.status = blueprint_ready`

### P3：隐性变量候选

作用：

- 把 P2 的“缺口”和 P2.5 的蓝图目标改写成“可测试的假设”

#### 1. 生成 prompt

```bash
python tools/latent_variable_builder.py \
  --slug demo-expert \
  --base-dir ./skills/expert
```

会生成：

```text
skills/expert/demo-expert/discovery/latent_variable_prompt.md
```

#### 2. 解析模型输出

```bash
python tools/latent_variable_builder.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --parse-output ./tmp/demo_latent_variables.json
```

成功后会得到：

- `discovery/latent_variables.json`
- `meta.discovery.status = variables_ready`

### P4：三联体问题生成

作用：

- 围绕高价值隐性变量设计 A/B/C 三联体
- A 建基线，B 改一个变量，C 叠加冲突

#### 1. 生成 prompt

默认会挑 `testability` 为 `high/medium` 的候选：

```bash
python tools/triplet_generator.py \
  --slug demo-expert \
  --base-dir ./skills/expert
```

如果你只想为部分变量生成：

```bash
python tools/triplet_generator.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --target-ids lv_002 lv_005 lv_003
```

会生成：

```text
skills/expert/demo-expert/discovery/triplet_builder_prompt.md
```

#### 2. 解析模型输出

```bash
python tools/triplet_generator.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --target-ids lv_002 lv_005 lv_003 \
  --parse-output ./tmp/demo_triplets.json
```

成功后会得到：

- `discovery/triplet_groups.json`
- `discovery/interview_script.md`
- `meta.discovery.status = triplets_ready`

### P5：访谈记录

作用：

- 按 A/B/C 脚本记录真实访谈
- 持久化问题、回答、追问、信号和备注

#### 1. 先看脚本，不进入交互

```bash
python tools/interview_session.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --dry-run
```

#### 2. 正式访谈

```bash
python tools/interview_session.py \
  --slug demo-expert \
  --base-dir ./skills/expert
```

摄像头辅助是可选能力，默认关闭。只有用户明确同意后，agent 才能使用：

```bash
python tools/interview_session.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --camera-assist
```

摄像头临时帧只用于当前 agent 的多模态分析，不写入 transcript；最终记录只保存结构化文字建议。

#### 3. 只完成某一个三联体

```bash
python tools/interview_session.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --triplet-id tg_001
```

#### 4. 从中断点恢复

```bash
python tools/interview_session.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --resume
```

注意：`--triplet-id` 和 `--resume` 不能同时使用。

成功后会得到：

- `discovery/interview_transcript.json`
- `discovery/interview_transcript.md`
- 完整通过质量门时：`meta.discovery.status = interview_completed`

### P6：访谈分析

作用：

- 从 transcript 中提取确认变量、优先级关系、边界条件、疑似偏差和未解问题

#### 1. 生成 prompt

```bash
python tools/interview_analyzer.py \
  --slug demo-expert \
  --base-dir ./skills/expert
```

会生成：

```text
skills/expert/demo-expert/discovery/interview_analyzer_prompt.md
```

#### 2. 解析模型输出

```bash
python tools/interview_analyzer.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --parse-output ./tmp/demo_interview_analysis.json
```

成功后会得到：

- `discovery/interview_analysis.json`
- `discovery/latent_findings.json`
- `discovery/latent_report.md`
- `meta.discovery.status = analysis_ready`

### P7：融合写入正式 Skill

作用：

- 把 discovery 结果写回 `expertise.md` / `heuristics.json` / `knowledge_graph.md`

#### 1. 先备份

```bash
python tools/version_manager.py \
  --action backup \
  --slug demo-expert \
  --base-dir ./skills/expert
```

#### 2. 执行融合

```bash
python tools/skill_writer.py \
  --action update \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --latent-report ./skills/expert/demo-expert/discovery/latent_report.md \
  --interview-transcript ./skills/expert/demo-expert/discovery/interview_transcript.md \
  --blueprint ./skills/expert/demo-expert/discovery/expert_blueprint.json \
  --discovery-meta ./skills/expert/demo-expert/discovery/interview_analysis.json
```

融合后：

- `expertise.md` 会追加 `## 隐性知识增强`
- `heuristics.json` 会新增 `latent_variables` / `priority_rules` / `boundary_conditions`
- `knowledge_graph.md` 会写入隐性变量、规则冲突和边界条件
- `manifest.json` 会把真正存在的 discovery 产物列入 artifacts

注意：`skill_writer.py` 会写 discovery 相关字段和文件，但不会替你在所有场景下自动推进 `meta.discovery.status = merged`。如果你的编排层需要严格状态流转，请在 P7 完成后自行归档该状态。

## 一条完整的 discovery 最小闭环

如果你已经有一份基础 Skill，完整手动链路通常是：

```bash
python tools/pre_researcher.py ...
python tools/pre_researcher.py ... --parse-output ./tmp/p2.json

python tools/blueprint_builder.py ...
python tools/blueprint_builder.py ... --parse-output ./tmp/p25.json

python tools/latent_variable_builder.py ...
python tools/latent_variable_builder.py ... --parse-output ./tmp/p3.json

python tools/triplet_generator.py ...
python tools/triplet_generator.py ... --parse-output ./tmp/p4.json

python tools/interview_session.py ...

python tools/interview_analyzer.py ...
python tools/interview_analyzer.py ... --parse-output ./tmp/p6.json

python tools/version_manager.py --action backup ...
python tools/skill_writer.py --action update ...
```

## Discovery 状态机

`meta.json` 中的 `discovery.status` 用于恢复流程。

| status | 含义 | 从哪一步继续 |
|--------|------|--------------|
| `not_started` | 尚未开始 | P2 |
| `profile_ready` | P2 完成 | P2.5 |
| `blueprint_ready` | P2.5 完成 | P3 |
| `variables_ready` | P3 完成 | P4 |
| `triplets_ready` | P4 完成 | P5 |
| `interview_in_progress` | P5 进行中 | `interview_session.py --resume` |
| `interview_completed` | P5 完成 | P6 |
| `analysis_ready` | P6 完成 | P7 |
| `merged` | P7 已归档完成 | discovery 结束 |
| `aborted` | 本轮放弃 | 清理或保留中间产物 |

## 版本管理

查看版本：

```bash
python tools/version_manager.py --action list --slug demo-expert --base-dir ./skills/expert
```

备份当前版本：

```bash
python tools/version_manager.py --action backup --slug demo-expert --base-dir ./skills/expert
```

回滚：

```bash
python tools/version_manager.py --action rollback --slug demo-expert --version v2 --base-dir ./skills/expert
```

如果只是放弃一轮尚未融合的 discovery，可以删除：

```text
skills/expert/{slug}/discovery/
```

如果已经执行过 P7，不要手工删正式产物，应该用 `rollback`。

## Mock 端到端验证

仓库自带 `mock_expert/`，适合做 smoke test，不依赖联网和真实访谈。

```bash
python -m pytest tools/test_e2e_mock.py -v --basetemp .\.pytest_tmp_e2e
```

mock 目录内容：

```text
mock_expert/
├── meta.json
└── discovery/
    ├── expert_profile.json
    ├── latent_variables.json
    ├── triplet_groups.json
    ├── interview_transcript.json
    ├── interview_transcript.md
    ├── interview_analysis.json
    ├── latent_findings.json
    └── latent_report.md
```

如果你只是想确认仓库逻辑是通的，先跑它最省心。

## 测试

全量测试：

```bash
python -m pytest tools/ -q --basetemp .\.pytest_tmp
```

Windows 下推荐显式加 `--basetemp`，避免系统临时目录权限或残留问题。

## 常见坑

### 1. 脚本不会自动调用模型

P2 / P3 / P4 / P6 默认只负责生成 prompt 和解析结果。

### 2. `pre_researcher.py` 没有 `--materials-dir`

材料必须这样传：

```bash
--materials file1.md file2.json file3.txt
```

### 3. P7 不能直接吃 P3 的 `latent_variables.json`

下面这种做法当前不支持：

```text
latent_variables.json -> skill_writer.py --discovery-meta
```

`--discovery-meta` 需要的是 P6 产物，也就是 `interview_analysis.json`。

### 4. `--dry-run` 和 `--parse-output` 互斥

这些脚本都一样：

- `pre_researcher.py`
- `latent_variable_builder.py`
- `triplet_generator.py`
- `interview_analyzer.py`

### 5. YAML 解析依赖 `PyYAML`

如果你的模型输出不是 JSON，而是 YAML，本地需要：

```bash
pip install pyyaml
```

### 6. `triplet_generator.py` 默认不会为所有候选生成三联体

它默认只挑 `testability` 为 `high/medium` 的变量。想强行指定，就用 `--target-ids`。

### 7. `interview_session.py` 是记录工具，不是模拟器

它负责交互式提问、追问、落盘和恢复。  
如果你要“模拟专家回答”，通常是在 AI 客户端里做，再把内容整理进 transcript。

## 项目结构

```text
expert-skill/
├── SKILL.md
├── README.md
├── docs/
├── prompts/
│   ├── intake.md
│   ├── expertise_analyzer.md
│   ├── expertise_builder.md
│   ├── expertise/
│   └── discovery/
├── tools/
│   ├── skill_writer.py
│   ├── version_manager.py
│   ├── pre_researcher.py
│   ├── latent_variable_builder.py
│   ├── triplet_generator.py
│   ├── interview_session.py
│   ├── interview_analyzer.py
│   └── test_*.py
├── mock_expert/
└── skills/
    └── expert/
        └── {slug}/
```

## V1 边界

当前版本已经实现了标准化 discovery 链路和本地 mock 验证，但还没有：

- 自动开放搜索
- 图形化访谈 UI
- 多专家交叉验证
- `latent_variables.json -> discovery_meta` 的直接转换
- 从 `merged` 自动触发第二轮 discovery
