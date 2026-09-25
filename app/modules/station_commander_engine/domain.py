"""Domain concepts for the Station Commander boundary.

This module intentionally contains only placeholder domain concepts and does not
implement business workflow logic.
"""


class StationCommanderContext:
    """Contextual metadata for commander oversight workflows."""

    def __init__(self, station_code=None):
        self.station_code = station_code
