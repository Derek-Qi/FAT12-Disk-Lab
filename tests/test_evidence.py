from datetime import datetime, timezone
import unittest


class EvidenceTests(unittest.TestCase):
    def test_receipt_date_uses_client_timezone_and_keeps_utc_timestamp(self):
        from tools.evidence import metadata
        result=metadata(datetime(2026,10,24,17,30,tzinfo=timezone.utc))
        self.assertEqual(result['date'],'2026-10-25')
        self.assertEqual(result['date_timezone'],'Asia/Shanghai')
        self.assertEqual(result['generated_at_utc'],'2026-10-24T17:30:00+00:00')
        self.assertTrue(result['python'])
        self.assertTrue(result['system'])

    def test_naive_receipt_timestamp_is_rejected(self):
        from tools.evidence import metadata
        with self.assertRaises(ValueError):metadata(datetime(2026,10,25))
