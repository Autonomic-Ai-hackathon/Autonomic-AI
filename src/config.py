# src/config.py
from ddtrace import patch_all
patch_all()

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
REGION = "us-central1"

# Database Collections
COL_ROUTER = "pointers" 
COL_AGENTS = "agents"   
COL_CHATS = "chats"     

# Pub/Sub Topics
TOPIC_AUDIT = os.getenv("TOPIC_AUDIT", "autonomic-audit-jobs")
TOPIC_REFINE = os.getenv("TOPIC_REFINE", "autonomic-refine-jobs")

# ✅ RENAMED 'TOPIC_EVAL' -> 'TOPIC_EVALUATE' to match refiner_worker.py imports
TOPIC_EVALUATE = os.getenv("TOPIC_EVALUATE", "autonomic-eval-jobs")

TOPIC_FEEDBACK = "autonomic-feedback-jobs"

@dataclass
class Config:
    """Application configuration."""
    project_id: str = PROJECT_ID
    datadog_api_key: str = os.getenv("DATADOG_API_KEY", "")
    vertex_ai_location: str = REGION
    
    def __post_init__(self):
        if not self.project_id or self.project_id == "your-project-id":
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is required")
        if not self.datadog_api_key:
            # Only enforce this locally or if strictly needed; 
            # on Cloud Run it might be injected differently, but good to keep if you rely on it.
            pass