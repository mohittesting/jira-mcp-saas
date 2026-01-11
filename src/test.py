#!/usr/bin/env python3
"""
Test script to verify mcp-atlassian server works independently
"""
import subprocess
import json
import time
import sys

def test_mcp_server():
    print("Starting mcp-atlassian server...\n")
    
    # Try different ways to start the server
    commands = [
        ["npx", "-y", "@modelcontextprotocol/server-atlassian"],
        ["mcp-atlassian"],
        ["node_modules/.bin/mcp-atlassian"]
    ]
    
    proc = None
    for cmd in commands:
        try:
            print(f"Trying: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            time.sleep(2)
            if proc.poll() is None:
                print(f"✓ Server started with PID {proc.pid}\n")
                break
            else:
                stderr = proc.stderr.read()
                print(f"✗ Failed: {stderr}\n")
                proc = None
        except FileNotFoundError:
            print(f"✗ Command not found\n")
            continue
    
    if proc is None:
        print("ERROR: Could not start mcp-atlassian server!")
        print("\nInstall it with:")
        print("  npm install -g @modelcontextprotocol/server-atlassian")
        return False
    
    # Check if process is still alive
    if proc.poll() is not None:
        stderr = proc.stderr.read()
        print(f"ERROR: Server died immediately!")
        print(f"stderr: {stderr}")
        return False
    
    print("Sending initialize request...")
    
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {
                "name": "test-client",
                "version": "1.0"
            },
            "capabilities": {}
        }
    }
    
    try:
        # Send request
        request_json = json.dumps(init_request) + "\n"
        print(f"Sending: {request_json.strip()}\n")
        proc.stdin.write(request_json)
        proc.stdin.flush()
        
        # Wait for response
        print("Waiting for response (10 seconds)...")
        start = time.time()
        response = None
        
        while time.time() - start < 10:
            if proc.poll() is not None:
                print("ERROR: Process died!")
                stderr = proc.stderr.read()
                print(f"stderr: {stderr}")
                return False
                
            # Try to read a line (non-blocking check)
            try:
                line = proc.stdout.readline()
                if line:
                    print(f"Received: {line.strip()}\n")
                    try:
                        response = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        print(f"Non-JSON output: {line}")
            except:
                pass
            
            time.sleep(0.1)
        
        if response:
            print("✓ SUCCESS! Server responded:")
            print(json.dumps(response, indent=2))
            
            # Send initialized notification
            print("\nSending initialized notification...")
            notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            proc.stdin.write(json.dumps(notif) + "\n")
            proc.stdin.flush()
            print("✓ Sent")
            
            return True
        else:
            print("✗ TIMEOUT: No response from server")
            # Check stderr
            stderr_lines = []
            try:
                while True:
                    line = proc.stderr.readline()
                    if not line:
                        break
                    stderr_lines.append(line)
            except:
                pass
            
            if stderr_lines:
                print("\nstderr output:")
                print("".join(stderr_lines))
            
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    print("=" * 60)
    print("MCP Atlassian Server Test")
    print("=" * 60 + "\n")
    
    success = test_mcp_server()
    
    print("\n" + "=" * 60)
    if success:
        print("✓ MCP server is working correctly!")
    else:
        print("✗ MCP server test failed")
        print("\nTroubleshooting:")
        print("1. Make sure you have Node.js installed")
        print("2. Install the server: npm install -g @modelcontextprotocol/server-atlassian")
        print("3. Set environment variables:")
        print("   - ATLASSIAN_URL")
        print("   - ATLASSIAN_EMAIL")  
        print("   - ATLASSIAN_API_TOKEN")
    print("=" * 60)