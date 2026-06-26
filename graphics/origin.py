# -*- coding: utf-8 -*-
# EditTime  : 2021-06-02 15:52
# Author    : Of yue
# File      : origin.py
# Intro     :

from __future__ import annotations

import os
import sys
from typing import Optional, Union, Sequence

import pandas
import pandas as pd

# --- Make OriginPro optional ---
try:
    import originpro as op  # type: ignore
except ModuleNotFoundError:
    op = None


class OriginPlot:
    def __init__(self):
        # If OriginPro is not available, keep object usable but inactive
        if op is None:
            self.database = None
            self.database_df = None
            self.plot_series = []
            self.worksheet = None
            return

        def origin_shutdown_exception_hook(exctype, value, traceback):
            # Ensure Origin exits cleanly on exceptions
            try:
                op.exit()
            except Exception:
                pass
            sys.__excepthook__(exctype, value, traceback)

        if getattr(op, "oext", False):
            sys.excepthook = origin_shutdown_exception_hook

        self.database = None
        self.database_df: Optional[pandas.DataFrame] = None
        self.plot_series = []
        self.worksheet = None

    def set_database_df(self, df: pandas.DataFrame):
        if op is None:
            # No OriginPro: keep df for potential later use, but do not crash
            self.database_df = df
            return

        self.database_df = df

        # Template workbook path (keep your original logic, but make it robust)
        tpl_path = os.path.join(op.path("u"), r"Templates", "trajectory.ogwu")
        if not os.path.exists(tpl_path):
            raise FileNotFoundError(
                f"Origin template not found: {tpl_path}\n"
                "Ensure trajectory.ogwu exists under Origin user Templates."
            )

        book_template = op.load_book(tpl_path)
        self.worksheet = book_template[0]

    def add_plot_df(self, cols: Union[Sequence, str], row: str, template=None):
        # Placeholder in your original file; keep as-is
        def _add_plot(ax):
            pass

    def plot(self):
        if op is None:
            # Safe no-op if OriginPro is not installed
            print("[INFO] originpro is not installed. Skipping Origin plotting.")
            return

        if getattr(op, "oext", False):
            op.set_show(True)

        if self.worksheet is None or self.database_df is None:
            raise RuntimeError("OriginPlot.plot() called before set_database_df().")

        self.worksheet.from_df(self.database_df)
        op.wait()
        op.wait("s", 0.2)

    def close(self):
        if op is None:
            return
        if getattr(op, "oext", False):
            # Keep original behavior, but avoid blocking in non-interactive runs if desired
            input("Press Enter to exit Origin...")
            op.exit()


def debug_origin(df: pandas.DataFrame):
    """
    Safe wrapper: if OriginPro (originpro) is not installed, do not raise.
    """
    p = OriginPlot()
    p.set_database_df(df)
    p.plot()
    p.close()


if __name__ == "__main__":
    pass

