"""benchmark/custom-binary-fmt -- Binary record format: magic 'BIN1' (4B) | count (u16 LE) | [tag(u8), nlen(u16 LE), name(utf8), value(u32 LE)]*N. Encode/decode."""
