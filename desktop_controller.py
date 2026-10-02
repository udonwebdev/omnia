import platform
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.DesktopController")

class DesktopController:
    """Handles OS-level window management, screen locking, and display triggers."""

    def __init__(self):
        self.os_type = platform.system()
        logger.info(f"Desktop Controller initialized for OS: {self.os_type}")

    def lock_workstation(self) -> bool:
        """Locks the local desktop host screen."""
        try:
            if self.os_type == "Windows":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
            elif self.os_type == "Darwin": # macOS
                subprocess.run(["pmset", "displaysleepnow"], check=True)
            elif self.os_type == "Linux":
                subprocess.run(["xdg-screensaver", "lock"], check=True)
            logger.info("Host screen lock initiated.")
            return True
        except Exception as e:
            logger.error(f"Failed to lock workstation: {e}")
            return False

    def open_hud(self, port: int = 8000) -> bool:
        """Launches the Omnia HUD in default browser."""
        import webbrowser
        try:
            webbrowser.open(f"http://127.0.0.1:{port}/hud")
            return True
        except Exception as e:
            logger.error(f"Failed to open HUD: {e}")
            return False

desktop_ctl = DesktopController()
