# Plan capture format

A plan file is a single UTF-8 JSON object.

```json
{
  "template": {
    "prompts": [
      {"name": "name"},
      {"name": "typescript", "default": true},
      {"name": "license", "default": "MIT"}
    ],
    "files": [
      {"path": "src/{{name}}/index.ts", "content": "export const n = \"{{name}}\";",
       "when": "typescript"},
      {"path": "bin/run", "content": "#!/bin/sh\n", "executable": true},
      {"path": "README.md", "content": "# {{name}}\n", "force": true}
    ],
    "hooks": [
      {"run": "npm install", "when": "typescript"}
    ]
  },
  "answers": {"name": "acme"},
  "existing": ["README.md"]
}
```

- `template.prompts` - ordered. Each has `name`, optionally `default`.
- `template.files` - ordered. Each has `path` and `content`, optionally `when`,
  `executable` and `force`.
- `template.hooks` - ordered. Each has `run`, optionally `when`.
- `answers` - the answers supplied on the command line.
- `existing` - paths that already exist in the target directory.

`prompts`, `files`, `hooks`, `answers` and `existing` may each be absent, and
are then empty.

## Report

The tool writes one JSON object keyed by plan file name with `.plan` stripped.
Each value has exactly these four keys:

```json
{
  "files": [{"path": "src/acme/index.ts", "content": "...", "mode": "644"}],
  "skipped": [{"path": "README.md", "reason": "EXISTS"}],
  "hooks": ["npm install"],
  "errors": []
}
```

- `files` - written files in write order, with `path`, `content` and `mode`
  (`"644"` or `"755"`)
- `skipped` - files not written, in declaration order, with `path` and `reason`
  (`"EXISTS"` or `"COLLISION"`)
- `hooks` - the rendered command strings that ran, in order
- `errors` - `code` and `detail`, where `code` is one of `MISSING_ANSWER`,
  `UNKNOWN_ANSWER`, `UNKNOWN_VARIABLE` or `UNSAFE_PATH`, and `detail` is the
  prompt name, answer name, variable name or rendered path it refers to
