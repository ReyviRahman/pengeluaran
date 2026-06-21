from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Text
from sqlmodel import Field, SQLModel


class ConversationMessage(SQLModel, table=True):
    """Satu baris percakapan untuk sebuah chat Telegram."""

    __tablename__ = "conversation_messages"

    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(sa_column=Column(BigInteger, index=True))
    role: str = Field(sa_column=Column(Text))
    message_type: str = Field(sa_column=Column(Text))
    content: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True),
    )
