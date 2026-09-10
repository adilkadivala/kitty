from langchain.tools import Tool
from typing import Dict, Any
from tavily import TavilyClient
import os

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))  

@Tool
def web_search(query: str) -> str:
    """Search the web for the given query."""
    return tavily_client.search(query)
    