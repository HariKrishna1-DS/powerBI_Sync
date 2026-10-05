import os
import types
import unittest
from unittest.mock import MagicMock, patch
import desktop_engine


class DesktopRecoveryTests(unittest.TestCase):
    def test_recovery_disables_automatic_work_without_disabling_http_workspace(self):
        for recovering in ('1', '0'):
            with self.subTest(recovering=recovering):
                app = MagicMock()
                create_app = MagicMock(return_value=app)
                http_server = MagicMock(effective_port=12345)
                modules = {'server': types.SimpleNamespace(create_app=create_app),
                           'waitress': types.SimpleNamespace(create_server=MagicMock(return_value=http_server))}
                with patch.dict(os.environ, DATATRACE_DESKTOP_TOKEN='fixture', DATATRACE_DATA_DIR='fixture', DATATRACE_CONNECTION_RECOVERY=recovering), \
                        patch.dict('sys.modules', modules), patch.object(desktop_engine, 'process_job'), \
                        patch.object(desktop_engine.threading, 'Event', return_value=MagicMock()), \
                        patch.object(desktop_engine.threading, 'Thread') as worker, patch('builtins.print'):
                    desktop_engine.main()
                create_app.assert_called_once_with(start_scheduler=recovering != '1')
                worker.return_value.start.assert_called_once()
                http_server.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
