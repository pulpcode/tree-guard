from __future__ import annotations

import unittest
from io import StringIO
from unittest.mock import patch

from treeguard.workbench_cli import main


class WorkbenchCLITests(unittest.TestCase):
    def test_starts_loopback_without_access_log(self) -> None:
        with patch("treeguard.workbench_cli.uvicorn.run") as run:
            exit_code = main(["--port", "8123"])

        self.assertEqual(exit_code, 0)
        run.assert_called_once_with(
            "treeguard.web:app",
            host="127.0.0.1",
            port=8123,
            access_log=False,
        )

    def test_rejects_invalid_port_before_start(self) -> None:
        with (
            patch("treeguard.workbench_cli.uvicorn.run") as run,
            patch("sys.stderr", StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            main(["--port", "0"])

        self.assertEqual(raised.exception.code, 2)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
