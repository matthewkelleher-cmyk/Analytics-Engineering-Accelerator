"""Load EIA data for the "electricity" source into the raw schema. See loader.py for options."""

import sys

from loader import main

if __name__ == "__main__":
    sys.exit(main("electricity"))