# Key-confusion policy

`detect_key_confusion(header_alg, key_type) -> bool` answers exactly one
question: *would honouring this token's `alg` with this key constitute an
algorithm confusion?*

## What `key_type` is

`key_type` is an operator-written description of a key, taken verbatim from the
key inventory. It has a fixed shape:

* the **leading token** is the JWK `kty`, the key type family. It is the
  leading run of alphanumeric characters, terminated by whitespace or by any
  punctuation character (`-`, `,`, `/`, `(` and so on). Case is not
  significant.
* everything after it is **unstructured operator prose**: usage notes, curve
  names, rotation dates, ticket references, how the key is stored or
  transported. It carries no policy meaning whatsoever.

So `"RSA public key"` has kty `RSA`, `"rsa"` has kty `RSA`, `"oct secret"` has
kty `oct`, `"EC P-256 verification key"` has kty `EC`, `"OKP Ed25519 public
key"` has kty `OKP`, and `"RSA-PSS public key (rotated 2025-11)"` has kty `RSA`
because the leading run stops at the hyphen.

Only the leading token is consulted. Scanning the whole string for a family
name reads the prose as if it were policy, and the prose routinely names
algorithms that have nothing to do with the key's own type - see the
`HMAC key wrapped by RSA KEK` row of the inventory, an ordinary symmetric
content key whose wrapping KEK happens to be RSA. Wrapping an HMAC key with an
RSA KEK is standard key management, not key confusion.

## Families

* **Asymmetric key families**: `RSA`, `EC`, `OKP`.
* **HMAC algorithm family**: `HS256`, `HS384`, `HS512`.

Anything else - `oct`, `octet`, an unrecognised word, an empty string - is not
an asymmetric family.

## The rule

Confusion is flagged (`True`) **iff** `header_alg` is in the HMAC algorithm
family **and** the kty of `key_type` is in one of the asymmetric key families.
Every other combination is `False`.

An asymmetric `alg` presented with an asymmetric key (`RS256` with an RSA key)
is the normal case, not a confusion. A symmetric `alg` presented with a
symmetric key is also normal.

## Reference cases

`../data/key_inventory.csv` is a truth table: one row per inventory key, with
its kid, its true kty, its `key_type` description, and the expected flag for
each of the four presentations `HS256`, `HS384`, `HS512` and `RS256`.
