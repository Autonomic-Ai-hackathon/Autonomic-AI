from ddtrace import patch_all
patch_all()

import os
import uvicorn
import threading
from dotenv import load_dotenv
from datadog import initialize, statsd  

# Load local .env if present
load_dotenv()

# Determine Identity
ROLE = os.getenv("SERVICE_ROLE", "gateway").lower()
PORT = int(os.getenv("PORT", 8080))

# ✅ FORCE DATADOG INITIALIZATION
# This ensures we hit the correct Local IP in Cloud Run
initialize()
# Test metric immediately on startup
statsd.increment("autonomic.startup.test")
print("🧪 Test metric sent on startup")

print(f"🧬 Autonomic-AI Boot Sequence... Identity: [ {ROLE.upper()} ]")


if __name__ == "__main__":
    if ROLE == "gateway":
        from src.services.gateway_service import app
        # Start Web Server
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    
    elif ROLE == "auditor":
        from src.services.auditor_worker import start_auditor, app
        
        auditor_thread = threading.Thread(target=start_auditor, daemon=True)
        auditor_thread.start()
        
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    
    elif ROLE == "refiner":
        from src.services.refiner_worker import start_refiner, app
        
        refiner_thread = threading.Thread(target=start_refiner, daemon=True)
        refiner_thread.start()
        
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    
    elif ROLE == "evaluator":
        from src.services.evaluator_worker import start_evaluator, app
        
        evaluator_thread = threading.Thread(target=start_evaluator, daemon=True)
        evaluator_thread.start()
        
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    
    elif ROLE == "feedback":
        from src.services.feedback_worker import start_feedback, app
        
        feedback_thread = threading.Thread(target=start_feedback, daemon=True)
        feedback_thread.start()
        
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    
    else:
        print(f"❌ Critical Error: Unknown SERVICE_ROLE '{ROLE}'")
        exit(1)