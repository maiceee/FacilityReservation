Campus Facility Reservation and Event Scheduling System

IT 401W Web Programming and Frameworks · Final Project B · Group 4


A Django web application for requesting, approving, and tracking campus facility reservations. Basic Users browse facilities and submit requests. Administrators review requests, manage facilities and closures, run events, and view reports.


Team


Beltran, Maicee Annlei J.

De Guzman, Dan Nico C.

Eusebio, Kurt Yanzie

Reyes, Kurt Ivan

Sabiaga, John Raven V.


Features

Basic User (/portal/)



Register, log in, and update a profile

Search facilities by name, code, or location; filter by category and minimum capacity

View facility details, amenities, availability, and closures

Submit reservation requests with automatic validation

View own reservations and cancel Pending or Approved ones before they start


Administrator (/manage/)



Dashboard with pending requests, upcoming events, booking trends, and facility usage

Manage users, categories, amenities, and facilities (archive instead of delete)

Review requests: approve or reject with a required reason

Reschedule or cancel approved reservations with a required reason

Check in, complete (with incident notes), or mark no-show

Facility closures with conflict detection

Reservation slip and completion summary

Reports with date filters and CSV exports (reservations and facility utilization)

Audit log and system settings (maximum event duration, advance-booking days)


Reservation Rules

Every request, approval, and reschedule is validated for: active facility and category, attendees within capacity, a future start, end after start, same-day schedule, facility operating hours, maximum duration (default 4 hours), booking window (default 30 days), closure overlap, and conflicts with blocking reservations. Time ranges are half-open, so back-to-back bookings are allowed. Approval and rescheduling lock the records inside a database transaction so two overlapping requests cannot both succeed.


Status flow: Pending → Approved → Checked In → Completed. Other outcomes: Rejected, Cancelled, No Show.


Tech Stack


Python and Django 6.1.2

SQLite (development and demonstration)

Django templates, plain CSS, and vanilla JavaScript

Chart.js 4.4.7 (bundled locally)


Requirements


Python 3.12 or newer (confirm against the Django 6.1 release notes)

Git


Setup

# 1. Clone the repository
git clone https://github.com/maiceee/FacilityReservation.git
cd FacilityReservation

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your environment file
cp .env.example .env            # Windows: copy .env.example .env

Edit .env:


Variable	Purpose
DJANGO_SECRET_KEY	Required. The app will not start without it.
DJANGO_DEBUG	Set to True for local development. When False, HTTPS redirect and secure cookies are enabled, so http://127.0.0.1:8000 will not work.
DJANGO_ALLOWED_HOSTS	Comma-separated hosts, for example 127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS	Needed for deployment behind HTTPS
DEMO_ACCOUNT_PASSWORD	Password for demo accounts created by seed_demo

Generate a secret key:


python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"

# 5. Create the database tables
python manage.py migrate

# 6. Create an administrator (choose one)
python manage.py create_admin
# or load demo data, which includes the administrator "demo_admin"
python manage.py seed_demo
# or: python manage.py seed_demo --password "YourStrongPassword"

# 7. Run the server
python manage.py runserver

Open http://127.0.0.1:8000/ in your browser.


Demo Data

seed_demo creates fictional data only: 3 facility categories, 6 facilities, 8 amenities, 1 administrator, 8 basic users, 24 reservations, 5 closure blocks, and 8 event records. The command requires a password through DEMO_ACCOUNT_PASSWORD or --password. No password is stored in the repository.


Running Checks and Tests

Run these before every merge or submission:


python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test

Project Structure

manage.py
requirements.txt
.env.example
facilityreservation/            Project settings and root URLs
Reservation/
  models.py                     Database models
  views.py                      Request handling
  services.py                   Business rules and transactions
  forms.py                      Form validation
  directory.py                  Search, filter, and pagination helpers
  decorators.py                 Role and ownership checks
  urls.py                       Routes
  tests.py, test_*.py           Automated tests
  migrations/                   Schema history
  management/commands/          create_admin, seed_demo
  static/Reservation/           CSS, JavaScript, fonts, icons, bundled Chart.js
templates/Reservation/          HTML templates (admin, user, registration, components)

Security Notes


Secrets and production settings are loaded from environment variables.

.env, local databases, virtual environments, and caches are excluded by .gitignore.

Django's built-in admin site is disabled. Administrators use /manage/.

Role and ownership checks run on the server. The public registration form can create only Basic Users.

With DJANGO_DEBUG=False, the app enables the HTTPS redirect, secure cookies, and HSTS.

Use fictional data for demonstrations.


Known Limitations


SQLite is suitable for demonstration. Use PostgreSQL for sustained production use.

No email notifications.

No recurring reservations.

Reservations cannot span midnight.

Accessibility checks and formal user testing results must be recorded separately in the project documentation.


Third-Party Components

Django (BSD 3-Clause), Chart.js (MIT), Quicksand font (SIL Open Font License), and Lucide icons. License files are included with the bundled assets.


Documentation

The full project documentation (requirements, diagrams, testing, ethics, and user manuals) is submitted separately.

