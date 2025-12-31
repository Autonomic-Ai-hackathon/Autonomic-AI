# src/core/logger.py
import sys
import json
import os
import uuid
from datetime import datetime, timedelta
from src.core.db import db

# Fetch the service name set in cloudbuild.yaml (e.g., autonomic-gateway)
# This ensures your dashboard query "service:autonomic-*" works correctly.
SERVICE_NAME = os.getenv("DD_SERVICE", "autonomic-ai")

def log_event(
    chat_id: str, 
    component: str, 
    message: str, 
    level: str = "INFO",
    metadata: dict = None
):
    """
    Logs events to both Datadog (via stdout JSON) and Firestore.
    """
    
    # ------------------------------------------------------------------
    # 1. DATADOG LOGGING (JSON to Stdout)
    # ------------------------------------------------------------------
    
    # Construct the log entry as a dictionary
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": level,                # Datadog maps "status" to the visual alert level
        "message": f"[{component}] {message}",
        "service": SERVICE_NAME,        # CRITICAL: Matches your dashboard filter
        "component": component,
        "chat_id": chat_id,             # Allows filtering by specific chat
        "ddsource": "python"
    }

    # Merge metadata if provided
    if metadata:
        log_entry.update(metadata)

    # Print as a single-line JSON string. 
    # The Datadog agent automatically parses this JSON.
    print(json.dumps(log_entry), file=sys.stdout, flush=True)

    # ------------------------------------------------------------------
    # 2. FIRESTORE LOGGING (For History & Admin Panel)
    # ------------------------------------------------------------------
    
    # Only write to DB if we have a chat_id (to avoid cluttering DB with system noise)
    # or if it is a critical system error.
    if chat_id or level in ["ERROR", "CRITICAL"]:
        try:
            # Create a copy for Firestore to avoid mutating the original dict if needed later
            db_log = {
                "chat_id": chat_id,
                "component": component,
                "message": message,
                "level": level,
                "timestamp": datetime.utcnow(),
                "log_id": str(uuid.uuid4()),
                "service": SERVICE_NAME
            }
            
            if metadata:
                db_log["metadata"] = metadata
            
            # Write to top-level 'logs' collection
            db.collection("logs").add(db_log)
            
        except Exception as e:
            # Fallback print if Firestore write fails (don't crash the app)
            print(json.dumps({
                "status": "ERROR", 
                "message": f"Failed to write log to Firestore: {str(e)}",
                "service": SERVICE_NAME
            }), file=sys.stdout)


# ------------------------------------------------------------------
# LOG RETRIEVAL HELPERS (Used by Frontend/Admin)
# ------------------------------------------------------------------

def get_chat_logs(chat_id: str, limit: int = 100):
    """
    Fetch logs for a specific chat.
    """
    logs_ref = db.collection("logs") \
        .where("chat_id", "==", chat_id) \
        .order_by("timestamp", direction="ASCENDING") \
        .limit(limit)
    
    return [doc.to_dict() for doc in logs_ref.stream()]


def get_system_errors(hours: int = 24):
    """
    Get all system errors across all chats.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    errors_ref = db.collection("logs") \
        .where("level", "in", ["ERROR", "CRITICAL"]) \
        .where("timestamp", ">=", cutoff) \
        .order_by("timestamp", direction="DESCENDING") \
        .limit(500)
    
    return [doc.to_dict() for doc in errors_ref.stream()]


def cleanup_old_logs(days: int = 7):
    """
    Delete logs older than X days to save storage costs.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    old_logs = db.collection("logs") \
        .where("timestamp", "<", cutoff) \
        .limit(500)
    
    batch = db.batch()
    count = 0
    
    for doc in old_logs.stream():
        batch.delete(doc.reference)
        count += 1
    
    batch.commit()
    print(json.dumps({
        "status": "INFO",
        "message": f"🗑️ Deleted {count} old logs",
        "service": SERVICE_NAME
    }))
    return count