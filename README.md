# LSA Booking & Payment Backend

A production-oriented backend prototype for booking sessions between a
**Parent** and a **Learning Session Assistant (LSA)**, with payment-driven
booking state transitions.

**Joel Joymon**
Email: joel.joymon2004@gmail.com
Phone: +91-9867014906
GitHub: [github.com/joeljoymon](https://github.com/joeljoymon)

---

## Entities

| Model     | Purpose                                                             |
|-----------|----------------------------------------------------------------------|
| `Parent`  | The guardian who books sessions.                                    |
| `LSA`     | The tutor/counsellor who conducts sessions, grouped by `subject`.    |
| `Booking` | A time slot between a `Parent` and an `LSA`. Has a lifecycle status. |
| `Payment` | One-to-one with a `Booking`; drives the booking's status via webhook.|

**Booking lifecycle:** `pending → confirmed` (payment success) or
`pending → cancelled` (payment failure) → `completed` (post-session, out of
scope for this prototype's automation).

## Design choices

### MVC vs. MVT

Django follows the **MVT (Model-View-Template)** pattern, not classic MVC:

- **Model** — same role as in MVC: `bookings/models.py` owns data shape,
  constraints, and indexes (`Parent`, `LSA`, `Booking`, `Payment`).
- **View** — in Django, the View is the layer that receives a request and
  returns a response (`bookings/views.py`). This is closer to what MVC calls
  the *Controller* than to MVC's "View."
- **Template** — the piece MVT renames: in a traditional web app, the
  Template renders HTML. This project is a pure JSON API, so DRF
  **Serializers** (`bookings/serializers.py`) take over that
  responsibility — they define how a Model instance is *presented* to the
  outside world, the same conceptual slot a Template fills for HTML.

Framework routing (`urls.py`) is Django's own dispatcher, standing in for
MVC's front controller. I used DRF's generic class-based views
(`ListAPIView`, `CreateAPIView`) rather than hand-rolled views, since they
give validation, pagination, and content negotiation for free and keep the
`views.py` layer thin — business rules that matter for correctness (overlap
checking, transactional locking) live in the serializer and view explicitly,
not hidden in a generic mixin.

### Solving the N+1 problem (`GET /api/lsas/available/`)

A naive "which LSAs are free right now" endpoint tends to loop through every
LSA and run a query per LSA to check their bookings — classic N+1. This
project avoids that in three ways, all visible in
`AvailableLSAListView.get_queryset`:

1. **Busy LSAs are resolved as one subquery**, not a per-LSA check:
   `Booking.objects.filter(...).values_list('lsa_id', flat=True)` is passed
   straight into `.exclude(id__in=...)`, so it compiles into a single SQL
   statement with a `NOT IN (SELECT ...)` clause.
2. **`annotate(Count(...))`** computes each LSA's upcoming-booking count in
   the same query as the LSA list, instead of triggering a `COUNT` query
   per row when the serializer accesses it.
3. **`prefetch_related(Prefetch(...))`** fetches all related bookings for
   every returned LSA in a single extra query, instead of one query per LSA
   when their bookings are accessed.

This is covered by
`test_lsa_queries.py::test_available_lsas_constant_query_count`, which uses
`django_assert_num_queries` to assert the endpoint issues a **fixed number
of queries regardless of how many LSAs/bookings exist** — the actual
signature of an N+1 bug is query count scaling with row count, so this test
would fail immediately if that regressed.

### Preventing double-bookings

Overlap is checked twice, for two different failure modes:

- **Serializer-level `validate()`** — a normal, single-request check:
  `start_time < existing.end_time AND end_time > existing.start_time`
  against bookings in `PENDING`/`CONFIRMED` status only (cancelled bookings
  don't block a slot).
- **View-level `select_for_update()`** inside `transaction.atomic()` — the
  serializer check alone has a race window: two simultaneous requests for
  the same slot can both pass validation before either commits. Locking the
  matching rows for the duration of the transaction closes that window on
  Postgres/MySQL (SQLite treats `select_for_update` as a no-op, since it
  doesn't support row-level locking — fine for this prototype's SQLite
  default, but this is the reason a real deployment should run Postgres).
- A DB-level `CheckConstraint` (`end_time > start_time`) is a last line of
  defense against malformed data regardless of application-layer bugs.

### Payment webhook → booking state transition

`POST /api/payments/webhook/` accepts `{"event": "payment.success" |
"payment.failed", "reference_id": "..."}` and:

1. Locks the `Payment` row (`select_for_update`) inside a transaction.
2. **Checks idempotency first** — if the payment isn't still `PENDING`, the
   webhook is treated as a harmless replay and returns `200` without
   double-applying a transition. Payment gateways commonly retry webhooks,
   so this matters for correctness, not just tidiness.
3. Updates `Payment.status` and the related `Booking.status` together in
   the same transaction, so they can never disagree.

## API summary

| Method | Endpoint                     | Purpose                                   |
|--------|-------------------------------|--------------------------------------------|
| GET    | `/api/lsas/available/`        | List active LSAs free in a `[start, end)` window. Query params: `subject`, `start`, `end` (ISO 8601). |
| POST   | `/api/bookings/`               | Create a booking. Body: `parent`, `lsa`, `start_time`, `end_time`. |
| POST   | `/api/payments/webhook/`       | Payment gateway callback. Body: `event`, `reference_id`. |

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

The project ships with SQLite for zero-config local setup. For anything
beyond local dev, point `DATABASES` in `core/settings.py` at Postgres —
the row-locking behaviour (`select_for_update`) that protects against
double-bookings and duplicate webhook effects requires it.

## Running tests

```bash
python -m pytest
```

10 tests across three files:

- `test_bookings.py` — booking creation, overlap rejection, adjacent
  (non-overlapping) bookings accepted, invalid time range rejected.
- `test_lsa_queries.py` — busy LSAs correctly excluded; query count stays
  constant as data volume grows (N+1 regression guard).
- `test_webhooks.py` — success confirms the booking, failure cancels it,
  replayed events are idempotent, unknown reference returns 404.

## What's intentionally out of scope

- Auth/permissions on the API (would use DRF's `IsAuthenticated` +
  token/session auth in a real deployment).
- Payment gateway signature verification on the webhook (a real
  integration would verify an HMAC signature header before trusting the
  payload).
- Pagination tuning, rate limiting, and structured logging.
