from app.kernel.context import ContextBudget, ContextManager


def test_zero_tool_budget_does_not_duplicate_tail_content():
    content, compacted = ContextManager._truncate_tokens("tool output", 0)

    assert content == ""
    assert compacted is True


def test_compaction_keeps_assistant_tool_call_and_matching_result_together():
    manager = ContextManager(ContextBudget(max_total_tokens=20, max_tool_output_tokens=20))
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "goal"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "type": "function"}],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "result"},
        {"role": "assistant", "content": "latest answer"},
    ]

    result, _ = manager.build(messages)

    assert result[-1]["content"] == "latest answer"
    tool_positions = [index for index, message in enumerate(result) if message.get("role") == "tool"]
    assistant_positions = [
        index
        for index, message in enumerate(result)
        if message.get("role") == "assistant" and message.get("tool_calls")
    ]
    assert all(index > assistant_positions[-1] for index in tool_positions)


def test_standalone_tool_messages_remain_budgetable():
    manager = ContextManager(ContextBudget(max_total_tokens=100))
    result, compacted = manager.build(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "goal"},
            {"role": "tool", "tool_call_id": "missing", "content": "orphan"},
            {"role": "assistant", "content": "answer"},
        ]
    )

    assert [message["role"] for message in result] == ["system", "user", "tool", "assistant"]
    assert compacted is True
