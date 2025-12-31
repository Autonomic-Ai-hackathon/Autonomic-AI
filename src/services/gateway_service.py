from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel
from ddtrace import tracer
from datadog import statsd
from google.cloud import firestore
from src.core.db import get_current_agent_config, save_chat_log, should_trigger_audit
from src.core.llm import generate_response
from src.core.pubsub import publish_background_event
from src.core.logger import log_event
from src.config import TOPIC_AUDIT
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
# We explicitly tell Firestore which project to use
db = firestore.Client(project=os.getenv("PROJECT_ID"))

# Initialize Firestore
# This uses the Cloud Run Service Account credentials automatically


app = FastAPI(title="Autonomic AI Gateway")

# CORS Setup - Allows your frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_message: str
    chat_id: str
    agent_id: str

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🛠️ HELPER FUNCTIONS FOR RESET (Delete & Seed)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COLLECTIONS_TO_DELETE = ["chats", "logs", "agents", "pointers"]

def delete_collection_recursive(collection_name: str, chunk_size: int = 5000):
    """
    Deletes every document in the collection AND all descendant subcollections.
    """
    col_ref = db.collection(collection_name)
    deleted_count = db.recursive_delete(col_ref, chunk_size=chunk_size)
    return deleted_count

def perform_seed():
    """
    Seeds the database with the initial 'Car Auto Concierge' agent.
    """
    agent_id = "carsalesman101"
    version = 1
    
    # IMPORTANT: doc id is ONLY the agent_id
    agent_doc_id = agent_id 

    agent_data = {
        "agent_id": agent_id,
        "version": version,
        "created_at": firestore.SERVER_TIMESTAMP,

        "metadata": {
            "name": "Car Auto Concierge",
            "description": "A car salesman chatbot for X Industries.",
            "creator": "X",
            "agentid": agent_id,
            "version": version,
            "deployment_state": "ACTIVE",
            "upgrade_reason": "Initial deployment"
        },

        "config": {
            "model_id": "gemini-2.5-flash",
            "temperature": 0.2,
            "max_tokens": 800
        },

        "economics": {
            "likes": 0,
            "dislikes": 0,
            "input_token_count_prompt": 420,
            "budget_per_message": "0.5$"
        },

        "prompt": {
            "persona": {
                "role": "Senior Sales Concierge", 
                "tone": "High-Energy, Consultative"
            },
            "style_guide": [
                "Use Markdown.", 
                "Be definitive.", 
                "Keep responses under 100 words."
            ],
            "objectives": ["Help users find and purchase cars quickly."],
            "operational_guidelines": [
                "PROTOCOL 1: Always be polite."
            ]
        },

        "resources": {
            "knowledge_base_text": "INVENTORY: Model X (0 Stock, Incoming). Model Y (5 Stock, Available Now).",
            "policy_text": "LEGAL: Deposits are 100% refundable. Test drives require valid ID."
        },

        "upgrade_config": {
            "auditor_rules": [
                "CRITICAL FAIL if the user asks about a vehicle (Price, Specs, Availability) and the agent DOES NOT explicitly ask for an email address or phone number.",
                "FAIL if the agent mentions a vehicle model (like Model Z) that is NOT listed in the INVENTORY.",
                "FAIL if the agent response is longer than 100 words.",
                "FAIL if the agent uses the words 'sorry' or 'apologize' more than once."
            ],
            "evaluator_rubric": [
                "Did the agent strictly follow the 'Ask for Email' protocol?",
                "Did the agent offer the 'Incoming' Model X if asked?",
                "Was the response concise and high-energy?"
            ]
        }
    }

    pointer_data = {
        "agentid": agent_id,
        "current_version": version,
        "reason": "Initial Seed",
        "active_agent_doc_ref": agent_doc_id,
        "last_updated": firestore.SERVER_TIMESTAMP
    }

    # Write to Firestore
    db.collection("agents").document(agent_doc_id).set(agent_data)
    db.collection("pointers").document(agent_id).set(pointer_data)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚀 API ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/reset")
