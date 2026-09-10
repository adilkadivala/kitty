"""LangChain chat model. Set LLM_PROVIDER=groq, ollama, or openrouter in .env"""

import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.callbacks import UsageMetadataCallbackHandler


usage_callback = UsageMetadataCallbackHandler()

load_dotenv()

MODEL_NAME = os.getenv("LLM_MODEL_NAME", "openai/gpt-oss-120b-cloud")
MODEL_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
API_KEY = os.getenv("LLM_API_KEY")



model = init_chat_model(
    model=MODEL_NAME,
    model_provider=MODEL_PROVIDER,
    api_key=API_KEY,
    temperature=0.7,
    timeout=120,
    max_retries=5,
    callbacks=[usage_callback]
)

def ask_assistant(prompt:str) -> str:
    messages = [
        SystemMessage(content="You are a helpful assistant that can answer questions and help with tasks."), 
        HumanMessage(content=prompt)
    ]
    response = ""
    for chunk in model.stream(messages):
        for block in chunk.content_blocks:
            if block["type"] == "text":
                response += block["text"]
                print(block["text"], end="", flush=True)    
    return response

