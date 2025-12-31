import time
import json
from fastapi import FastAPI
from ddtrace import tracer
from datadog import statsd
from src.config import TOPIC_REFINE
from src.core.db import db, get_current_agent_config
from src.core.pubsub import listen_to_topic, publish_background_event
from src.core.llm import generate_response
from src.core.logger import log_event

app = FastAPI(title="Autonomic Evaluator Worker")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "evaluator"}

def run_evaluation(payload):
    # ✅ Start the Timer Context Manager
    # Everything inside this block will be timed for the "latency" metric
    with statsd.timed("autonomic.evaluator.latency", tags=[f"candidate_id:{payload.get('target_agent_id')}"]):
        
        chat_id = payload.get("chat_id")
        candidate_agent_id = payload.get("target_agent_id")
        original_agent_id = payload.get("original_agent_id")
        failure_reason = payload.get("trigger_reason")
        refinement_depth = payload.get("refinement_depth", 0)

        # Distributed Tracing
        current_span = tracer.current_span()
        if current_span:
            current_span.set_tag("chat_id", chat_id)
            current_span.set_tag("candidate_id", candidate_agent_id)
            current_span.set_tag("component", "EVALUATOR")

        log_event(chat_id, "EVALUATOR", f"🧪 Evaluating Candidate {candidate_agent_id}...", "INFO")

        try:
            # ---------------------------------------------------------
            # STEP 1: FETCH CONTEXT (Chat History & Candidate Config)
            # ---------------------------------------------------------
            chat_doc_ref = db.collection("chats").document(chat_id).get()
            
            if not chat_doc_ref.exists:
                log_event(chat_id, "EVALUATOR", "❌ Chat history not found. Aborting.", "ERROR")
                return
            
            chat_data = chat_doc_ref.to_dict()
            history = chat_data.get("history", [])
            
            # ✅ FETCH AUDIT REASON (Added as per request)
            # We extract it safely here to pass it to handle_failure if needed
            audit_result = chat_data.get("audit_result", {})
            original_audit_reason = audit_result.get("reason", "Unknown Audit Failure")

            last_user_input = ""
            conversation_context = ""
            
            for turn in history:
                role = turn.get("role")
                content = turn.get("content")
                if role == "user":
                    last_user_input = content 
                conversation_context += f"{role.upper()}: {content}\n"

            if not last_user_input:
                log_event(chat_id, "EVALUATOR", "❌ No user input found in history.", "ERROR")
                return

            # B. Get Candidate Agent Config
            candidate_doc = db.collection("agents").document(candidate_agent_id).get()
            if not candidate_doc.exists:
                log_event(chat_id, "EVALUATOR", "❌ Candidate agent doc missing.", "ERROR")
                return
                
            candidate_data = candidate_doc.to_dict()
            candidate_prompt_config = candidate_data.get("prompt", {})
            upgrade_config = candidate_data.get("upgrade_config", {})
            auditor_rules = upgrade_config.get("auditor_rules", [])

            candidate_system_prompt = f"""
You are a {candidate_prompt_config.get('persona', {}).get('role', 'Agent')}.
OBJECTIVES: {candidate_prompt_config.get('objectives', [])}
GUIDELINES: {candidate_prompt_config.get('operational_guidelines', [])}
TONE: {candidate_prompt_config.get('persona', {}).get('tone', 'Neutral')}
"""

            # ---------------------------------------------------------
            # STEP 2: REPLAY SIMULATION (Run Agent on Chat)
            # ---------------------------------------------------------
            log_event(chat_id, "EVALUATOR", "🔄 Replaying conversation with NEW agent...", "INFO")
            
            replay_response = generate_response(
                last_user_input, 
                system_prompt=candidate_system_prompt
            )["text"]

            log_event(chat_id, "EVALUATOR", f"🗣️ New Agent Response: {replay_response}", "INFO")

            # ---------------------------------------------------------
            # STEP 3: VERIFY PERFORMANCE (Did it fix the specific error?)
            # ---------------------------------------------------------
            performance_prompt = f"""
JUDGE THIS FIX.

ORIGINAL FAILURE REASON: "{failure_reason}"
USER INPUT: "{last_user_input}"
NEW AGENT RESPONSE: "{replay_response}"

Did the new response fix the issue and address the failure reason?
Return JSON: {{"verdict": "PASS" or "FAIL", "reason": "..."}}
"""
            perf_result = generate_response(performance_prompt, system_prompt="You are a Quality Judge.")
            perf_json = json.loads(perf_result["text"].replace("```json", "").replace("```", "").strip())
            
            if perf_json.get("verdict") == "FAIL":
                # Pass original_audit_reason to handler
                handle_failure(chat_id, candidate_agent_id, refinement_depth, f"Performance Check Failed: {perf_json.get('reason')}", original_audit_reason)
                return

            log_event(chat_id, "EVALUATOR", "✅ Step 1 Passed: The agent fixed the immediate issue.", "INFO")

            # ---------------------------------------------------------
            # STEP 4: VERIFY COMPLIANCE (Regression Testing)
            # ---------------------------------------------------------
            rules_text = "\n".join([f"- {r}" for r in auditor_rules])
            prompt_text = json.dumps(candidate_prompt_config, indent=2)
            
            compliance_prompt = f"""
AUDIT THIS CONFIGURATION.

IMMUTABLE RULES (Must NOT be violated):
{rules_text}

NEW CANDIDATE PROMPT CONFIG:
{prompt_text}

Does the new configuration violate ANY of the immutable rules? 
For example, if a rule says "Never apologize", and the new prompt says "Apologize profusely", that is a FAIL.

Return JSON: {{"verdict": "PASS" or "FAIL", "reason": "..."}}
"""
            comp_result = generate_response(compliance_prompt, system_prompt="You are a Compliance Officer.")
            comp_json = json.loads(comp_result["text"].replace("```json", "").replace("```", "").strip())

            if comp_json.get("verdict") == "FAIL":
                # Pass original_audit_reason to handler
                handle_failure(chat_id, candidate_agent_id, refinement_depth, f"Compliance Check Failed: {comp_json.get('reason')}", original_audit_reason)
                return

            log_event(chat_id, "EVALUATOR", "✅ Step 2 Passed: No regression or rule violations.", "INFO")

            # ---------------------------------------------------------
            # STEP 5: DEPLOYMENT (Promote to Prod)
            # ---------------------------------------------------------
            log_event(chat_id, "EVALUATOR", f"🚀 PROMOTING {candidate_agent_id} to LIVE!", "SUCCESS")
            
            # Update the Pointer (Atomic Switch)
            db.collection("pointers").document(original_agent_id).update({
                "active_agent_doc_ref": candidate_agent_id,
                "current_version": candidate_data.get("version"),
                "last_updated": time.time(),
                "reason": f"Auto-fixed: {failure_reason}"
            })
            
            # Mark Candidate as Active
            db.collection("agents").document(candidate_agent_id).update({
                "metadata.deployment_state": "ACTIVE"
            })

            statsd.gauge(
                "autonomic.backend.cost",
                perf_result["metrics"]["estimated_cost"],
                tags=["service:evaluator", "step:performance", f"agent_id:{candidate_agent_id}"]
            )

            statsd.gauge(
                "autonomic.backend.cost",
                comp_result["metrics"]["estimated_cost"],
                tags=["service:evaluator", "step:compliance", f"agent_id:{candidate_agent_id}"]
            )
            
            statsd.increment("autonomic.deployments.success", tags=[f"agent_id:{original_agent_id}"])

        except Exception as e:
            log_event(chat_id, "EVALUATOR", f"🔥 Critical Error: {str(e)}", "ERROR")


