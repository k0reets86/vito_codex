from modules.mcp_tool_scope import enforce_mcp_tool_scope


def test_mcp_tool_scope_allows_publish_subset():
    schema = {"tools": [{"name": "create_post"}, {"name": "upload_media"}]}
    ok, reason = enforce_mcp_tool_scope(
        task_type="social_publish",
        adapter_schema=schema,
        input_data={"requested_tools": ["create_post"]},
    )
    assert ok is True
    assert "scope_ok" in reason


def test_mcp_tool_scope_blocks_out_of_scope_tool():
    schema = {"tools": [{"name": "create_post"}, {"name": "delete_user"}]}
    ok, reason = enforce_mcp_tool_scope(
        task_type="social_publish",
        adapter_schema=schema,
        input_data={"requested_tools": ["delete_user"]},
    )
    assert ok is False
    assert "out_of_scope" in reason

