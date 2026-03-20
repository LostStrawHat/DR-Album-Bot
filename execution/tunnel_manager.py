import subprocess
import os
import time
import re
import signal
import psutil

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CLOUDFLARED_PATH = os.path.join(WORKSPACE_ROOT, 'cloudflared_local')
LOG_FILE = os.path.join(WORKSPACE_ROOT, '.tmp', 'tunnel.log')
PID_FILE = os.path.join(WORKSPACE_ROOT, '.tmp', 'tunnel.pid')
DASHBOARD_PID_FILE = os.path.join(WORKSPACE_ROOT, '.tmp', 'dashboard.pid')
PYTHON_PATH = os.path.join(WORKSPACE_ROOT, 'venv', 'bin', 'python')

def is_tunnel_running():
    """Checks if the cloudflared process is actually running."""
    if not os.path.exists(PID_FILE):
        return False
    
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        if psutil.pid_exists(pid):
            process = psutil.Process(pid)
            if 'cloudflared' in process.name().lower():
                return True
    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    
    return False

def is_dashboard_running():
    """Checks if the dashboard process is actually running using psutil."""
    if not os.path.exists(DASHBOARD_PID_FILE):
        return False
    
    try:
        with open(DASHBOARD_PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        if psutil.pid_exists(pid):
            process = psutil.Process(pid)
            # Check if this PID is indeed a python process running dashboard.py
            cmd_line = " ".join(process.cmdline())
            if 'python' in cmd_line.lower() and 'dashboard.py' in cmd_line.lower():
                return True
    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    
    return False

def start_dashboard():
    """Starts the dashboard in the background."""
    if is_dashboard_running():
        return None

    print("Starting Dashboard...")
    cmd = [PYTHON_PATH, os.path.join(WORKSPACE_ROOT, 'execution', 'dashboard.py')]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    
    with open(DASHBOARD_PID_FILE, 'w') as f:
        f.write(str(process.pid))
    
    # Give it a moment to bind to the port
    time.sleep(3)
    return process.pid

def start_tunnel():
    """Starts a new Cloudflare tunnel and returns the process PID."""
    if is_tunnel_running():
        print("Tunnel already running.")
        return None

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    # Clear old log to ensure we get a fresh URL
    if os.path.exists(LOG_FILE):
        open(LOG_FILE, 'w').close()

    print(f"Starting Cloudflare tunnel: {CLOUDFLARED_PATH}")
    
    # Command to run cloudflared
    cmd = [CLOUDFLARED_PATH, "tunnel", "--url", "http://localhost:5050"]
    
    # Open log file for output
    log_f = open(LOG_FILE, 'w')
    
    # Spawn process
    process = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid # Ensure it runs in a new session
    )
    
    with open(PID_FILE, 'w') as f:
        f.write(str(process.pid))
    
    return process.pid

def get_tunnel_url(timeout=30):
    """Parses the tunnel log to find the public URL."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                content = f.read()
                # Cloudflare URLs match this pattern
                match = re.search(r'https://[a-zA-Z0-9.-]*\.trycloudflare\.com', content)
                if match:
                    return match.group(0)
        time.sleep(1)
    return None

def ensure_tunnel_active():
    """Ensures a tunnel is running and returns the URL. Restarts if stopped."""
    # 1. Ensure Dashboard is running (otherwise tunnel gives 502)
    if not is_dashboard_running():
        start_dashboard()

    # 2. Ensure Tunnel is running
    if not is_tunnel_running():
        print("Tunnel not running. Starting...")
        start_tunnel()
    
    url = get_tunnel_url()
    return url

if __name__ == "__main__":
    # Test script
    url = ensure_tunnel_active()
    print(f"Tunnel URL: {url}")
