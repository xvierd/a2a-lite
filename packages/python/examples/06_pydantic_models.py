"""
Example: Using Pydantic models for type-safe inputs/outputs.

This is the SIMPLEST way to handle complex data - just use Pydantic!

Run: python examples/06_pydantic_models.py
Test: a2a-lite test http://localhost:8787 create_user -p '{"user": {"name": "Alice", "email": "alice@example.com", "age": 30}}'
"""
from pydantic import BaseModel
from typing import List, Optional
from a2a_lite import Agent


# Define your models - that's it!
class User(BaseModel):
    name: str
    email: str
    age: int


class UserResponse(BaseModel):
    id: int
    user: User
    message: str


# Create agent
agent = Agent(
    name="UserService",
    description="Manages users with Pydantic models",
)

# Fake database
users_db: List[User] = []


@agent.skill("create_user", description="Create a new user")
async def create_user(user: User) -> dict:
    """
    Just use the Pydantic model as a parameter.
    A2A Lite automatically converts JSON to the model!
    """
    users_db.append(user)
    return {
        "id": len(users_db),
        "user": user.model_dump(),
        "message": f"Created user {user.name}",
    }


@agent.skill("list_users", description="List all users")
async def list_users() -> List[dict]:
    """Return all users."""
    return [u.model_dump() for u in users_db]


@agent.skill("find_user", description="Find user by name")
async def find_user(name: str) -> Optional[dict]:
    """Find a user by name."""
    for user in users_db:
        if user.name.lower() == name.lower():
            return user.model_dump()
    return None


if __name__ == "__main__":
    agent.run(port=8787)
