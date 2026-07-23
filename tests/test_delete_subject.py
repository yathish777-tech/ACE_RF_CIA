import unittest
from unittest.mock import patch

from flask import Flask

from routes import admin


class DummyQuery:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    def filter_by(self, **kwargs):
        return self

    def count(self):
        return 0

    def delete(self):
        self.calls.append((self.name, 'delete'))
        return 1


class DummySubjectQuery:
    def __init__(self, subject, calls):
        self.subject = subject
        self.calls = calls

    def get_or_404(self, sid):
        self.calls.append(('subject', sid))
        return self.subject


class DummySession:
    def __init__(self, calls):
        self.calls = calls

    def delete(self, obj):
        self.calls.append(('session_delete', obj.id))

    def commit(self):
        self.calls.append(('session_commit', None))


class TestDeleteSubject(unittest.TestCase):
    def test_delete_subject_removes_staff_assignments_before_subject_delete(self):
        calls = []
        subject = type('Subject', (), {'id': 5})()

        class DummySubjectModel:
            query = DummySubjectQuery(subject, calls)

        class DummyModel:
            query = DummyQuery('model', calls)

        class DummyRetestApplicationModel:
            query = DummyQuery('retest_application', calls)

        dummy_session = DummySession(calls)
        app = Flask(__name__)
        app.testing = True

        def unwrap(func):
            while hasattr(func, '__wrapped__'):
                func = func.__wrapped__
            return func

        with app.app_context(), \
             patch.object(admin, 'Subject', DummySubjectModel), \
             patch.object(admin, 'RetestApplication', DummyRetestApplicationModel), \
             patch.object(admin, 'SubjectStaffSection', DummyModel), \
             patch.object(admin, 'CIADate', DummyModel), \
             patch.object(admin, 'StaffAssignment', DummyModel), \
             patch.object(admin, 'db', type('DummyDB', (), {'session': dummy_session})()), \
             patch.object(admin, 'flash', lambda *args, **kwargs: None), \
             patch.object(admin, 'redirect', lambda *args, **kwargs: None), \
             patch.object(admin, 'url_for', lambda *args, **kwargs: '/subjects'):
            unwrap(admin.delete_subject)(5)

        self.assertIn(('model', 'delete'), calls)
        self.assertTrue(any(item == ('session_delete', 5) for item in calls))
        self.assertLess(calls.index(('model', 'delete')), calls.index(('session_delete', 5)))


if __name__ == '__main__':
    unittest.main()
