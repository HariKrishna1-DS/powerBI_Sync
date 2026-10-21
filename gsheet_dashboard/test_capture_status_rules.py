"""Current queue evidence must agree between extraction and SLA reports."""
from copy import deepcopy
from datetime import datetime
import unittest
from unittest.mock import patch

from tracker_sync import FULL, REMAINING, driving, mapped_status, merge_trackers
from production_rules import merge_trackers as legacy_merge
from sla_status import queue_rule


class CaptureStatusRulesTests(unittest.TestCase):
    def test_capture_checks_comments_product_task_and_task_status_together(self):
        cases = [
            ({'ETA Comments': 'ETA: Assigned to the abstractor'}, 'Assign to ABS'),
            ({'ETAComments': 'As per the ABSTRACTORS, awaiting copies'}, 'Assign to ABS'),
            ({'ETA Comments': 'Update from Abstract'}, 'Assign to ABS'),
            ({'ETA Comments': 'ETA EOD or sooner'}, 'Assign to ABS'),
            ({'TaskStatus': 'Completed and Delivered', 'Completed Time': '10/20/2026 09:15 AM',
              'ETAComments': '10/21 EOD or sooner'}, 'Completed and Delivered'),
            ({'ETA Comments': 'ON HOLD. Waiting for the abstractor'}, 'Waiting for Effective Date'),
            ({'ETA Comments': 'We apologize for the abstractor delay'}, 'Need to Assign ABS'),
            ({'Product': 'Attorney Appro..', 'ETA Comments': 'abstractor'}, 'Attorney Approval'),
            ({'Product': 'Home Builders', 'ETA Comments': 'abstractor'}, 'Home Builder'),
            ({'TaskName': 'CRSP2', 'ETA Comments': 'abstractor'}, 'SearchFix'),
            ({'Product': 'Quality Control', 'ETA Comments': 'abstractor'}, 'SearchFix'),
            ({'TaskName': 'TypingModule', 'TaskStatus': 'In Progress'}, 'Typing in Progress'),
            ({'TaskStatus': 'Workflow Suspended'}, 'Awaiting for Clarification'),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                row = {'Order Number': 'A', **fields}
                self.assertEqual(mapped_status(row, 'Completed and Delivered'), expected)
                self.assertEqual(queue_rule(row)[1], expected)
                self.assertEqual(mapped_status(dict(row, **{'Out Time': '10/20/2026 09:15 AM'})), 'Completed and Delivered')
                self.assertEqual(queue_rule(dict(row, **{'Out Time': '10/20/2026 09:15 AM'}))[1], 'Completed and Delivered')

    def test_repeated_capture_corrects_stale_completed_label_and_preserves_manual_fields(self):
        raw = {'Order Number': 'TPS-AD-931726171', 'Product': 'Current Owner', 'Task Name': 'Search',
               'Task Status': 'Available', 'ETA Comments': 'Order has been assigned to the abstractor'}
        tracker = dict(raw, Status='Completed and Delivered', Searcher='Manual searcher', **{'Out Time': '', 'Review/QC': '=A1'})
        saved = deepcopy((raw, tracker))
        actual, _ = merge_trackers({FULL: [], REMAINING: [tracker]}, [raw], [raw], datetime(2026, 10, 20, 9))
        fixed = actual[REMAINING][0]
        self.assertEqual(fixed['Status'], 'Assign to ABS')
        self.assertEqual(fixed['Out Time'], '')
        self.assertEqual((fixed['Searcher'], fixed['Review/QC']), ('Manual searcher', '=A1'))
        self.assertEqual((raw, tracker), saved)
        # A genuine recorded completion remains authoritative.
        tracker['Out Time'] = '10/20/2026 08:45 AM'
        actual, _ = merge_trackers({FULL: [], REMAINING: [tracker]}, [raw], [raw], datetime(2026, 10, 20, 9))
        self.assertEqual(actual[REMAINING][0]['Status'], 'Completed and Delivered')

    def test_comment_only_and_product_only_changes_are_status_drivers(self):
        old = {'Order Number': 'A', 'Product': 'Current Owner', 'Task Name': 'Search', 'Task Status': 'Available'}
        for changed in ({'ETA Comments': 'As per the abstractor, ETA is tomorrow'}, {'Product': 'Attorney Approval'}):
            raw = dict(old, **changed)
            self.assertNotEqual(driving(old), driving(raw))
            tracker = dict(old, Status='Search In Progress')
            actual, _ = merge_trackers({FULL: [], REMAINING: [tracker]}, [raw], [old], datetime(2026, 10, 20, 9))
            self.assertEqual(actual[REMAINING][0]['Status'], queue_rule(raw)[1])

    def test_new_orders_and_legacy_merge_use_the_same_classification(self):
        raw = {'Order Number': 'A', 'Product': 'Full Title', 'Task Name': 'Search', 'Task Status': 'Available',
               'ETA Comments': 'Update from the abstractor'}
        actual, _ = merge_trackers({FULL: [], REMAINING: []}, [raw], [], datetime(2026, 10, 20, 9))
        self.assertEqual(actual[FULL][0]['Status'], 'Assign to ABS')
        preview = {'name': 'preview1', 'created': '2026-10-20T03:30:00Z', 'rows': [raw]}
        actual, _ = legacy_merge(preview, None, [[], []])
        self.assertEqual(actual[0][0]['Status'], 'Assign to ABS')
        actual[0][0]['Status'] = 'Completed and Delivered'
        actual, _ = legacy_merge(preview, preview, actual)
        self.assertEqual(actual[0][0]['Status'], 'Assign to ABS')

    def test_unchanged_eta_is_rechecked_on_each_day_in_both_capture_paths(self):
        raw = {'Order Number': 'A', 'Product': 'Full Title', 'Task Status': 'Available',
               'ETA Comments': 'Received 10/08, fee approved 10/15; ETA 10/21 EOD or sooner.'}
        preview = {'name': 'preview1', 'created': '2026-10-19T03:30:00Z', 'rows': [raw]}
        tracker = dict(raw, Status='Search In Progress', Searcher='Manual searcher', **{'Out Time': ''})
        current = {FULL: [tracker], REMAINING: []}
        legacy = [[tracker], []]
        original = deepcopy((raw, tracker))
        for day, expected in ((20, 'Assign to ABS'), (21, 'Need to Assign ABS'), (22, 'Assign to ABS')):
            today = datetime(2026, 10, day, 10)
            with patch('sla_status.queue_rule', side_effect=lambda row, as_of=None: queue_rule(row, today)):
                current, _ = merge_trackers(current, [raw], [raw], today)
                legacy, _ = legacy_merge(preview, preview, legacy)
            self.assertEqual(current[FULL][0]['Status'], expected)
            self.assertEqual(legacy[0][0]['Status'], expected)
            self.assertEqual(current[FULL][0]['Searcher'], 'Manual searcher')
        self.assertEqual((raw, tracker), original)


if __name__ == '__main__':
    unittest.main()
