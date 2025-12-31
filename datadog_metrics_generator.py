#!/usr/bin/env python3
"""
Autonomic AI - Traffic Generator v5 (Triple Monitor Trigger)
------------------------------------------------------------
1. Triggers Budget Breaches (3x) -> Fixed $0.18+ costs
2. Triggers Latency Anomalies (3x) -> Fixed 25s durations
3. Triggers Optimization Failures (2x) -> Forces Audit Fail -> Evaluator Fail
"""

import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datadog import initialize, api

# ============================================================
# 🔑 CONFIGURATION
# ============================================================
DATADOG_API_KEY = "Your Datadog API Key Here"
DATADOG_APP_KEY = "your datadog app key here"
DD_SITE = "datadoghq.com" #Change if using EU or other sites

# ============================================================
# ⚙️ SETUP
# ============================================================

# 1. Initialize Metrics
initialize(api_key=DATADOG_API_KEY, app_key=DATADOG_APP_KEY)

# 2. Initialize Logs (With Retry & Session)
LOG_INTAKE_URL = f"https://http-intake.logs.{DD_SITE}/v1/input"
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

# Constants
AGENT_ID = "carsalesman101"
CHAT_IDS = [f"chat_{str(i).zfill(3)}" for i in range(1, 10)]
SERVICES = {
    "gateway": "autonomic-gateway",
    "auditor": "autonomic-auditor",
    "refiner": "autonomic-refiner",
    "evaluator": "autonomic-evaluator"
}

# --- GLOBAL COUNTERS ---
TOTAL_REQUESTS = 0
FORCED_BUDGET_COUNT = 0
FORCED_LATENCY_COUNT = 0
FORCED_OPTIMIZATION_COUNT = 0  # We want exactly 2 of these

# ============================================================
# 🛠️ HELPER FUNCTIONS
# ============================================================

