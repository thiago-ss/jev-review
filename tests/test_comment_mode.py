"""Exercise CLI-to-transport comment writes independently of approval eligibility."""
import unittest
from unittest.mock import patch

from jev_review.cli import _github_one, build_parser
from jev_review.github import GitHubClient
from jev_review.models import Review, RiskLevel, ChecklistItem, ChecklistStatus
from jev_review.policy import Action, PolicyDecision
from jev_review.provider import JevResult, JevProviderError
from test_github import FakeGitHub


class CommentModeTests(unittest.TestCase):
    def run_case(self, action=Action.ESCALATE, *, comment=True, allowed=True, outage=False, xray=False):
        transport = FakeGitHub()
        client = GitHubClient('test', api_url='https://example.test', transport=transport, bot_login='jev-bot')
        review = Review(True, RiskLevel.LOW, tuple(ChecklistItem(n, ChecklistStatus.PASS, .99) for n in ('correctness', 'security', 'tests')), .99, .99)
        config = {'xray_enabled': xray, 'allowlisted_repositories': ['o/r'] if allowed else [], 'trusted_checks': {'ci': [7]}, 'trusted_reviewers': ['alice'], 'fallback_reviewers': ['alice']}
        with patch('jev_review.github.GitHubClient', return_value=client), patch('jev_review.provider.JevProvider') as provider, patch('jev_review.cli.evaluate', return_value=PolicyDecision(action, ())) as evaluate:
            if outage:
                provider.return_value.review_with_result.side_effect = JevProviderError('unavailable')
            else:
                provider.return_value.review_with_result.return_value = (review, JevResult('jev-1.13.0', {}, {}))
            result = _github_one('o/r', 1, execute=False, comment_only=comment, config_raw=config)
            if not outage:
                self.assertEqual(evaluate.call_args.args[2].mode, 'shadow')
        return result, [call for call in transport.calls if call[0] == 'POST']

    def test_comment_only_never_approves_or_requests_reviewers(self):
        for action in Action:
            with self.subTest(action=action):
                result, writes = self.run_case(action)
                self.assertEqual(len(writes), 1)
                self.assertTrue(writes[0][1].endswith('/reviews'))
                self.assertEqual(writes[0][2]['event'], 'COMMENT')
                self.assertFalse(result['audit']['dry_run'])
                self.assertEqual(result['plan']['reviewers'], [])
                self.assertIn('<!-- jev-review:', writes[0][2]['body'])

    def test_dry_run_and_nonallowlisted_repo_do_not_write(self):
        for params in ({'comment': False}, {'allowed': False}):
            with self.subTest(params=params):
                _, writes = self.run_case(**params)
                self.assertEqual(writes, [])

    def test_provider_outage_can_publish_comment_without_approval(self):
        result, writes = self.run_case(outage=True)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][2]['event'], 'COMMENT')
        self.assertIn('provider_error', result)

    def test_investigation_is_opt_in_and_comment_only(self):
        with patch('jev_review.investigation.investigate', return_value={'perspectives': {}, 'scope_complete': True}) as investigate:
            result, writes = self.run_case(xray=True)
            self.assertEqual(investigate.call_count, 1)
            self.assertIn('investigation', result)
            self.assertEqual(writes[0][2]['event'], 'COMMENT')
            self.run_case(xray=True, comment=False)
            self.assertEqual(investigate.call_count, 1)

    def test_modes_are_explicit_and_mutually_exclusive(self):
        parser = build_parser()
        args = parser.parse_args(['poll', '--repo', 'o/r', '--comment-only'])
        self.assertTrue(args.comment_only)
        self.assertFalse(args.execute)
        with self.assertRaises(ValueError):
            _github_one('o/r', 1, execute=True, comment_only=True, config_raw={})


if __name__ == '__main__':
    unittest.main()
