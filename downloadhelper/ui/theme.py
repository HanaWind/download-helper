"""现代化暗色主题（QSS 样式表与配色常量）。"""

COLORS = {
    "bg": "#0F1420",
    "panel": "#141B29",
    "card": "#1A2133",
    "card_hover": "#1F2739",
    "border": "#242E44",
    "text": "#E6EBF5",
    "muted": "#8A97B1",
    "accent": "#4C8DFF",
    "accent2": "#8B7CFF",
    "success": "#35D399",
    "warn": "#FFB020",
    "danger": "#FF5C5C",
}

QSS = f"""
* {{
    color: {COLORS['text']};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
}}

QWidget#AppContainer {{
    background: {COLORS['bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}

QWidget#TitleBar {{
    background: #121826;
    border-top-left-radius: 13px;
    border-top-right-radius: 13px;
    border-bottom: 1px solid #1B2334;
}}

QLabel#AppTitle {{
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.4px;
}}

QLabel#AppSubtitle {{
    color: {COLORS['muted']};
    font-size: 12px;
}}

QLabel#HeroTitle {{
    font-size: 20px;
    font-weight: 600;
}}

QLabel#HeroSubtitle {{
    color: {COLORS['muted']};
    font-size: 12.5px;
}}

QLabel#Muted {{ color: {COLORS['muted']}; }}
QLabel#Hint {{ color: {COLORS['muted']}; font-size: 12px; }}
QLabel#HintError {{ color: {COLORS['danger']}; font-size: 12px; }}
QLabel#HintOk {{ color: {COLORS['success']}; font-size: 12px; }}

QLineEdit {{
    background: #121A29;
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 9px 14px;
    selection-background-color: {COLORS['accent']};
}}
QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
QLineEdit:disabled {{ color: {COLORS['muted']}; background: #101623; }}

QPushButton#PrimaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS['accent']}, stop:1 {COLORS['accent2']});
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    padding: 10px 26px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #5C99FF, stop:1 #9A8DFF);
}}
QPushButton#PrimaryButton:pressed {{ background: #3F7CE6; }}
QPushButton#PrimaryButton:disabled {{ background: #2A3550; color: #7C88A3; }}

QPushButton#GhostButton {{
    background: #182031;
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 9px 18px;
    color: {COLORS['text']};
}}
QPushButton#GhostButton:hover {{ background: #212B41; border: 1px solid #33405C; }}

QPushButton#DangerButton {{
    background: rgba(255, 92, 92, 0.12);
    border: 1px solid rgba(255, 92, 92, 0.35);
    border-radius: 10px;
    padding: 9px 18px;
    color: #FF8A8A;
}}
QPushButton#DangerButton:hover {{ background: rgba(255, 92, 92, 0.2); }}

QToolButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 5px;
}}
QToolButton:hover {{ background: #212B41; }}
QToolButton:pressed {{ background: #2A3550; }}
QToolButton#CloseButton:hover {{ background: #E0455C; }}
QToolButton#IconButton {{
    background: #182031;
    border: 1px solid {COLORS['border']};
}}

QFrame#Card {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}
QFrame#Card:hover {{ background: {COLORS['card_hover']}; }}

QProgressBar {{
    background: #131A29;
    border: none;
    border-radius: 5px;
    height: 8px;
    max-height: 8px;
}}
QProgressBar::chunk {{
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS['accent']}, stop:1 {COLORS['accent2']});
}}
QProgressBar[state="paused"]::chunk {{ background: #5A6480; }}
QProgressBar[state="error"]::chunk {{ background: {COLORS['danger']}; }}
QProgressBar[state="finished"]::chunk {{ background: {COLORS['success']}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: #26314A;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #33405C; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}

QSpinBox {{
    background: #121A29;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 6px 8px;
    min-width: 90px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; background: transparent; }}

QToolTip {{
    background: #1B2334;
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    padding: 5px 8px;
}}

QWidget#EmptyState QLabel {{ color: {COLORS['muted']}; }}
"""
