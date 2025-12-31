# src/core/db.py
import time
from google.cloud import firestore
from src.config import PROJECT_ID, COL_ROUTER, COL_AGENTS, COL_CHATS

db = firestore.Client(project=PROJECT_ID)

def get_current_agent_config(agent_id: str):
    """
    Fetches agent config matching the seeded structure.
    Pointer points directly to agent doc (no version suffix).
    """
    # Step 1: Check the pointer
    pointer_doc = db.collection(COL_ROUTER).document(agent_id).get()
    if not pointer_doc.exists:
        raise ValueError(f"⚠️ No pointer found for agent_id={agent_id}")
    
    # Step 2: Get the active doc reference (just "carsalesman", not "carsalesman_v1")
    active_doc_ref = pointer_doc.get("active_agent_doc_ref")  # "carsalesman"
    
    # Step 3: Fetch the actual agent document
    agent_doc = db.collection(COL_AGENTS).document(active_doc_ref).get()
    if not agent_doc.exists:
        raise ValueError(f"CRITICAL: Pointer points to {active_doc_ref} but it doesn't exist!")
    
    return agent_doc.to_dict()

def save_chat_log(chat_id: str, agent_id: str, version: str, user_msg: str, bot_msg: str, metrics: dict):
    """
    Saves the interaction + cost metrics to Firestore.
    Uses ArrayUnion to APPEND to existing history (continues conversation).
    """
    doc_ref = db.collection(COL_CHATS).document(chat_id)
    data = {
        "metadata": {
            "agent_id": agent_id,
            "version": version,
            "last_active": time.time()
        },
        "history": firestore.ArrayUnion([
            {
                "role": "user",
                "content": user_msg,
                "timestamp": time.time()
            },
            {
                "role": "model",
                "content": bot_msg,
                "metrics": metrics,
                "timestamp": time.time()
            }
        ])
    }
    
    doc_ref.set(data, merge=True)

# ✅ NEW: Check if auditor should be triggered
def should_trigger_audit(chat_id: str) -> bool:
    """
    Returns True if auditor should be triggered.
    Logic:
    - Trigger if NO audit_result exists
    - Trigger if audit_result exists BUT verdict is "PASS"
    - Don't trigger if audit_result exists AND verdict is "FAIL"
    """
    doc_ref = db.collection(COL_CHATS).document(chat_id)
    chat_doc = doc_ref.get()
    
    if not chat_doc.exists:
        # New chat, trigger audit
        return True
    
    chat_data = chat_doc.to_dict()
    audit_result = chat_data.get("audit_result")
    
    if not audit_result:
        # No audit result exists, trigger audit
        return True
    
    verdict = audit_result.get("verdict", "").upper()
    
    if verdict == "PASS":
        # Previous audit passed, trigger new audit for new message
        return True
    elif verdict == "FAIL":
        # Previous audit failed, don't trigger (waiting for fix)
        return False
    else:
        # Unknown verdict, trigger to be safe
        return True
