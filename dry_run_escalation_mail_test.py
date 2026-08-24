"""
Dry-run test for tutor escalation coordinator emails.

Safe by design:
- does not connect to the real database
- does not send SMTP email
- does not write application data
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import sys

import utils.email_utils as email_utils


def make_application(student_year):
    return SimpleNamespace(
        id=99,
        student_id=7,
        student=SimpleNamespace(year=student_year),
        subject=SimpleNamespace(subject_name="Dry Run Subject"),
        register_number="TEST-001",
        cia_number=1,
        tutor=SimpleNamespace(name="Dry Run Tutor"),
        student_name="Dry Run Student",
    )


def run_case(label, student_year, query_result, expected_recipients):
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = query_result

    fake_user = SimpleNamespace(
        query=query,
        id=MagicMock(name="User.id"),
        is_active=MagicMock(name="User.is_active"),
        handling_year=MagicMock(name="User.handling_year"),
    )

    fake_staff_role_entry = SimpleNamespace(
        user_id=MagicMock(name="StaffRoleEntry.user_id"),
        role_name=MagicMock(name="StaffRoleEntry.role_name"),
    )

    sent_messages = []
    application = make_application(student_year)

    fake_models = SimpleNamespace(
        User=fake_user,
        StaffRoleEntry=fake_staff_role_entry,
    )

    with patch.dict(sys.modules, {"models": fake_models}), patch.object(
        email_utils,
        "_send",
        side_effect=lambda **kwargs: sent_messages.append(kwargs),
    ):
        email_utils.notify_coordinator_after_tutor_late(application)

    recipients = [message["to"] for message in sent_messages]

    assert recipients == expected_recipients, (
        f"{label}: expected {expected_recipients}, got {recipients}"
    )
    assert query.filter.called, f"{label}: coordinator query was not filtered"
    assert len(query.filter.call_args.args) == 3, (
        f"{label}: expected role, active, and handling_year filters"
    )

    shown_recipients = recipients if recipients else "no email sent"
    print(f"PASS: {label} -> {shown_recipients}")


def main():
    print("Dry-run only: no real email, no database writes.")

    run_case(
        "3rd-year student goes to 3rd-year coordinator",
        student_year=3,
        query_result=[
            SimpleNamespace(
                email="year3.coordinator@test.invalid",
                name="Year 3 Coordinator",
            )
        ],
        expected_recipients=["year3.coordinator@test.invalid"],
    )

    run_case(
        "4th-year student goes to 4th-year coordinator",
        student_year=4,
        query_result=[
            SimpleNamespace(
                email="year4.coordinator@test.invalid",
                name="Year 4 Coordinator",
            )
        ],
        expected_recipients=["year4.coordinator@test.invalid"],
    )

    run_case(
        "4th-year student with no 4th-year coordinator",
        student_year=4,
        query_result=[],
        expected_recipients=[],
    )

    print("All dry-run escalation checks passed.")


if __name__ == "__main__":
    main()
