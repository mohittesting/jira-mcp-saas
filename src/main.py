from crewai import Agent, Task, Crew
from crewai.tools import BaseTool
from dotenv import load_dotenv
from pydantic import PrivateAttr

import subprocess
import json
import uuid
import threading
import queue
import time
import sys
import os

load_dotenv()


class JiraMCPTool(BaseTool):
    name: str = "jira_fetch"
    description: str = "Fetch a Jira issue using MCP Atlassian"

    _proc: subprocess.Popen | None = PrivateAttr(default=None)
    _responses: queue.Queue | None = PrivateAttr(default=None)
    _initialized: bool = PrivateAttr(default=False)

    def __init__(self):
        super().__init__()

        print("[MCP] Starting mcp-atlassian server...", file=sys.stderr)

        # ✅ START MCP SERVER (CORRECT WAY)
        self._proc = subprocess.Popen(
            ["node", "index.js"],
            cwd="/mcp-atlassian/packages/server-atlassian",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={
                **os.environ,
                "NODE_ENV": "production",
            },
        )

        print(f"[MCP] Process started with PID: {self._proc.pid}", file=sys.stderr)
        self._responses = queue.Queue()

        # ---- STDOUT reader (JSON-RPC messages) ----
        def reader():
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._responses.put(msg)
                    print(f"[MCP RECV] {json.dumps(msg)[:200]}", file=sys.stderr)
                except json.JSONDecodeError:
                    print(f"[MCP LOG] {line}", file=sys.stderr)

        # ---- STDERR reader ----
        def error_reader():
            for line in self._proc.stderr:
                print(f"[MCP ERR] {line.rstrip()}", file=sys.stderr)

        threading.Thread(target=reader, daemon=True).start()
        threading.Thread(target=error_reader, daemon=True).start()

        # ---- Check MCP is alive ----
        time.sleep(2)
        if self._proc.poll() is not None:
            raise RuntimeError("MCP server exited immediately")

        print("[MCP] Server is running, initializing...", file=sys.stderr)
        self._initialize()

    def _initialize(self):
        init_payload = {
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "crewai-mcp-client",
                    "version": "0.1.0"
                },
                "capabilities": {}
            }
        }

        self._send(init_payload)

        try:
            msg = self._responses.get(timeout=10)
            if "error" in msg:
                raise RuntimeError(msg["error"])
        except queue.Empty:
            raise RuntimeError("Timeout waiting for MCP initialize")

        self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        self._initialized = True
        print("[MCP] Initialization complete", file=sys.stderr)

    def _send(self, payload: dict):
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

    def _call_mcp(self, method: str, params: dict):
        if not self._initialized:
            raise RuntimeError("MCP not initialized")

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        self._send(payload)

        start = time.time()
        while time.time() - start < 30:
            try:
                msg = self._responses.get(timeout=5)
            except queue.Empty:
                continue

            if msg.get("id") == request_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result")

            self._responses.put(msg)

        raise RuntimeError("Timeout waiting for MCP response")

    def _run(self, story_key: str) -> str:
        try:
            result = self._call_mcp(
                "tools/call",
                {
                    "name": "jira_get_issue",
                    "arguments": {
                        "issue_key": story_key
                    }
                }
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching issue: {e}"

    def __del__(self):
        if self._proc:
            self._proc.terminate()
            self._proc.wait(timeout=5)


# -------------------- CREW SETUP --------------------

jira_agent = Agent(
    role="Jira User Story Analyst",
    goal="Fetch a Jira user story using MCP Atlassian",
    backstory="Expert in Jira who retrieves issue data using MCP.",
    tools=[JiraMCPTool()],
    verbose=True
)

fetch_task = Task(
    description="Fetch the Jira user story with key {{story_key}} and return the raw issue data.",
    expected_output="Raw Jira issue JSON.",
    agent=jira_agent
)

crew = Crew(
    agents=[jira_agent],
    tasks=[fetch_task],
    process="sequential",
    verbose=True
)

# -------------------- RUN --------------------

if __name__ == "__main__":
    result = crew.kickoff(inputs={"story_key": "NEX-808"})
    print("\n===== JIRA ISSUE OUTPUT =====\n")
    print(result)
