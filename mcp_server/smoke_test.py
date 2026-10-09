"""Protocol smoke test; does not claim a model-native tool call."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DATABASE = ROOT / "data/campus_customs_new.db"
CASES = [
    (101, "get_customer_order_context"),
    (102, "get_rent_payment_context"),
    (103, "get_bulk_pricing_context"),
]


def expected_rows(ticket_id):
    connection = sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    def rows(sql, args=()):
        return [dict(row) for row in connection.execute(sql, args)]
    def one(sql, args=()):
        found = rows(sql, args)
        return found[0] if found else None
    try:
        ticket = one("SELECT * FROM tickets WHERE id=?", (ticket_id,))
        expected = {"ticket": ticket}
        if ticket_id in (101, 103):
            expected["inventory"] = one("SELECT * FROM inventory WHERE sku=? AND size=?", (ticket["sku"], ticket["size"]))
            expected["pricing"] = one("SELECT * FROM pricing WHERE sku=?", (ticket["sku"],))
        if ticket_id in (101, 102):
            expected["desk"] = rows("SELECT * FROM desk")
            expected["cash_accounts"] = rows("SELECT * FROM cash_accounts ORDER BY name")
        if ticket_id == 101:
            invoice = one("SELECT * FROM invoices WHERE id=?", (ticket["invoice_id"],))
            expected["invoice"] = invoice
            expected["vendor"] = one("SELECT * FROM vendors WHERE id=?", (invoice["vendor_id"],)) if invoice else None
        elif ticket_id == 102:
            expected["lease"] = one("SELECT * FROM leases WHERE id=?", (ticket["lease_id"],))
            expected["open_invoices"] = rows("SELECT * FROM invoices WHERE status='open' ORDER BY due_date,id")
            expected["payments"] = rows("SELECT * FROM payments ORDER BY id")
        else:
            expected["inventory_all_sizes"] = rows("SELECT * FROM inventory WHERE sku=? ORDER BY size", (ticket["sku"],))
        return expected
    finally:
        connection.close()


async def main():
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["campus-customs"]
    before = {name: hashlib.sha256((ROOT / "data" / name).read_bytes()).hexdigest()
              for name in ("campus_customs.db", "campus_customs_new.db")}
    report = {
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
        "transport": "stdio",
        "config_source": ".mcp.json: mcpServers.campus-customs",
        "database": "data/campus_customs_new.db",
        "test_method": "Assistant-operated FastMCP client over actual MCP protocol; not model-native tool invocation",
        "assistant_native_status": "pending_mcp_restart_and_tool_availability",
        "issues": [
            {"issue": "FastMCP missing; sandbox blocked PyPI network", "resolution": "Installed FastMCP 3.4.8 in HW5 venv with approved network access", "status": "resolved"},
            {"issue": "Sandboxed Codex CLI could not resolve its home directory", "resolution": "Ran Codex configuration commands with approved normal user access", "status": "resolved"},
            {"issue": "Codex mcp list did not include project-local server", "resolution": "Registered campus-customs with codex mcp add; codex mcp get confirmed command and args", "status": "resolved"},
            {"issue": "Current chat tool catalog does not expose campus-customs tools", "resolution": "Restart the assistant MCP connection, then make native calls using the prompts below", "status": "pending"},
        ],
        "tests": [],
    }
    transport = StdioTransport(command=sys.executable if config["command"] == "python" else config["command"], args=config["args"], cwd=str(ROOT), keep_alive=False)
    async with Client(transport, timeout=30, init_timeout=30) as client:
        tools = await client.list_tools()
        report["discovered_tools"] = [tool.name for tool in tools]
        assert {name for _, name in CASES}.issubset(report["discovered_tools"])
        for ticket_id, name in CASES:
            prompt = f"Call the campus-customs MCP tool {name} with ticket_id={ticket_id} and return its complete actual output. Do not resolve the ticket."
            result = await client.call_tool(name, {"ticket_id": ticket_id})
            assert not result.is_error, f"MCP error from {name}"
            actual = result.structured_content
            if actual is None:
                actual = json.loads(next(block.text for block in result.content if block.type == "text"))
            expected = expected_rows(ticket_id)
            checks = {key: actual.get(key) == value for key, value in expected.items()}
            assert all(checks.values()), f"Database mismatch: {checks}"
            report["tests"].append({
                "prompt_used": "User's Problem 4 request directed this protocol call; no separate natural-language prompt was submitted to a model.",
                "assistant_prompt_to_run_after_restart": prompt,
                "tool_name": name,
                "arguments": {"ticket_id": ticket_id},
                "actual_output": actual,
                "mcp_content": [block.model_dump(mode="json") for block in result.content],
                "protocol_status": "passed",
                "database_comparison": {"all_returned_database_rows_match": True, "checks": checks},
                "assistant_native_status": "pending",
            })
    after = {name: hashlib.sha256((ROOT / "data" / name).read_bytes()).hexdigest() for name in before}
    assert before == after, "Database changed during read-only testing"
    report["database_hashes"] = after
    report["databases_unchanged"] = True
    (ROOT / "output/mcp_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Three actual MCP calls passed; all returned database rows match; databases unchanged. Native assistant calls pending.")


if __name__ == "__main__":
    asyncio.run(main())
