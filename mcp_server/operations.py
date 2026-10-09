"""Operational MCP tools. Human decisions are never supplied by a model."""
import json
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hmac
import os
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import uuid4


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS resolution_reviews (
        id TEXT PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
        kind TEXT NOT NULL CHECK(kind IN ('simulated_restock','pricing_decision')),
        payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','denied','executed')),
        requested_on TEXT NOT NULL, approved_by TEXT, decision_on TEXT,
        UNIQUE(ticket_id,kind))""",

    """CREATE TABLE IF NOT EXISTS purchase_approvals (
        id TEXT PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
        vendor_id INTEGER NOT NULL REFERENCES vendors(id), sku TEXT NOT NULL,
        size TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0), unit_cost TEXT NOT NULL,
        amount TEXT NOT NULL, account TEXT NOT NULL REFERENCES cash_accounts(name),
        requested_on TEXT NOT NULL, lead_days_snapshot INTEGER NOT NULL,
        supplier_evidence TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','denied','executed')),
        approved_by TEXT, payment_id INTEGER REFERENCES payments(id))""",
    """CREATE UNIQUE INDEX IF NOT EXISTS one_active_purchase_per_ticket
        ON purchase_approvals(ticket_id) WHERE status IN ('pending','executed')""",
    """CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY, approval_id TEXT NOT NULL UNIQUE REFERENCES purchase_approvals(id),
        ticket_id INTEGER NOT NULL REFERENCES tickets(id), vendor_id INTEGER NOT NULL REFERENCES vendors(id),
        sku TEXT NOT NULL, size TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0),
        unit_cost TEXT NOT NULL, amount TEXT NOT NULL, ordered_on TEXT NOT NULL,
        earliest_arrival TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ordered' CHECK(status='ordered'))""",
    """CREATE TABLE IF NOT EXISTS payment_approvals (
        id TEXT PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
        kind TEXT NOT NULL CHECK(kind IN ('invoice','rent')), ref_id INTEGER NOT NULL,
        amount TEXT NOT NULL, account TEXT NOT NULL REFERENCES cash_accounts(name),
        due_date TEXT NOT NULL, requested_on TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','approved','denied','executed')),
        approved_by TEXT, decision_on TEXT, payment_id INTEGER REFERENCES payments(id),
        reason TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS message_drafts (
        id TEXT PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
        recipient TEXT NOT NULL, body TEXT NOT NULL, created_on TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status='draft'))""",
    """CREATE TABLE IF NOT EXISTS quote_drafts (
        ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id), sku TEXT NOT NULL,
        size TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0),
        unit_price TEXT NOT NULL, unit_cost_snapshot TEXT NOT NULL,
        rationale TEXT NOT NULL, created_on TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status='draft'))""",
    """CREATE TABLE IF NOT EXISTS fulfillments (
        ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id), sku TEXT NOT NULL,
        size TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0), fulfilled_on TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shipment_plans (
        id TEXT PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
        vendor_id INTEGER NOT NULL REFERENCES vendors(id), sku TEXT NOT NULL,
        size TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0), planned_on TEXT NOT NULL,
        earliest_arrival TEXT NOT NULL, evidence TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status='draft'))""",
    """CREATE TRIGGER IF NOT EXISTS cash_out_only BEFORE UPDATE OF balance ON cash_accounts
        WHEN NEW.balance < 0 OR NEW.balance > OLD.balance
        BEGIN SELECT RAISE(ABORT,'Balance must not be negative or increase'); END""",
    """CREATE TRIGGER IF NOT EXISTS stock_nonnegative BEFORE UPDATE OF qty ON inventory
        WHEN NEW.qty < 0 BEGIN SELECT RAISE(ABORT,'Stock must not be negative'); END""",
)


