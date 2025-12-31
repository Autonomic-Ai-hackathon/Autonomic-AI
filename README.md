

# Autonomic AI: Self-Healing GenAI Swarm

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Google Cloud](https://img.shields.io/badge/Google_Cloud-Vertex_AI-red.svg)](https://cloud.google.com/vertex-ai)
[![Datadog](https://img.shields.io/badge/Datadog-Observability-purple.svg)](https://www.datadoghq.com/)

> **"The fear of GenAI isn't that it won't work... it's that it will work, and you won't know when it fails."**

**Autonomic AI** is an event-driven system that turns the "Black Box" of GenAI into a transparent "Glass Box." It uses a swarm of backend agents to audit, refine, and deploy new versions of a user-facing chatbot automatically when business logic fails.

---


## ☁️ Infrastructure Deployment
We use a fully scripted `gcloud` setup to provision Pub/Sub, Firestore, and Cloud Run.
For a detailed breakdown of the IAM permissions and infrastructure commands, see our [Deployment Guide](DEPLOYMENT.md).

## Datadog Info
For datadog usage and detail please check the DATADOG.md file 
[Datadog file](DATADOG.md)


## 🚀 How It Works

Autonomic AI operates on a **Closed-Loop Control System**:

1.  **Gateway Agent (`carsalesman101`)**: Interacts with the user.
2.  **Auditor (The Judge)**: Asynchronously scores every conversation against a strict "Rulebook" via Google Pub/Sub.
3.  **Refiner (The Fixer)**: If the Auditor flags a mistake (e.g., failure to capture a lead), the Refiner uses Gemini to rewrite the system prompt.
4.  **Evaluator (The Tester)**: Runs the new prompt in a sandbox against the failed conversation to ensure the fix works.
5.  **Deployment**: Automatically updates the agent version in Firestore and deploys it to production.
6.  **Datadog Ops Center**: Visualizes the entire process and alerts humans only if the AI fails to fix itself.

---

## 🏗️ Architecture

The system is built on **Google Cloud Platform** using an Event-Driven Architecture.

* **Frontend/Gateway**: Python FastAPI
* **Message Broker**: Google Pub/Sub
* **LLM Provider**: Google Vertex AI (Gemini 2.5 Flash)
* **Database**: Google Firestore (Store Agent "DNA" & Version History)
* **Observability**: Datadog (Log Streams, Dashboards, Workflows)

---

## 🧬 Agent Configuration ("The DNA")

Agents are not hardcoded. They are defined by a JSON configuration file stored in Firestore. Below is the configuration for the demo agent `carsalesman101`.

```json
{
  "agent_id": "carsalesman101",
  "version": 1,
  "config": {
    "model_id": "gemini-2.5-flash",
    "temperature": 0.2,
    "max_tokens": 800
  },
  "prompt": {
    "persona": {
      "role": "Senior Sales Concierge",
      "tone": "High-Energy, Consultative"
    },
    "operational_guidelines": [
      "PROTOCOL 1: Always be polite.",
      "PROTOCOL 2: Be definitive.",
      "PROTOCOL 3: Keep responses under 100 words."
    ]
  },
  "upgrade_config": {
    "auditor_rules": [
      "CRITICAL FAIL if the user asks about a vehicle and the agent DOES NOT explicitly ask for an email address.",
      "FAIL if the agent mentions a vehicle model not in INVENTORY."
    ]
  },
  "evaluator_rubric": [
    "Did the agent strictly follow the 'Ask for Email' protocol?",
    "Was the response concise and high-energy?"
  ]
}

```

---

## 🛠️ Setup & Installation

### Prerequisites

* Python 3.10+
* Google Cloud Project with Vertex AI & Pub/Sub enabled
* Datadog Account (API Key & App Key)

### 1. Clone the Repository

```bash
git clone [https://github.com/yourusername/autonomic-ai.git](https://github.com/yourusername/autonomic-ai.git)
cd autonomic-ai

```

### 2. Install Dependencies

```bash
pip install -r requirements.txt

```

### 3. Environment Variables

Create a `.env` file in the root directory:

```env
GOOGLE_APPLICATION_CREDENTIALS="path/to/your/service-account.json"
GCP_PROJECT_ID="your-project-id"
PUBSUB_TOPIC_AUDIT="audit-stream"
DATADOG_API_KEY="your-dd-api-key"
DATADOG_APP_KEY="your-dd-app-key"

```

### 4. Run the Gateway

```bash
uvicorn main:app --reload

```

---

## 📊 Datadog Dashboard

We built a custom "Autonomic AI Ops Center" to visualize the swarm's thought process.

* **Optimization Rate**: 
* **Budget Breach**: Alerts if cost > $0.10/msg.
* **Log Stream**: Filters by `service:auditor`, `service:refiner` to show real-time debugging.

*(Import the `datadog_dashboard.json` file located in the `/dashboards` folder to replicate our view.)*

---

## 🧪 Testing the Self-Healing Loop

1. Start the chat via the API or UI.
2. **Trigger a Fail**: Ask about a car price but *do not* provide contact info.
* *User:* "How much is the Model Y?"
* *Agent (v1):* "It is $45,000." (Fails to ask for email).


3. **Watch the Logs**:
* `Auditor` detects breach -> triggers `Refiner`.
* `Refiner` generates patch -> sends to `Evaluator`.
* `Evaluator` approves -> `v1.2` deployed.


4. **Verify Fix**: Chat again.
* *User:* "How much is the Model Y?"
* *Agent (v1.2):* "It is $45,000. May I have your email to send the quote?"



---

## 🔮 What's Next?

* **Multi-Modal Auditing**: Support for voice/video analysis with Gemini 1.5 Pro.
* **Confluent Integration**: Real-time clickstream ingestion for personalized prompting.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

```

