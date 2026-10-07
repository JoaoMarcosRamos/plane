"""Actual Deep Agents harness with a scripted model and a closed product surface."""

from langchain_core.messages import AIMessage

from app.agent.agent import build_product_runtime_agent, run_agent
from tests.agent.conftest import ScriptedChatModel


def test_actual_harness_answers_without_personal_tools():
    model = ScriptedChatModel(
        responses=[AIMessage(content="The supplied risk has insufficient evidence.")]
    )
    executor = build_product_runtime_agent(model)
    run = run_agent("Analyze the authorized snapshot", agent=executor)
    assert run.ok and "insufficient evidence" in run.reply
    assert all(not tools for tools in model.published_tools)
    assert not run.tool_calls and not run.pending_approvals