def money(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid monetary amount') from exc
    if not result.is_finite() or result < 0 or result != result.quantize(Decimal('0.01')):
        raise ValueError('Amount must be nonnegative, finite, and have at most two decimal places')
    return result


def register_operations(mcp, database: Path):
    @contextmanager
    def connect(write=False):
        conn = sqlite3.connect(database.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield conn
            if write:
                conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def one(c, sql, args=()):
        row = c.execute(sql, args).fetchone()
        return dict(row) if row else None

    def rows(c, sql, args=()):
        return [dict(row) for row in c.execute(sql, args)]

    def extensions(c):
        if not one(c, "SELECT name FROM sqlite_master WHERE type='table' AND name='payment_approvals'"):
            raise ValueError('Run the trusted initialize_shop_tools command before operational tools')

    def today(c):
        values = rows(c, 'SELECT date_today FROM desk')
        if len(values) != 1:
            raise ValueError('desk must contain exactly one business date')
        return date.fromisoformat(values[0]['date_today'])

    def ticket(c, ticket_id):
        value = one(c, 'SELECT * FROM tickets WHERE id=?', (ticket_id,))
        if not value:
            raise ValueError('Ticket does not exist')
        return value

    def admin(token):
        secret = os.environ.get('CAMPUS_HUMAN_APPROVAL_SECRET', '')
        if not secret or not hmac.compare_digest(secret, token):
            raise ValueError('Human-only command: trusted approval capability required')

    def obligation(c, t, kind, ref_id):
        if kind == 'invoice':
            if t['invoice_id'] != ref_id:
                raise ValueError('Invoice is not linked to this ticket')
            value = one(c, 'SELECT * FROM invoices WHERE id=?', (ref_id,))
            if not value or value['status'] != 'open':
                raise ValueError('Invoice is missing or is not open/unpaid')
            return money(value['amount']), value['due_date']
        if t['lease_id'] != ref_id:
            raise ValueError('Lease is not linked to this ticket')
        value = one(c, 'SELECT * FROM leases WHERE id=?', (ref_id,))
        if not value:
            raise ValueError('Lease does not exist')
        return money(value['monthly_rent']), value['next_due']

    @mcp.tool
    def initialize_shop_tools(human_capability: str) -> dict:
        """Human/backend setup only. Add operational tables to the working copy."""
        admin(human_capability)
        with connect(True) as c:
            for statement in SCHEMA:
                c.execute(statement)
        return {'initialized': True, 'tables': ['payment_approvals', 'message_drafts', 'quote_drafts', 'fulfillments', 'shipment_plans', 'purchase_approvals', 'purchases']}

    @mcp.tool
    def get_ticket_context(ticket_id: int) -> dict:
        """Read the ticket, shop date, and any operational records for this ticket."""
        with connect() as c:
            value = ticket(c, ticket_id)
            result = {'ticket': value, 'desk': rows(c, 'SELECT * FROM desk'), 'business_date': today(c).isoformat()}
            initialized = bool(one(c, "SELECT name FROM sqlite_master WHERE name='payment_approvals'"))
            result['operational_schema_initialized'] = initialized
            if initialized:
                for table in ('payment_approvals', 'message_drafts', 'quote_drafts', 'fulfillments', 'shipment_plans', 'purchase_approvals', 'purchases', 'resolution_reviews'):
                    result[table] = rows(c, f'SELECT * FROM {table} WHERE ticket_id=?', (ticket_id,))
            return result

    @mcp.tool
    def get_vendor_shipping_status(ticket_id: int, vendor_id: int) -> dict:
        """Read a vendor and all its open invoices. Shipping is blocked by any open bill.
        A lead time is not a confirmed arrival; supplier/SKU mapping remains unspecified.
        """
        with connect() as c:
            ticket(c, ticket_id)
            vendor = one(c, 'SELECT * FROM vendors WHERE id=?', (vendor_id,))
            if not vendor:
                raise ValueError('Vendor does not exist')
            invoices = rows(c, "SELECT * FROM invoices WHERE vendor_id=? AND status='open' ORDER BY id", (vendor_id,))
            if vendor['lead_days'] < 0:
                raise ValueError('Invalid vendor lead time')
            return {'vendor': vendor, 'open_unpaid_invoices': invoices,
                    'shipping_allowed': not invoices, 'business_date': today(c).isoformat(),
                    'earliest_arrival_if_shipped_today': (today(c) + timedelta(days=vendor['lead_days'])).isoformat() if not invoices else None,
                    'lead_time_assumption': 'Calendar-day arithmetic from scenario date; actual business/calendar-day policy and delivery are unconfirmed.'}

    @mcp.tool
    def request_payment_approval(ticket_id: int, kind: Literal['invoice', 'rent'], ref_id: int,
                                 account: str = 'checking', reason: str = '') -> dict:
        """Create a pending human request for the database obligation amount, never pay.
        Refuse insufficient cash. Repeated requests for the same obligation are reused.
        """
        with connect(True) as c:
            extensions(c)
            t = ticket(c, ticket_id)
            if t['status'] != 'open':
                raise ValueError('Payment request requires an open ticket')
            amount, due = obligation(c, t, kind, ref_id)
            if amount <= 0:
                raise ValueError('Payment amount must be positive')
            cash = one(c, 'SELECT * FROM cash_accounts WHERE name=?', (account,))
            if not cash or money(cash['balance']) < amount:
                raise ValueError('Payment refused: insufficient cash or missing account')
            existing = one(c, "SELECT * FROM payment_approvals WHERE kind=? AND ref_id=? AND due_date=? AND status IN ('pending','approved','executed')", (kind, ref_id, due))
            if existing:
                if existing['account'] != account or money(existing['amount']) != amount or existing['ticket_id'] != ticket_id:
                    raise ValueError('Conflicting request already exists for this obligation')
                return {'approval_request': existing, 'human_approval_required': existing['status'] == 'pending'}
            approval_id = str(uuid4())
            c.execute('INSERT INTO payment_approvals(id,ticket_id,kind,ref_id,amount,account,due_date,requested_on,status,reason) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (approval_id, ticket_id, kind, ref_id, str(amount), account, due, today(c).isoformat(), 'pending', reason[:2000]))
            return {'approval_request': one(c, 'SELECT * FROM payment_approvals WHERE id=?', (approval_id,)), 'human_approval_required': True}

    @mcp.tool
    def get_payment_approval(ticket_id: int, approval_id: str) -> dict:
        """Read the stored payment request for this ticket, including human decision."""
        with connect() as c:
            extensions(c)
            value = one(c, 'SELECT * FROM payment_approvals WHERE id=? AND ticket_id=?', (approval_id, ticket_id))
            if not value:
                raise ValueError('Approval request not found for this ticket')
            return value

    @mcp.tool
    def record_human_payment_decision(ticket_id: int, approval_id: str, approve: bool,
                                       human_name: str, human_capability: str) -> dict:
        """Human/backend only, never an agent tool. Decide a pending payment request."""
        admin(human_capability)
        if not human_name.strip():
            raise ValueError('Human identity is required')
        with connect(True) as c:
            extensions(c)
            value = one(c, 'SELECT * FROM payment_approvals WHERE id=? AND ticket_id=?', (approval_id, ticket_id))
            if not value or (value['status'] != 'pending' and not (value['status'] == 'approved' and not approve)):
                raise ValueError('Only pending requests can be approved; approved requests can be revoked by denial')
            c.execute('UPDATE payment_approvals SET status=?,approved_by=?,decision_on=? WHERE id=?',
                      ('approved' if approve else 'denied', human_name.strip()[:200], today(c).isoformat(), approval_id))
            return one(c, 'SELECT * FROM payment_approvals WHERE id=?', (approval_id,))

    def execute_payment(c, ticket_id, approval_id):
        extensions(c)
        request = one(c, 'SELECT * FROM payment_approvals WHERE id=? AND ticket_id=?', (approval_id, ticket_id))
        if not request:
            raise ValueError('Approval request not found for ticket')
        if request['status'] == 'executed':
            return {'payment': one(c, 'SELECT * FROM payments WHERE id=?', (request['payment_id'],)), 'already_executed': True}
        if request['status'] != 'approved' or not request['approved_by']:
            raise ValueError('Payment refused: explicit human approval required')
        t = ticket(c, ticket_id)
        if t['status'] != 'open':
            raise ValueError('Payment requires an open ticket')
        amount, due = obligation(c, t, request['kind'], request['ref_id'])
        if amount != money(request['amount']) or due != request['due_date']:
            raise ValueError('Obligation changed; new human approval required')
        if one(c, "SELECT id FROM payment_approvals WHERE kind=? AND ref_id=? AND due_date=? AND status='executed'", (request['kind'], request['ref_id'], due)):
            raise ValueError('Obligation already paid')
        cash = one(c, 'SELECT * FROM cash_accounts WHERE name=?', (request['account'],))
        if not cash or money(cash['balance']) < amount:
            raise ValueError('Payment refused: insufficient cash')
        remaining = money(cash['balance']) - amount
        paid_on = today(c).isoformat()
        c.execute('UPDATE cash_accounts SET balance=?,date=? WHERE name=?', (float(remaining), paid_on, request['account']))
        payment_id = c.execute('INSERT INTO payments(kind,ref_id,amount,account,paid_at,approved_by) VALUES(?,?,?,?,?,?)',
                               (request['kind'], request['ref_id'], float(amount), request['account'], paid_on, request['approved_by'])).lastrowid
        if request['kind'] == 'invoice':
            c.execute("UPDATE invoices SET status='paid' WHERE id=?", (request['ref_id'],))
            c.execute("UPDATE tickets SET notes=COALESCE(notes,'') || ? WHERE id=?", (f'\nInvoice payment {payment_id} recorded; fulfillment remains separate.', ticket_id))
        else:
            # No recurrence rule exists in the original DB. One month from the due
            # date, clamping to month end, is an explicit assignment convention.
            import calendar
            old = date.fromisoformat(due)
            year, month = (old.year + 1, 1) if old.month == 12 else (old.year, old.month + 1)
            next_due = old.replace(year=year, month=month, day=min(old.day, calendar.monthrange(year, month)[1]))
            c.execute('UPDATE leases SET next_due=? WHERE id=?', (next_due.isoformat(), request['ref_id']))
            c.execute("UPDATE tickets SET status='resolved',notes=COALESCE(notes,'') || ? WHERE id=?", (f'\nRent payment {payment_id} recorded with human approval.', ticket_id))
        c.execute("UPDATE payment_approvals SET status='executed',payment_id=? WHERE id=?", (payment_id, approval_id))
        return {'payment': one(c, 'SELECT * FROM payments WHERE id=?', (payment_id,)), 'cash_account': one(c, 'SELECT * FROM cash_accounts WHERE name=?', (request['account'],)), 'ticket': ticket(c, ticket_id), 'already_executed': False}


    @mcp.tool
    def execute_approved_payment(ticket_id: int, approval_id: str) -> dict:
        """Execute only a stored human-approved payment; atomic and replay-safe."""
        with connect(True) as c:
            return execute_payment(c, ticket_id, approval_id)

    @mcp.tool
    def save_message_draft(ticket_id: int, recipient: str, body: str) -> dict:
        """Store an unsent customer/vendor message draft. No communication is sent."""
        if not recipient.strip() or not body.strip() or len(body) > 4000:
            raise ValueError('Recipient and body required; body maximum 4000 characters')
        with connect(True) as c:
            extensions(c)
            ticket(c, ticket_id)
            draft_id = str(uuid4())
            c.execute('INSERT INTO message_drafts(id,ticket_id,recipient,body,created_on) VALUES(?,?,?,?,?)', (draft_id, ticket_id, recipient[:200], body, today(c).isoformat()))
            return one(c, 'SELECT * FROM message_drafts WHERE id=?', (draft_id,))

    @mcp.tool
    def save_quote_draft(ticket_id: int, unit_price: str, rationale: str) -> dict:
        """Store a ticket-specific unsent quote at or above recorded cost. No approval,
        global price change, revenue, or stock reservation is implied.
        """
        with connect(True) as c:
            extensions(c)
            t = ticket(c, ticket_id)
            if t['type'] != 'price_override' or not t['qty'] or t['qty'] <= 0:
                raise ValueError('A positive-quantity price-override ticket is required')
            pricing = one(c, 'SELECT * FROM pricing WHERE sku=?', (t['sku'],))
            if not pricing or money(unit_price) < money(pricing['unit_cost']):
                raise ValueError('Quote refused: missing pricing or below recorded cost')
            c.execute('INSERT INTO quote_drafts(ticket_id,sku,size,qty,unit_price,unit_cost_snapshot,rationale,created_on) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET unit_price=excluded.unit_price,unit_cost_snapshot=excluded.unit_cost_snapshot,rationale=excluded.rationale,created_on=excluded.created_on',
                      (ticket_id, t['sku'], t['size'], t['qty'], str(money(unit_price)), str(money(pricing['unit_cost'])), rationale[:2000], today(c).isoformat()))
            return {'quote': one(c, 'SELECT * FROM quote_drafts WHERE ticket_id=?', (ticket_id,)), 'draft_only': True, 'approval_policy_unspecified': True}

    @mcp.tool
    def plan_vendor_shipment(ticket_id: int, vendor_id: int, qty: int, supplier_evidence: str) -> dict:
        """Store a shipment DRAFT using vendor lead_days only when no open invoice exists.
        Requires supplied evidence for the SKU/vendor match. Never ship or add stock.
        """
        if qty <= 0 or not supplier_evidence.strip():
            raise ValueError('Positive quantity and supplier evidence are required')
        with connect(True) as c:
            extensions(c)
            t = ticket(c, ticket_id)
            if not t['sku'] or not t['size']:
                raise ValueError('Ticket has no product/size')
            if one(c, "SELECT id FROM invoices WHERE vendor_id=? AND status='open'", (vendor_id,)):
                raise ValueError('Shipment refused: vendor has an open unpaid invoice')
            vendor = one(c, 'SELECT * FROM vendors WHERE id=?', (vendor_id,))
            if not vendor or vendor['lead_days'] < 0:
                raise ValueError('Vendor missing or invalid lead time')
            arrival = today(c) + timedelta(days=vendor['lead_days'])
            plan_id = str(uuid4())
            c.execute('INSERT INTO shipment_plans(id,ticket_id,vendor_id,sku,size,qty,planned_on,earliest_arrival,evidence) VALUES(?,?,?,?,?,?,?,?,?)',
                      (plan_id, ticket_id, vendor_id, t['sku'], t['size'], qty, today(c).isoformat(), arrival.isoformat(), supplier_evidence[:2000]))
            return {'shipment_plan': one(c, 'SELECT * FROM shipment_plans WHERE id=?', (plan_id,)), 'draft_only': True, 'lead_time_assumption': 'Calendar days; unconfirmed policy. Evidence text is not independently verified.'}

    @mcp.tool
    def fulfill_customer_order(ticket_id: int) -> dict:
        """Fulfill a customer_order from actual exact-size stock; atomically decrement
        inventory and resolve ticket. Idempotent, no revenue or imagined restock.
        """
        with connect(True) as c:
            extensions(c)
            t = ticket(c, ticket_id)
            existing = one(c, 'SELECT * FROM fulfillments WHERE ticket_id=?', (ticket_id,))
            if existing:
                return {'fulfillment': existing, 'already_fulfilled': True}
            if t['type'] != 'customer_order' or t['status'] != 'open' or not t['qty'] or t['qty'] <= 0:
                raise ValueError('An open positive-quantity customer_order is required')
            stock = one(c, 'SELECT * FROM inventory WHERE sku=? AND size=?', (t['sku'], t['size']))
            if not stock or stock['qty'] < t['qty']:
                raise ValueError('Fulfillment refused: insufficient exact-size stock')
            c.execute('UPDATE inventory SET qty=qty-? WHERE sku=? AND size=?', (t['qty'], t['sku'], t['size']))
            c.execute('INSERT INTO fulfillments VALUES(?,?,?,?,?)', (ticket_id, t['sku'], t['size'], t['qty'], today(c).isoformat()))
            c.execute("UPDATE tickets SET status='resolved',notes=COALESCE(notes,'') || ? WHERE id=?", ('\nFulfilled from recorded stock; no revenue added.', ticket_id))
            return {'fulfillment': one(c, 'SELECT * FROM fulfillments WHERE ticket_id=?', (ticket_id,)), 'ticket': ticket(c, ticket_id), 'already_fulfilled': False}

    @mcp.tool
    def list_shop_tickets() -> dict:
        """Read the three assignment tickets and their current stored statuses."""
        with connect() as c:
            return {'tickets': rows(c, 'SELECT * FROM tickets WHERE id IN (101,102,103) ORDER BY id'),
                    'business_date': today(c).isoformat()}

    @mcp.tool
    def get_checking_balance() -> dict:
        """Read the actual checking account; no currency is inferred."""
        with connect() as c:
            cash = one(c, "SELECT * FROM cash_accounts WHERE name='checking'")
            if not cash:
                raise ValueError('Checking account not found')
            return {'account': cash, 'business_date': today(c).isoformat(), 'currency': None}

    @mcp.tool
    def get_cash_obligations(ticket_id: int) -> dict:
        """Read cash, open invoices, leases, payments and shop date without switching tickets."""
        with connect() as c:
            ticket(c, ticket_id)
            return {'ticket_id': ticket_id, 'desk': rows(c, 'SELECT * FROM desk'),
                    'cash_accounts': rows(c, 'SELECT * FROM cash_accounts ORDER BY name'),
                    'open_invoices': rows(c, "SELECT * FROM invoices WHERE status='open' ORDER BY id"),
                    'leases': rows(c, 'SELECT * FROM leases ORDER BY id'),
                    'payments': rows(c, 'SELECT * FROM payments ORDER BY id'),
                    'uncertainties': ['Known obligations are not a complete cash forecast; currency/reservations are unspecified.']}

    @mcp.tool
    def list_approval_requests(ticket_id: int | None = None) -> dict:
        """Read durable payment/purchase requests, including executed and denied ones."""
        with connect() as c:
            extensions(c)
            if ticket_id is not None:
                ticket(c, ticket_id)
            where = ' WHERE ticket_id=?' if ticket_id is not None else ''
            args = (ticket_id,) if ticket_id is not None else ()
            return {'payments': rows(c, 'SELECT * FROM payment_approvals' + where + ' ORDER BY requested_on,id', args),
                    'purchases': rows(c, 'SELECT * FROM purchase_approvals' + where + ' ORDER BY requested_on,id', args)}

    @mcp.tool
    def approve_and_execute_payment(ticket_id: int, approval_id: str, human_name: str, human_capability: str) -> dict:
        """Human-only: grant a pending payment and execute in ONE transaction.
        Insufficient cash/stale obligations roll back the decision as well as payment.
        An already-executed request returns its original payment without charging again.
        """
        admin(human_capability)
        if not human_name.strip():
            raise ValueError('Human identity is required')
        with connect(True) as c:
            extensions(c)
            request = one(c, 'SELECT * FROM payment_approvals WHERE id=? AND ticket_id=?', (approval_id, ticket_id))
            if not request:
                raise ValueError('Approval request not found for ticket')
            if request['status'] == 'executed':
                return execute_payment(c, ticket_id, approval_id)
            if request['status'] != 'pending':
                raise ValueError('Only a pending payment can be approved through this route')
            c.execute("UPDATE payment_approvals SET status='approved',approved_by=?,decision_on=? WHERE id=?", (human_name.strip()[:200], today(c).isoformat(), approval_id))
            return execute_payment(c, ticket_id, approval_id)

    @mcp.tool
    def request_purchase_approval(ticket_id: int, vendor_id: int, qty: int, supplier_evidence: str,
                                  account: str = 'checking') -> dict:
        """Prepare a purchase for the ticket's exact product/size at recorded unit cost.
        Require supplied supplier evidence. Never debit cash or invent received stock.
        Only one pending/executed purchase per ticket; shipping block rechecked at approval.
        """
        if qty <= 0 or not supplier_evidence.strip() or len(supplier_evidence) > 2000:
            raise ValueError('Positive quantity and supplier evidence (up to 2000 characters) are required')
        with connect(True) as c:
            extensions(c)
            t = ticket(c, ticket_id)
            if t['status'] != 'open' or not t['sku'] or not t['size'] or not t['qty']:
                raise ValueError('An open product ticket is required for a purchase')
            vendor = one(c, 'SELECT * FROM vendors WHERE id=?', (vendor_id,))
            pricing = one(c, 'SELECT * FROM pricing WHERE sku=?', (t['sku'],))
            stock = one(c, 'SELECT * FROM inventory WHERE sku=? AND size=?', (t['sku'], t['size']))
            if not vendor or not pricing or not stock or vendor['lead_days'] < 0:
                raise ValueError('Vendor/pricing/stock missing or lead time invalid')
            if qty > max(0, t['qty'] - stock['qty']):
                raise ValueError('Purchase quantity exceeds the recorded ticket stock shortage')
            cost = money(pricing['unit_cost'])
            amount = cost * qty
            if amount <= 0:
                raise ValueError('Purchase amount must be positive')
            cash = one(c, 'SELECT * FROM cash_accounts WHERE name=?', (account,))
            if not cash or money(cash['balance']) < amount:
                raise ValueError('Purchase refused: insufficient cash')
            existing = one(c, "SELECT * FROM purchase_approvals WHERE ticket_id=? AND status IN ('pending','executed')", (ticket_id,))
            if existing:
                if (existing['vendor_id'], existing['qty'], existing['account'], money(existing['unit_cost'])) != (vendor_id, qty, account, cost):
                    raise ValueError('Conflicting purchase request already exists for this ticket')
                return {'approval_request': existing, 'human_approval_required': existing['status'] == 'pending'}
            approval_id = str(uuid4())
            c.execute('INSERT INTO purchase_approvals(id,ticket_id,vendor_id,sku,size,qty,unit_cost,amount,account,requested_on,lead_days_snapshot,supplier_evidence,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (approval_id, ticket_id, vendor_id, t['sku'], t['size'], qty, str(cost), str(amount), account, today(c).isoformat(), vendor['lead_days'], supplier_evidence, 'pending'))
            return {'approval_request': one(c, 'SELECT * FROM purchase_approvals WHERE id=?', (approval_id,)),
                    'human_approval_required': True,
                    'vendor_has_open_unpaid_invoice': bool(one(c, "SELECT id FROM invoices WHERE vendor_id=? AND status='open'", (vendor_id,))),
                    'cost_assumption': 'Recorded unit_cost only; supplier evidence/price is not independently verified. No receipt is modeled.'}

    @mcp.tool
    def approve_and_execute_purchase(ticket_id: int, approval_id: str, human_name: str, human_capability: str) -> dict:
        """Human-only: atomically approve and record a prepared cash-out purchase.
        Recheck price/product/shortage/lead time, vendor unpaid bills, and available cash.
        Never add stock or contact a vendor; repeated approval is idempotent.
        """
        admin(human_capability)
        if not human_name.strip():
            raise ValueError('Human identity is required')
        with connect(True) as c:
            extensions(c)
            request = one(c, 'SELECT * FROM purchase_approvals WHERE id=? AND ticket_id=?', (approval_id, ticket_id))
            if not request:
                raise ValueError('Purchase request not found for ticket')
            if request['status'] == 'executed':
                return {'purchase': one(c, 'SELECT * FROM purchases WHERE approval_id=?', (approval_id,)), 'payment': one(c, 'SELECT * FROM payments WHERE id=?', (request['payment_id'],)), 'already_executed': True}
            if request['status'] != 'pending':
                raise ValueError('Only pending purchases can be approved')
            t = ticket(c, ticket_id)
            pricing = one(c, 'SELECT * FROM pricing WHERE sku=?', (t['sku'],))
            stock = one(c, 'SELECT * FROM inventory WHERE sku=? AND size=?', (t['sku'], t['size']))
            vendor = one(c, 'SELECT * FROM vendors WHERE id=?', (request['vendor_id'],))
            if t['status'] != 'open' or (t['sku'], t['size']) != (request['sku'], request['size']) or not pricing or not stock or not vendor:
                raise ValueError('Purchase facts changed; new request required')
            if money(pricing['unit_cost']) != money(request['unit_cost']) or vendor['lead_days'] != request['lead_days_snapshot'] or request['qty'] > max(0, t['qty'] - stock['qty']):
                raise ValueError('Purchase price/lead time/shortage changed; new request required')
            if one(c, "SELECT id FROM invoices WHERE vendor_id=? AND status='open'", (request['vendor_id'],)):
                raise ValueError('Purchase refused: vendor has an open unpaid invoice')
            cash = one(c, 'SELECT * FROM cash_accounts WHERE name=?', (request['account'],))
            amount = money(request['amount'])
            if amount != money(request['unit_cost']) * request['qty']:
                raise ValueError('Purchase amount does not match its prepared quantity and unit cost')
            if not cash or money(cash['balance']) < amount:
                raise ValueError('Purchase refused: insufficient cash')
            current_date = today(c)
            arrival = current_date + timedelta(days=vendor['lead_days'])
            purchase_id = c.execute('INSERT INTO purchases(approval_id,ticket_id,vendor_id,sku,size,qty,unit_cost,amount,ordered_on,earliest_arrival) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                    (approval_id, ticket_id, request['vendor_id'], request['sku'], request['size'], request['qty'], request['unit_cost'], request['amount'], current_date.isoformat(), arrival.isoformat())).lastrowid
            c.execute('UPDATE cash_accounts SET balance=?,date=? WHERE name=?', (float(money(cash['balance']) - amount), current_date.isoformat(), request['account']))
            payment_id = c.execute("INSERT INTO payments(kind,ref_id,amount,account,paid_at,approved_by) VALUES('purchase',?,?,?,?,?)", (purchase_id, float(amount), request['account'], current_date.isoformat(), human_name.strip()[:200])).lastrowid
            c.execute("UPDATE purchase_approvals SET status='executed',approved_by=?,payment_id=? WHERE id=?", (human_name.strip()[:200], payment_id, approval_id))
            c.execute("UPDATE tickets SET notes=COALESCE(notes,'') || ? WHERE id=?", (f'\nPurchase {purchase_id} recorded with human approval; stock receipt unconfirmed.', ticket_id))
            return {'purchase': one(c, 'SELECT * FROM purchases WHERE id=?', (purchase_id,)), 'payment': one(c, 'SELECT * FROM payments WHERE id=?', (payment_id,)),
                    'cash_account': one(c, 'SELECT * FROM cash_accounts WHERE name=?', (request['account'],)), 'already_executed': False,
                    'receipt_confirmed': False, 'lead_time_assumption': 'Calendar days from desk date; not a delivery confirmation.'}

    @mcp.tool
    def deny_prepared_request(ticket_id: int, approval_id: str, request_type: Literal['payment','purchase'], human_name: str, human_capability: str) -> dict:
        """Human-only denial of an unexecuted request; no spending."""
        admin(human_capability)
        if not human_name.strip():
            raise ValueError('Human identity required')
        table = 'payment_approvals' if request_type == 'payment' else 'purchase_approvals'
        with connect(True) as c:
            request = one(c, f'SELECT * FROM {table} WHERE id=? AND ticket_id=?', (approval_id, ticket_id))
            if not request or request['status'] not in ('pending', 'approved'):
                raise ValueError('Only pending or approved/unexecuted requests can be denied')
            c.execute(f"UPDATE {table} SET status='denied',approved_by=? WHERE id=?", (human_name.strip()[:200], approval_id))
            return one(c, f'SELECT * FROM {table} WHERE id=?', (approval_id,))

    @mcp.tool
    def reset_working_database(human_capability: str, confirmation: Literal['RESET_WORKING_DATABASE']) -> dict:
        """Human-only reset via SQLite backup from original into the fixed working DB.
        Recreate empty operational schema. Audit files remain untouched; original read-only.
        """
        admin(human_capability)
        import hashlib
        original = database.with_name('campus_customs.db')
        if original.resolve() == database.resolve():
            raise ValueError('Reset target must differ from original')
        before = hashlib.sha256(original.read_bytes()).hexdigest()
        source = sqlite3.connect(original.as_uri() + '?mode=ro', uri=True)
        target = sqlite3.connect(database.as_uri() + '?mode=rw', uri=True)
        try:
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Original database failed integrity check')
            source.backup(target)
            target.execute('PRAGMA foreign_keys=ON')
            target.execute('BEGIN IMMEDIATE')
            for statement in SCHEMA:
                target.execute(statement)
            target.commit()
        except BaseException:
            target.rollback()
            raise
        finally:
            target.close()
            source.close()
        if hashlib.sha256(original.read_bytes()).hexdigest() != before:
            raise RuntimeError('Original hash changed during reset')
        return {'reset': True, 'original_sha256': before, 'operational_requests_cleared': True,
                'audit_preserved': True, 'extensions_reinitialized': True}

    @mcp.tool
    def prepare_resolution_review(ticket_id: int, kind: Literal['simulated_restock','pricing_decision'], rationale: str, unit_price: str | None = None) -> dict:
        """Prepare a non-payment business decision. Never approve, receive stock or resolve.
        Restock explicitly assumes the paid linked reprint covers only the ticket quantity,
        calendar-day lead time and classroom-only receipt. Pricing completion is an unsent
        conditional response to a price_override, not supply/customer acceptance/revenue.
        """
        with connect(True) as c:
            extensions(c)
            t = ticket(c,ticket_id)
            if t['status'] != 'open' or not rationale.strip(): raise ValueError('Open ticket and rationale required')
            if kind == 'simulated_restock':
                if t['type'] != 'customer_order': raise ValueError('Customer order required')
                inv = one(c,'SELECT * FROM invoices WHERE id=?',(t['invoice_id'],))
                if not inv or inv['status']!='paid' or t['sku'] not in inv['description'] or t['size'] not in inv['description'].split(): raise ValueError('Paid linked invoice with recorded SKU/size evidence required')
                vendor = one(c,'SELECT * FROM vendors WHERE id=?',(inv['vendor_id'],))
                if one(c,"SELECT id FROM invoices WHERE vendor_id=? AND status='open'",(vendor['id'],)): raise ValueError('Vendor has unpaid invoice')
                payment = one(c,"SELECT * FROM payments WHERE kind='invoice' AND ref_id=?",(inv['id'],))
                if not payment: raise ValueError('Invoice payment evidence required')
                payload={'simulation':True,'qty':t['qty'],'sku':t['sku'],'size':t['size'],'vendor_id':vendor['id'],
                    'lead_days':vendor['lead_days'],'earliest_arrival':(date.fromisoformat(payment['paid_at'])+timedelta(days=vendor['lead_days'])).isoformat(),
                    'source':inv['description'],'assumptions':['Paid reprint covers only requested ticket quantity; invoice has no line quantity','Calendar days from recorded payment date','Classroom simulation only; no physical delivery claimed'], 'rationale':rationale}
            else:
                if t['type']!='price_override': raise ValueError('Price-override ticket required')
                pricing=one(c,'SELECT * FROM pricing WHERE sku=?',(t['sku'],))
                price=money(unit_price)
                if price < money(pricing['unit_cost']): raise ValueError('Below-cost proposal refused by implementation safeguard')
                payload={'simulation':False,'sku':t['sku'],'size':t['size'],'qty':t['qty'],'unit_price':str(price),'unit_cost':str(money(pricing['unit_cost'])),'list_price':str(money(pricing['list_price'])),
                    'rationale':rationale,'completion_rule':'Resolve price decision only by saving a human-authorized unsent conditional quote; no fulfillment or acceptance claimed',
                    'supply_caveat':'No stock reservation, replenishment, supplier commitment, customer acceptance or revenue. Fulfillment requires separate confirmation.'}
            existing=one(c,'SELECT * FROM resolution_reviews WHERE ticket_id=? AND kind=?',(ticket_id,kind))
            if existing:
                if json.loads(existing['payload'])!=payload: raise ValueError('Existing review differs; do not silently replace a decision')
                return {'review':existing,'payment_required':False}
            rid=str(uuid4())
            c.execute('INSERT INTO resolution_reviews(id,ticket_id,kind,payload,requested_on) VALUES(?,?,?,?,?)',(rid,ticket_id,kind,json.dumps(payload),today(c).isoformat()))
            return {'review':one(c,'SELECT * FROM resolution_reviews WHERE id=?',(rid,)),'payment_required':False}

    @mcp.tool
    def decide_resolution_review(ticket_id: int, review_id: str, approve: bool, human_name: str, acknowledge_completion_rule: bool, human_capability: str) -> dict:
        """Trusted human decision, not registered with agents. No payments. Pricing
        approval explicitly accepts quote-only completion; restock approval creates a
        simulation plan only and does not receive inventory or resolve the order.
        """
        admin(human_capability)
        if not human_name.strip() or not acknowledge_completion_rule: raise ValueError('Named human must acknowledge the proposed completion rule/assumptions')
        with connect(True) as c:
            r=one(c,'SELECT * FROM resolution_reviews WHERE id=? AND ticket_id=?',(review_id,ticket_id))
            if not r: raise ValueError('Review not found')
            if r['status']!='pending' and not (r['status']=='approved' and r['kind']=='pricing_decision' and approve): return {'review':r,'ticket':ticket(c,ticket_id),'already_decided':True}
            payload=json.loads(r['payload']);t=ticket(c,ticket_id)
            if t['status']!='open': raise ValueError('Ticket changed; review refused')
            status='approved' if approve else 'denied'
            if approve and r['kind']=='pricing_decision':
                pricing=one(c,'SELECT * FROM pricing WHERE sku=?',(t['sku'],))
                if (t['sku'],t['size'],t['qty'])!=(payload['sku'],payload['size'],payload['qty']): raise ValueError('Ticket product/quantity changed; new review required')
                if str(money(pricing['unit_cost']))!=payload['unit_cost'] or str(money(pricing['list_price']))!=payload['list_price']: raise ValueError('Pricing changed; new review required')
                c.execute('INSERT INTO quote_drafts(ticket_id,sku,size,qty,unit_price,unit_cost_snapshot,rationale,created_on) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET unit_price=excluded.unit_price,rationale=excluded.rationale,created_on=excluded.created_on',
                    (ticket_id,t['sku'],t['size'],t['qty'],payload['unit_price'],payload['unit_cost'],payload.get('conditional_quote',payload['rationale']+'; '+payload['supply_caveat']),today(c).isoformat()))
                c.execute("UPDATE tickets SET status='resolved',notes=COALESCE(notes,'')||? WHERE id=?",('\nHuman-authorized pricing decision recorded as unsent conditional quote; no fulfillment, customer acceptance or revenue claimed.',ticket_id));status='executed'
            c.execute('UPDATE resolution_reviews SET status=?,approved_by=?,decision_on=? WHERE id=?',(status,human_name.strip(),today(c).isoformat(),review_id))
            return {'review':one(c,'SELECT * FROM resolution_reviews WHERE id=?',(review_id,)),'ticket':ticket(c,ticket_id),'payment_executed':False}

    @mcp.tool
    def advance_simulation_date(new_date: str, reason: str, human_capability: str) -> dict:
        """Explicit trusted classroom clock advance; no physical time/delivery assertion.
        Never automatic. Changes desk.date_today only, not historical payment dates.
        """
        admin(human_capability)
        if not reason.strip(): raise ValueError('Simulation reason required')
        proposed=date.fromisoformat(new_date)
        with connect(True) as c:
            if proposed < today(c): raise ValueError('Cannot move simulation backwards')
            c.execute("UPDATE desk SET date_today=?,notes=COALESCE(notes,'')||?",(proposed.isoformat(),'\nSIMULATION clock advance: '+reason))
            return {'business_date':proposed.isoformat(),'simulation':True,'physical_delivery_claimed':False}

    @mcp.tool
    def confirm_simulated_receipt_and_fulfill(ticket_id: int, review_id: str, human_name: str, confirm_simulation: bool, human_capability: str) -> dict:
        """Human-confirmed classroom receipt and fulfillment, never physical delivery.
        Requires approved restock assumptions, paid invoice, vendor unblocked, and desk
        date at/after recorded simulated arrival. Atomic and idempotent; no cash change.
        """
        admin(human_capability)
        if not confirm_simulation or not human_name.strip(): raise ValueError('Explicit named simulation confirmation required')
        with connect(True) as c:
            r=one(c,'SELECT * FROM resolution_reviews WHERE id=? AND ticket_id=?',(review_id,ticket_id))
            if not r or r['kind']!='simulated_restock': raise ValueError('Restock review required')
            if r['status']=='executed': return {'review':r,'already_executed':True,'simulation':True}
            if r['status']!='approved': raise ValueError('Human-approved simulation plan required')
            payload=json.loads(r['payload']);t=ticket(c,ticket_id)
            if t['status']!='open' or t['type']!='customer_order' or t['qty']!=payload['qty']: raise ValueError('Ticket changed')
            if today(c)<date.fromisoformat(payload['earliest_arrival']): raise ValueError('Simulated lead time has not elapsed on desk.date_today')
            inv=one(c,'SELECT * FROM invoices WHERE id=?',(t['invoice_id'],))
            if inv['status']!='paid' or one(c,"SELECT id FROM invoices WHERE vendor_id=? AND status='open'",(payload['vendor_id'],)): raise ValueError('Vendor/invoice blocked')
            if not one(c,'SELECT * FROM inventory WHERE sku=? AND size=?',(t['sku'],t['size'])): raise ValueError('Inventory row missing')
            c.execute('UPDATE inventory SET qty=qty+? WHERE sku=? AND size=?',(payload['qty'],t['sku'],t['size']))
            c.execute('UPDATE inventory SET qty=qty-? WHERE sku=? AND size=?',(t['qty'],t['sku'],t['size']))
            c.execute('INSERT INTO fulfillments VALUES(?,?,?,?,?)',(ticket_id,t['sku'],t['size'],t['qty'],today(c).isoformat()))
            c.execute("UPDATE tickets SET status='resolved',notes=COALESCE(notes,'')||? WHERE id=?",('\nSIMULATION ONLY: human-confirmed classroom receipt and fulfillment; no physical delivery claimed.',ticket_id))
            c.execute("UPDATE resolution_reviews SET status='executed',approved_by=?,decision_on=? WHERE id=?",(human_name,today(c).isoformat(),review_id))
            return {'review':one(c,'SELECT * FROM resolution_reviews WHERE id=?',(review_id,)),'ticket':ticket(c,ticket_id),'simulation':True,'physical_delivery_claimed':False,'cash_changed':False}

    @mcp.tool
    def record_conditional_quote_decision(ticket_id: int, review_id: str, human_name: str, human_capability: str) -> dict:
        """Record a human pricing decision and unsent stock-conditional quote, WITHOUT
        applying the proposed resolution criterion or changing ticket status.
        Current exact-size availability is read at execution, not assumed from a draft.
        """
        admin(human_capability)
        if not human_name.strip(): raise ValueError('Named human decision required')
        with connect(True) as c:
            r=one(c,'SELECT * FROM resolution_reviews WHERE id=? AND ticket_id=?',(review_id,ticket_id))
            if not r or r['kind']!='pricing_decision': raise ValueError('Pricing proposal required')
            if r['status']=='approved': return {'review':r,'quote':one(c,'SELECT * FROM quote_drafts WHERE ticket_id=?',(ticket_id,)),'already_recorded':True,'ticket':ticket(c,ticket_id)}
            if r['status']!='pending': raise ValueError('Pending pricing proposal required')
            t=ticket(c,ticket_id);p=json.loads(r['payload'])
            pricing=one(c,'SELECT * FROM pricing WHERE sku=?',(t['sku'],))
            stock=one(c,'SELECT * FROM inventory WHERE sku=? AND size=?',(t['sku'],t['size']))
            if t['status']!='open' or (t['sku'],t['size'],t['qty'])!=(p['sku'],p['size'],p['qty']): raise ValueError('Ticket changed')
            if str(money(pricing['unit_cost']))!=p['unit_cost'] or str(money(pricing['list_price']))!=p['list_price']: raise ValueError('Pricing changed')
            available=stock['qty'] if stock else 0
            caveat=f"Only {available} of the requested {t['qty']} {t['sku']} size {t['size']} units are currently in stock. Fulfillment of all {t['qty']} is not guaranteed. No inventory reserved; no replenishment/supplier commitment or customer acceptance implied."
            body=f"UNSENT CONDITIONAL QUOTE: {t['qty']} hoodies at {p['unit_price']} per hoodie; proposed total {money(p['unit_price'])*t['qty']}. Currency unspecified in database. Existing list price retained where applicable. {caveat} No message sent and no revenue recorded."
            p.update(decision_scope='Human pricing decision and draft only; resolution criterion not applied',available_snapshot=available,requested_qty=t['qty'],conditional_quote=body)
            c.execute('INSERT INTO quote_drafts(ticket_id,sku,size,qty,unit_price,unit_cost_snapshot,rationale,created_on) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id) DO UPDATE SET unit_price=excluded.unit_price,unit_cost_snapshot=excluded.unit_cost_snapshot,rationale=excluded.rationale,created_on=excluded.created_on',(ticket_id,t['sku'],t['size'],t['qty'],p['unit_price'],p['unit_cost'],body,today(c).isoformat()))
            c.execute("UPDATE resolution_reviews SET status='approved',payload=?,approved_by=?,decision_on=? WHERE id=?",(json.dumps(p),human_name,today(c).isoformat(),review_id))
            c.execute("UPDATE tickets SET notes=COALESCE(notes,'')||? WHERE id=?",('\nHuman business decision: price '+p['unit_price']+' retained; unsent conditional quote prepared. Resolution criterion not applied.',ticket_id))
            return {'review':one(c,'SELECT * FROM resolution_reviews WHERE id=?',(review_id,)),'quote':one(c,'SELECT * FROM quote_drafts WHERE ticket_id=?',(ticket_id,)),'ticket':ticket(c,ticket_id),'conditional_quote':body,'resolution_applied':False,'cash_changed':False}

    @mcp.tool
    def get_runtime_identity() -> dict:
        """Read the SQLite connection's actual path and MCP process identity."""
        with connect() as c:
            db=next(r for r in c.execute('PRAGMA database_list') if r['name']=='main')
            return {'working_database_path':str(Path(db['file']).resolve()),'mcp_pid':os.getpid()}

    @mcp.tool
    def recover_committed_resolution(expected_reset_sequence: int, reason: str, human_capability: str) -> dict:
        """Recover already-committed completion records erased by a later reset.
        Trusted fixed evidence file + audit verification, not a new simulation, payment,
        receipt or inventory operation. Restore only desk,101 completion/review and103
        pricing completion/review/quote. Cash, payments, leases and inventory untouched.
        Refuse if reset generation or financial/stock evidence no longer matches.
        """
        admin(human_capability)
        if not reason.strip(): raise ValueError('Recovery reason required')
        root=database.parent.parent if database.parent.name=='data' else database.parent
        evidence=json.loads((root/'output/resolution_completion_evidence.json').read_text(encoding='utf-8'))
        audit=json.loads((root/'output/audit_trail.json').read_text(encoding='utf-8'))
        resets=[e['sequence'] for e in audit if e.get('event')=='dashboard_tool_result' and any(t.get('tool')=='reset_working_database' for t in e.get('tool_calls',[])) and (e.get('results') or {}).get('reset')]
        if max(resets,default=0)!=expected_reset_sequence: raise ValueError('Reset generation changed; inspect again before recovery')
        receipt=evidence['actions']['101_simulated_receipt_fulfillment'];pricing_decision=evidence['actions']['103_pricing_completion']
        if not receipt.get('simulation') or receipt.get('physical_delivery_claimed') is not False: raise ValueError('Source is not an explicitly simulated completion')
        for action,tool in [(receipt,'confirm_simulated_receipt_and_fulfill'),(pricing_decision,'decide_resolution_review')]:
            if not any(e.get('event')=='dashboard_tool_result' and any(t.get('tool')==tool for t in e.get('tool_calls',[])) and e.get('results')==action for e in audit): raise ValueError('Source completion is not corroborated by actual audit result')
        source=evidence['verified_rows'];source101=next(t for t in source['tickets'] if t['id']==101);source103=next(t for t in source['tickets'] if t['id']==103)
        review101=next(r for r in source['resolution_reviews'] if r['ticket_id']==101);review103=next(r for r in source['resolution_reviews'] if r['ticket_id']==103)
        if source101['status']!='resolved' or source103['status']!='resolved' or review101['status']!='executed' or review103['status']!='executed': raise ValueError('Source is not completed')
        quote=next(q for q in source['quote_drafts'] if q['ticket_id']==103)
        if money(quote['unit_price'])!=Decimal('58') or 'Only 8 of the requested 20' not in quote['rationale']: raise ValueError('Source does not match authorized58 conditional quote')
        def insert_row(c,table,row):
            columns=list(row)
            c.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[k] for k in columns])
        with connect(True) as c:
            if money(one(c,"SELECT balance FROM cash_accounts WHERE name='checking'")['balance'])!=Decimal('160'): raise ValueError('Cash changed; recovery refused')
            expected={('invoice',501):Decimal('840'),('rent',1):Decimal('2400')}
            current=rows(c,'SELECT * FROM payments')
            if len(current)!=2 or {(p['kind'],p['ref_id']):money(p['amount']) for p in current}!=expected: raise ValueError('Current payment evidence differs; never repay in recovery')
            if one(c,'SELECT status FROM invoices WHERE id=501')['status']!='paid': raise ValueError('Invoice not paid')
            for ticket_id,src in [(101,source101),(103,source103)]:
                t=ticket(c,ticket_id)
                if any(t[k]!=src[k] for k in ['type','sku','size','qty','invoice_id','lease_id']): raise ValueError('Ticket scope changed')
            for stock in source['inventory']:
                now=one(c,'SELECT qty FROM inventory WHERE sku=? AND size=?',(stock['sku'],stock['size']))
                if not now or now['qty']!=stock['qty']: raise ValueError('Stock changed; no receipt or inventory operations will be repeated')
            current_pricing=one(c,"SELECT * FROM pricing WHERE sku='CC-HOOD-NAVY'")
            if money(current_pricing['list_price'])!=Decimal('58') or money(current_pricing['unit_cost'])!=Decimal('22'): raise ValueError('Pricing changed; recovery refused')
            saved={'desk':rows(c,'SELECT * FROM desk'),'tickets':[ticket(c,101),ticket(c,103)],'resolution_reviews':rows(c,'SELECT * FROM resolution_reviews'),'quote_drafts':rows(c,'SELECT * FROM quote_drafts'),'fulfillments':rows(c,'SELECT * FROM fulfillments')}
            src_desk=source['desk'][0]
            c.execute('UPDATE desk SET date_today=?,notes=?',(src_desk['date_today'],src_desk['notes']))
            for src in [source101,source103]:
                c.execute('UPDATE tickets SET status=?,notes=? WHERE id=?',(src['status'],src['notes'],src['id']))
            for r in [review101,review103]:
                c.execute('DELETE FROM resolution_reviews WHERE ticket_id=? AND kind=?',(r['ticket_id'],r['kind']));insert_row(c,'resolution_reviews',r)
            fulfillment=next(f for f in source['fulfillments'] if f['ticket_id']==101)
            c.execute('DELETE FROM fulfillments WHERE ticket_id=101');insert_row(c,'fulfillments',fulfillment)
            c.execute('DELETE FROM quote_drafts WHERE ticket_id=103');insert_row(c,'quote_drafts',quote)
            return {'recovered':True,'recovery_only':True,'reason':reason,'source_commit_review_ids':[review101['id'],review103['id']],
                'superseded_state':saved,'tickets':[ticket(c,101),ticket(c,102),ticket(c,103)],'business_date':today(c).isoformat(),
                'cash_changed':False,'inventory_changed':False,'payments_repeated':False,'simulation_repeated':False,
                'simulation':True,'physical_delivery_claimed':False,'instructor_confirmed':False}
