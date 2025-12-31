import json
import datetime
import traceback
from fastapi import FastAPI
from ddtrace import tracer
from datadog import statsd 
from src.config import TOPIC_REFINE, TOPIC_EVALUATE
from src.core.db import db
from src.core.pubsub import listen_to_topic, publish_background_event
from src.core.llm import generate_response
from src.core.logger import log_event

app = FastAPI(title="Autonomic Refiner Worker")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "refiner"}

def refine_agent(payload):
    # ✅ Start Timer
    with statsd.timed("autonomic.refiner.latency", tags=[f"agent_id:{payload.get('agent_id')}"]):
        chat_id = payload.get("chat_id")
        agent_id = payload.get("agent_id")
        failure_reason = payload.get("failure_reason")
        refinement_depth = payload.get("refinement_depth", 0)
        
        if refinement_depth >= 2:
            log_event(
                chat_id, 
                "REFINER", 
                f"⛔ STOPPING: Refinement loop detected. Agent {agent_id} failed optimization twice.", 
                "CRITICAL",
                metadata={
                    "action": "email_alert", 
                    "recipient": "admin@user.com", 
                    "reason": "Automatic fix failed to resolve issue."
                }
            )
            return

        current_span = tracer.current_span()
        if current_span:
            current_span.set_tag("chat_id", chat_id)
            current_span.set_tag("agent_id", agent_id)
            current_span.set_tag("component", "REFINER")

        log_event(chat_id, "REFINER", f"🛠️ Starting refinement for {agent_id}. Reason: {failure_reason}", "INFO")

        try:
            # 1. FETCH AGENT CONFIG
            agent_ref = db.collection("agents").document(agent_id)
            agent_doc = agent_ref.get()
            
            if not agent_doc.exists:
                log_event(chat_id, "REFINER", "❌ Agent doc not found", "ERROR")
                return
                
            agent_data = agent_doc.to_dict()
            current_version = agent_data.get("version", 1)
            prompt_config = agent_data.get("prompt", {})

            # 2. EXTRACT ONLY MUTABLE FIELDS
            mutable_context = {
                "persona": prompt_config.get("persona"),
                "style_guide": prompt_config.get("style_guide"),
                "objectives": prompt_config.get("objectives"),
                "operational_guidelines": prompt_config.get("operational_guidelines")
            }

            # 3. GENERATE OPTIMIZATION PROMPT
            refine_prompt = f"""
You are an Expert AI Agent Architect. 
Your goal is to fix a conversational agent that failed a quality audit.

FAILURE CONTEXT:
The agent failed with this reason: "{failure_reason}"

CURRENT MUTABLE CONFIGURATION:
{json.dumps(mutable_context, indent=2)}

INSTRUCTIONS:
1. Analyze the failure reason.
2. Modify the 'persona', 'objectives', or 'operational_guidelines' to prevent this failure.
3. Keep the JSON structure exactly the same.
4. Do NOT change the tone unless it was the cause of failure.
5. Add specific guidelines to handle the edge case described in the failure.

Return ONLY the valid JSON of the modified configuration.
"""

            log_event(chat_id, "REFINER", "🤖 Asking LLM to fix the prompt...", "INFO")
            
            # Call LLM
            llm_result = generate_response(
                refine_prompt,
                system_prompt="You are a strict JSON generator. Output only valid JSON."
            )
            
            cleaned_response = llm_result["text"].replace("``````", "").replace("```json", "").replace("```", "").strip()
            
            try:
                new_mutable_config = json.loads(cleaned_response)
            except json.JSONDecodeError:
                log_event(chat_id, "REFINER", "❌ LLM generated invalid JSON. Aborting.", "ERROR")
                return

            # 4. CREATE NEW CANDIDATE VERSION
            new_version = current_version + 1
            base_id = agent_id.split("_v")[0] 
            new_agent_id = f"{base_id}_v{new_version}"

            # Construct new full config
            new_agent_data = agent_data.copy()
            new_agent_data["version"] = new_version
            new_agent_data["agent_id"] = new_agent_id
            new_agent_data["created_at"] = datetime.datetime.utcnow()
            
            # Update metadata
            new_agent_data["metadata"]["version"] = new_version
            new_agent_data["metadata"]["agentid"] = new_agent_id
            new_agent_data["metadata"]["upgrade_reason"] = f"Refinement fix for: {failure_reason}"
            new_agent_data["metadata"]["deployment_state"] = "TEST_CANDIDATE" 
            
            new_agent_data["prompt"].update(new_mutable_config)

            # 5. SAVE TO FIRESTORE
            log_event(chat_id, "REFINER", f"💾 Saving candidate: {new_agent_id}", "INFO")
            db.collection("agents").document(new_agent_id).set(new_agent_data)
            # Extract cost from LLM result
            metrics = llm_result.get("metrics", {})
            cost = metrics.get("estimated_cost", 0.0)

            statsd.gauge(
                "autonomic.backend.cost",
                cost,
                tags=[
                    "service:refiner",  # <--- Change this for each worker (refiner/evaluator)
                    f"agent_id:{agent_id}"
                ]
            )
            # 6. TRIGGER EVALUATOR
            evaluator_payload = {
                "target_agent_id": new_agent_id,
                "original_agent_id": base_id,
                "chat_id": chat_id,
                "trigger_reason": failure_reason,
                "refinement_depth": refinement_depth,
                "version": new_version
            }
            
            publish_background_event(TOPIC_EVALUATE, evaluator_payload)
            
            # ✅ Send Event to Datadog (Visual Overlay on charts)
            # ✅ CORRECTED
            statsd.event(
                title="Refiner: Fix Applied",
                message=f"Fixed agent {agent_id}. Reason: {failure_reason}", # <--- CHANGED 'text' TO 'message'
                alert_type="info",
                tags=[f"agent_id:{agent_id}", "source:refiner"]
            )
            
            log_event(
                chat_id, 
                "REFINER", 
                f"✅ Refinement Complete. {new_agent_id} sent to Evaluator.", 
                "SUCCESS"
            )

        except Exception as e:
            log_event(chat_id, "REFINER", f"🔥 Error during refinement: {str(e)}", "ERROR")
            traceback.print_exc()

def start_refiner():
    log_event(None, "REFINER", "🚀 Refiner Service starting...", "INFO")
    listen_to_topic("sub-refiner", refine_agent)