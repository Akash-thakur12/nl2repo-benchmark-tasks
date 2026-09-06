"""Reference model for the scaffolder, following docs/scaffold-spec.md literally.

Section numbers in comments refer to that document. This is the authority for
expected output; nothing is hardcoded. The golden repository is written in
TypeScript and must agree with this model exactly.
"""
import json

OPEN = "{{"
CLOSE = "}}"


class ScaffoldError(Exception):
    def __init__(self, code, detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


def render_value(value):
    """2.4: booleans as true/false, integral numbers without a trailing .0."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def interpolate(text, answers):
    """2.1-2.3. {{{{ is a literal {{ and never opens a reference."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith(OPEN * 2, i):          # 2.3
            out.append(OPEN)
            i += 4
            continue
        if text.startswith(CLOSE * 2, i):
            out.append(CLOSE)
            i += 4
            continue
        if text.startswith(OPEN, i):
            end = text.find(CLOSE, i + 2)
            if end == -1:
                out.append(text[i])
                i += 1
                continue
            name = text[i + 2:end]                # 2.1 no trimming
            if name not in answers:
                raise ScaffoldError("UNKNOWN_VARIABLE", name)   # 2.2
            out.append(render_value(answers[name]))
            i = end + 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def truthy(value):
    """3.2: only the empty string is a falsy string; only 0 is a falsy number."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return value != ""


def normalise(path):
    """4.5: collapse repeated slashes and drop '.' segments, then judge safety."""
    if path.startswith("/"):
        raise ScaffoldError("UNSAFE_PATH", path)
    parts = []
    for segment in path.split("/"):
        if segment == "" or segment == ".":
            continue
        if segment == "..":
            if not parts:
                raise ScaffoldError("UNSAFE_PATH", path)
            parts.pop()
            continue
        parts.append(segment)
    if not parts:
        raise ScaffoldError("UNSAFE_PATH", path)
    return "/".join(parts)


def build_answers(template, supplied):
    """1.1-1.3: prompts in declaration order, missing outranks unknown."""
    prompts = template.get("prompts", []) or []
    answers = {}
    for prompt in prompts:
        name = prompt["name"]
        if name in supplied:
            answers[name] = supplied[name]
        elif "default" in prompt:
            answers[name] = prompt["default"]
        else:
            raise ScaffoldError("MISSING_ANSWER", name)
    known = {prompt["name"] for prompt in prompts}
    for name in supplied:
        if name not in known:
            raise ScaffoldError("UNKNOWN_ANSWER", name)
    return answers


def condition_holds(entry, answers):
    """3.1, 3.3."""
    when = entry.get("when")
    if when is None:
        return True
    if when not in answers:
        raise ScaffoldError("UNKNOWN_VARIABLE", when)
    return truthy(answers[when])


def render(plan):
    template = plan.get("template", {}) or {}
    supplied = plan.get("answers", {}) or {}
    existing = set(plan.get("existing", []) or [])

    empty = {"files": [], "skipped": [], "hooks": [], "errors": []}

    try:
        answers = build_answers(template, supplied)

        files = []
        skipped = []
        claimed = set()      # 4.3 every rendered path, written or not
        for entry in template.get("files", []) or []:      # 4.1
            if not condition_holds(entry, answers):
                continue
            path = normalise(interpolate(entry["path"], answers))   # 2.5, 4.5
            content = interpolate(entry.get("content", ""), answers)
            if path in claimed:                            # 4.3 collision first
                skipped.append({"path": path, "reason": "COLLISION"})
                continue
            claimed.add(path)
            if path in existing and not entry.get("force"):
                skipped.append({"path": path, "reason": "EXISTS"})    # 4.2
                continue
            mode = "755" if entry.get("executable") else "644"        # 4.4
            files.append({"path": path, "content": content, "mode": mode})

        hooks = []
        for entry in template.get("hooks", []) or []:      # 5.1, 5.2
            if not condition_holds(entry, answers):
                continue
            hooks.append(interpolate(entry["run"], answers))          # 5.3

        return {"files": files, "skipped": skipped, "hooks": hooks, "errors": []}
    except ScaffoldError as failure:                       # 5.4, 6.4
        return dict(empty, errors=[{"code": failure.code, "detail": failure.detail}])


def render_text(text):
    return render(json.loads(text))
