import json
import datetime
from ddtrace import tracer
from fastapi import FastAPI
from datadog import statsd 
from src.config import TOPIC_REFINE
from src.core.db import db, get_current_agent_config
from src.core.pubsub import listen_to_topic, publish_background_event
from src.core.llm import generate_response
from src.core.logger import log_event

# Health check endpoint for Cloud Run
app = FastAPI(title="Autonomic Auditor Worker")

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run"""
    return {
        "status": "healthy",
        "service": "auditor",
        "message": "Auditor worker is running"
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Autonomic Auditor",
        "status": "active",
        "role": "quality_auditor"
    }


def evaluate_interaction(payload):
    """
    Comprehensive Auditor that evaluates BOTH:
    1. Compliance Rules (auditor_rules) - PASS/FAIL checks
    2. Quality Rubric (evaluator_rubric) - Performance scoring
    """
    # ✅ Start Timer: Everything indented below this runs inside the timer
    with statsd.timed("autonomic.auditor.latency", tags=[f"agent_id:{payload.get('agent_id')}"]):
        chat_id = payload.get("chat_id")
        agent_id = payload.get("agent_id")
        
        current_span = tracer.current_span()
        if current_span:
            current_span.set_tag("chat_id", chat_id)
            current_span.set_tag("agent_id", agent_id)
            current_span.set_tag("component", "AUDITOR")
        
        log_event(chat_id, "AUDITOR", "🧐 Picked up audit job from Queue...", "INFO")
        
        try:
            # STEP 1: FETCH CONTEXT
            log_event(chat_id, "AUDITOR", "📖 Fetching conversation and rules...", "INFO")
            
            chat_doc = db.collection("chats").document(chat_id).get()
            if not chat_doc.exists:
                log_event(chat_id, "AUDITOR", "❌ Chat not found in DB. Skipping.", "ERROR")
                return
            
            chat_data = chat_doc.to_dict()
            history = chat_data.get("history", [])
            
            # Check if audit already exists
            existing_audit = chat_data.get("audit_result")
            if existing_audit:
                log_event(
                    chat_id, 
                    "AUDITOR", 
                    f"⚠️ Previous audit found: {existing_audit.get('reason', '')} - Updating...", 
                    "WARNING"
                )
            
            # Get agent config
            agent_config = get_current_agent_config(agent_id)
            
            # Get both auditor_rules and evaluator_rubric
            upgrade_config = agent_config.get("upgrade_config", {})
            audit_rules_list = upgrade_config.get("auditor_rules", [])
            evaluator_rubric_list = upgrade_config.get("evaluator_rubric", [])
            
            if not audit_rules_list:
                audit_rules_list = ["Check for helpfulness and accuracy."]
            if not evaluator_rubric_list:
                evaluator_rubric_list = ["Agent provided correct information."]
            
            # Format rules for the prompt
            audit_rules = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(audit_rules_list)])
            evaluator_rubric = "\n".join([f"- {item}" for item in evaluator_rubric_list])
            
            # Get resources
            resources = agent_config.get("resources", {})
            knowledge_base = resources.get("knowledge_base_text", "")
            policies = resources.get("policy_text", "")
            
            # STEP 2: BUILD EVALUATION PROMPT
            log_event(chat_id, "AUDITOR", "🤖 Evaluating with LLM...", "INFO")
            
            user_input = payload['user_input']
            bot_response = payload['bot_response']
            
            # Build conversation history clearly separating turns
            conversation_context = ""
            if history:
                conversation_context = "=== CONVERSATION HISTORY (Read Chronologically) ===\n"
                for i, turn in enumerate(history):
                    role = turn.get("role", "unknown")
                    content = turn.get("content", "")
                    conversation_context += f"Turn {i+1} [{role.upper()}]: {content}\n"
                conversation_context += "===================================================\n"
            
            # --- STRICTER PROMPT IMPLEMENTATION ---
            prompt = f"""
You are a SENTINEL QUALITY AUDITOR for an Automotive AI Agent.
Your objective is to detect ANY failure, hallucination, or missed opportunity in the 'Current Exchange'.

### 1. INPUT DATA
<CONVERSATION_HISTORY>
{conversation_context}
</CONVERSATION_HISTORY>

<KNOWLEDGE_BASE_AND_INVENTORY>
{knowledge_base}
</KNOWLEDGE_BASE_AND_INVENTORY>

<LEGAL_POLICIES>
{policies}
</LEGAL_POLICIES>

<CURRENT_EXCHANGE_TO_AUDIT>
User Input: "{user_input}"
Bot Response: "{bot_response}"
</CURRENT_EXCHANGE_TO_AUDIT>

### 2. THE STANDARDS
You must evaluate the Bot Response based on three hierarchy levels.

**PRIORITY 1: SCOPE SAFETY (Immediate FAIL if violated)**
1. The Bot MUST NOT answer questions unrelated to the car dealership, vehicles, or buying process (e.g., cooking, politics, coding).
2. The Bot MUST NOT hallucinate inventory (making up cars not in the <KNOWLEDGE_BASE>).

**PRIORITY 2: AUDIT RULES (Binary Compliance Checks)**
If the bot violates ANY of these specific rules, it is a FAIL.
{audit_rules}

**PRIORITY 3: EVALUATOR RUBRIC (Quality & Strategy)**
Evaluate the quality of the response against these guidelines. Sub-par performance here is a FAIL.
{evaluator_rubric}

