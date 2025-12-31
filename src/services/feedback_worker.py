from google.cloud import firestore
from src.core.db import db, get_current_configuration
from src.core.pubsub import listen_to_topic
from src.config import PROJECT_ID

def process_feedback(payload):
    """
    Payload: { "chat_id": "123", "score": 1, "agent_version_id": "car_concierge_v2" }
    """
    agent_v_id = payload.get("agent_version_id")
    score = payload.get("score") # 1 (Like) or -1 (Dislike)
    
    # --- STEP 1: LOG THE DETAIL (For Humans) ---
    db.collection("feedback").add({
        "chat_id": payload["chat_id"],
        "score": score,
        "comment": payload.get("comment", ""),
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    
    # --- STEP 2: UPDATE THE GENOME (For AI) ---
    # We update the SPECIFIC version that generated the chat
    agent_ref = db.collection("agents").document(agent_v_id)
    
    updates = {}
    
    if score > 0:
        # Atomic Increment: Safe for high concurrency
        updates["stats.likes"] = firestore.Increment(1)
    elif score < 0:
        updates["stats.dislikes"] = firestore.Increment(1)
        
    # Optional: If you track cost per feedback
    # updates["stats.cost_accrued"] = firestore.Increment(0.02)

    agent_ref.update(updates)
    
    print(f"✅ Updated Genome {agent_v_id}: Score logged.")

def start_feedback():
    listen_to_topic("sub-feedback", process_feedback)