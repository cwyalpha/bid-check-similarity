from __future__ import annotations

import unittest
import tkinter as tk

from checksim.ui import CheckSimApp


class CheckSimUiTest(unittest.TestCase):
    def test_polling_uses_explicit_running_state(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = CheckSimApp(root)
            calls: list[tuple[int, object]] = []

            def fake_after(delay: int, callback: object) -> None:
                calls.append((delay, callback))

            app.after = fake_after  # type: ignore[method-assign]
            app.is_running = True
            app.run_button.configure(state="disabled")

            self.assertFalse(app.run_button["state"] == "disabled")
            self.assertEqual(str(app.run_button["state"]), "disabled")

            app._poll_events()
            self.assertEqual(len(calls), 1)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()

