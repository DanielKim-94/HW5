"""Shared database tools for all Campus Customs homework agents."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from fastmcp import FastMCP


DATABASE = Path(__file__).resolve().parents[1] / "data" / "campus_customs_new.db"
mcp = FastMCP("Campus Customs")


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    # mode=ro fails if the working database is missing; never creates a new one.
    connection = sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")  # Keep each tool's reads in one snapshot.
        yield connection
    finally:
        connection.close()


def _one(connection: sqlite3.Connection, sql: str, values: tuple = ()) -> Any:
    row = connection.execute(sql, values).fetchone()
    return dict(row) if row is not None else None


def _all(connection: sqlite3.Connection, sql: str, values: tuple = ()) -> list[dict]:
    return [dict(row) for row in connection.execute(sql, values).fetchall()]


def _ticket(connection: sqlite3.Connection, ticket_id: int, expected_type: str) -> dict:
    ticket = _one(connection, "SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} does not exist.")
    if ticket["type"] != expected_type:
        raise ValueError(f"Ticket {ticket_id} must have type {expected_type}.")
    return ticket


@mcp.tool
def get_customer_order_context(ticket_id: int = 101) -> dict[str, Any]:
    """Read a customer-order ticket, exact-size stock, pricing, linked invoice/vendor,
    business date, and cash. Missing linked rows return null. Does not fulfill orders.
    """
    with _database() as connection:
        ticket = _ticket(connection, ticket_id, "customer_order")
        invoice = _one(connection, "SELECT * FROM invoices WHERE id = ?", (ticket["invoice_id"],))
        return {
            "ticket": ticket,
            "inventory": _one(connection, "SELECT * FROM inventory WHERE sku = ? AND size = ?", (ticket["sku"], ticket["size"])),
            "pricing": _one(connection, "SELECT * FROM pricing WHERE sku = ?", (ticket["sku"],)),
            "invoice": invoice,
            "vendor": _one(connection, "SELECT * FROM vendors WHERE id = ?", (invoice["vendor_id"],)) if invoice else None,
            "desk": _all(connection, "SELECT * FROM desk"),
            "cash_accounts": _all(connection, "SELECT * FROM cash_accounts ORDER BY name"),
            "uncertainties": [
                "SKU/size matches are not declared foreign keys.",
                "The invoice has no structured line quantities or delivery date.",
                "Payment does not establish a replenishment or fulfillment rule.",
                "Currency and stock-reservation semantics are unspecified.",
            ],
        }


@mcp.tool
def get_rent_payment_context(ticket_id: int = 102) -> dict[str, Any]:
    """Read a rent-notice ticket, linked lease, business date, accounts, all open
    invoices, and all recorded payments. Payments are unfiltered because their
    original kind/ref_id schema has no foreign keys. New payments use the
    documented invoice/rent convention. Does not pay rent or approve spending.
    """
    with _database() as connection:
        ticket = _ticket(connection, ticket_id, "rent_notice")
        return {
            "ticket": ticket,
            "lease": _one(connection, "SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)),
            "desk": _all(connection, "SELECT * FROM desk"),
            "cash_accounts": _all(connection, "SELECT * FROM cash_accounts ORDER BY name"),
            "open_invoices": _all(connection, "SELECT * FROM invoices WHERE status = ? ORDER BY due_date, id", ("open",)),
            "payments": _all(connection, "SELECT * FROM payments ORDER BY id"),
            "uncertainties": [
                "Payment kind/ref_id and account relationships are not defined by foreign keys.",
                "Returned payments are unfiltered; operational tools use kind invoice/rent with the corresponding record ID.",
                "Currency and available/reserved cash semantics are unspecified; every payment requires human approval.",
                "Open invoices do not necessarily represent every cash obligation.",
            ],
        }


@mcp.tool
def get_bulk_pricing_context(ticket_id: int = 103) -> dict[str, Any]:
    """Read a price-override ticket, exact-size stock, all stock sizes for its SKU,
    and recorded unit cost/list price. Other sizes are context, not substitutes.
    Does not approve discounts, change pricing, or reserve inventory.
    """
    with _database() as connection:
        ticket = _ticket(connection, ticket_id, "price_override")
        return {
            "ticket": ticket,
            "inventory": _one(connection, "SELECT * FROM inventory WHERE sku = ? AND size = ?", (ticket["sku"], ticket["size"])),
            "inventory_all_sizes": _all(connection, "SELECT * FROM inventory WHERE sku = ? ORDER BY size", (ticket["sku"],)),
            "pricing": _one(connection, "SELECT * FROM pricing WHERE sku = ?", (ticket["sku"],)),
            "uncertainties": [
                "SKU/size matches are not declared foreign keys.",
                "No discount amount, minimum margin, approval policy, or customer deadline is stored.",
                "No structured SKU-to-vendor mapping or restock commitment is stored.",
                "Currency and stock-reservation semantics are unspecified.",
            ],
        }


from operations import register_operations

register_operations(mcp, DATABASE)

if __name__ == "__main__":
    mcp.run(transport="stdio")
