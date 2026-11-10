"""Entry point: ``python -m app`` serves, ``python -m app migrate`` runs the migration job."""

import sys

from app.main import main

sys.exit(main(argv=sys.argv[1:]))
