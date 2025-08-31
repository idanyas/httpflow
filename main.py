# -*- coding: utf-8 -*-

import sys
import os
from pathlib import Path
import logging
import json
from functools import cached_property

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
import traceback 
from typing import List, Dict, Any, Optional, Union

from flowlauncher import FlowLauncher, FlowLauncherAPI

LOG_FILENAME = "plugin_httpforwarder_errors.log"
PLUGIN_JSON_FILE = "plugin.json"

class HttpQueryForwarder(FlowLauncher):
    icon: str 
    plugindir: str
    resolved_default_icon_path: str

    def __init__(self):
        super().__init__()
        
        self.plugindir = str(Path(__file__).resolve().parent)
        self.icon = self._get_default_ico_from_plugin_json(self.plugindir)
        self.resolved_default_icon_path = self._resolve_icon_path_static(
            self.icon, self.plugindir, self.logger
        )
        
        self.logger.info(f"HttpQueryForwarder initialized with icon: {self.resolved_default_icon_path}")

    @cached_property
    def settings_path(self) -> Path:
        """Get the path to the settings file managed by Flow Launcher"""
        try:
            # Try to find the Flow Launcher data directory
            app_data = Path(__file__).resolve().parent.parent.parent
            settings_dir = app_data / 'Settings' / 'Plugins' / self.__class__.__name__
            settings_file = settings_dir / 'Settings.json'
            
            self.logger.debug(f"Settings path resolved to: {settings_file}")
            return settings_file
        except Exception as e:
            self.logger.error(f"Failed to resolve settings path: {e}")
            return Path.home() / 'AppData' / 'Roaming' / 'FlowLauncher' / 'Settings' / 'Plugins' / self.__class__.__name__ / 'Settings.json'

    @cached_property
    def settings(self) -> Dict[str, Any]:
        """Load settings from Flow Launcher's settings file"""
        default_settings = {
            "server_address": "http://127.0.0.1",
            "server_port": "8080",
            "server_path": "/",
            "query_param_name": "q",
            "url_encode_query": True,
            "request_timeout": "5",
            "custom_url_template": ""
        }
        
        try:
            if self.settings_path.exists():
                self.logger.info(f"Loading settings from: {self.settings_path}")
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    
                # Merge with defaults to ensure all keys exist
                for key, default_value in default_settings.items():
                    if key not in loaded_settings:
                        loaded_settings[key] = default_value
                        
                self.logger.debug(f"Loaded settings: {loaded_settings}")
                return loaded_settings
            else:
                self.logger.info(f"Settings file not found at {self.settings_path}, using defaults")
                return default_settings
        except Exception as e:
            self.logger.error(f"Failed to load settings: {e}", exc_info=True)
            return default_settings

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Safely get a setting value with fallback"""
        return self.settings.get(key, default)

    def _get_default_ico_from_plugin_json(self, current_plugindir: str) -> str:
        try:
            plugin_json_path = Path(current_plugindir) / PLUGIN_JSON_FILE
            if plugin_json_path.exists():
                with open(plugin_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("IcoPath", "")
            return ""
        except:
            return ""

    @staticmethod
    def _resolve_icon_path_static(icon_path_str: Optional[str], plugin_dir_str: str, logger_instance: logging.Logger) -> str:
        if not icon_path_str:
            return ""
        
        normalized_path_str = icon_path_str.replace("\\", "/")
        
        if normalized_path_str.startswith(("http://", "https://")):
            return normalized_path_str
        
        if os.path.isabs(normalized_path_str):
            abs_path_obj = Path(normalized_path_str)
            if abs_path_obj.exists() and abs_path_obj.is_file():
                return str(abs_path_obj.resolve()).replace("\\", "/")
            logger_instance.debug(f"Absolute icon path ('{normalized_path_str}') not found or not a file.")
            return ""
        
        if not plugin_dir_str:
            logger_instance.warning(f"Cannot resolve relative icon '{normalized_path_str}': plugin_dir_str is empty.")
            return ""
        
        try:
            prospective_path = Path(plugin_dir_str) / normalized_path_str
            resolved_abs_path = prospective_path.resolve()
            
            if resolved_abs_path.exists() and resolved_abs_path.is_file():
                return str(resolved_abs_path).replace("\\", "/")
            
            logger_instance.debug(f"Icon not found at: {resolved_abs_path}")
            return ""
        except Exception as e:
            logger_instance.error(f"Error resolving icon '{normalized_path_str}': {e}")
            return ""

    def query(self, param: str = "") -> List[dict]:
        """Main query handler"""
        logger_to_use = self.logger
        final_resolved_default_icon = self.resolved_default_icon_path
        current_plugindir = self.plugindir

        logger_to_use.debug(f"Querying with param: '{param}'")

        # Get settings with proper type handling
        server_addr = str(self.get_setting("server_address", "http://localhost"))
        server_port_str = str(self.get_setting("server_port", "8080"))
        raw_server_path = str(self.get_setting("server_path", "/"))
        server_path = ("/" + raw_server_path.lstrip("/")) if not raw_server_path.startswith("/") else raw_server_path
        if server_path == "//":
            server_path = "/"
        
        query_param_name = str(self.get_setting("query_param_name", "q"))
        url_encode_setting = self.get_setting("url_encode_query", True)

        if isinstance(url_encode_setting, str):
            url_encode = url_encode_setting.lower() == 'true'
        else:
            url_encode = bool(url_encode_setting)

        timeout_val = self.get_setting("request_timeout", "5")
        try:
            timeout = int(timeout_val)
            if timeout <= 0:
                logger_to_use.warning(f"Request timeout ('{timeout_val}') is not positive. Defaulting to 5s.")
                timeout = 5
        except (ValueError, TypeError):
            logger_to_use.warning(f"Invalid request_timeout value '{timeout_val}'. Defaulting to 5s.")
            timeout = 5
        
        current_url_for_error_reporting: str = "URL not constructed"
        results: List[dict] = []
        response_obj_for_logging = None

        try:
            # Check if a custom URL template should be used
            custom_url_template = str(self.get_setting("custom_url_template", "") or "").strip()

            if custom_url_template:
                logger_to_use.info("Using custom URL template from settings.")
                # Prepare substitution values
                encoded_for_placeholder = quote_plus(param)
                replaced_url = (
                    custom_url_template
                    .replace("{encoded_query}", encoded_for_placeholder)
                    .replace("{query}", param)
                    .replace("{query_param_name}", query_param_name)
                )

                # Ensure scheme; if missing, default to http
                if not urlsplit(replaced_url).scheme:
                    replaced_url = "http://" + replaced_url
                    logger_to_use.debug(f"No scheme detected in template. Defaulting to http -> '{replaced_url}'")

                parsed = urlsplit(replaced_url)

                # If neither {query} nor {encoded_query} were used, append the query param using the configured name
                if ("{encoded_query}" not in custom_url_template) and ("{query}" not in custom_url_template):
                    query_to_send = quote_plus(param) if url_encode else param
                    existing_qs = list(parse_qsl(parsed.query, keep_blank_values=True))
                    existing_qs.append((query_param_name, query_to_send))
                    new_query = urlencode(existing_qs, doseq=True)
                    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
                else:
                    # Placeholders already handled; use as-is
                    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))

                current_url_for_error_reporting = url
                logger_to_use.info(f"Requesting URL (custom template): {url}")

            else:
                # Legacy path: build URL from server_address/port/path/query_param_name
                effective_server_addr = server_addr
                if not urlsplit(effective_server_addr).scheme and effective_server_addr:
                    effective_server_addr = "http://" + effective_server_addr
                
                parsed_addr = urlsplit(effective_server_addr)
                scheme = parsed_addr.scheme or "http"
                netloc_host = parsed_addr.hostname
                if not netloc_host:
                    raise ValueError(f"Invalid server_address '{server_addr}': no hostname.")

                final_netloc = f"{netloc_host}:{parsed_addr.port}" if parsed_addr.port else (f"{netloc_host}:{server_port_str}" if server_port_str else netloc_host)
                query_to_send = quote_plus(param) if url_encode else param
                query_params_str = f"{query_param_name}={query_to_send}"
                url = urlunsplit((scheme, final_netloc, server_path, query_params_str, ''))
                current_url_for_error_reporting = url
                logger_to_use.info(f"Requesting URL: {url}")

            response_obj_for_logging = requests.get(url, timeout=timeout)
            response_obj_for_logging.raise_for_status()
            server_response_data = response_obj_for_logging.json()

            if not isinstance(server_response_data, list):
                raise ValueError(f"Server response from {url} is not a JSON list.")

            for item_data in server_response_data:
                if not (isinstance(item_data, dict) and item_data.get("Title")):
                    continue
                
                item_specific_icon = self._resolve_icon_path_static(
                    item_data.get("IcoPath"), current_plugindir, logger_to_use
                )
                
                result_entry: Dict[str, Any] = {
                    "Title": item_data["Title"],
                    "SubTitle": item_data.get("SubTitle", ""),
                    "IcoPath": item_specific_icon or final_resolved_default_icon,
                    "Score": int(item_data.get("Score", 0)),
                }
                
                if item_data.get("AutoCompleteText"):
                    result_entry["AutoCompleteText"] = item_data["AutoCompleteText"]
                
                plugin_context_data: Any = item_data.get("ContextData")
                if item_data.get("ContextMenuItems") and isinstance(item_data["ContextMenuItems"], list):
                    plugin_context_data = {
                        "original_data": item_data.get("ContextData"),
                        "defined_menu_items": item_data["ContextMenuItems"]
                    }
                if plugin_context_data is not None:
                    result_entry["ContextData"] = plugin_context_data
                
                json_rpc = item_data.get("JsonRPCAction")
                if isinstance(json_rpc, dict):
                    method, params = json_rpc.get("method"), json_rpc.get("parameters", [])
                    if method and hasattr(self, method) and callable(getattr(self, method)):
                        result_entry["JsonRPCAction"] = {
                            "method": method,
                            "parameters": params if isinstance(params, list) else ([params] if params is not None else [])
                        }
                    else:
                        logger_to_use.warning(f"Invalid JsonRPCAction method ('{method}') or not callable.")
                
                results.append(result_entry)

        except requests.exceptions.Timeout:
            logger_to_use.error(f"Request timed out: {current_url_for_error_reporting}.", exc_info=True)
            results = [{
                "Title": "Error: Request Timed Out",
                "SubTitle": f"Server at {current_url_for_error_reporting} timed out.",
                "IcoPath": final_resolved_default_icon
            }]
        except requests.exceptions.RequestException as e:
            logger_to_use.error(f"Network Request Failed: {current_url_for_error_reporting}. Error: {e}", exc_info=True)
            results = [{
                "Title": "Error: Network Request Failed",
                "SubTitle": f"Could not connect to '{current_url_for_error_reporting}'. {type(e).__name__}",
                "IcoPath": final_resolved_default_icon
            }]
        except (json.JSONDecodeError, ValueError) as e:
            response_text = response_obj_for_logging.text[:500] if response_obj_for_logging else "N/A"
            logger_to_use.error(f"Data Error: {current_url_for_error_reporting}. Response: '{response_text}'. Error: {e}", exc_info=True)
            results = [{
                "Title": f"Error: {type(e).__name__}",
                "SubTitle": str(e),
                "IcoPath": final_resolved_default_icon
            }]
        except Exception:
            logger_to_use.exception(f"Unexpected error in query: {current_url_for_error_reporting}.")
            results = [{
                "Title": "Error: Plugin Error",
                "SubTitle": "Unexpected error. Check logs.",
                "IcoPath": final_resolved_default_icon
            }]
        
        if not results and param.strip():
            results.append({
                "Title": "No results",
                "SubTitle": f"No results for query '{param}' from server.",
                "IcoPath": final_resolved_default_icon
            })
        elif not results and not param.strip():
            results.append({
                "Title": "HTTP Query Forwarder Ready",
                "SubTitle": "Enter a query to forward to your HTTP server",
                "IcoPath": final_resolved_default_icon
            })
        
        return results

    def context_menu(self, data: Any) -> List[dict]:
        """Handle context menu requests"""
        menu_results: List[dict] = []
        logger_to_use = self.logger
        final_resolved_default_icon = self.resolved_default_icon_path
        current_plugindir = self.plugindir

        if isinstance(data, dict) and "defined_menu_items" in data:
            for item_def in data.get("defined_menu_items", []):
                if not (isinstance(item_def, dict) and item_def.get("Title")):
                    continue
                
                item_icon = self._resolve_icon_path_static(
                    item_def.get("IcoPath"), current_plugindir, logger_to_use
                )
                
                ctx_result: Dict[str, Any] = {
                    "Title": item_def["Title"],
                    "SubTitle": item_def.get("SubTitle", ""),
                    "IcoPath": item_icon or final_resolved_default_icon
                }
                
                json_rpc = item_def.get("JsonRPCAction")
                if isinstance(json_rpc, dict):
                    method, params = json_rpc.get("method"), json_rpc.get("parameters", [])
                    if method and hasattr(self, method) and callable(getattr(self, method)):
                        ctx_result["JsonRPCAction"] = {
                            "method": method,
                            "parameters": params if isinstance(params, list) else ([params] if params is not None else [])
                        }
                    else:
                        logger_to_use.warning(f"Invalid context JsonRPCAction method ('{method}').")
                
                menu_results.append(ctx_result)
        
        if not menu_results:
            default_context_title = "No context actions defined by server"
            if isinstance(data, dict) and "original_data" in data:
                default_context_title = "No specific context actions (original data present)"

            menu_results.append({
                "Title": default_context_title,
                "IcoPath": final_resolved_default_icon
            })
        
        return menu_results

    def open_url(self, url: str):
        """Open URL in default browser"""
        self.logger.info(f"Opening URL: {url}")
        try:
            webbrowser.open(url)
            self.logger.debug(f"Successfully opened URL: {url}")
        except Exception as e:
            self.logger.error(f"Failed to open URL '{url}': {e}", exc_info=True)
            FlowLauncherAPI.show_msg(
                "Error Opening URL",
                f"Could not open: {url}",
                self.resolved_default_icon_path
            )

    def shell_run(self, command: Union[str, List[str]]):
        """Execute shell command"""
        cmd_str = command[0] if isinstance(command, list) and command else str(command)
        self.logger.info(f"Executing shell command: {cmd_str}")
        
        try:
            # Use Flow Launcher's ShellRun API
            payload = {
                "method": "Flow.Launcher.ShellRun",
                "parameters": [cmd_str]
            }
            print(json.dumps(payload))
            self.logger.info(f"Shell command requested: {cmd_str}")
        except Exception as e:
            self.logger.error(f"Failed to execute shell command '{cmd_str}': {e}", exc_info=True)
            FlowLauncherAPI.show_msg(
                "Shell Command Error",
                f"Failed to execute command",
                self.resolved_default_icon_path
            )

    def copy_to_clipboard(self, text: Any, directCopy: Union[str, bool] = False, showDefaultNotification: Union[str, bool] = True):
        """Copy text to clipboard"""
        text_to_copy = str(text)
        self.logger.info(f"Copying to clipboard: {text_to_copy[:50]}...")
        
        try:
            # Convert string bools if needed
            should_direct_copy = str(directCopy).lower() == 'true' if isinstance(directCopy, str) else bool(directCopy)
            should_show_notification = str(showDefaultNotification).lower() == 'true' if isinstance(showDefaultNotification, str) else bool(showDefaultNotification)

            payload = {
                "method": "Flow.Launcher.CopyToClipboard",
                "parameters": [text_to_copy, should_direct_copy, should_show_notification]
            }
            print(json.dumps(payload))
            self.logger.info("Text copied to clipboard")
        except Exception as e:
            self.logger.error(f"Failed to copy to clipboard: {e}", exc_info=True)
            FlowLauncherAPI.show_msg(
                "Clipboard Error",
                "Failed to copy to clipboard",
                self.resolved_default_icon_path
            )

    def change_query(self, new_query: str, requery: Union[str, bool] = "false"):
        """Change the query in Flow Launcher"""
        query_str = str(new_query)
        
        try:
            should_requery = str(requery).lower() == 'true' if isinstance(requery, str) else bool(requery)
            self.logger.info(f"Changing query to: {query_str}, requery: {should_requery}")
            
            FlowLauncherAPI.change_query(query_str, requery=should_requery)
            self.logger.info("Query changed successfully")
        except Exception as e:
            self.logger.error(f"Failed to change query: {e}", exc_info=True)
            FlowLauncherAPI.show_msg(
                "Query Change Error",
                "Failed to change query",
                self.resolved_default_icon_path
            )

    def flow_show_msg(self, title: str, sub_title: str, ico_path_param: Optional[str] = None):
        """Show a message using Flow Launcher API"""
        title_str, sub_title_str = str(title), str(sub_title)
        
        try:
            icon_to_use = self._resolve_icon_path_static(
                ico_path_param, self.plugindir, self.logger
            ) or self.resolved_default_icon_path
            
            self.logger.info(f"Showing message: {title_str}")
            
            payload = {
                "method": "Flow.Launcher.ShowMsg",
                "parameters": [title_str, sub_title_str, icon_to_use]
            }
            print(json.dumps(payload))
            self.logger.info("Message displayed")
        except Exception as e:
            self.logger.error(f"Failed to show message: {e}", exc_info=True)


if __name__ == "__main__":
    HttpQueryForwarder()