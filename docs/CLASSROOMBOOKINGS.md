# Relation to classroombookings

Moved from the README on 2026-10-15, with the original classroombookings README.

This repository is a fork of classroombookings by Craig A Rodway. The original PHP app is unchanged at
the root (`crbs-core/`, `index.php`, `assets/`), and `./deploy.sh --legacy` runs it next to
SmartSched. SmartSched imports its database: users with their password hashes, roles, access lists and
bookings. The import is tested on CRBS's own install SQL; an upgrade of a running CRBS server is still a
declared gap.

What stays the same: the booking grid by day or by room, single and recurring bookings, booking
limits, holidays and timetable weeks, roles with the CRBS permissions, room access lists, LDAP
sign-in, the CSV export columns, and the 13 CRBS interface languages. What is added: the planning side,
a published timetable that bookings can never collide with, the reservation panel, calendar feeds and
push, approvals, an audit log with undo, in-app notifications and an e-mail outbox. Where SmartSched
behaves differently on purpose (mostly security, such as no privilege escalation in the role editor,
sign-out ending every session, or keeping booking history when a user is deleted), the difference is
listed with its setting, if there is one, in [docs/CRBS_PARITY.md](CRBS_PARITY.md).

The CRBS superset gate (`python3 scripts/parity_check.py`) holds one row per CRBS behaviour, audit item
or screen, each tied to API tests on the real Bahar data and, where there is a screen, to a Playwright
test title. Run on 2026-10-15 at commit `a0a6b4c` on a clean checkout: **192 rows, 172 pass, 20
declared gaps, 0 fail, 0 missing**; all 157 API tests passed. Each gap is declared in the inventory
with a reason and a proposed fix: 11 rows have a screen that no Playwright step in the inventory drives
yet (multi-booking, cancel many, the staff dashboard, SMTP, the installer's requirements step on an
empty database, and others); 4 are wave-1 screens still in progress (room features, find-a-room,
audit viewer, approvals); 2 are the Google/Microsoft push and the webhooks, which have no settings
screen and no live tenant test; 3 are the legacy MySQL upgrade and a side-by-side comparison with a
running CRBS (Phase 18 parts 3 and 4). The UI column
of this run checks that the Playwright titles exist; the specs themselves run in the pod CI `e2e-real`
gate. Details: [docs/CRBS_PARITY.md](CRBS_PARITY.md) §9.

## The original classroombookings README

### classroombookings - open source room booking system for schools.

By Craig A Rodway.

[![License: AGPLv3](https://img.shields.io/static/v1?label=License&message=AGPLv3&color=3DA639&style=flat-square)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Twitter Follow](https://img.shields.io/twitter/follow/crbsapp.svg?style=social)](https://twitter.com/crbsapp)

This is a web-based room booking system for schools and is designed to be as easy to use as possible. Set up your bookable rooms, day schedule and timetable for the year. Add user accounts, and allow them to make and manage bookings from anywhere.

It is available to [download and install yourself](https://www.classroombookings.com/self-host/) or there is a great value [hosted service](https://www.classroombookings.com/pricing/).

It is web-based - PHP and MySQL - and currently uses the [CodeIgniter 3](https://codeigniter.com/) framework.

#### Documentation
For installation instructions and configuration guide, please [read the documentation pages](https://www.classroombookings.com/docs/self-hosted/).

#### Bug Reports & Feature Requests
Please check out [GitHub Issues](https://github.com/craigrodway/classroombookings/issues) to view existing issues or open a new bug report.

#### Security
To report any security issues, please email craig@classroombookings.com instead of using the issue tracker.

#### Credits

This project makes use of several third parties, some of which are listed below.

- [CodeIgniter](https://codeigniter.com/) (MIT)
- [Unpoly](https://unpoly.com/) (MIT)
- [FamFamFam Silk Icons](http://www.famfamfam.com/lab/icons/silk/) ([CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), Unmodified)
