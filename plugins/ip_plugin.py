"""plugins/ip_plugin.py — Sample plugin for fetching public and local IP info."""

import re
import socket
import urllib.request

PLUGIN_NAME = "Network Info Plugin"
PLUGIN_DESCRIPTION = "Provides local and public IP address information via voice."


def can_handle(text: str) -> bool:
    t = text.lower().strip()
    return any(p in t for p in ("what is my ip", "my ip address", "local ip", "public ip", "network ip"))


def execute(text: str, config: dict) -> str:
    t = text.lower().strip()
    
    # Check for local IP request
    if "local" in t:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return f"Your local IP address is {local_ip}."
        except Exception:
            return "Could not determine local IP address."

    # Default to public IP
    try:
        req = urllib.request.Request(
            "https://api.ipify.org?format=json",
            headers={"User-Agent": "Jarvis-Assistant/1.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            import json
            data = json.loads(response.read().decode())
            pub_ip = data.get("ip")
            return f"Your public IP address is {pub_ip}."
    except Exception as e:
        return f"Could not retrieve IP address: {e}"
