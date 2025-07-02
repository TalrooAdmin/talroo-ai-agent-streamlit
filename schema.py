from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Any, Union
import uuid
from datetime import datetime

# --- Payload Schemas ---

class TextPayload(BaseModel):
    content: str

class UIComponentPayload(BaseModel):
    componentName: str
    componentProps: Dict[str, Any]

class UserActionPayload(BaseModel):
    actionType: str
    actionData: Dict[str, Any]

# --- Main ChatMessage Schema ---

class ChatMessage(BaseModel):
    """
    Defines the standardized message object for all interactions.
    """
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4()}")
    sender: Literal['user', 'ai']
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: Literal['text', 'ui_component', 'user_action']
    payload: Union[TextPayload, UIComponentPayload, UserActionPayload]
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)