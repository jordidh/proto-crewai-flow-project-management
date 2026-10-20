# Comparision with Claude Workflow

Comparision to evaluate the performance of this CrewAI project over a Claude Workflow

---

## Configuration

### Model Comparison Requirements

To ensure a fair comparison, both implementations must run on equivalent LLM tiers.

---

### Find a Gemini model close to Claude model

#### 1. Direct Comparison (Same Model)

Claude Code uses **Opus 5.5**. Because CrewAI supports Anthropic models, we can call claude-opus-5-5 directly in the CrewAI project via API. This isolates the framework as the only variable.

#### 2. Cross-Vendor Comparison (Gemini)

If we want to compare Anthropic against Google Gemini, the closest equivalent tier is **Gemini 3.1 Pro** (gemini-3.1-pro-preview). In Google's lineup, the Pro tier fulfills a role comparable to Opus for complex reasoning tasks.

Other models you might encounter and why they are not ideal matches:

- Gemini 3.8 Flash: While newer (released September 2026) and optimized for agentic and engineering tasks, Flash is Google's high-speed, cost-efficient tier. It aligns closer to Sonnet than to Opus.
- Gemini 4 Argon: Announced as Google's next frontier model in late September 2026, it is currently restricted to vetted cyber defense partners and unavailable for general testing.

#### Recommended Testing Methodology

Running CrewAI on Gemini while testing the Claude workflow on Opus 5.5 introduces confounding variables: you would be testing both the frameworks and the models simultaneously, making it impossible to determine which factor caused any differences in quality or latency.

Suggested Approach:

- Baseline Test (Frameworks Isolated): Run both CrewAI and the Claude workflow on Claude Opus 5.5.
- Secondary Test (Cross-Vendor): Run CrewAI a second time using Gemini 3.1 Pro to measure vendor-specific trade-offs in quality, latency, and cost.

---

### Find a Claude model close to Gemini model

The closest Claude equivalent to Google's **Gemini 3.5 Flash-Lite** (or the Flash-Lite class in general) is **Claude 3.5 Haiku**.

#### Why they align (Tier & Purpose):

| Feature / Metric | Gemini 3.5 Flash-Lite | Claude 5.5 Haiku |
| --- | --- | --- |
| **Model Tier** | Ultra-lightweight, high-throughput utility tier | Fast, lightweight economy tier |
| **Primary Use Case** | Subagent tasks, structured classification, high-volume routing | Low-latency tasks, subagent execution, fast code assistance |
| **Pricing Target** | Budget-tier pricing (< $1 / 1M input tokens) | Budget-tier pricing (~ $0.80–$1.00 / 1M input tokens) |
| **Speed & Latency** | Optimized for minimal time-to-first-token (TTFT) | Fastest model in the Anthropic family |

#### How the Claude and Gemini Tiers Map Directly:

To understand where each model fits across both ecosystems:

1. **Frontier / Deep Reasoning Tier:**
  1.1. **Anthropic:** Claude 3.5 / 3.7 / 4.x Sonnet or Opus
  1.2. **Google:** Gemini 1.5 / 3.1 Pro
2. **Workhorse High-Speed Tier:**
  2.1. **Anthropic:** Claude 3.5 Sonnet (balanced) / standard Haiku
  2.2. **Google:** Gemini Flash (standard)
3. **High-Throughput Subagent / Utility Tier:**
  3.1. **Anthropic:** **Claude 5.5 Haiku**
  3.2. **Google:** **Gemini Flash-Lite** (e.g., 1.5 Flash-8B, 3.5 Flash-Lite)

---

## Comparision

### Data

Token comsumption:

| Project | Model | Duration | Completion Tokens |
|-|-|-:|-:|
| CrewAI | Gemini 3.5 Flash-Lite | 0m 59s | 20180 |
| CrewAI | Claude 5.5 Haiku | 6m 40s | 103714 |
| Claude | Claude 5.5 Haiku | 22m 47s | 80906 |

Note: 

Generated documentation size:

| File | Lines CrewAI + Gemini | Lines CrewAI + Haiku | Lines Claude + Haiku |
|---|---:|---:|---:|
| `control/change_log.md` | 17 | 35 | 84 |
| `control/risk_register.md` | 82 | 244 | 303 |
| `initiation/business_case.md` | 79 | 138 | 427 |
| `initiation/project_charter.md` | 94 | 137 | 258 |
| `initiation/stakeholder_register.md` | 69 | 148 | 269 |
| `initiation/team_charter.md` | 73 | 165 | 273 |
| `performance/evm_metrics.json` | 186 | 42 | 1522 |
| `performance/project_dashboard.md` | 76 | 145 | 195 |
| `performance/s_curve.csv` | 2 | 1 | 30 |
| `performance/status_report.md` | 61 | 210 | 387 |
| `planning/backlog.md` | 56 | - | 447 |
| `planning/definition_of_done.md` | 53 | 254 | 257 |
| `planning/requirements_specification.md` | 177 | 340 | 388 |
| `planning/schedule_model.json` | 338 | 16 |  3178 |
| `planning/wbs.md` | 71 | 275 | 897 |
| Total | 1434 | 2150 | 8915 |

### Conclusion

In this run, the Claude workflow generated 8,915 documentation lines, compared with 2,150 for CrewAI using Claude Haiku. That is about 4.1 times as many lines, while CrewAI completed faster (6m 40s versus 22m 47s) and recorded more completion tokens (103,714 versus 80,906). The CrewAI + Gemini run was the fastest (59s), with 20,180 completion tokens and 1,434 lines, but it uses a different model and is therefore not a direct framework comparison. The Haiku comparison is more informative because both workflows used the same model, but it is still not fully equivalent: the CrewAI output has no `planning/backlog.md`, and line counts alone do not measure accuracy, completeness, or usefulness. These measurements describe this particular run and do not show that either workflow produced higher-quality results. A stronger assessment should use the same model, inputs, and output requirements, ensure all expected artifacts are present, and score the results against shared quality criteria.
