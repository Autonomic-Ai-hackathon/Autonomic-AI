
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
*(Import `Dashboard.json` to view)*

### Key Widgets

1. **Current Active Version:** Displays the live version of the agent (e.g., `v1` -> `v2`). Colors change if a rollback occurs.
2. **Optimization Rate:** A custom formula tracking the success rate of our self-healing code:


3. **Log Stream:** A live feed filtering `service:autonomic-*` to show the conversation between the Auditor and Refiner.
4. **SLO Widget:** Tracks "Successful Interaction Rate" (Target: 95%).

---

## 🚨 Detection Rules & Monitors

We defined **3 Critical Detection Rules** to ensure safety and performance.
*(Import the JSONs in the `monitors/` folder)*

### 1. ⛔ Optimization Failure (The "Actionable" Rule)

* **Context:** If the "Refiner" agent tries to fix a bug but the "Evaluator" rejects the fix twice, the system gives up to prevent infinite loops.
* **Query:** `sum(last_5m):sum:autonomic.optimization.failed{*} >= 1`
* **Action:** Triggers a **Datadog Workflow** to open a Case.
* **Why:** This is the only time a human *must* intervene.

### 2. 💸 Budget Breach Alert

* **Context:** GenAI costs can spiral. We monitor per-message cost.
* **Query:** `max(last_5m):avg:autonomic.budget.breach.amount{*} >= 0.1`
* **Threshold:** Alerts if a single message costs > $0.10.
* **Why:** Detects prompt injection attacks or infinite looping agents.

### 3. 🐢 Latency Anomaly (AI-Powered)

* **Context:** Users expect speed.
* **Query:** Uses Datadog's **Anomaly Detection** algorithm (`anomalies(..., 'agile', 2)`) to detect deviations from the baseline.
* **Why:** Static thresholds fail because LLM latency varies by token count. Anomaly detection adapts to the traffic pattern.

---

## ⚡ Automated Remediation (Workflow)

We use **Datadog Workflows** to close the loop between detection and action.

* **Trigger:** The **⛔ Optimization Failure** monitor fires.
* **Workflow ID:** `Auto-Remediation: Optimization Failure`
* **Step 1:** Extracts `agent_id` and `failure_reason` from the alert tags.
* **Step 2:** Automatically creates a **Datadog Case** in the Case Management portal.
* **Result:** The on-call engineer receives a curated Case with the exact chat logs needed to fix the prompt manually.

---

## 🛠️ Setup & Replication

### 1. Prerequisites

* A Datadog Account with API/APP Keys.
* Python 3.10+ installed.

### 2. Import Configuration

1. **Dashboard:** Import `Dashboard.json` into Dashboards.
2. **Monitors:** Create new monitors using the JSON definitions provided in the `monitors` section of this folder.
3. **Workflow:** Import `workflow.json` into Datadog Workflows.

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