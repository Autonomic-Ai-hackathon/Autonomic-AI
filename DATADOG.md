
# 🐶 Autonomic AI: Datadog Observability Strategy

> **Datadog Partner Challenge Submission**
> **Project:** Autonomic AI (Self-Healing GenAI Swarm)
> **Platform:** Google Cloud Vertex AI (Gemini 2.5 Flash)
> **Datadog Org Name:** *[Independent Developer]*

## 🧠 The Strategy: "Autonomic Observability"

Most GenAI monitoring is passive—watching a model fail. We built an **Autonomic Observability** strategy where Datadog metrics drive the application's business logic.

Our system uses a swarm of AI agents (Auditor, Refiner, Evaluator) to fix bugs in real-time. We use Datadog to visualize this "thought process" and intervene only when the self-healing loop fails.

### Key Telemetry Signals

We instrumented our Python application to emit custom metrics that track the lifecycle of a self-repairing agent:

| Metric Name | Type | Description |
| --- | --- | --- |
| `autonomic.agent.cost` | Gauge | Real-time cost per message based on token usage. |
| `autonomic.audit.verdict` | Count | Tracks `pass` vs `fail` decisions by the Auditor agent. |
| `autonomic.optimization.failed` | Count | **CRITICAL:** Triggered when the Refiner tries to fix an agent but fails validation. |
| `autonomic.deployments.success` | Count | Triggered when a new agent version (e.g., v1.2) is deployed to production. |
| `autonomic.agent.latency.avg` | Gauge | End-to-end latency seen by the user. |

---

## 📊 The "Autonomic AI Ops Center" Dashboard

We built a unified control plane to monitor the health of the swarm.
*(Import [`DATADOG/Dashboard.json`](DATADOG/Dashboard.json) to view)*

### Dashboard Metrics & Usage Detail

The dashboard provides a "Glass Cockpit" view of the AI swarm's autonomic functions. Here is how each section is used operationally:

#### **1. Live Agent State**
* **Current Active Version:** Displays the live version of the agent (e.g., `v1` -> `v2`).
    * *Usage:* Instant visual confirmation that a self-healing deployment succeeded. Background turns **Purple** for v2+ to indicate an evolved agent is active.
* **Active Detection Rules:** A "Manage Status" widget filtering for our critical monitors.
    * *Usage:* An "All Green" check for on-call engineers. Shows immediate status of Budget, Latency, and Optimization alerts.

#### **2. Performance & Cost (The "Business" View)**
* **User Facing Latency:** Tracks `autonomic.agent.latency.avg`.
    * *Usage:* Ensures the self-healing loops aren't causing unacceptable user delays.
* **Backend Component Latency:** Breakdowns latency by agent role (Auditor, Refiner, Evaluator).
    * *Usage:* Identifies bottlenecks. If the "Refiner" latency spikes, the self-healing code generation is struggling.
* **ChatBot Agent Cost ($):** Tracks `autonomic.agent.cost`.
    * *Usage:* Financial guardrail. GenAI costs can scale linearly with tokens; this widget catches runaways early.

#### **3. Auditor & Quality Control (The "Brain" View)**
* **Pass Rate %:** Formula: `(Pass / (Pass + Fail)) * 100`.
    * *Usage:* The primary KPI for the "Auditor" agent. A drop below 50% turns the widget **Red**, indicating the current model version is hallucinating frequently.
* **Auditor Pass vs Fail:** A bar chart comparing verdicts over time.
    * *Usage:* Correlates "Fail" spikes with deployment events.

#### **4. Auto-Correction Loop (The "Self-Healing" View)**
* **Optimization Rate:** Formula: `(Success / (Success + Failed)) * 100`.
    * *Usage:* Measures the effectiveness of the "Refiner" agent. If this drops, our automated fixes are being rejected by the "Evaluator," requiring human code review.
* **Optimization Failures by Agent:** Top list of agents causing failures.
    * *Usage:* Rapidly identifies which specific agent ID is stuck in a failure loop.

#### **5. System Logs**
* **LOG STREAM:** A live feed filtering `service:autonomic-*`.
    * *Usage:* Provides the raw "thought process" (logs) of the agents. Engineers can read the conversation between the Auditor and Refiner here to debug logic errors.

---

## 🚨 Detection Rules & Monitors

