# -*- coding: utf-8 -*-

import sys
import os
from pathlib import Path
import logging
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
import traceback 
from typing import List, Dict, Any, Optional, Union

from flowlauncher import FlowLauncher, FlowLauncherAPI

LOG_FILENAME = "plugin_httpforwarder_errors.log"
PLUGIN_JSON_FILE = "plugin.json"

class HttpQueryForwarder(FlowLauncher):
    icon: str 
    plugindir: str
    resolved_default_icon_path: str
    _logger: Optional[logging.Logger] = None
    _default_settings: Dict[str, Any]

    def __init__(self):
        # Initialize basic attributes before super().__init__()
        self.plugindir = str(Path(__file__).resolve().parent)
        self.icon = self._get_default_ico_from_plugin_json(self.plugindir)
        self.resolved_default_icon_path = ""
        
        # Define default settings
        self._default_settings = {
            "server_address": "http://127.0.0.1",
            "server_port": "8080",
            "server_path": "/",
            "query_param_name": "q",
            "url_encode_query": True,
            "request_timeout": "5",
            "custom_url_template": ""
        }
        
        # Initialize a fallback logger before super().__init__()
        self._init_fallback_logger()
        
        # Call parent constructor - this should load settings
        super().__init__()
        
        # Log what settings we have after super().__init__()
        self.get_logger().info(f"After super().__init__(), settings attribute exists: {hasattr(self, 'settings')}")
        if hasattr(self, 'settings'):
            self.get_logger().info(f"Settings type: {type(self.settings)}")
            self.get_logger().info(f"Settings content: {self.settings}")
        
        # Resolve icon path after initialization
        self.resolved_default_icon_path = self._resolve_icon_path_static(
            self.icon, self.plugindir, self.get_logger()
        )
        
        self.get_logger().info(f"HttpQueryForwarder initialized with icon: {self.resolved_default_icon_path}")

    def _init_fallback_logger(self):
        """Initialize a fallback logger for use before FlowLauncher sets up its logger"""
        logger_name = f"HttpQueryForwarder.Fallback"
        self._logger = logging.getLogger(logger_name)
        
        if not self._logger.handlers:
            log_file_path = Path(self.plugindir) / LOG_FILENAME
            try:
                handler = logging.FileHandler(log_file_path, encoding='utf-8', mode='a')
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self._logger.addHandler(handler)
                self._logger.setLevel(logging.DEBUG)
            except Exception as e:
                # If we can't create a file logger, at least use console
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
                self._logger.addHandler(console_handler)
                self._logger.setLevel(logging.DEBUG)
                self._logger.error(f"Failed to create file logger: {e}")

    def get_logger(self) -> logging.Logger:
        """Get the logger, using FlowLauncher's if available, otherwise fallback"""
        # Try to use FlowLauncher's logger if it exists
        if hasattr(self, 'logger') and isinstance(getattr(self, 'logger', None), logging.Logger):
            return self.logger
        # Otherwise use our fallback logger
        return self._logger

    def get_settings_dict(self) -> Dict[str, Any]:
        """Get settings as a dictionary, handling various possible formats"""
        # First, check if settings exist and what type they are
        if hasattr(self, 'settings'):
            settings_value = self.settings
            self.get_logger().debug(f"Found settings attribute, type: {type(settings_value)}")
            
            # If it's already a dict, return it (merged with defaults)
            if isinstance(settings_value, dict):
                result = self._default_settings.copy()
                result.update(settings_value)
                self.get_logger().debug(f"Settings is dict, merged with defaults: {result}")
                return result
            
            # If it's a string, try to parse it as JSON
            if isinstance(settings_value, str):
                try:
                    parsed = json.loads(settings_value)
                    if isinstance(parsed, dict):
                        result = self._default_settings.copy()
                        result.update(parsed)
                        self.get_logger().debug(f"Settings was JSON string, parsed and merged: {result}")
                        return result
                except json.JSONDecodeError:
                    self.get_logger().warning(f"Settings is string but not valid JSON: {settings_value}")
            
            # If settings has attributes like an object, try to convert to dict
            if hasattr(settings_value, '__dict__'):
                try:
                    settings_dict = vars(settings_value)
                    result = self._default_settings.copy()
                    result.update(settings_dict)
                    self.get_logger().debug(f"Settings was object, converted to dict: {result}")
                    return result
                except Exception as e:
                    self.get_logger().warning(f"Could not convert settings object to dict: {e}")
        
        self.get_logger().warning("No valid settings found, using defaults")
        return self._default_settings.copy()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Safely get a setting value with fallback"""
        settings = self.get_settings_dict()
        value = settings.get(key, default)
        self.get_logger().debug(f"Getting setting '{key}': {value} (default was: {default})")
        return value

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
        logger_to_use = self.get_logger()
        
        # Handle case where initialization might not be complete
        final_resolved_default_icon = getattr(self, 'resolved_default_icon_path', '')
        if not final_resolved_default_icon:
            # Try to resolve icon if not already done
            icon = getattr(self, 'icon', '')
            plugindir = getattr(self, 'plugindir', str(Path(__file__).resolve().parent))
            final_resolved_default_icon = self._resolve_icon_path_static(icon, plugindir, logger_to_use)
        
        current_plugindir = getattr(self, 'plugindir', str(Path(__file__).resolve().parent))

        logger_to_use.info(f"=== Query started with param: '{param}' ===")
        
        # Log all current settings for debugging
        all_settings = self.get_settings_dict()
        logger_to_use.info(f"All current settings: {all_settings}")

        # Get settings with proper type handling
        server_addr = str(self.get_setting("server_address", "http://localhost"))
        server_port_str = str(self.get_setting("server_port", "8080"))
        raw_server_path = str(self.get_setting("server_path", "/"))
        server_path = ("/" + raw_server_path.lstrip("/")) if not raw_server_path.startswith("/") else raw_server_path
        if server_path == "//":
            server_path = "/"
        
        query_param_name = str(self.get_setting("query_param_name", "q"))
        url_encode_setting = self.get_setting("url_encode_query", True)

        # Log the settings being used
        logger_to_use.info(f"Using settings: server_address='{server_addr}', server_port='{server_port_str}', server_path='{server_path}', query_param_name='{query_param_name}'")

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
                logger_to_use.info(f"Using custom URL template: '{custom_url_template}'")
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
                logger_to_use.info(f"Final URL (from custom template): {url}")

            else:
                # Build URL from individual settings
                logger_to_use.info("Building URL from individual settings (no custom template)")
                effective_server_addr = server_addr
                if not urlsplit(effective_server_addr).scheme and effective_server_addr:
                    effective_server_addr = "http://" + effective_server_addr
                    logger_to_use.debug(f"Added http:// scheme to server address: '{effective_server_addr}'")
                
                parsed_addr = urlsplit(effective_server_addr)
                scheme = parsed_addr.scheme or "http"
                netloc_host = parsed_addr.hostname
                if not netloc_host:
                    raise ValueError(f"Invalid server_address '{server_addr}': no hostname.")

                # Build the network location (host:port)
                if parsed_addr.port:
                    # Port was included in the server_address
                    final_netloc = f"{netloc_host}:{parsed_addr.port}"
                    logger_to_use.debug(f"Using port from server_address: {parsed_addr.port}")
                elif server_port_str:
                    # Use the separate port setting
                    final_netloc = f"{netloc_host}:{server_port_str}"
                    logger_to_use.debug(f"Using port from server_port setting: {server_port_str}")
                else:
                    # No port specified
                    final_netloc = netloc_host
                    logger_to_use.debug("No port specified, using default for scheme")
                
                query_to_send = quote_plus(param) if url_encode else param
                query_params_str = f"{query_param_name}={query_to_send}"
                url = urlunsplit((scheme, final_netloc, server_path, query_params_str, ''))
                current_url_for_error_reporting = url
                logger_to_use.info(f"Final URL (from individual settings): {url}")

            logger_to_use.info(f"Making HTTP request to: {url}")
            response_obj_for_logging = requests.get(url, timeout=timeout)
            response_obj_for_logging.raise_for_status()
            server_response_data = response_obj_for_logging.json()

            if not isinstance(server_response_data, list):
                raise ValueError(f"Server response from {url} is not a JSON list.")

            logger_to_use.info(f"Received {len(server_response_data)} items from server")

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
        
        logger_to_use.info(f"=== Query completed, returning {len(results)} results ===")
        return results

    def context_menu(self, data: Any) -> List[dict]:
        """Handle context menu requests"""
        menu_results: List[dict] = []
        logger_to_use = self.get_logger()
        final_resolved_default_icon = getattr(self, 'resolved_default_icon_path', '')
        current_plugindir = getattr(self, 'plugindir', str(Path(__file__).resolve().parent))

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
        self.get_logger().info(f"Opening URL: {url}")
        try:
            webbrowser.open(url)
            self.get_logger().debug(f"Successfully opened URL: {url}")
        except Exception as e:
            self.get_logger().error(f"Failed to open URL '{url}': {e}", exc_info=True)
            FlowLauncherAPI.show_msg(
                "Error Opening URL",
                f"Could not open: {url}",
                getattr(self, 'resolved_default_icon_path', '')
            )

    def shell_run(self, command: Union[str, List[str]]):
        """Execute shell command"""
        cmd_str = command[0] if isinstance(command, list) and command else str(command)
        self.get_logger().info(f"Executing shell command: {cmd_str}")
        
        try:
            # Use Flow Launcher's ShellRun API
            payload = {
                "method": "Flow.Launcher.ShellRun",
                "parameters": [cmd_str]
            }
            print(json.dumps(payload))
            self.get_logger().info(f"Shell command requested: {cmd_str}")
        except Exception as e:
            self.get_logger().error(f"Failed to execute shell command '{cmd_str}': {e}", exc_info=True)
            FlowLauncherAPI.show_msg(
                "Shell Command Error",
                f"Failed to execute command",
                getattr(self, 'resolved_default_icon_path', '')
            )

    def copy_to_clipboard(self, text: Any, directCopy: Union[str, bool] = False, showDefaultNotification: Union[str, bool] = True):
        """Copy text to clipboard"""
        text_to_copy = str(text)
        self.get_logger().info(f"Copying to clipboard: {text_to_copy[:50]}...")
        
        try:
            # Convert string bools if needed
            should_direct_copy = str(directCopy).lower() == 'true' if isinstance(directCopy, str) else bool(directCopy)
            should_show_notification = str(showDefaultNotification).lower() == 'true' if isinstance(showDefaultNotification, str) else bool(showDefaultNotification)

            payload = {
                "method": "Flow.Launcher.CopyToClipboard",
                "parameters": [text_to_copy, should_direct_copy, should_show_notification]
            }
            print(json.dumps(payload))
            self.get_logger().info("Text copied to clipboard")
        except Exception as e:
            self.get_logger().error(f"Failed to copy to clipboard: {e}", exc_info=True)
            FlowLauncherAPI.show_msg(
                "Clipboard Error",
                "Failed to copy to clipboard",
                getattr(self, 'resolved_default_icon_path', '')
            )

    def change_query(self, new_query: str, requery: Union[str, bool] = "false"):
        """Change the query in Flow Launcher"""
        query_str = str(new_query)
        
        try:
            should_requery = str(requery).lower() == 'true' if isinstance(requery, str) else bool(requery)
            self.get_logger().info(f"Changing query to: {query_str}, requery: {should_requery}")
            
            FlowLauncherAPI.change_query(query_str, requery=should_requery)
            self.get_logger().info("Query changed successfully")
        except Exception as e:
            self.get_logger().error(f"Failed to change query: {e}", exc_info=True)
            FlowLauncherAPI.show_msg(
                "Query Change Error",
                "Failed to change query",
                getattr(self, 'resolved_default_icon_path', '')
            )

    def flow_show_msg(self, title: str, sub_title: str, ico_path_param: Optional[str] = None):
        """Show a message using Flow Launcher API"""
        title_str, sub_title_str = str(title), str(sub_title)
        
        try:
            icon_to_use = self._resolve_icon_path_static(
                ico_path_param, 
                getattr(self, 'plugindir', str(Path(__file__).resolve().parent)), 
                self.get_logger()
            ) or getattr(self, 'resolved_default_icon_path', '')
            
            self.get_logger().info(f"Showing message: {title_str}")
            
            payload = {
                "method": "Flow.Launcher.ShowMsg",
                "parameters": [title_str, sub_title_str, icon_to_use]
            }
            print(json.dumps(payload))
            self.get_logger().info("Message displayed")
        except Exception as e:
            self.get_logger().error(f"Failed to show message: {e}", exc_info=True)


if __name__ == "__main__":
    HttpQueryForwarder()