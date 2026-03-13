import os
import requests
import sentry_sdk
from app import vanguard_log


class MonitoringManager:
    """Manages Uptime Heartbeats for Better Stack (Rev 101)."""

    @staticmethod
    def send_heartbeat(process_name="General"):
        heartbeat_url = os.environ.get('BETTER_STACK_HEARTBEAT_URL')
        if not heartbeat_url or "placeholder" in heartbeat_url:
            vanguard_log(f"Heartbeat skipped for {process_name} (URL not configured)", "DEBUG")
            return False
        try:
            # Better Stack Heartbeat es un simple GET
            res = requests.get(heartbeat_url, timeout=5)
            if res.status_code == 200:
                vanguard_log(f"Heartbeat sent successfully for: {process_name}", "INFO")
                return True
            else:
                vanguard_log(f"Heartbeat failed for {process_name}. Status: {res.status_code}", "WARNING")
        except Exception as e:
            vanguard_log(f"Error sending heartbeat for {process_name}: {e}", "ERROR")
            sentry_sdk.capture_exception(e)
        return False

    @staticmethod
    def watchdog_ping():
        """Ping continuo para procesos de larga duración (ej: IA Engine)."""
        MonitoringManager.send_heartbeat("AI_PROCESSOR_WATCHDOG")
