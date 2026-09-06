# samples/

Captured incident windows, one JSON file per incident under `incidents/`.

Each file records:

* `samples_in_arrival_order` — the samples exactly as the collector delivered
  them to the consumer, in delivery order, with the platform metric series
  under their real names.
* `recorded_verdict` — the verdict the on-call engineer saw at the time, and
  which a correct classifier must reproduce when the window is replayed through
  it. These have all been reviewed; they are ground truth.

To replay a capture, feed `samples_in_arrival_order` into `add()` in the order
listed, mapping each series to its ingest parameter per
`../docs/collector-agent.md` §1, then call `diagnose()`.
