import sys
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from utils.settings import Settings
from utils.app import APP_NAME, APP_VERSION, ensure_dirs, clean_logs, configure_tesseract


if __name__ == "__main__":
    ensure_dirs()
    clean_logs()
    configure_tesseract()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    w = MainWindow(Settings())
    w.show()
    sys.exit(app.exec())