def send_log(service, message, status="INFO", attributes=None):
    """Sends a structured log via HTTP (Robust)"""
    headers = {
        "Content-Type": "application/json",
        "DD-API-KEY": DATADOG_API_KEY
    }
    
    payload = {
        "ddsource": "python",
        "ddtags": "env:hackathon-dev,version:v1",
        "hostname": service,
        "service": service,
        "message": f"[{service.split('-')[1].upper()}] {message}",
        "status": status,
        "timestamp": int(time.time() * 1000)
    }
    
    if attributes:
        payload.update(attributes)

    try:
        session.post(LOG_INTAKE_URL, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Log Failed: {e}")

def send_metric(name, value, tags, metric_type='gauge'):
    """Sends metric to Datadog API"""
    try:
        api.Metric.send(
            metric=name,
            points=[(time.time(), value)],
            tags=tags,
            type=metric_type
        )
    except Exception as e:
        print(f"⚠️ Metric Failed: {e}")

def calculate_cost(input_tokens, output_tokens):
    return round((input_tokens * 0.30 / 1e6) + (output_tokens * 2.50 / 1e6), 8)


# ============================================================
# 1. GATEWAY (Triggers Budget & Latency Alerts)
# ============================================================
def run_gateway(chat_id, current_version):
    global TOTAL_REQUESTS, FORCED_BUDGET_COUNT, FORCED_LATENCY_COUNT
    
    service = SERVICES["gateway"]
    TOTAL_REQUESTS += 1
    print(f"🔵 [GATEWAY] Req #{TOTAL_REQUESTS} | Processing {chat_id}...")

    # --- LOGIC CONTROL ---
    # Warmup: First 5 requests are normal to establish baseline for anomalies
    is_warmup = TOTAL_REQUESTS <= 5
    
    trigger_high_cost = False
    trigger_high_latency = False

    if not is_warmup:
        # Trigger Budget Breach (Limit to 3 times)
        if FORCED_BUDGET_COUNT < 3:
            trigger_high_cost = True
            FORCED_BUDGET_COUNT += 1
        
        # Trigger Latency Spike (Limit to 3 times)
        if FORCED_LATENCY_COUNT < 3:
            trigger_high_latency = True
            FORCED_LATENCY_COUNT += 1

    # --- COST CALCULATIONS ---
    if trigger_high_cost:
        print(f"   💸 FORCING BUDGET BREACH ({FORCED_BUDGET_COUNT}/3)")
        # 600k tokens * $0.30/1m = $0.18 (Guaranteed > $0.10)
        input_tokens = random.randint(550000, 650000)
        output_tokens = random.randint(2000, 5000)
    else:
        # Normal
        input_tokens = random.randint(300, 800)
        output_tokens = random.randint(50, 200)

    # --- LATENCY CALCULATIONS ---
    if trigger_high_latency:
        print(f"   🐢 FORCING LATENCY SPIKE ({FORCED_LATENCY_COUNT}/3)")
        # 25,000ms (25s) is a huge anomaly compared to normal 1s
        latency = random.randint(22000, 28000)
    else:
        # Normal (800ms - 1.5s)
        latency = random.randint(800, 1500)

    cost = calculate_cost(input_tokens, output_tokens)

    # Logs
    send_log(service, f"📥 Request received for agent: {AGENT_ID}", "INFO")
    send_log(service, f"✅ Config loaded: v{current_version}", "INFO")
    
    # METRICS
    tags = [f"agent_id:{AGENT_ID}", f"version:v{current_version}", f"chat_id:{chat_id}"]
    
    send_metric("autonomic.chat.count", 1, tags, "count")
    send_metric("autonomic.agent.cost", cost, tags, "gauge")
    send_metric("autonomic.agent.current_version", current_version, [f"agent_id:{AGENT_ID}"], "gauge")
    send_metric("autonomic.agent.latency.avg", latency, tags, "gauge") 

    # --- BUDGET BREACH ---
    if cost > 0.10:
        print(f"   🚨 BUDGET BREACH RECORDED: ${cost:.4f}")
        send_log(service, f"⚠️ Budget Breach: ${cost:.4f}", "WARNING")
        
        # Includes output_tokens so the Budget Monitor can "group by" correctly
        breach_tags = tags + [f"input_tokens:{input_tokens}", f"output_tokens:{output_tokens}"]
        
        send_metric("autonomic.budget.breach", 1, breach_tags, "count")
        send_metric("autonomic.budget.breach.amount", cost, breach_tags, "gauge")

    return cost

# ============================================================
# 2. AUDITOR (Forces Failures to feed Evaluator)
# ============================================================
def run_auditor(chat_id):
    service = SERVICES["auditor"]
    print(f"🟡 [AUDITOR] Auditing {chat_id}...")
    
    latency = random.randint(1200, 3000)
    cost = calculate_cost(1000, 50)
    
    # --- LOGIC CONTROL ---
    # If we haven't hit our 2 optimization failures yet, we MUST fail the audit
    # so the request moves to the Refiner -> Evaluator pipeline.
    force_audit_fail = FORCED_OPTIMIZATION_COUNT < 2
    
    if force_audit_fail:
        is_fail = True
    else:
        is_fail = random.random() < 0.20 # Normal low failure rate

    verdict = "FAIL" if is_fail else "PASS"
    reason = "Forced Audit Failure" if force_audit_fail else "Compliance Check"

    send_log(service, f"🧐 Picked up audit job...", "INFO")
    send_log(service, f"⚖️ Verdict: {verdict} | Reason: {reason}", "WARNING" if is_fail else "INFO")

    tags = [f"agent_id:{AGENT_ID}"]
    
    send_metric("autonomic.auditor.latency.avg", latency/1000.0, tags, "gauge") # Seconds
    send_metric("autonomic.backend.cost", cost, ["service:auditor"] + tags, "gauge")
    send_metric("autonomic.audit.verdict", 1, tags + [f"verdict:{verdict.lower()}"], "count")

    return verdict, reason

# ============================================================
# 3. REFINER
# ============================================================
def run_refiner(chat_id, reason, current_version):
    service = SERVICES["refiner"]
    print(f"🟠 [REFINER] Fixing issue...")
    
    latency = random.randint(2000, 5000)
    cost = calculate_cost(1500, 400)
    
    send_log(service, f"🛠️ Refinement started for {reason}", "INFO")
    send_log(service, "✅ Refinement Complete.", "SUCCESS")
    
    tags = [f"agent_id:{AGENT_ID}"]
    
    send_metric("autonomic.refiner.latency.avg", latency/1000.0, tags, "gauge") # Seconds
    send_metric("autonomic.backend.cost", cost, ["service:refiner"] + tags, "gauge")
    
    return f"{AGENT_ID}_v{current_version+1}", current_version + 1

# ============================================================
# 4. EVALUATOR (UPDATED: Triggers Optimization Failure 2x)
# ============================================================
def run_evaluator(candidate_id, new_version, chat_id, audit_reason):
    global FORCED_OPTIMIZATION_COUNT
    service = SERVICES["evaluator"]
    print(f"🟣 [EVALUATOR] Testing {candidate_id}...")
    
    latency = random.randint(3000, 6000)
    cost = calculate_cost(2000, 200)
    
    send_log(service, f"🧪 Evaluating {candidate_id}...", "INFO")
    
    # --- LOGIC CONTROL ---
    if FORCED_OPTIMIZATION_COUNT < 2:
        success = False
        FORCED_OPTIMIZATION_COUNT += 1
        print(f"   ⛔ FORCING OPTIMIZATION FAILURE ({FORCED_OPTIMIZATION_COUNT}/2)")
    else:
        success = True # Always succeed after triggers are done to prevent more alerts

    tags = [f"agent_id:{AGENT_ID}"]
    
    send_metric("autonomic.evaluator.latency.avg", latency/1000.0, tags, "gauge") # Seconds
    send_metric("autonomic.backend.cost", cost, ["service:evaluator"] + tags, "gauge")

    if success:
        send_log(service, f"🚀 PROMOTING {candidate_id}!", "SUCCESS")
        send_metric("autonomic.deployments.success", 1, tags, "count")
        return new_version
    else:
        print("   ❌ Optimization Failed")
        send_log(service, "⛔ OPTIMIZATION FAILED", "ERROR")
        
        # --- RICH FAILURE METRIC ---
        # Matches your "Optimization Failure" Monitor query
        failure_tags = tags + [
            f"chat_id:{chat_id}",
            f"reason:performance", # The key tag for your monitor query
            f"audit_reason:{audit_reason}",
            f"refinement_version:v{new_version}"
        ]
        
        send_metric("autonomic.optimization.failed", 1, failure_tags, "count")
        return None

# ============================================================
# 🚀 MAIN
# ============================================================
def main():
    if "YOUR_DD" in DATADOG_API_KEY:
        print("❌ ERROR: Set API Keys first!")
        return

    print("🚀 Starting Datadog Generator v5 (Triple Monitor Trigger)...")
    print("ℹ️  Targets: 3 Budget Breaches | 3 Latency Spikes | 2 Optimization Failures")
    
    current_version = 1
    
    while True:
        try:
            # Burst of traffic
            for _ in range(random.randint(1, 3)):
                chat_id = random.choice(CHAT_IDS)
                
                # 1. Gateway
                run_gateway(chat_id, current_version)
                
                # 2. Auditor
                verdict, audit_reason = run_auditor(chat_id) # Capture reason
                
                if verdict == "FAIL":
                    # 3. Refiner
                    cand_id, cand_ver = run_refiner(chat_id, audit_reason, current_version)
                    
                    # 4. Evaluator (Now passing chat_id and audit_reason)
                    final_ver = run_evaluator(cand_id, cand_ver, chat_id, audit_reason)
                    
                    if final_ver:
                        current_version = final_ver
                        print(f"✨ UPGRADE: v{current_version}")

            time.sleep(random.randint(2, 5))

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"🔥 Error: {e}")

if __name__ == "__main__":
    main()