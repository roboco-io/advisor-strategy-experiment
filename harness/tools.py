"""Anthropic 정의 bash/text_editor 도구의 client-side 샌드박스 실행."""
from __future__ import annotations
import os
import signal
import subprocess

BASH_TOOL = {"type": "bash_20250124", "name": "bash"}
EDITOR_TOOL = {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}


class Sandbox:
    def __init__(self, workdir: str, timeout: int = 120):
        self.workdir = os.path.realpath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.timeout = timeout

    def _resolve(self, path: str) -> str:
        full = os.path.realpath(os.path.join(self.workdir, path))
        if full != self.workdir and not full.startswith(self.workdir + os.sep):
            raise ValueError(f"path escapes workdir: {path}")
        return full

    def run_bash(self, inp: dict) -> str:
        if inp.get("restart"):
            return "bash session restarted"
        cmd = inp["command"]
        proc = subprocess.Popen(
            cmd, shell=True, cwd=self.workdir, start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        pgid = os.getpgid(proc.pid)  # capture NOW, while proc is guaranteed alive
        try:
            out, _ = proc.communicate(timeout=self.timeout)
            result = out[:20000] or "(no output)"
        except subprocess.TimeoutExpired:
            result = f"error: command timed out after {self.timeout}s"
        finally:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return result

    def edit(self, inp: dict) -> str:
        cmd = inp["command"]
        try:
            path = self._resolve(inp["path"])
        except (ValueError, KeyError) as e:
            return f"error: {e}"
        if cmd == "view":
            if os.path.isdir(path):
                return "\n".join(sorted(os.listdir(path)))
            with open(path) as f:
                return f.read()[:20000]
        if cmd == "create":
            os.makedirs(os.path.dirname(path) or self.workdir, exist_ok=True)
            with open(path, "w") as f:
                f.write(inp.get("file_text", ""))
            return f"created {inp['path']}"
        if cmd == "str_replace":
            with open(path) as f:
                text = f.read()
            old, new = inp["old_str"], inp["new_str"]
            if text.count(old) != 1:
                return "error: old_str must match exactly once"
            with open(path, "w") as f:
                f.write(text.replace(old, new))
            return "edited"
        if cmd == "insert":
            with open(path) as f:
                lines = f.readlines()
            lines.insert(inp["insert_line"], inp["insert_text"] + "\n")
            with open(path, "w") as f:
                f.writelines(lines)
            return "inserted"
        return f"error: unknown command {cmd}"


def handle_tool_use(block, sandbox: Sandbox) -> dict:
    name = block.name
    result = {"type": "tool_result", "tool_use_id": block.id}
    try:
        if name == "bash":
            result["content"] = sandbox.run_bash(block.input)
        elif name == "str_replace_based_edit_tool":
            content = sandbox.edit(block.input)
            result["content"] = content
            if isinstance(content, str) and content.startswith("error:"):
                result["is_error"] = True
        else:
            result["content"] = f"error: unknown tool {name}"
            result["is_error"] = True
    except Exception as e:  # noqa: BLE001 - 도구 오류는 모델에 되돌려줌
        result["content"] = f"error: {e}"
        result["is_error"] = True
    return result