### 3. EVALUATION LOGIC
Analyze the 'Current Exchange' step-by-step:
1. **Context Check**: Does the response make sense given the <CONVERSATION_HISTORY>?
2. **Fact Check**: Is the information found in <KNOWLEDGE_BASE>?
3. **Missed Lead Check**: If the user showed *any* buying intent, did the bot try to capture contact info or move the sale forward?
4. **Rule Check**: Did it violate any Priority 2 Rule?

### 4. OUTPUT FORMAT
Return strictly valid JSON.
- If the bot failed ANY standard, verdict is "FAIL".
- The 'reason' must be specific (e.g., "Violated Rule #2: Failed to ask for email", "Hallucinated: 2024 Model X is not in inventory").
- Set 'priority' to HIGH for hallucinations or safety violations, MEDIUM for missed logic.

{{
  "verdict": "PASS" or "FAIL",
  "reason": "concise explanation of the error or confirmation of success",
  "priority": "HIGH" or "MEDIUM" or "LOW"
}}
"""
            
            # Call LLM with JSON mode, strictly limiting creativity
            llm_result = generate_response(
                prompt, 
                system_prompt="You are a precise JSON-outputting code auditor. Do not use Markdown. Output only the JSON object."
            )
            
            # Log raw response (Flattened to fix log viewer issues)
            raw_response = llm_result["text"]
            flattened_log = raw_response.replace("\n", " ").replace("\r", "").strip()
            log_event(
                chat_id,
                "AUDITOR",
                f"📝 Raw LLM response: {flattened_log[:300]}...",
                "INFO"
            )
            
            # Clean JSON markdown if present
            clean_text = raw_response.replace("```json", "").replace("```", "").strip()
            
            if not clean_text:
                log_event(chat_id, "AUDITOR", "❌ LLM returned empty response!", "ERROR")
                audit_result = {
                    "verdict": "FAIL",
                    "reason": "LLM evaluation failed - empty response",
                    "priority": "HIGH"
                }
            else:
                try:
                    audit_result = json.loads(clean_text)
                    log_event(chat_id, "AUDITOR", "✅ Valid JSON received", "INFO")
                except json.JSONDecodeError as e:
                    log_event(
                        chat_id,
                        "AUDITOR",
                        f"❌ Invalid JSON: {str(e)} | Response: {flattened_log[:300]}",
                        "ERROR"
                    )
                    audit_result = {
                        "verdict": "FAIL",
                        "reason": f"LLM evaluation failed - invalid JSON output.",
                        "priority": "HIGH"
                    }
            
            verdict = audit_result.get("verdict", "FAIL")
            reason = audit_result.get("reason", "Unknown error")
            priority = audit_result.get("priority", "LOW")
            
            # STEP 3: UPDATE CHAT WITH AUDIT RESULT
            log_event(chat_id, "AUDITOR", "💾 Saving audit result...", "INFO")
            
            # --- DATADOG METRIC ---
            statsd.increment(
                "autonomic.audit.verdict",
                tags=[
                    f"verdict:{verdict.lower()}",  # "pass" or "fail"
                    f"agent_id:{agent_id}",
                    f"reason:{reason[:30]}" # Truncate reason for tag safety
                ]
            )
            # Extract cost from LLM result
            metrics = llm_result.get("metrics", {})
            cost = metrics.get("estimated_cost", 0.0)

            statsd.gauge(
                "autonomic.backend.cost",
                cost,
                tags=[
                    "service:auditor", 
                    f"agent_id:{agent_id}"
                ]
            )
            db.collection("chats").document(chat_id).update({
                "audit_result": {
                    "verdict": verdict,
                    "reason": reason,
                    "priority": priority,
                    "timestamp": datetime.datetime.utcnow()
                }
            })
            
            log_event(
                chat_id, 
                "AUDITOR", 
                f"⚖️ Verdict: {verdict} | Priority: {priority} | Reason: {reason[:100]}", 
                "WARNING" if verdict == "FAIL" else "SUCCESS"
            )
            
            # STEP 4: ESCALATE IF FAILED
            if verdict == "FAIL":
                log_event(chat_id, "AUDITOR", "🚨 Escalating to Refiner...", "CRITICAL")
                
                refine_payload = {
                    "chat_id": chat_id,
                    "agent_id": agent_id,
                    "failure_reason": reason,
                    "original_input": user_input,
                    "bad_response": bot_response,
                    "full_history": history,
                    "priority": priority
                }
                
                publish_background_event(TOPIC_REFINE, refine_payload)
                log_event(chat_id, "AUDITOR", "✅ Refine job queued.", "INFO")
            else:
                log_event(chat_id, "AUDITOR", "✅ Case closed. No action needed.", "SUCCESS")
        
        except Exception as e:
            log_event(chat_id, "AUDITOR", f"🔥 Error: {str(e)}", "ERROR")
            
            if current_span:
                current_span.set_tag("error", True)
                current_span.set_tag("error.message", str(e))
            
            return


def start_auditor():
    """
    Start listening to Pub/Sub.
    This will be called in a background thread by main.py
    """
    log_event(None, "AUDITOR", "🚀 Auditor Service starting...", "INFO")
    listen_to_topic("sub-auditor", evaluate_interaction)