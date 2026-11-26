
"""Dark Samsung-inspired colour theme for the Kivy calculator."""

# --------------------------------------------------
# GENERAL
# --------------------------------------------------

BG = (0.0, 0.0, 0.0, 1)              # pure black background
PANEL = (0.075, 0.075, 0.075, 1)     # dark modal panels

TEXT = (1.0, 1.0, 1.0, 1)            # white text
MUTED = (0.58, 0.58, 0.58, 1)        # secondary text
ERROR = (1.0, 0.30, 0.30, 1)        # error messages

# --------------------------------------------------
# PRESS GLOW
# --------------------------------------------------

GLOW_COLOR = (0.35, 0.60, 1.0, 1)    # subtle blue glow
GLOW_ALPHA = 0.18

# --------------------------------------------------
# KEYS
# Each style: (normal colour, pressed colour, text colour)
# --------------------------------------------------

KEY_STYLES = {
    "pastel_red": (
    (0.22, 0.22, 0.22, 1),  # Normal background
    (0.32, 0.32, 0.32, 1),  # Pressed background
    (1.0, 0.55, 0.55, 1),  # Pastel red text
),
    "coral_pink": (
    (0.22, 0.22, 0.22, 1),  # Normal background
    (0.32, 0.32, 0.32, 1),  # Pressed background
    (1.0, 0.40, 0.48, 1),   # Coral pink text
),
"orange": (
    (0.22, 0.22, 0.22, 1),  # Normal background
    (0.32, 0.32, 0.32, 1),  # Pressed background
    (1.0, 0.45, 0.05, 1),   # Orange text
),
"green": (
    (0.22, 0.22, 0.22, 1),
    (0.32, 0.32, 0.32, 1),
    (0.20, 0.85, 0.45, 1),
),
"maroon": (
    (0.22, 0.22, 0.22, 1),  # Normal background
    (0.32, 0.32, 0.32, 1),  # Pressed background
    (0.65, 0.10, 0.25, 1),  # Maroon text
),
"red": (
    (0.22, 0.22, 0.22, 1),  # Normal background
    (0.32, 0.32, 0.32, 1),  # Pressed background
    (1.0, 0.12, 0.12, 1),   # Bright red text
),
    # Number button
"num": (
    (0.105, 0.105, 0.105, 1),
    (0.22, 0.22, 0.22, 1),
    TEXT,
),

    # C, delete, parentheses and percentage
    "func": (
    (0.17, 0.17, 0.17, 1),  # Normal background
    (0.27, 0.27, 0.27, 1),  # Pressed background
    (0.35, 0.60, 1.0, 1),   # Blue text
),

    # Arithmetic operators
    "op": (
    (0.17, 0.17, 0.17, 1),  # Normal background
    (0.27, 0.27, 0.27, 1),  # Pressed background
    (0.55, 0.72, 1.0, 1),   # Blue text
),

    # Equals button
    "eq": (
        (0.25, 0.48, 0.90, 1),
        (0.35, 0.58, 1.0, 1),
        TEXT,
    ),

    # Scientific buttons
    "sci": (
    (0.14, 0.17, 0.23, 1),   # Normal blue-tinted background
    (0.21, 0.29, 0.42, 1),   # Pressed background
    (0.60, 0.76, 1.0, 1),   # Light blue text
),

    # Top bar and small buttons
    "pill": (
        (0.13, 0.13, 0.13, 1),
        (0.25, 0.25, 0.25, 1),
        (0.90, 0.90, 0.90, 1),
    ),

    # Active scientific toggle
    "pill_active": (
        (0.20, 0.38, 0.70, 1),
        (0.28, 0.48, 0.85, 1),
        TEXT,
    ),
}
