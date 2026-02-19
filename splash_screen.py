"""
Simple splash screen for application startup.
"""

from PySide6.QtWidgets import QSplashScreen, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor

from config import AppConfig


class SplashScreen(QSplashScreen):
    """Simple splash screen with app name and version."""

    def __init__(self, app: QApplication):
        # Create a simple pixmap for the splash screen
        pixmap = QPixmap(400, 220)
        pixmap.fill(QColor("#fafafa"))  # Light mode background
        
        # Draw splash screen content
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw app name
        font_large = QFont("Segoe UI", 36, QFont.Weight.Bold)
        painter.setFont(font_large)
        painter.setPen(QColor("#323130"))
        app_name_rect = pixmap.rect()
        app_name_rect.setTop(60)
        painter.drawText(
            app_name_rect,
            Qt.AlignmentFlag.AlignCenter,
            AppConfig.APP_NAME
        )
        
        # Draw version
        font_small = QFont("Segoe UI", 10)
        painter.setFont(font_small)
        painter.setPen(QColor("#605e5c"))
        version_text = f"Version {AppConfig.APP_VERSION}"
        version_rect = pixmap.rect()
        version_rect.setBottom(pixmap.height() - 30)
        painter.drawText(
            version_rect,
            Qt.AlignmentFlag.AlignCenter,
            version_text
        )
        
        # Draw loading text
        font_loading = QFont("Segoe UI", 9)
        painter.setFont(font_loading)
        painter.setPen(QColor("#8a8886"))
        loading_rect = pixmap.rect()
        loading_rect.setBottom(pixmap.height() - 10)
        painter.drawText(
            loading_rect,
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
            "Loading..."
        )
        
        painter.end()
        
        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlags(
            Qt.WindowType.SplashScreen | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )
        
        # Center splash screen on screen
        screen = app.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            splash_geometry = self.geometry()
            splash_geometry.moveCenter(screen_geometry.center())
            self.move(splash_geometry.topLeft())
        
        # Ensure splash is immediately visible
        self.show()
        self.raise_()
        self.activateWindow()
