"""SteamDB parsing tasks for browser automation."""
from typing import Dict, List, Any, Optional, Callable
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtCore import QUrl
from sqlalchemy.orm import Session

from src.services import GameService, DepotService
from src.db import Depot, Manifest


class SteamDBTask:
    """Base class for SteamDB parsing tasks."""
    name = "Base Task"
    description = "Base class for tasks"
    target_type = None  # "app" or "depot"

    def __init__(self, page: QWebEnginePage, target_id: Optional[str] = None):
        self.page = page
        self.target_id = target_id

    def get_url(self) -> Optional[str]:
        """Return the URL to navigate to before executing the script."""
        if self.target_type == "app" and self.target_id:
            return f"https://steamdb.info/app/{self.target_id}/depots/"
        elif self.target_type == "depot" and self.target_id:
            return f"https://steamdb.info/depot/{self.target_id}/"
        return None

    def get_js_code(self) -> str:
        """Return the JavaScript code to execute for parsing."""
        raise NotImplementedError("Subclass must implement get_js_code()")

    def process_result(self, result: Any) -> Any:
        """Process the result from JS execution. Returns sentinel strings for errors."""
        if result in ("RETRY_REQUIRED", "RATE_LIMITED", None):
            return result
        return result

    def get_block_detection_js(self) -> str:
        """Common JS to detect Cloudflare, rate limits, or missing layout."""
        return """
            const bodyText = document.body.innerText;
            if (bodyText.includes('rate limited') || bodyText.includes('scraping bots')) {
                return "RATE_LIMITED";
            }
            const isSteamDB = document.querySelector('.navbar-brand') || document.querySelector('.app-logo');
            if (!isSteamDB) {
                return "RETRY_REQUIRED";
            }
        """

    def save_result(self, session: Session, result: Any) -> Any:
        """Save the result to the database. Must be overridden by subclass."""
        raise NotImplementedError("Subclass must implement save_result()")

    def run(self, callback: Callable[[Any], None]) -> None:
        """Run the task: navigate if needed, then execute JS."""
        target_url = self.get_url()
        
        if target_url and self.page.url().toString() != target_url:
            def on_load_finished(ok):
                self.page.loadFinished.disconnect(on_load_finished)
                if ok:
                    self._execute_js(callback)
                else:
                    callback(None)
            self.page.loadFinished.connect(on_load_finished)
            self.page.load(QUrl(target_url))
        else:
            self._execute_js(callback)

    def _execute_js(self, callback: Callable[[Any], None]) -> None:
        js_code = self.get_js_code()
        
        def internal_callback(result):
            processed = self.process_result(result)
            callback(processed)

        self.page.runJavaScript(js_code, internal_callback)


