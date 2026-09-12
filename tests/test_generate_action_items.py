import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp_tools.registry import notion_generate_action_items


SAMPLE_NOTES = (
    "Discussed Q3 marketing budget. Need final numbers from finance by Friday. "
    "Follow up with Alex on ad creative proposals."
)

SAMPLE_LIST = (
    "- Get final numbers from finance by Friday.\n"
    "- Follow up with Alex on ad creative proposals."
)


def test_generate_action_items_returns_markdown_list():
    mock_model = MagicMock()
    mock_model.bind.return_value.invoke.return_value.content = SAMPLE_LIST

    with patch("mcp_tools.registry.model", mock_model):
        result = notion_generate_action_items.invoke({"notes": SAMPLE_NOTES})

    assert any(line.strip().startswith("- ") for line in result.splitlines())
    mock_model.bind.assert_called()


def test_generate_action_items_wraps_errors():
    mock_model = MagicMock()
    mock_model.bind.return_value.invoke.side_effect = RuntimeError("llm down")

    with patch("mcp_tools.registry.model", mock_model):
        result = notion_generate_action_items.invoke({"notes": SAMPLE_NOTES})

    assert result.startswith("Tool error:")
