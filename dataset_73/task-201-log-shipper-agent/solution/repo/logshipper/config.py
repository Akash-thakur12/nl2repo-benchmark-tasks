"""Session configuration (spec section 9).

The first record of a session is always a config record. The shipper reloads
its configuration on SIGHUP, so a capture may carry further config records; the
limits they carry take effect where the record is applied.
"""


class Config:
    FIELDS = ("max_lines", "max_bytes", "max_age_ms", "max_retries", "spool_max_bytes")

    def __init__(self, record):
        self.apply(record)

    def apply(self, record):
        """Replace every limit from a config record (the first, or a reload)."""
        for name in self.FIELDS:
            value = record[name]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError("config.%s must be a positive integer" % name)
            setattr(self, name, value)