class DepotsParsingTask(SteamDBTask):
    """Task to parse depots information from SteamDB."""
    name = "Parse Depots"
    description = "Parses the depots table from the SteamDB app page and updates the database."
    target_type = "app"

    def get_js_code(self) -> str:
        """JavaScript to parse depot table from SteamDB."""
        return f"""
        (function() {{
            const rows = document.querySelectorAll('tr.depot');
            const nameElement = document.querySelector('h1[itemprop="name"]');
            const appName = nameElement ? nameElement.textContent.trim() : null;
            
            if (rows.length > 0) {{
                const depots = [];
                rows.forEach(row => {{
                    const depotId = row.getAttribute('data-depotid');
                    if (!depotId) return;

                    const configCell = row.querySelector('td.depot-config');
                    if (!configCell) return;

                    let os = null;
                    let language = null;
                    let name = null;

                    const osSpan = configCell.querySelector('span.depot-os');
                    if (osSpan) os = osSpan.textContent.trim();

                    const langSpan = configCell.querySelector('span.depot-language');
                    if (langSpan) language = langSpan.textContent.trim();

                    const mutedSpans = configCell.querySelectorAll('span.i.muted');
                    if (mutedSpans.length > 0) {{
                        name = Array.from(mutedSpans).map(span => span.textContent.trim()).join(' ');
                    }}

                    if (!os && name) {{
                        if (name.includes('exe_win') || name.includes('exe_windows')) os = 'Windows';
                        else if (name.includes('exe_linux')) os = 'Linux';
                        else if (name.includes('exe_mac')) os = 'macOS';
                    }}

                    depots.push({{
                        depot_id: depotId,
                        os: os,
                        language: language,
                        name: name
                    }});
                }});
                return {{
                    name: appName,
                    depots: depots
                }};
            }}

            {self.get_block_detection_js()}

            return {{
                name: appName,
                depots: []
            }};
        }})();
        """

    def process_result(self, result: Any) -> Any:
        result = super().process_result(result)
        if isinstance(result, str):
            return result  # Sentinel (RETRY_REQUIRED, etc.)
        if not isinstance(result, dict):
            return {"name": None, "depots": []}
        return result

    def save_result(self, session: Session, result: Dict[str, Any]) -> str:
        depots = result.get('depots', [])
        app_name = result.get('name')

        if not self.target_id:
            raise ValueError("App ID is required to save depots.")

        # Update game name if found
        if app_name:
            GameService(session).update_game(self.target_id, {'name': app_name})

        if not depots:
            return f"Updated game name to '{app_name}' (no depots found)" if app_name else "No depots found or parsing failed"

        # Upsert depots
        depot_service = DepotService(session)
        for depot_data in depots:
            depot_id = depot_data['depot_id']
            if session.query(Depot).filter(Depot.depot_id == depot_id).first():
                depot_service.update_depot(depot_id, {
                    'os': depot_data.get('os'),
                    'language': depot_data.get('language'),
                })
            else:
                depot_service.create_depot({
                    'depot_id': depot_id,
                    'app_id': self.target_id,
                    'name': depot_data.get('name') or f"Depot {depot_id}",
                    'os': depot_data.get('os'),
                    'language': depot_data.get('language'),
                })

        msg = f"Updated/Created {len(depots)} depots"
        if app_name:
            msg = f"Updated game name to '{app_name}' and " + msg.lower()
        return msg


class ManifestsParsingTask(SteamDBTask):
    """Task to parse manifest history for a specific depot from SteamDB."""
    name = "Parse Manifests"
    description = "Parses the manifest history table for a depot and updates the database."
    target_type = "depot"

    def get_js_code(self) -> str:
        return f"""
        (function() {{
            const manifestTable = document.querySelector('#manifests');
            
            if (manifestTable) {{
                const manifests = [];
                const rows = manifestTable.querySelectorAll('tbody tr');
                rows.forEach(row => {{
                    const dateCell = row.querySelector('td:nth-child(1)');
                    const relativeDateCell = row.querySelector('td:nth-child(2)');
                    const manifestIdCell = row.querySelector('td:nth-child(3) a');
                    
                    if (dateCell && relativeDateCell && manifestIdCell) {{
                        manifests.push({{
                            seen_date: dateCell.textContent.trim(),
                            relative_date: relativeDateCell.getAttribute('data-time'),
                            manifest_id: manifestIdCell.textContent.trim()
                        }});
                    }}
                }});
                return manifests;
            }}

            {self.get_block_detection_js()}

            return []; // Valid SteamDB, just no manifests table.
        }})();
        """

    def process_result(self, result: Any) -> Any:
        result = super().process_result(result)
        if isinstance(result, str):
            return result  # Sentinel
        if not isinstance(result, list):
            return []
        return result

    def save_result(self, session: Session, result: List[Dict[str, Any]]) -> str:
        if not result:
            return "No manifests found or parsing failed"

        count = 0
        for manifest_data in result:
            manifest_id = manifest_data['manifest_id']
            
            manifest = session.query(Manifest).filter(Manifest.manifest_id == manifest_id).first()
            if not manifest:
                new_manifest = Manifest(
                    manifest_id=manifest_id,
                    depot_id=self.target_id,
                    date_str=manifest_data['seen_date']
                )
                session.add(new_manifest)
                count += 1
        
        session.commit()
        return f"Created {count} new manifests for depot {self.target_id}"