def handle_failure(chat_id, agent_id, depth, evaluator_reason, audit_reason="N/A"):
    """
    Decides whether to Retry (Refiner) or Alert (Datadog).
    Now includes 'audit_reason' fetched from the original chat logs.
    """
    log_event(chat_id, "EVALUATOR", f"❌ Candidate Rejected. Reason: {evaluator_reason}", "WARNING")
    
    if depth < 2:
        # RETRY: Send back to Refiner
        retry_payload = {
            "chat_id": chat_id,
            "agent_id": agent_id,
            "failure_reason": evaluator_reason,
            "refinement_depth": depth + 1
        }
        publish_background_event(TOPIC_REFINE, retry_payload)
        log_event(chat_id, "EVALUATOR", "🔄 Sent back to Refiner for retry.", "INFO")
    else:
        # ALERT: Give up and notify humans
        msg = f"⛔ OPTIMIZATION FAILED for {agent_id} after 2 attempts. Manual Fix Required."
        log_event(chat_id, "EVALUATOR", msg, "CRITICAL")
        
        statsd.increment(
            "autonomic.optimization.failed",
            tags=[f"agent_id:{agent_id}", "reason:max_depth_exceeded"]
        )
        
        # ✅ Fixed: Added audit_reason to the tags
        statsd.increment(
            "autonomic.optimization.failed",
            tags=[
                f"agent_id:{agent_id}",
                f"chat_id:{chat_id}",
                f"audit_reason:{audit_reason}", 
                f"evaluator_reason:{evaluator_reason}"
                
            ]
        )

        statsd.event(
            title="Autonomic AI: Optimization Given Up",
            text=f"Agent {agent_id} failed to self-heal.\nEvaluator Error: {evaluator_reason}\nOriginal Audit: {audit_reason}",
            alert_type="error"
        )

def start_evaluator():
    listen_to_topic("sub-evaluator", run_evaluation)