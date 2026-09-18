
## What's Built So Far

### 1. Project Foundation
- Django project (`config`) with `django-environ` for `.env`-based settings
- SQLite database (Postgres-ready via `DATABASE_URL` swap)
- Django REST Framework installed with Token + Session auth
- 6 apps scaffolded under `apps/`: `core`, `properties`, `availability`, `guests`, `bookings`, `integrations`, plus `dashboard`

### 2. Database Schema — Properties Domain
Implemented in `apps/properties/models.py`, inheriting from `apps.core.models.BaseModel` (adds `is_active`, `created_at`, `updated_at` to every model):

- **Property** — hotel/property record (name, code, address, check-in/out times, tax number)
- **RoomType** — room category per property (Deluxe, Suite, etc.) with occupancy limits
- **Room** — physical room with status (`AVAILABLE`, `OCCUPIED`, `RESERVED`, `BLOCKED`, `MAINTENANCE`, `OUT_OF_SERVICE`)
- **RatePlan** — sellable rate plan (meal plan, cancellation policy, refundable flag) — no price on the plan itself; pricing is date-driven and will live in `RoomRate` (availability app, not yet built)

### 3. REST API (`/api/`)
- `PropertySerializer`, `RoomTypeSerializer`, `RoomSerializer`, `RatePlanSerializer` (DRF ModelSerializers)
- `ModelViewSet`s for all 4 models with filtering (`django-filter`), search, ordering
- Cross-field validation (e.g. a Room's `room_type` must belong to the same `property`)
- Routed via `DefaultRouter` at `/api/properties/`, `/api/room-types/`, `/api/rooms/`, `/api/rate-plans/`

### 4. Role-Based Access Control (RBAC)
Built in `apps/core/models.py` — a **dynamic permission** system (not fixed roles):

- **StaffProfile** — extends Django's `User` with employee code, phone, optional property assignment
- **StaffPermission** — one row per (staff, module) with `can_view` / `can_add` / `can_edit` / `can_delete` flags
- **`Module`** — TextChoices enum of every manageable section (Properties, Rooms, Bookings, Payments, Reports, Staff, Integrations, etc.)
- `StaffProfile.has_permission(module, action)` — single source of truth for all permission checks; superusers bypass, everyone else needs an explicit grant
- Enforced via `apps.core.decorators.module_permission_required` (function views) and `apps.core.mixins.ModulePermissionRequiredMixin` (class-based views)

### 5. Custom Dashboard (replaces Django admin for daily staff use)
Built in `apps/dashboard/` — a separate app so it can depend on every domain app without creating circular imports:

- **Custom login/logout** at `/dashboard/login/` (branded, not `/admin/login/`)
- **Dashboard home** (`/dashboard/`) — live counts (properties, rooms, room types, rate plans), room status breakdown bar chart, current-month calendar, "Today's Operations" panel (check-ins/check-outs/occupancy — wired to real data once `bookings` app exists)
- **Generic CRUD layer** (`apps/dashboard/generic_views.py`) — `BaseListView` / `BaseCreateView` / `BaseUpdateView` / `BaseDeleteView`, each permission-checked automatically via the mixin
- **One shared list template** (`dashboard/shared/list.html`) driven by a per-model `columns` config — new models don't need new list HTML
- **One shared form template** (`dashboard/shared/form.html`) — auto-styled Tailwind inputs via `StyledModelForm` base class
- Full CRUD live for: **Properties, Room Types, Rooms, Rate Plans**

### 6. Django Admin
Still available at `/admin/` for superuser-level management — all 4 property models + StaffProfile/StaffPermission (with inline permission editing) registered.

## Not Yet Built (Next Steps)

Per the original roadmap:

1. **Availability app** — `Availability`, `SeasonalRate`, `Restriction`, `RoomRate` (date-based pricing)
2. **Guests app** — `Guest` model, guest history
3. **Bookings app** — `Booking`, `BookingRoom`, check-in/check-out, room assignment
4. **Payments** — `Payment`, `Invoice`, `Refund`
5. **Reports** — booking/revenue/occupancy/cancellation reports (built as queries over Bookings/Payments, not new models)
6. **STAAH Integration** (`apps/integrations`) — `SyncLog`, `ChannelMapping`, availability/rate/reservation sync with Booking.com, Agoda, Expedia via STAAH API

## Setup (Development)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements/development.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Django Admin: `http://127.0.0.1:8000/admin/`
- Staff Dashboard: `http://127.0.0.1:8000/dashboard/`
- REST API: `http://127.0.0.1:8000/api/`

## Environment Variables (`.env`)

```env
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

---
*Last updated: September 18, 2026*