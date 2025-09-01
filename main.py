# -*- coding: utf-8 -*-

import sys
import os
from pathlib import Path
import json

# --- BEGIN SYS.PATH MODIFICATION ---
plugindir_path = Path(__file__).resolve().parent
libdir = plugindir_path / 'lib'
sys.path.insert(0, str(plugindir_path))
if libdir.is_dir():
    sys.path.insert(0, str(libdir))
# --- END SYS.PATH MODIFICATION ---

import webbrowser
import requests
from urllib.parse import quote_plus, urlunsplit, urlsplit, urlencode, parse_qsl
from typing import List, Dict, Any, Optional, Union

from flowlauncher import FlowLauncher, FlowLauncherAPI


class HttpQueryForwarder(FlowLauncher):
    
    def query(self, param: str = "") -> List[dict]:
        """Main query handler"""
        # Get settings with defaults
        settings = getattr(self, 'settings', {}) or {}
        
        # Default values
        defaults = {
            "server_address": "http://127.0.0.1",
            "server_port": "8080",
            "server_path": "/",
            "query_param_name": "q",
            "url_encode_query": True,
            "request_timeout": "5",
            "custom_url_template": ""
        }
        
        # Get each setting with fallback to default
        server_addr = str(settings.get("server_address", defaults["server_address"]))
        server_port = str(settings.get("server_port", defaults["server_port"]))
        server_path = str(settings.get("server_path", defaults["server_path"]))
        query_param_name = str(settings.get("query_param_name", defaults["query_param_name"]))
        url_encode_query = settings.get("url_encode_query", defaults["url_encode_query"])
        request_timeout = settings.get("request_timeout", defaults["request_timeout"])
        custom_url_template = str(settings.get("custom_url_template", defaults["custom_url_template"]))
        
        # Ensure server_path starts with /
        if server_path and not server_path.startswith("/"):
            server_path = "/" + server_path
        
        # Handle boolean
        if isinstance(url_encode_query, str):
            url_encode = url_encode_query.lower() == 'true'
        else:
            url_encode = bool(url_encode_query)
        
        # Handle timeout
        try:
            timeout = int(request_timeout)
            if timeout <= 0:
                timeout = 5
        except (ValueError, TypeError):
            timeout = 5
        
        results = []
        icon_path = "Images/icon.png"
        
        try:
            # Check for custom URL template
            custom_url_template = custom_url_template.strip()
            
            if custom_url_template:
                # Use custom template
                encoded_query = quote_plus(param)
                url = (
                    custom_url_template
                    .replace("{encoded_query}", encoded_query)
                    .replace("{query}", param)
                    .replace("{query_param_name}", query_param_name)
                )
                
                # Add scheme if missing
                if not urlsplit(url).scheme:
                    url = "http://" + url
                    
                # If template doesn't contain query placeholders, append query param
                if "{query}" not in custom_url_template and "{encoded_query}" not in custom_url_template:
                    parsed = urlsplit(url)
                    query_value = quote_plus(param) if url_encode else param
                    existing_qs = list(parse_qsl(parsed.query, keep_blank_values=True))
                    existing_qs.append((query_param_name, query_value))
                    new_query = urlencode(existing_qs, doseq=True)
                    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
            else:
                # Build URL from components
                # Ensure server_addr has a scheme
                if not urlsplit(server_addr).scheme:
                    server_addr = "http://" + server_addr
                
                parsed = urlsplit(server_addr)
                scheme = parsed.scheme or "http"
                host = parsed.hostname
                
                if not host:
                    raise ValueError(f"Invalid server address: {server_addr}")
                
                # Handle port
                if parsed.port:
                    netloc = f"{host}:{parsed.port}"
                elif server_port:
                    netloc = f"{host}:{server_port}"
                else:
                    netloc = host
                
                # Build query string
                query_value = quote_plus(param) if url_encode else param
                query_string = f"{query_param_name}={query_value}"
                
                # Construct final URL
                url = urlunsplit((scheme, netloc, server_path, query_string, ''))
            
            # Make request
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list):
                raise ValueError("Server response is not a JSON list")
            
            # Process results
            for item in data:
                if isinstance(item, dict) and item.get("Title"):
                    result = {
                        "Title": item["Title"],
                        "SubTitle": item.get("SubTitle", ""),
                        "IcoPath": item.get("IcoPath", icon_path),
                        "Score": int(item.get("Score", 0))
                    }
                    
                    # Add optional fields
                    if item.get("AutoCompleteText"):
                        result["AutoCompleteText"] = item["AutoCompleteText"]
                    
                    if item.get("ContextData"):
                        result["ContextData"] = item["ContextData"]
                    
                    # Handle context menu items
                    if item.get("ContextMenuItems") and isinstance(item["ContextMenuItems"], list):
                        result["ContextData"] = {
                            "original_data": item.get("ContextData"),
                            "defined_menu_items": item["ContextMenuItems"]
                        }
                    
                    # Handle actions
                    if item.get("JsonRPCAction"):
                        action = item["JsonRPCAction"]
                        if isinstance(action, dict) and action.get("method"):
                            method = action["method"]
                            if hasattr(self, method):
                                result["JsonRPCAction"] = {
                                    "method": method,
                                    "parameters": action.get("parameters", [])
                                }
                    
                    results.append(result)
            
        except requests.exceptions.Timeout:
            results = [{
                "Title": "Error: Request Timed Out",
                "SubTitle": f"Server at {url if 'url' in locals() else server_addr} timed out",
                "IcoPath": icon_path
            }]
        except requests.exceptions.RequestException as e:
            results = [{
                "Title": "Error: Network Request Failed",
                "SubTitle": f"Could not connect to server: {str(e)[:50]}",
                "IcoPath": icon_path
            }]
        except Exception as e:
            results = [{
                "Title": "Error: Plugin Error",
                "SubTitle": str(e)[:100],
                "IcoPath": icon_path
            }]
        
        if not results:
            if param:
                results = [{
                    "Title": "No results",
                    "SubTitle": f"No results for '{param}'",
                    "IcoPath": icon_path
                }]
            else:
                results = [{
                    "Title": "HTTP Query Forwarder",
                    "SubTitle": f"Ready. Server: {server_addr}",
                    "IcoPath": icon_path
                }]
        
        return results

    def context_menu(self, data: Any) -> List[dict]:
        """Handle context menu requests"""
        menu_results = []
        icon_path = "Images/icon.png"
        
        if isinstance(data, dict) and "defined_menu_items" in data:
            for item_def in data.get("defined_menu_items", []):
                if isinstance(item_def, dict) and item_def.get("Title"):
                    ctx_result = {
                        "Title": item_def["Title"],
                        "SubTitle": item_def.get("SubTitle", ""),
                        "IcoPath": item_def.get("IcoPath", icon_path)
                    }
                    
                    json_rpc = item_def.get("JsonRPCAction")
                    if isinstance(json_rpc, dict):
                        method = json_rpc.get("method")
                        params = json_rpc.get("parameters", [])
                        if method and hasattr(self, method):
                            ctx_result["JsonRPCAction"] = {
                                "method": method,
                                "parameters": params if isinstance(params, list) else []
                            }
                    
                    menu_results.append(ctx_result)
        
        if not menu_results:
            menu_results.append({
                "Title": "No context actions available",
                "IcoPath": icon_path
            })
        
        return menu_results

    def open_url(self, url: str):
        """Open URL in browser"""
        webbrowser.open(url)

    def shell_run(self, command: Union[str, List[str]]):
        """Execute shell command"""
        cmd_str = command[0] if isinstance(command, list) and command else str(command)
        payload = {
            "method": "Flow.Launcher.ShellRun",
            "parameters": [cmd_str]
        }
        print(json.dumps(payload))

    def copy_to_clipboard(self, text: Any, directCopy: Union[str, bool] = False, showDefaultNotification: Union[str, bool] = True):
        """Copy text to clipboard"""
        text_to_copy = str(text)
        
        # Convert string bools if needed
        should_direct_copy = str(directCopy).lower() == 'true' if isinstance(directCopy, str) else bool(directCopy)
        should_show_notification = str(showDefaultNotification).lower() == 'true' if isinstance(showDefaultNotification, str) else bool(showDefaultNotification)
        
        payload = {
            "method": "Flow.Launcher.CopyToClipboard",
            "parameters": [text_to_copy, should_direct_copy, should_show_notification]
        }
        print(json.dumps(payload))

    def change_query(self, new_query: str, requery: Union[str, bool] = "false"):
        """Change query"""
        should_requery = str(requery).lower() == 'true' if isinstance(requery, str) else bool(requery)
        FlowLauncherAPI.change_query(new_query, requery=should_requery)

    def flow_show_msg(self, title: str, sub_title: str, ico_path: Optional[str] = None):
        """Show message"""
        icon = ico_path or "Images/icon.png"
        payload = {
            "method": "Flow.Launcher.ShowMsg",
            "parameters": [str(title), str(sub_title), icon]
        }
        print(json.dumps(payload))


if __name__ == "__main__":
    HttpQueryForwarder()