"""Regression checks for the customer-history rescan workflow."""
from datetime import datetime, timezone, timedelta
import main

main.init_db()
conn = main.db()
merchant = conn.execute("SELECT * FROM merchants WHERE id='m_demo'").fetchone()
now = datetime.now(timezone.utc).isoformat()
today = datetime.now(timezone.utc).date()
# Fresh isolated identifiers for this test.
cid = 'test_rescan_customer'
bid = 'test_rescan_bill'
conn.execute("DELETE FROM events WHERE external_id LIKE 'history:test_rescan_bill%'")
conn.execute("DELETE FROM customer_bills WHERE id=?", (bid,))
conn.execute("DELETE FROM customers WHERE id=?", (cid,))
conn.execute("INSERT INTO customers(id,merchant_id,name,email,phone,external_id,segment,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (cid,'m_demo','Rescan Test','rescan@example.com',None,'rescan','B2B',now,now))
conn.execute("INSERT INTO customer_bills(id,merchant_id,customer_id,invoice_id,amount,currency,due_date,paid_date,status,payment_method,source,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (bid,'m_demo',cid,'RESCAN-1',9000,'INR',(today-timedelta(days=9)).isoformat(),None,'unpaid',None,'manual',None,now,now))
conn.commit(); conn.close()

# First scan creates a fresh event.
r1 = main.scan_customer_histories(merchant)
assert r1['customers_evaluated'] >= 1
assert any(x['id'] for x in r1['created'])
first = [x for x in r1['created'] if x['customer'] == 'Rescan Test'][0]

# Second scan supersedes the first and creates another fresh event for the same bill.
r2 = main.scan_customer_histories(merchant)
assert r2['superseded'] >= 1
second = [x for x in r2['created'] if x['customer'] == 'Rescan Test'][0]
assert second['id'] != first['id']

conn = main.db()
rows = conn.execute("SELECT id,lifecycle_status,external_id FROM events WHERE merchant_id='m_demo' AND id IN (?,?)", (first['id'], second['id'])).fetchall()
conn.close()
lookup = {r['id']: dict(r) for r in rows}
assert lookup[first['id']]['lifecycle_status'] == 'SUPERSEDED'
assert lookup[second['id']]['lifecycle_status'] in {'RECOMMENDED','ESCALATION_REQUIRED','NO_ACTION'}
assert lookup[second['id']]['external_id'] == f'history:{bid}'
print('customer rescan regression: PASS')
