"""
Reporting latex display widget
Deprecated as this will move to another repo, but for now will keep as reference
"""
import os
import pandas as pd

from IPython.display import display, Markdown


class Report:
    COUNTER = 0

    def __init__(self, debug=False) -> None:
        self.debug = debug

    def output(self, df: pd.DataFrame, column_format=None, size=None):
        if size is not None:
            df = df[:size]

        if self.debug:
            return display(df)

        output = f'{Report.COUNTER}.tex'
        Report.COUNTER += 1

        if df is not None and len(df):
            df.to_latex(output, column_format=column_format, index=False, escape=True)
        else:
            if os.path.exists(output):
                os.remove(output)
            open(output, 'a').close()

        display(Markdown(f'STAMUSINPUT: {output}'))
