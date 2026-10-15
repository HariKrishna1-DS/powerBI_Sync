import os
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch

from server import main


class LocalLauncherTests(unittest.TestCase):
    def setUp(self):
        self.stopped = threading.Event()
        self.app = Mock(extensions={'stop_scheduler': self.stopped})
        self.server = Mock(effective_port='8510')
        self.probe = MagicMock()
        self.probe.__enter__.return_value = self.probe
        for target, value in (
                ('server.create_app', Mock(return_value=self.app)),
                ('server.socket.socket', Mock(return_value=self.probe)),
                ('waitress.create_server', Mock(return_value=self.server)),
                ('webbrowser.open', Mock(return_value=True)),
                ('builtins.print', Mock())):
            patcher = patch(target, value)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            setattr(self, target.split('.')[-1], mock)
        environment = patch.dict(os.environ, {'HOST': '127.0.0.1', 'PORT': '8510'})
        environment.start()
        self.addCleanup(environment.stop)

    def launch(self, *args):
        with patch('sys.argv', ['server.py', *args]):
            main()

    def test_opens_system_browser_only_after_binding_the_actual_port(self):
        events = []
        self.probe.bind.side_effect = [OSError('Port occupied'), None]
        self.server.effective_port = '8511'
        self.create_server.side_effect = lambda *args, **kwargs: (events.append('bound') or self.server)
        self.open.side_effect = lambda *args, **kwargs: (events.append('opened') or True)
        self.server.run.side_effect = lambda: events.append('serving')
        self.launch('--open-browser')
        self.assertEqual(events, ['bound', 'opened', 'serving'])
        self.create_server.assert_called_once_with(self.app, host='127.0.0.1', port=8511, threads=8)
        self.open.assert_called_once_with('http://127.0.0.1:8511', new=2)
        self.print.assert_called_once_with('DataTrace Workspace: http://127.0.0.1:8511', flush=True)
        self.assertTrue(self.stopped.is_set())
        self.server.close.assert_called_once()

    def test_direct_server_command_does_not_open_a_browser(self):
        self.launch()
        self.open.assert_not_called()
        self.server.run.assert_called_once()

    def test_bind_failure_never_announces_ready_or_opens_browser(self):
        self.create_server.side_effect = PermissionError('Cannot bind')
        with self.assertRaises(PermissionError):
            self.launch('--open-browser')
        self.open.assert_not_called()
        self.print.assert_not_called()
        self.assertTrue(self.stopped.is_set())

    def test_browser_failure_keeps_workspace_available(self):
        self.open.side_effect = OSError('No default browser')
        self.launch('--open-browser')
        self.server.run.assert_called_once()
        self.assertIn('Microsoft Edge or Google Chrome', self.print.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
