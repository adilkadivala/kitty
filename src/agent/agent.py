import os
from dotenv import load_dotenv


load_dotenv()
from langchain.agents import create_agent, AgentState
from langchain.tools import Tool
from langchain_core.utils.uuid import uuid7
from langgraph.checkpoint.memory import InMemorySaver
from langchain.messages import AIMessage, HumanMessage

from mcp_tools.registry import get_tools

from pydantic import BaseModel
from dataclasses import dataclass

MODEL_NAME = os.getenv("LLM_MODEL_NAME", "openai/gpt-oss-120b-cloud")
MODEL_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
API_KEY = os.getenv("LLM_API_KEY")


tools = get_tools()

@dataclass
class Context:
    user_id: str

class Answer(BaseModel):
    summary: str
    confidence: float

class MyState(AgentState):
    user_id: str
    call_count: int

agent = create_agent(
    model=MODEL_NAME,
    model_provider=MODEL_PROVIDER,
    api_key=API_KEY,
    tools=tools, 
    response_format=Answer,
    state_schema=MyState,
    checkpointer=InMemorySaver(),
    context_schema=Context,
)


config = {"configurable": {"thread_id": str(uuid7())}}

# initial question
result = agent.stream_events(
    {"messages": [{"role": "user", "content": "What's the weather in San Francisco?"}]},
    config=config,
    context=Context(user_id="user-123"),
)

# follow up question
result = agent.stream_events(
    {"messages": [{"role": "user", "content": "What about tomorrow?"}]},
    config=config,
    context=Context(user_id="user-123"),
)

for snapshot in stream.values:
    # Each snapshot contains the full state at that point
    latest_message = snapshot["messages"][-1]
    if latest_message.content:
        if isinstance(latest_message, HumanMessage):
            print(f"User: {latest_message.content}")
        elif isinstance(latest_message, AIMessage):
            print(f"Agent: {latest_message.content}")
    elif latest_message.tool_calls:
        print(f"Calling tools: {[tc['name'] for tc in latest_message.tool_calls]}")