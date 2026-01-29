import os

from fastapi import FastAPI

from prompt_ledger import PromptLedger

app = FastAPI()

# Initialize PromptLedger client
ledger = PromptLedger(
    api_url=os.getenv("PROMPT_LEDGER_URL"), api_key=os.getenv("PROMPT_LEDGER_API_KEY")
)


@app.on_event("startup")
def startup_event():
    # Example: Create a prompt on startup
    try:
        ledger.create_prompt(
            name="user_welcome",
            template="Hello {{name}}! Welcome to {{app_name}}.",
            description="Welcome message for new users",
            owner_team="product",
        )
        print("Prompt 'user_welcome' created or already exists.")
    except Exception as e:
        print(f"Could not create prompt: {e}")


@app.get("/")
def read_root():
    return {"message": "Sample App is running. Use /welcome to test PromptLedger."}


@app.get("/welcome")
def send_welcome_email():
    try:
        result = ledger.execute(
            prompt_name="user_welcome",
            variables={"name": "New User", "app_name": "Our Awesome App"},
            model={"provider": "openai", "model_name": "gpt-4o-mini"},
            params={"temperature": 0.7, "max_tokens": 100},
        )
        return {"welcome_message": result["response_text"]}
    except Exception as e:
        return {"error": str(e)}
