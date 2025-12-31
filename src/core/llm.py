import time
import vertexai
from vertexai.generative_models import GenerativeModel
from src.config import PROJECT_ID, REGION

# Initialize Vertex AI once
vertexai.init(project=PROJECT_ID, location=REGION)

def generate_response(user_input: str, system_prompt: str, model_name: str = "gemini-2.5-flash"):
    """
    Calls Gemini and returns the text + usage metrics with ACCURATE cost.
    Forces JSON output mode for structured responses.
    """
    start_time = time.time()
    
    # Force JSON output mode
    generation_config = {
        "temperature": 0.2,
        "max_output_tokens": 2000,
        "response_mime_type": "application/json"
    }
    
    model = GenerativeModel(
        model_name=model_name,
        system_instruction=[system_prompt],
        generation_config=generation_config
    )
    
    # Generate
    response = model.generate_content(user_input)
    end_time = time.time()
    latency_ms = (end_time - start_time) * 1000
    
    # Get actual token usage from API
    try:
        usage_metadata = response.usage_metadata
        input_tokens = usage_metadata.prompt_token_count
        output_tokens = usage_metadata.candidates_token_count
    except Exception:
        # Fallback: estimate tokens (1 token ≈ 4 chars)
        input_tokens = (len(system_prompt) + len(user_input)) // 4
        output_tokens = len(response.text) // 4
    
    # Accurate Gemini 2.5 Flash pricing (2025)
    INPUT_PRICE_PER_1M = 0.30   # $ per 1M tokens
    OUTPUT_PRICE_PER_1M = 2.50  # $ per 1M tokens
    
    input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_1M
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
    total_cost = input_cost + output_cost
    
    return {
        "text": response.text,
        "metrics": {
            "latency_ms": round(latency_ms, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated_cost": round(total_cost, 6),
            "model_used": model_name
        }
    }
