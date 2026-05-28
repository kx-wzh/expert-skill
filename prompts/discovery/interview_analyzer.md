# P6 访谈分析 Prompt

## 任务描述

你正在对一次专家访谈记录进行系统性分析。你的目标**不是**总结专家说了什么，而是从访谈行为——包括迟疑、边界发明、矛盾、模糊用词等信号——中提取专家自己都未意识到的判断模式和决策规则。

每个三联体（A→B→C）是一个设计好的探针：A 建立基准，B 引入隐性变量，C 叠加冲突。你需要逐三联体分析专家在各层的反应，再跨三联体做一致性综合。

---

## 输入

### 专家基本信息
{name}（{expertise_type}）

### 三联体问题组
```json
{triplet_groups_json}
```

### 访谈记录
```json
{interview_transcript_json}
```

### 摄像头辅助建议

访谈记录中可能包含 `camera_suggestions`。这些字段来自可选摄像头辅助，只能作为追问触发线索或分析注意力提示。

你可以说明某个追问是由摄像头辅助建议触发的，但不能仅凭摄像头建议生成隐性知识发现。每个 `latent_findings[*].evidence.expert_quote` 必须引用专家原话、追问回答或 A/B/C 决策行为，不能写成 `camera_suggestion`、`摄像头建议` 或其他非专家原话。

---

## 单三联体分析要求

对每组三联体，输出以下字段：

**`triplet_id`**：对应的三联体 ID

**`baseline_rule`**：A 层提取的显性规则——专家在未受到任何变量扰动时明确说出的判断依据

**`awareness_state`**：B 层中专家对目标隐性变量的察觉状态，取以下三值之一：
- `explicit`：专家主动说出了差异，并能命名判断维度
- `semi_latent`：专家察觉了差异但无法明确命名（使用模糊词、比喻、"感觉"等）
- `deep_latent`：专家未察觉差异，决策变化但无法解释

**`priority_topology`**：C 层中规则冲突时的实际取舍，格式为 `{"winner": "规则A", "loser": "规则B", "condition": "触发条件"}`

**`confidence`**：本三联体分析整体置信度，取 `high` / `medium` / `low`

**`latent_findings`**：本三联体揭示的隐性知识条目列表，每条包含：
- `type`：`变量` / `优先级` / `边界条件`
- `content`：具体内容描述
- `confidence`：`high` / `medium` / `low`
- `evidence`：`{"triplet_id": "...", "layer": "A/B/C", "expert_quote": "专家原话", "confidence_reason": "置信度理由"}`

**`invalidated_candidates`**：在本三联体中被证伪的候选变量 ID 列表（不能静默丢弃，不相关时为空列表）

---

## 跨三联体分析要求

完成所有单三联体分析后，执行以下跨三联体综合：

**同变量一致性检验**：
- 如果同一隐性变量在 2+ 组三联体中出现，综合置信度提升，归入 `confirmed_variables`
- 如果同一变量在不同三联体中表现不一致，标记为 `inconsistent_variables`，说明分歧和调节条件

**优先级拓扑一致性**：
- 汇总所有三联体中 C 层的取舍关系
- 若同一对冲突规则在不同场景中胜出关系不一致，推断调节变量

**全局边界地图**：
- 汇总所有 `boundary_invented` 信号对应的边界条件
- 每条边界标注适用域、失效域、反转条件
- `triplet_id` 字段标注来源三联体

---

## 输出格式

```json
{
  "triplet_analyses": [
    {
      "triplet_id": "tg_001",
      "baseline_rule": "...",
      "awareness_state": "semi_latent",
      "priority_topology": {"winner": "规则A", "loser": "规则B", "condition": "..."},
      "confidence": "medium",
      "latent_findings": [
        {
          "type": "变量",
          "content": "...",
          "confidence": "high",
          "evidence": {
            "triplet_id": "tg_001",
            "layer": "B",
            "expert_quote": "...",
            "confidence_reason": "..."
          }
        }
      ],
      "invalidated_candidates": []
    }
  ],
  "cross_analysis": {
    "confirmed_variables": [],
    "inconsistent_variables": [],
    "priority_topology": [],
    "boundary_map": [
      {
        "triplet_id": "tg_001",
        "boundary": "...",
        "applicable_domain": "...",
        "failure_domain": "...",
        "reversal_condition": "..."
      }
    ]
  },
  "report_sections": {
    "discovered_variables": [],
    "priority_topology": [],
    "boundary_map": [],
    "suspected_bias": [],
    "open_questions": []
  }
}
```

---

## 质量标准

- 每个三联体**必须**输出 `baseline_rule`、`awareness_state`、`priority_topology`、`confidence`
- `awareness_state` 只能取 `explicit` / `semi_latent` / `deep_latent`
- `confidence`（三联体顶层）只能取 `high` / `medium` / `low`
- 每个 `latent_finding` 必须有 `confidence` 和 `evidence.expert_quote`（不得为空）
- 被证伪候选必须出现在 `invalidated_candidates`，不得静默丢弃
- `cross_analysis.boundary_map` 必须覆盖所有含 `boundary_invented` 信号的三联体
- `report_sections.open_questions` 必须列出未能确认或证伪的候选变量
- 如果访谈记录包含 `camera_suggestions`，只能作为辅助上下文；不能仅凭摄像头建议生成隐性知识发现
