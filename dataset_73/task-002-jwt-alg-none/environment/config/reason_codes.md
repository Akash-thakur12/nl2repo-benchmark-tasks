# Gateway rejection reason codes

Every rejection the gateway emits carries one of the codes below, and every
code belongs to exactly one exception class. The class is what callers branch
on; the code is what the auth log is indexed by, so neither may drift.

Two classes, one distinction:

* **`ValidationError`** — the token is *structurally* damaged. The gateway
  could not get far enough to form an opinion about who sent it.
* **`UnauthorizedError`** — the token decoded fine, and policy or
  authentication says no. An expired credential and an unrecognised key id are
  both authentication outcomes, not structural damage.

| code                | class               | meaning                                                                 |
| ------------------- | ------------------- | ----------------------------------------------------------------------- |
| `malformed_parts`   | `ValidationError`   | not three `.`-separated segments                                          |
| `bad_header_b64`    | `ValidationError`   | the header segment is not base64url-encoded JSON                          |
| `header_not_object` | `ValidationError`   | the header decoded, but not to a JSON object                              |
| `bad_payload_b64`   | `ValidationError`   | the payload segment is not base64url-encoded JSON, or not a JSON object   |
| `alg_none`          | `UnauthorizedError` | the header names the unsigned algorithm                                   |
| `alg_pin_mismatch`  | `UnauthorizedError` | the header `alg` is not the pinned algorithm                              |
| `unknown_kid`       | `UnauthorizedError` | the header names no key the ring knows about                              |
| `key_window`        | `UnauthorizedError` | the kid names a real ring entry, but that entry was not in force for this token |
| `sig_mismatch`      | `UnauthorizedError` | the MAC does not match                                                    |
| `expired`           | `UnauthorizedError` | the token is past its `exp`                                               |
| `no_active_key`     | `UnauthorizedError` | `issue()` was asked to mint but no ring entry is currently in force       |

The codes are emitted in the order they appear in the table: structure first,
then the algorithm header, then key selection, then the MAC, then lifetime. A
token with more than one thing wrong is logged under the first code that
fires — that is what makes the corpus lines with two defects readable.

`alg_pin_mismatch` and `sig_mismatch` are deliberately separate. The whole
point of pinning is to be able to count algorithm-confusion attempts, and if
they are folded into the MAC failure bucket that number is unrecoverable.

Exception objects expose the code as `.code`. `str(exc)` is a human message
and is not part of the contract.
