# scaffolder

Renders a project scaffolding plan into the file tree it would produce, without
touching the disk.

    ./run.sh <plan_dir> <output_json>

Runs on Node's built-in TypeScript type stripping, so there is nothing to
install and nothing to build.

## Layout

    src/types.ts        the plan and report shapes
    src/values.ts       value rendering and truthiness
    src/interpolate.ts  {{name}} substitution and brace escaping
    src/paths.ts        path normalisation and safety
    src/answers.ts      prompt resolution
    src/render.ts       the file and hook passes
    src/cli.ts          directory walk and JSON output

Behaviour is specified in `docs/scaffold-spec.md`; section numbers appear in
comments beside the rule each piece implements.