We defined **3 Critical Detection Rules** to ensure safety and performance.
*(Import the JSONs from the `DATADOG/monitors/` folder)*

### 1. ⛔ Optimization Failure (The "Actionable" Rule)
*(File: [`DATADOG/monitors/optimization_failure.json`](DATADOG/monitors/optimization_failure.json))*

* **Context:** If the "Refiner" agent tries to fix a bug but the "Evaluator" rejects the fix twice, the system gives up to prevent infinite loops.
* **Query:** `sum(last_5m):sum:autonomic.optimization.failed{*} >= 1`
* **Action:** Triggers a **Datadog Workflow** to open a Case.
* **Why:** This is the only time a human *must* intervene.

### 2. 💸 Budget Breach Alert
*(File: [`DATADOG/monitors/budget_breach.json`](DATADOG/monitors/budget_breach.json))*

* **Context:** GenAI costs can spiral. We monitor per-message cost.
* **Query:** `max(last_5m):avg:autonomic.budget.breach.amount{*} >= 0.1`
* **Threshold:** Alerts if a single message costs > $0.10.
* **Why:** Detects prompt injection attacks or infinite looping agents.

### 3. 🐢 Latency Anomaly (AI-Powered)
*(File: [`DATADOG/monitors/latency_anomaly.json`](DATADOG/monitors/latency_anomaly.json))*

* **Context:** Users expect speed.
* **Query:** Uses Datadog's **Anomaly Detection** algorithm (`anomalies(..., 'agile', 2)`) to detect deviations from the baseline.
* **Why:** Static thresholds fail because LLM latency varies by token count. Anomaly detection adapts to the traffic pattern.

---

## ⚡ Automated Remediation (Workflow)

We use **Datadog Workflows** to close the loop between detection and action.
*(File: [`DATADOG/workflow.json`](DATADOG/workflow.json))*

* **Trigger:** The **⛔ Optimization Failure** monitor fires.
* **Workflow ID:** `Auto-Remediation: Optimization Failure`
* **Step 1:** Extracts `agent_id` and `failure_reason` from the alert tags.
* **Step 2:** Automatically creates a **Datadog Case** in the Case Management portal.
* **Result:** The on-call engineer receives a curated Case with the exact chat logs needed to fix the prompt manually.

---
---

## 📸 Evidence & Screenshots

### Incident Management in Action
When the "Optimization Failure" rule is triggered, our Workflow automatically opens a Case.
*(Screenshot: `DATADOG/Screenshots/Screenshot 2026-01-01 031033.PNG`)*

![Datadog Case Created](DATADOG/Screenshots/Screenshot202026-01-0120031033.PNG)

---

## 🛠️ Setup & Replication

### 1. Prerequisites

* A Datadog Account with API/APP Keys.
* Python 3.10+ installed.

### 2. Import Configuration

1.  **Dashboard:** Import [`DATADOG/Dashboard.json`](DATADOG/Dashboard.json) into Dashboards.
2.  **Monitors:** Create new monitors using the JSON definitions provided in `DATADOG/monitors/`.
3.  **Workflow:** Import [`DATADOG/workflow.json`](DATADOG/workflow.json) into Datadog Workflows.

### 3. Run the Traffic Generator

We included a script `datadog_metrics_generator.py` that simulates the entire swarm lifecycle. It is programmed to trigger all 3 detection rules for the demo.

**Configuration:**
Open `datadog_metrics_generator.py` and set your keys:

```python
DATADOG_API_KEY = "YOUR_API_KEY"
DATADOG_APP_KEY = "YOUR_APP_KEY"
DD_SITE = "datadoghq.com"

```

**Run the simulation:**

```bash
pip install datadog requests
python datadog_metrics_generator.py

```

### 4. What to Expect (The Demo Flow)

The script runs a loop that generates specific signals:

1. **Normal Traffic:** ~5 requests to establish a baseline.
2. **Budget Breach (3x):** Sends requests with massive token counts to trigger the **💸 Budget Breach** monitor.
3. **Latency Spikes (3x):** Artificially delays responses by 25s to trigger the **🐢 Latency Monitor**.
4. **Optimization Failure (2x):** Simulates a "Refiner" failure where the agent cannot be fixed. This will trigger the **Workflow** and create a **Case** in your Datadog account.


