import json
import re
import unittest
from jev_review.experiment_report import render_report


class ExperimentReportTests(unittest.TestCase):
    def test_source_cannot_escape_script_or_html_and_probabilities_are_traceable(self):
        attack = '</script><script>alert("bad")</script>'
        row = {'label': attack, 'family': 'auth', 'variant': 'broken', 'expected': 'hold', 'choice': 'hold', 'probabilities': {'approve': .01, 'hold': .98, 'review': .01}, 'state': attack, 'evidence': {'request_id': 'req-real'}}
        page = render_report([row], {'model': 'jev-test'})
        self.assertNotIn(attack, page)
        encoded = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', page, re.S).group(1)
        self.assertEqual(json.loads(encoded)['rows'][0]['state'], attack)
        self.assertIn('1%', page)
        self.assertIn('req-real', page)
        self.assertIn('not measured production risk', page)

    def test_missing_response_is_not_plotted_as_zero_probability(self):
        page = render_report([{'label': 'Outage', 'variant': 'broken', 'expected': 'hold', 'error': 'unavailable'}], {})
        self.assertIn('Unavailable', page)
        self.assertNotIn('<circle ', page)
        self.assertIn('aria-live="polite"', page)
