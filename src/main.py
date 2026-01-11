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
        
        # Start MCP Atlassian server
        try:
            self._proc = subprocess.Popen(
                ["npx", "-y", "@modelcontextprotocol/server-atlassian"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env={**subprocess.os.environ}
            )
        except FileNotFoundError:
            # Try without npx
            try:
                self._proc = subprocess.Popen(
                    ["mcp-atlassian"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            except FileNotFoundError:
                raise RuntimeError(
                    "Could not find mcp-atlassian. Install it with:\n"
                    "npm install -g @modelcontextprotocol/server-atlassian"
                )

        print(f"[MCP] Process started with PID: {self._proc.pid}", file=sys.stderr)
        self._responses = queue.Queue()

        # Background thread to read stdout
        def reader():
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                print(f"[MCP STDOUT RAW] {line}", file=sys.stderr)
                try:
                    msg = json.loads(line)
                    self._responses.put(msg)
                    print(f"[MCP RECV] {json.dumps(msg)[:200]}", file=sys.stderr)
                except json.JSONDecodeError as e:
                    print(f"[MCP LOG] Non-JSON: {line}", file=sys.stderr)

        # Background thread to read stderr
        def error_reader():
            for line in self._proc.stderr:
                print(f"[MCP ERR] {line.strip()}", file=sys.stderr)

        threading.Thread(target=reader, daemon=True).start()
        threading.Thread(target=error_reader, daemon=True).start()

        # Wait for process to start and check if it's alive
        time.sleep(2)
        
        if self._proc.poll() is not None:
            # Process died
            stderr_output = self._proc.stderr.read()
            raise RuntimeError(f"MCP server exited immediately. stderr: {stderr_output}")
        
        print("[MCP] Server is running, starting initialization...", file=sys.stderr)

        # Initialize MCP connection
        self._initialize()

    def _initialize(self):
        """Complete MCP initialization handshake"""
        print("[MCP] Starting initialization...", file=sys.stderr)
        
        # Step 1: Send initialize request
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

        self._send_request(init_payload)
        
        # Wait for initialize response
        try:
            msg = self._responses.get(timeout=10)
            if msg.get("id") == "init":
                if "error" in msg:
                    raise RuntimeError(f"Initialize failed: {msg['error']}")
                print(f"[MCP] Initialize response received", file=sys.stderr)
            else:
                # Put it back if it's not our response
                self._responses.put(msg)
        except queue.Empty:
            raise RuntimeError("Timeout waiting for initialize response")

        # Step 2: Send initialized notification (CRITICAL!)
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        
        self._send_request(initialized_notification)
        print("[MCP] Sent initialized notification", file=sys.stderr)
        
        # Give server a moment to process
        time.sleep(0.5)
        
        self._initialized = True
        print("[MCP] Initialization complete!", file=sys.stderr)

    def _send_request(self, payload):
        """Send a JSON-RPC request to MCP server"""
        msg = json.dumps(payload)
        print(f"[MCP SEND] {msg[:200]}", file=sys.stderr)
        self._proc.stdin.write(msg + "\n")
        self._proc.stdin.flush()

    def _call_mcp(self, method: str, params: dict):
        """Call an MCP tool method"""
        if not self._initialized:
            raise RuntimeError("MCP not initialized")

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        self._send_request(payload)

        # Wait for response with matching ID
        start_time = time.time()
        timeout = 30
        
        try:
            while time.time() - start_time < timeout:
                msg = self._responses.get(timeout=5)
                
                if msg.get("id") == request_id:
                    if "error" in msg:
                        error_detail = json.dumps(msg["error"], indent=2)
                        raise RuntimeError(f"MCP error: {error_detail}")
                    return msg.get("result")
                else:
                    # Not our message, put it back
                    self._responses.put(msg)
                    time.sleep(0.1)
                    
        except queue.Empty:
            raise RuntimeError(f"Timeout waiting for response from MCP (request_id: {request_id})")

    def _run(self, story_key: str) -> str:
        """Fetch a Jira issue"""
        print(f"[TOOL] Fetching Jira issue: {story_key}", file=sys.stderr)
        
        try:
            result = self._call_mcp(
                method="tools/call",
                params={
                    "name": "jira_get_issue",
                    "arguments": {
                        "issue_key": story_key
                    }
                }
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error fetching issue: {str(e)}"

    def __del__(self):
        """Cleanup MCP process"""
        if self._proc:
            self._proc.terminate()
            self._proc.wait(timeout=5)


# --------------------------------------------------
# Agents and Tasks
# --------------------------------------------------
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

# --------------------------------------------------
# RUN
# --------------------------------------------------
if __name__ == "__main__":
    result = crew.kickoff(
        inputs={"story_key": "NEX-808"}
    )

    print("\n\n===== JIRA ISSUE OUTPUT =====\n")
    print(result)