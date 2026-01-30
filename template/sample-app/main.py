import os

import httpx
from fastapi import FastAPI

app = FastAPI()

# PromptLedger API configuration
PROMPT_LEDGER_URL = os.getenv("PROMPT_LEDGER_URL", "http://prompt-ledger-api:8000")
PROMPT_LEDGER_API_KEY = os.getenv(
    "PROMPT_LEDGER_API_KEY", "dev-key-change-in-production"
)


@app.on_event("startup")
async def startup_event():
    """Create a sample prompt on startup."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{PROMPT_LEDGER_URL}/v1/prompts/user_welcome",
                headers={"X-API-Key": PROMPT_LEDGER_API_KEY},
                json={
                    "description": "Welcome message for new users",
                    "owner_team": "product",
                    "template_source": "Hello {{name}}! Welcome to {{app_name}}.",
                    "created_by": "sample-app",
                    "set_active": True,
                },
                timeout=10.0,
            )
            if response.status_code in (200, 201):
                print("Prompt 'user_welcome' created or already exists.")
            else:
                print(
                    f"Could not create prompt: {response.status_code} - {response.text}"
                )
    except Exception as e:
        print(f"Error connecting to PromptLedger API: {e}")


@app.get("/")
def read_root():
    return {"message": "Sample App is running. Use /welcome to test PromptLedger."}


@app.get("/welcome")
async def send_welcome_message():
    """Execute a prompt via PromptLedger API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PROMPT_LEDGER_URL}/v1/executions:run",
                headers={"X-API-Key": PROMPT_LEDGER_API_KEY},
                json={
                    "prompt_name": "user_welcome",
                    "environment": "production",
                    "variables": {"name": "New User", "app_name": "Our Awesome App"},
                    "model": {"provider": "openai", "model_name": "gpt-4o-mini"},
                    "params": {"temperature": 0.7, "max_tokens": 100},
                },
                timeout=30.0,
            )

            if response.status_code == 200:
                result = response.json()
                return {"welcome_message": result.get("response_text")}
            else:
                return {
                    "error": f"API error: {response.status_code}",
                    "details": response.text,
                }
    except Exception as e:
        return {"error": str(e)}