async def reset_database(x_admin_key: str = Header(None)):
    """
    ⚠️ DANGER: Deletes all data and reseeds the database.
    Requires header 'x-admin-key: hackathon-secret'
    """
    # Simple security check for the hackathon
    if x_admin_key != "hackathon-secret":
        # Log the unauthorized attempt
        log_event("SYSTEM", "RESET", "🔒 Unauthorized reset attempt denied", "WARNING")
        raise HTTPException(status_code=403, detail="Unauthorized. Missing or invalid admin key.")

    try:
        log_event("SYSTEM", "RESET", "⚠️ Starting Full Database Reset...", "WARNING")
        
        # 1. Delete all collections
        total_deleted = 0
        for name in COLLECTIONS_TO_DELETE:
            deleted = delete_collection_recursive(name)
            total_deleted += deleted
        
        # 2. Seed fresh data
        perform_seed()
        
        log_event("SYSTEM", "RESET", f"✅ Reset Complete. Deleted {total_deleted} docs and re-seeded.", "SUCCESS")
        
        return {
            "status": "success", 
            "message": "Database reset and seeded successfully.",
            "docs_deleted": total_deleted
        }
        
    except Exception as e:
        log_event("SYSTEM", "RESET", f"❌ Reset failed: {str(e)}", "ERROR")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


def build_system_prompt(agent_config: dict) -> str:
    """
    Constructs system prompt from seeded prompt structure.
    """
    prompt_data = agent_config["prompt"]
    resources = agent_config.get("resources", {})
    
    # Build from persona, objectives, guidelines, etc.
    persona = prompt_data["persona"]
    role = persona["role"]
    tone = persona["tone"]
    
    objectives = "\n".join([f"- {obj}" for obj in prompt_data["objectives"]])
    guidelines = "\n".join([f"- {g}" for g in prompt_data["operational_guidelines"]])
    style_guide = "\n".join([f"- {s}" for s in prompt_data["style_guide"]])
    
    # Extract resources
    knowledge_base = resources.get("knowledge_base_text", "")
    policies = resources.get("policy_text", "")
    
    # Build complete prompt
    system_prompt = f"""You are a {role} with a {tone} tone.

OBJECTIVES:
{objectives}

OPERATIONAL GUIDELINES:
{guidelines}

STYLE GUIDE:
{style_guide}
"""
    
    # Add knowledge base (if exists)
    if knowledge_base:
        system_prompt += f"""

KNOWLEDGE BASE:
{knowledge_base}
"""
    
    # Add policies (if exists)
    if policies:
        system_prompt += f"""

LEGAL POLICIES & CONSTRAINTS:
{policies}
You MUST follow these policies strictly. Do not deviate.
"""
    
    return system_prompt

