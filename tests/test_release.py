import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

# Always use an isolated database. A child test process reopens the same file.
child_run = __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] in ("--replay", "--rerun")
temporary = None if child_run else tempfile.TemporaryDirectory()
if temporary:
    os.environ["APEXTRACK_TEST_DB"] = str(Path(temporary.name) / "apextrack.db")
os.environ["DATABASE_URL"] = f"sqlite:///{os.environ['APEXTRACK_TEST_DB']}"
os.environ["SECRET_KEY"] = "local-release-tests"
os.environ.pop("SIGNUP_CODE", None)
os.environ.pop("ALLOW_SIGNUP", None)

from backend import database as db_models
from backend import main as app

SENDER = "+14035550101"
SECOND = "+14035550102"
OTHER = "+14035550103"
LINE = "+14035550199"
STAFF = "+14035550198"


def reply(message_id, number=SENDER):
    return {"body": {"id": message_id, "type": "SMS", "direction": "Inbound",
                     "from": {"phoneNumber": number}, "to": [{"phoneNumber": LINE}],
                     "subject": "YES"}}


async def post_replies(payload, repeat=1):
    transport = httpx.ASGITransport(app=app.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for _ in range(repeat):
            await client.post("/rc/webhook", json=payload)
    pending = getattr(app, "_background_tasks", ())
    if pending:
        await asyncio.gather(*tuple(pending))


def fake_sender():
    return AsyncMock(return_value={"sent": True, "detail": "Accepted in test"})


def recipients_called(sender):
    return [call.args[2] for call in sender.await_args_list]


async def send_evening_record(appt_id):
    with app.SessionLocal() as db:
        a = db.get(db_models.Appointment, appt_id)
        return await app._send_to_all_recipients(db, a, lambda name: f"Reminder for {name}", "SMS EVENING")


def child():
    mode, value = sys.argv[1:3]
    with patch.object(app, "send_sms", fake_sender()) as sender:
        if mode == "--replay":
            asyncio.run(post_replies(reply(value)))
        elif mode == "--rerun":
            asyncio.run(send_evening_record(int(value)))
        else:
            raise ValueError(mode)
    print(json.dumps(recipients_called(sender)))


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        with db_models.engine.begin() as connection:
            for table in reversed(db_models.Base.metadata.sorted_tables):
                connection.execute(table.delete())
        self.today = app.business_now().date()
        self.tomorrow = (self.today + timedelta(days=1)).isoformat()
        self.future = (self.today + timedelta(days=3)).isoformat()
        with app.SessionLocal() as db:
            db.add_all([
                db_models.User(id=1, username="owner", password="test-only", role="admin"),
                db_models.User(id=2, username="assistant", password="test-only", role="assistant",
                               owner_id=1, can_planner=True, can_confirmations=True),
                db_models.BookingConfig(owner_id=1, slug="local-agent", enabled=True),
                db_models.RcToken(owner_user_id=1, access_token="fake", refresh_token="fake",
                                  token_expiry="2099-01-01T00:00:00", rc_phone_number=LINE),
            ])
            db.commit()
        self.client = TestClient(app.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + app.create_token(1, "admin", 0)}

    def add_appointment(self, hour, phone=SENDER, **fields):
        with app.SessionLocal() as db:
            data = dict(owner_id=1, created_by=1, lead_name="Test Client", phone_number=phone,
                        scheduled_for=self.future + "T" + hour, booked_at=app.business_now_str())
            data.update(fields)
            a = db_models.Appointment(**data)
            db.add(a)
            db.commit()
            return a.id

    def add_prompt(self, appt_id):
        with app.SessionLocal() as db:
            a = db.get(db_models.Appointment, appt_id)
            a.sms_sent_booking = True
            if hasattr(db_models, "SmsLog"):
                db.add(db_models.SmsLog(direction="out", kind="booking", status="sent",
                                        appointment_id=a.id, phone=a.phone_number,
                                        dedupe_key=f"out:{a.id}:booking:{a.scheduled_for}:{a.phone_number}"))
            db.commit()

    def statuses(self, ids):
        with app.SessionLocal() as db:
            return [db.get(db_models.Appointment, key).sms_status for key in ids]

    def restart(self, mode, value):
        output = subprocess.check_output(
            [sys.executable, str(Path(__file__).resolve()), mode, str(value)], text=True)
        return json.loads(output.strip().splitlines()[-1])

    def test_ambiguous_yes_alerts_staff(self):
        ids = [self.add_appointment(hour) for hour in ("10:00", "11:00", "12:00")]
        for key in ids:
            self.add_prompt(key)
        with patch.object(app, "TAMEEMA_PHONE", STAFF), patch.object(app, "send_sms", fake_sender()) as sender:
            asyncio.run(post_replies(reply("ambiguous")))
        self.assertEqual(self.statuses(ids), ["", "", ""])
        self.assertEqual(recipients_called(sender), [STAFF])
        self.assertIn("matches 3 bookings", sender.await_args.args[3])

    def test_single_yes_only_confirms_once_across_restart(self):
        first = self.add_appointment("10:00")
        self.add_prompt(first)
        with patch.object(app, "send_sms", fake_sender()) as sender:
            asyncio.run(post_replies(reply("same-id"), repeat=3))
        self.assertEqual(self.statuses([first]), ["confirmed"])
        self.assertEqual(recipients_called(sender), [SENDER])
        # This appointment could be incorrectly confirmed by the replay.
        second = self.add_appointment("11:00")
        self.add_prompt(second)
        self.assertEqual(self.restart("--replay", "same-id"), [])
        self.assertEqual(self.statuses([second]), [""])

    def test_cancelled_row_rejects_confirmation(self):
        key = self.add_appointment("10:00", appt_status="cancelled")
        with patch.object(app, "send_sms", fake_sender()) as sender:
            response = self.client.patch(f"/confirmations/{key}/status", headers=self.headers,
                                         json={"status": "confirmed"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(recipients_called(sender), [])
        self.assertEqual(self.statuses([key]), [""])

    def test_move_released_row_within_occupied_hour(self):
        key = self.add_appointment("10:00", appt_status="cancelled")
        self.add_appointment("10:45", SECOND)
        response = self.client.put(f"/appointments/{key}", headers=self.headers, json={
            "lead_name": "Moved Client", "scheduled_for": self.future + "T10:30", "recipients": []})
        self.assertEqual(response.status_code, 400)

    def test_restore_and_agent_booking_cannot_both_win(self):
        key = self.add_appointment("12:00", appt_status="rescheduled")
        checked, release, booking_checked = Event(), Event(), Event()
        conflict = app.appointment_conflict

        def interleave(db, owner, slot, exclude_id=None):
            result = conflict(db, owner, slot, exclude_id)
            if exclude_id == key:
                checked.set()
                release.wait(3)
            elif slot == self.future + "T12:00":
                booking_checked.set()
            return result

        with patch.object(app, "appointment_conflict", interleave), ThreadPoolExecutor(2) as executor:
            restoring = executor.submit(self.client.patch, f"/appointments/{key}/appt-status",
                                       headers=self.headers, json={"appt_status": ""})
            try:
                self.assertTrue(checked.wait(3))
                booking = executor.submit(self.client.post, "/api/book/local-agent", json={
                    "lead_name": "Agent Client", "scheduled_for": self.future + "T12:00"})
                if booking_checked.wait(0.5):
                    booking.result(timeout=3)
            finally:
                release.set()
            results = sorted([restoring.result(timeout=3).status_code, booking.result(timeout=3).status_code])
        self.assertEqual(results, [200, 409])

    def test_evening_stops_for_cancelled_row_mid_batch(self):
        self.add_appointment("10:00", scheduled_for=self.tomorrow + "T10:00")
        key = self.add_appointment("11:00", SECOND, scheduled_for=self.tomorrow + "T11:00")
        sent = []

        async def cancel_while_sending(db, owner, phone, message):
            sent.append(phone)
            if phone == SENDER:
                with app.SessionLocal() as session:
                    session.get(db_models.Appointment, key).appt_status = "cancelled"
                    session.commit()
            return {"sent": True}

        with patch.object(app, "send_sms", cancel_while_sending):
            asyncio.run(app._run_sms_job("evening"))
        self.assertEqual(sent, [SENDER])

    def test_recipient_delivery_dedupes_reruns_and_process_restart(self):
        key = self.add_appointment("10:00")
        with app.SessionLocal() as db:
            db.add(db_models.AppointmentRecipient(appointment_id=key, name="Extra", phone_number=SECOND))
            db.commit()
        with patch.object(app, "send_sms", fake_sender()) as sender:
            sender.side_effect = [{"sent": True}, {"sent": False}, {"sent": True}, {"sent": True}]
            asyncio.run(send_evening_record(key))
            asyncio.run(send_evening_record(key))
            self.assertEqual(recipients_called(sender), [SENDER, SECOND, SECOND])
        self.assertEqual(self.restart("--rerun", key), [])
        with app.SessionLocal() as db:
            db.get(db_models.Appointment, key).scheduled_for = self.future + "T11:00"
            db.commit()
        self.assertEqual(self.restart("--rerun", key), [SENDER, SECOND])

    def test_webhook_challenge_uses_a_small_header_only_response(self):
        challenge = "challenge" * 15
        response = self.client.post("/rc/webhook", headers={"Validation-Token": challenge})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Validation-Token"], challenge)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(response.content, b"")
        self.assertNotIn("Content-Security-Policy", response.headers)
        self.assertIn("Content-Security-Policy", self.client.get("/").headers)

    def test_webhook_registration_reuses_active_subscription(self):
        requests = []
        existing = {"id": "existing", "status": "Active",
                    "deliveryMode": {"address": app._rc_webhook_url()}}

        def ringcentral(request):
            requests.append(request.method)
            return httpx.Response(200, json={"records": [existing]})

        real_client = httpx.AsyncClient
        with app.SessionLocal() as db, patch.dict(os.environ, {"RC_WEBHOOK_TOKEN": "stale-setting"}):
            row = db.query(db_models.RcToken).first()
            with patch.object(app.httpx, "AsyncClient",
                              side_effect=lambda **kw: real_client(transport=httpx.MockTransport(ringcentral), **kw)):
                result = asyncio.run(app._sync_rc_webhook_locked(db, row, create_if_missing=True))
        self.assertEqual(result["status"], "already_registered")
        self.assertEqual(result["subscription_id"], "existing")
        self.assertEqual(requests, ["GET"])

    def test_webhook_registration_creates_subscription_without_token(self):
        requests = []

        def ringcentral(request):
            requests.append(request.method)
            if request.method == "GET":
                return httpx.Response(200, json={"records": []})
            self.assertEqual(json.loads(request.content)["deliveryMode"], {
                "transportType": "WebHook", "address": app._rc_webhook_url(),
            })
            return httpx.Response(201, json={"id": "new"})

        real_client = httpx.AsyncClient
        with app.SessionLocal() as db, patch.dict(os.environ, {"RC_WEBHOOK_TOKEN": "stale-setting"}):
            row = db.query(db_models.RcToken).first()
            with patch.object(app.httpx, "AsyncClient",
                              side_effect=lambda **kw: real_client(transport=httpx.MockTransport(ringcentral), **kw)):
                result = asyncio.run(app._sync_rc_webhook_locked(db, row, create_if_missing=True))
        self.assertEqual(result["status"], "registered")
        self.assertEqual(requests, ["GET", "POST"])

    def test_failed_webhook_creation_keeps_existing_subscription(self):
        calls = []
        real_client = httpx.AsyncClient
        old_subscription = {
            "id": "old-webhook",
            "status": "Blacklisted",
            "deliveryMode": {"address": app._rc_webhook_url()},
        }

        def ringcentral(request):
            calls.append(request.method)
            if request.method == "GET":
                return httpx.Response(200, json={"records": [old_subscription]})
            return httpx.Response(400, json={"errorCode": "SUB-525", "message": "provider detail"})

        with app.SessionLocal() as db:
            row = db.query(db_models.RcToken).first()
            with patch.object(app.httpx, "AsyncClient",
                              side_effect=lambda **kw: real_client(transport=httpx.MockTransport(ringcentral), **kw)):
                with self.assertRaisesRegex(RuntimeError, r"^RingCentral rejected the subscription \(400, SUB-525\)\.$"):
                    asyncio.run(app._sync_rc_webhook_locked(db, row, create_if_missing=True))
        self.assertEqual(calls, ["GET", "POST"])

    def test_dry_run_does_not_consume_live_send(self):
        key = self.add_appointment("10:00", scheduled_for=self.tomorrow + "T10:00")
        with patch.object(app, "send_sms", AsyncMock(return_value={"dry_run": True, "sent": False})):
            asyncio.run(app._run_sms_job("evening"))
        with app.SessionLocal() as db:
            self.assertFalse(db.get(db_models.Appointment, key).sms_sent_evening)
            db.query(db_models.RcToken).first().dry_run = False
            db.commit()
        with patch.object(app, "send_sms", fake_sender()) as sender:
            asyncio.run(app._run_sms_job("evening"))
            self.assertEqual(recipients_called(sender), [SENDER])

    def test_signup_requires_code(self):
        data = {"username": "newadmin", "password": "local-test-password"}
        self.assertEqual(self.client.post("/create-user", json=data).status_code, 403)
        with patch.dict(os.environ, {"SIGNUP_CODE": "local-code"}):
            self.assertEqual(self.client.post("/create-user", json=data).status_code, 403)
            self.assertEqual(self.client.post("/create-user", json={**data, "signup_code": "✗"}).status_code, 403)
            self.assertEqual(self.client.post("/create-user", json={**data, "signup_code": "local-code"}).status_code, 201)

    def test_static_304_cache_headers(self):
        path = f"/static/app.js?v={app.BUILD_HASH}"
        asset = self.client.get(path)
        cached = self.client.get(path, headers={"If-None-Match": asset.headers["ETag"]})
        wrong_query = self.client.get("/static/app.js?prev=bad")
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached.headers.get("Cache-Control"), asset.headers["Cache-Control"])
        self.assertIn("Accept-Encoding", cached.headers.get("Vary", ""))
        self.assertNotIn("immutable", wrong_query.headers["Cache-Control"])

    def test_active_filter_precedes_limit_and_count_clamps(self):
        self.add_appointment("07:00", appt_status="cancelled")
        self.add_appointment("08:00", sms_status="rescheduled")
        key = self.add_appointment("10:00")
        r = self.client.get("/appointments?active=1&limit=1", headers=self.headers)
        self.assertEqual([a["id"] for a in r.json()], [key])
        r = self.client.get("/appointments/new-count?since_ms=999999999999999999", headers=self.headers)
        self.assertEqual(r.json(), {"count": 0})

    def test_backup_is_readable_and_has_no_temporary_files(self):
        import sqlite3
        self.add_appointment("10:00")
        r = self.client.post("/backup", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        path = Path(r.json()["path"])
        with sqlite3.connect(path) as backup:
            self.assertEqual(backup.execute("pragma integrity_check").fetchone(), ("ok",))
            self.assertEqual(backup.execute("select count(*) from appointments").fetchone(), (1,))
        self.assertFalse(list(path.parent.glob(".backup-*")))


if __name__ == "__main__":
    if child_run:
        child()
    else:
        unittest.main()
