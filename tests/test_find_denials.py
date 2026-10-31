"""Inspect destructive find commands without executing any deletion."""
import unittest
from unittest.mock import Mock

from sudarshan.security import Policy


class FindDenialTests(unittest.TestCase):
    def test_broad_find_deletion_is_denied_before_approval_in_every_mode(self):
        commands = (
            'find / -delete', 'find / -depth -type f -delete',
            'find -L / -delete', 'find -P -O2 / -delete',
            '/usr/bin/find "/" -delete', 'find /* -delete',
            'find ~ -delete', 'find ~/ -delete', 'find "$HOME" -delete',
            "find '${HOME}' -delete", 'find ${HOME}/../ -delete',
            'echo ready && find / -delete', 'echo ready; find / -delete',
            'echo ready\nfind / -delete',
            'find / -exec rm {} \\;', 'find / -execdir /bin/rm -rf {} +',
        )
        for mode in ('safe', 'read-only', 'yolo'):
            for name in ('bash', 'sandbox_bash'):
                for command in commands:
                    with self.subTest(mode=mode, name=name, command=command):
                        approver = Mock(return_value=True)
                        self.assertEqual(
                            Policy(mode, approver).check({'name': name, 'args': {'command': command}}),
                            'dangerous bash command is never allowed')
                        approver.assert_not_called()

    def test_local_cleanup_and_root_listing_still_follow_ordinary_policy(self):
        for command in ('find ./scratch -type f -delete', 'find / -maxdepth 1 -print'):
            call = {'name': 'bash', 'args': {'command': command}}
            with self.subTest(command=command):
                self.assertIsNone(Policy('yolo').check(call))
                approver = Mock(return_value=True)
                self.assertIsNone(Policy('safe', approver).check(call))
                approver.assert_called_once()
                self.assertIsNotNone(Policy('read-only').check(call))
