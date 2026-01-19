"""Script to seed initial AI models into the database."""

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.prompt_ledger.db.database import AsyncSessionLocal
from src.prompt_ledger.models.model import Model


async def seed_models():
    """Seed initial AI models."""
    
    models = [
        {
            "provider": "openai",
            "model_name": "gpt-4o",
            "max_tokens": 128000,
            "supports_streaming": True,
        },
        {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "max_tokens": 128000,
            "supports_streaming": True,
        },
        {
            "provider": "openai",
            "model_name": "gpt-4-turbo",
            "max_tokens": 128000,
            "supports_streaming": True,
        },
        {
            "provider": "openai",
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 16384,
            "supports_streaming": True,
        },
    ]
    
    async with AsyncSessionLocal() as db:
        for model_data in models:
            # Check if model already exists
            result = await db.execute(
                select(Model).where(
                    Model.provider == model_data["provider"],
                    Model.model_name == model_data["model_name"],
                )
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                model = Model(
                    model_id=uuid4(),
                    **model_data
                )
                db.add(model)
                print(f"Added model: {model_data['provider']}/{model_data['model_name']}")
            else:
                print(f"Model already exists: {model_data['provider']}/{model_data['model_name']}")
        
        await db.commit()
        print("Model seeding completed.")


if __name__ == "__main__":
    asyncio.run(seed_models())
