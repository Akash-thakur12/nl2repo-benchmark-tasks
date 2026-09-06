"""Report assembly (session-format.md, Report)."""


def build(shipper):
    return {
        "delivered": shipper.delivered,
        "dlq": shipper.dead_letters,
        "dropped": shipper.buffer.dropped,
        "pending": shipper.buffer.texts(),
        "offsets": {
            name: {"read": handle.read_offset, "acked": handle.acked_offset}
            for name, handle in sorted(shipper.files.items())
        },
    }