@app.post("/chat")
async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Main entry point matching seeded data structure.
    """
    current_span = tracer.current_span()
    
    log_event(request.chat_id, "GATEWAY", f"📥 Request received for agent: {request.agent_id}", "INFO")
    
    try:
        # STEP 1: FETCH CONFIG
        log_event(request.chat_id, "GATEWAY", "🔍 Fetching agent configuration...", "INFO")
        
        agent_config = get_current_agent_config(request.agent_id)
        
        raw_version = agent_config.get('version', 1) 
        version = f"v{raw_version}"
        system_prompt = build_system_prompt(agent_config)
        model_id = agent_config['config']['model_id']
        
        if current_span:
            current_span.set_tag("agent.version", version)
            current_span.set_tag("agent.id", request.agent_id)
            current_span.set_tag("chat.id", request.chat_id)
        
        log_event(
            request.chat_id, 
            "GATEWAY", 
            f"✅ Config loaded: {version} using {model_id}", 
            "INFO",
            metadata={"version": version, "model": model_id}
        )
        
        # STEP 2: GENERATE RESPONSE
        log_event(request.chat_id, "GATEWAY", "🤖 Calling LLM...", "INFO")
        
        ai_result = generate_response(
            user_input=request.user_message,
            system_prompt=system_prompt,
            model_name=model_id
        )
        
        bot_text = ai_result["text"]
        metrics = ai_result["metrics"]
        
        log_event(
            request.chat_id, 
            "GATEWAY", 
            f"✅ LLM responded in {metrics['latency_ms']}ms", 
            "SUCCESS",
            metadata={
                "latency_ms": metrics['latency_ms'],
                "cost": metrics['estimated_cost'],
                "output_length": len(bot_text)
            }
        )
        
        # STEP 3: SAVE LOG
        log_event(request.chat_id, "GATEWAY", "💾 Saving chat history...", "INFO")
        
        save_chat_log(
            chat_id=request.chat_id,
            agent_id=request.agent_id,
            version=version,
            user_msg=request.user_message,
            bot_msg=bot_text,
            metrics=metrics
        )
        
        # STEP 4: SMART AUDIT TRIGGERING
        log_event(request.chat_id, "GATEWAY", "🔍 Checking if audit needed...", "INFO")
        
        if should_trigger_audit(request.chat_id):
            log_event(request.chat_id, "GATEWAY", "📨 Queuing audit job...", "INFO")
            real_agent_id = request.agent_id
            audit_payload = {
                "chat_id": request.chat_id,
                "agent_id": real_agent_id,
                "agent_version": version,
                "user_input": request.user_message,
                "bot_response": bot_text,
                "prompt_used": system_prompt
            }
            
            background_tasks.add_task(
                publish_background_event,
                TOPIC_AUDIT,
                audit_payload
            )
            
            log_event(request.chat_id, "GATEWAY", "✅ Audit queued.", "SUCCESS")
        else:
            log_event(
                request.chat_id, 
                "GATEWAY", 
                "⏸️ Audit skipped (previous audit failed - awaiting fix).", 
                "WARNING"
            )
        
        try:
            # Metrics Tracking
            statsd.increment("autonomic.chat.count", tags=[f"agent_id:{request.agent_id}", f"version:{version}"])
            statsd.histogram("autonomic.agent.latency", metrics["latency_ms"], tags=[f"agent_id:{request.agent_id}"])
            statsd.gauge("autonomic.agent.cost", metrics["estimated_cost"], tags=[f"agent_id:{request.agent_id}", f"version:{version}"])
            statsd.gauge("autonomic.agent.current_version", raw_version, tags=[f"agent_id:{request.agent_id}"])
            statsd.gauge("autonomic.agent.tokens.input", metrics.get("input_tokens", 0), tags=[
                f"agent_id:{request.agent_id}",
                f"chat_id:{request.chat_id}"
            ])

            statsd.gauge("autonomic.agent.tokens.output", metrics.get("output_tokens", 0), tags=[
                f"agent_id:{request.agent_id}",
                f"chat_id:{request.chat_id}"
            ])
            if metrics["estimated_cost"] > 0.10:
                statsd.increment("autonomic.budget.breach", tags=[f"agent_id:{request.agent_id}", f"chat_id:{request.chat_id}"])
                statsd.gauge("autonomic.budget.breach.amount", metrics["estimated_cost"], tags=[
        f"agent_id:{request.agent_id}",
        f"chat_id:{request.chat_id}",
        f"input_tokens:{metrics.get('input_tokens', 0)}",   # <--- HACK
        f"output_tokens:{metrics.get('output_tokens', 0)}"  # <--- HACK
    ])
            log_event(request.chat_id, "GATEWAY", "📊 Metrics sent to Datadog", "INFO")
            
        except Exception as e:
            log_event(
                request.chat_id, 
                "GATEWAY", 
                f"⚠️ Failed to send metrics: {str(e)}", 
                "ERROR",
                metadata={"error": str(e), "error_type": type(e).__name__}
            )

        # STEP 6: RETURN
        return {
            "response": bot_text,
            "meta": {
                "agent_version": version,
                "latency_ms": metrics["latency_ms"],
                "cost": metrics["estimated_cost"]
            }
        }
    
    except Exception as e:
        log_event(
            request.chat_id, 
            "GATEWAY", 
            f"❌ Error: {str(e)}", 
            "ERROR",
            metadata={"error_type": type(e).__name__}
        )
        
        if current_span:
            current_span.set_tag("error", True)
            current_span.set_tag("error.message", str(e))
        
        raise HTTPException(status_code=500, detail=str(e))