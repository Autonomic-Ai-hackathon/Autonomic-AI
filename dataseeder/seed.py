from google.cloud import firestore

# If running on Cloud Run / Cloud Functions / Cloud Shell (ADC), this is enough:
db = firestore.Client()

# If running locally with a service account, use this instead:
# from google.oauth2 import service_account
# creds = service_account.Credentials.from_service_account_file("./serviceAccountKey.json")
# db = firestore.Client(credentials=creds, project=creds.project_id)

def seed_database():
    print("Starting Firestore seed...")

    agent_id = "carsalesman101"
    version = 1

    # IMPORTANT: doc id is ONLY the agent_id now
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
            # THE "STRICT" RULES FOR THE AUDITOR 



            "auditor_rules": [
                # 1. THE TRAP: This specific phrasing forces the LLM to catch the missing email.
                "CRITICAL FAIL if the user asks about a vehicle (Price, Specs, Availability) and the agent DOES NOT explicitly ask for an email address or phone number.",
                
                # 2. Hallucination Check
                "FAIL if the agent mentions a vehicle model (like Model Z) that is NOT listed in the INVENTORY.",
                
                # 3. Concise Check (Objective measurement)
                "FAIL if the agent response is longer than 100 words.",
                
                # 4. Tone Check
                "FAIL if the agent uses the words 'sorry' or 'apologize' more than once."
            ],
            "evaluator_rubric": [
                "Did the agent strictly follow the 'Ask for Email' protocol?",
                "Did the agent offer the 'Incoming' Model X if asked?",
                "Was the response concise and high-energy?"
            ]
        }
    }

    # Pointer data (same collection, same doc id, same field names)
    pointer_data = {
        "agentid": agent_id,
        "current_version": version,
        "reason": "Initial Seed",
        "active_agent_doc_ref": agent_doc_id,
        "last_updated": firestore.SERVER_TIMESTAMP
    }

    try:
        # A) agents/{agent_id}
        db.collection("agents").document(agent_doc_id).set(agent_data)
        print(f"Created Agent Doc: agents/{agent_doc_id}")

        # B) pointers/{agent_id}
        db.collection("pointers").document(agent_id).set(pointer_data)
        print(f"Created Pointer Doc: pointers/{agent_id}")

        print("✅ Database Seed Complete! Auditor rules are now strictly configured.")
    except Exception as e:
        print(f"🔥 Error seeding database: {e}")

if __name__ == "__main__":
    seed_database()