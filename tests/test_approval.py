from mcp_local.approval import approval_required
def test_delete_requires_approval():assert approval_required("delete_path",{"path":"x"})
def test_risky_shell_requires_approval():assert approval_required("run_command",{"command":"git push origin main"})
def test_safe_shell_does_not_require_approval():assert not approval_required("run_command",{"command":"git status"})
