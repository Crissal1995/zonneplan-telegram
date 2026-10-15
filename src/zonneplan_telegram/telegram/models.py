"""
Minimal Telegram update models describing only the fields this bot reads.

Telegram sends a lot more fields per update; ``extra="ignore"`` keeps the parsing
forward-compatible without modelling the full Bot API surface.
"""

from pydantic import BaseModel, ConfigDict, Field


class Chat(BaseModel):
    """The subset of a chat needed to address the reply."""

    model_config = ConfigDict(extra="ignore")

    id: int


class User(BaseModel):
    """The subset of a Telegram user recorded by the analytics store."""

    model_config = ConfigDict(extra="ignore")

    id: int
    username: str | None = None


class Message(BaseModel):
    """The subset of a message that can carry a bot command."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    chat: Chat
    text: str | None = None
    from_: User | None = Field(default=None, alias="from")


class Update(BaseModel):
    """An incoming update delivered to the webhook."""

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: Message | None = None
