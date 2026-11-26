import ast
import json
import math
import operator
import re
from pathlib import Path

# Must be set before any other Kivy import creates the window — this
# turns off desktop-only multitouch emulation, where right-click shows
# a red dot simulating a second finger (for testing pinch gestures
# without real touch hardware). It doesn't affect real touchscreens.
from kivy.config import Config
Config.set("input", "mouse", "mouse,multitouch_on_demand")

from kivy.uix.textinput import TextInput
from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.utils import platform

from theme import BG, ERROR, GLOW_ALPHA, GLOW_COLOR, KEY_STYLES, MUTED, PANEL, TEXT

# Haptics are optional: plyer isn't available on every platform/build,
# so fall back to doing nothing rather than crashing if it's missing.
try:
    from plyer import vibrator
except Exception:
    vibrator = None


def _vibrate_device():
    if platform != "android" or vibrator is None:
        return
    try:
        vibrator.vibrate(0.02)
    except Exception:
        pass


HISTORY_FILE = Path(__file__).with_name("history.json")
SETTINGS_FILE = Path(__file__).with_name("settings.json")
SYMBOL_FONT = str(
    Path(__file__).parent / "assets" / "fonts" / "seguisym.ttf"
)

OPERATORS = ("+", "−", "×", "÷", "^", "%")

# --------------------------------------------------
# UNIT CONVERSION
# --------------------------------------------------

UNIT_CATEGORIES = {
    "Length": {
        "mm": 0.001,
        "cm": 0.01,
        "m": 1,
        "km": 1000,
        "in": 0.0254,
        "ft": 0.3048,
        "yd": 0.9144,
        "mi": 1609.344,
    },

    "Weight": {
        "mg": 0.000001,
        "g": 0.001,
        "kg": 1,
        "t": 1000,
        "oz": 0.028349523125,
        "lb": 0.45359237,
    },

    "Area": {
        "mm²": 0.000001,
        "cm²": 0.0001,
        "m²": 1,
        "km²": 1000000,
        "hectare": 10000,
        "acre": 4046.8564224,
        "ft²": 0.09290304,
    },

    "Volume": {
        "ml": 0.001,
        "l": 1,
        "m³": 1000,
        "tsp": 0.00492892,
        "tbsp": 0.0147868,
        "cup": 0.236588,
        "pt": 0.473176,
        "qt": 0.946353,
        "gal (US)": 3.785411784,
    },

    "Time": {
        "ms": 0.001,
        "s": 1,
        "min": 60,
        "hr": 3600,
        "day": 86400,
        "wk": 604800,
        "year (365 days)": 31536000,
    },

    "Data": {
        "bit": 0.125,
        "byte": 1,
        "KB": 1000,
        "MB": 1000000,
        "GB": 1000000000,
        "TB": 1000000000000,
        "KiB": 1024,
        "MiB": 1048576,
        "GiB": 1073741824,
        "TiB": 1099511627776,
    },

    "Speed": {
        "m/s": 1,
        "km/h": 1 / 3.6,
        "mph": 0.44704,
        "knot": 0.5144444444,
    },

    "Temperature": ("°C", "°F", "K"),

    "Pressure": {
        "Pa": 1,
        "kPa": 1000,
        "MPa": 1000000,
        "bar": 100000,
        "atm": 101325,
        "psi": 6894.757293,
    },

    "Energy": {
        "J": 1,
        "kJ": 1000,
        "cal": 4.184,
        "kcal": 4184,
        "Wh": 3600,
        "kWh": 3600000,
    },

    "Power": {
        "W": 1,
        "kW": 1000,
        "MW": 1000000,
        "hp": 745.699872,
    },

    "Force": {
        "N": 1,
        "kN": 1000,
        "lbf": 4.4482216153,
    },

    "Angle": {
        "radian": 1,
        "degree": math.pi / 180,
        "gradian": math.pi / 200,
    },

    "Fuel Consumption": (
        "L/100 km",
        "km/L",
        "mpg (US)",
        "mpg (UK)",
    ),
}


def convert_temperature(value, from_unit, to_unit):
    if from_unit == "°F":
        celsius = (value - 32) * 5 / 9
    elif from_unit == "K":
        celsius = value - 273.15
    else:
        celsius = value

    if to_unit == "°F":
        return celsius * 9 / 5 + 32
    if to_unit == "K":
        return celsius + 273.15

    return celsius


def convert_fuel_consumption(value, from_unit, to_unit):
    if value <= 0:
        raise ValueError("Value must be positive")

    # Convert everything to L/100 km first.
    if from_unit == "L/100 km":
        base = value
    elif from_unit == "km/L":
        base = 100 / value
    elif from_unit == "mpg (US)":
        base = 235.214583 / value
    elif from_unit == "mpg (UK)":
        base = 282.480936 / value
    else:
        raise ValueError("Invalid fuel unit")

    # Convert from L/100 km to the target unit.
    if to_unit == "L/100 km":
        return base
    if to_unit == "km/L":
        return 100 / base
    if to_unit == "mpg (US)":
        return 235.214583 / base
    if to_unit == "mpg (UK)":
        return 282.480936 / base

    raise ValueError("Invalid fuel unit")


def convert_units(category, value, from_unit, to_unit):
    if category == "Temperature":
        return convert_temperature(value, from_unit, to_unit)

    if category == "Fuel Consumption":
        return convert_fuel_consumption(value, from_unit, to_unit)

    units = UNIT_CATEGORIES[category]
    base_value = value * units[from_unit]

    return base_value / units[to_unit]

# --------------------------------------------------
# SAFE EVALUATION
# --------------------------------------------------

def safe_evaluate(expression):
    expression = (
        expression.replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("^", "**")
        .replace("π", "pi")
    )

    functions = {
        "sin": lambda x: math.sin(math.radians(x)),
        "cos": lambda x: math.cos(math.radians(x)),
        "tan": lambda x: math.tan(math.radians(x)),
        "sqrt": math.sqrt,
        "log": math.log10,
        "ln": math.log,
        "factorial": math.factorial,
        "abs": abs,
    }

    constants = {"pi": math.pi, "e": math.e}

    binary = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
    }

    unary = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    def calculate(node):
        if isinstance(node, ast.Expression):
            return calculate(node.body)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError()

        if isinstance(node, ast.Name):
            if node.id in constants:
                return constants[node.id]
            raise ValueError()

        if isinstance(node, ast.BinOp):
            operation = binary.get(type(node.op))
            if operation is None:
                raise ValueError()
            return operation(calculate(node.left), calculate(node.right))

        if isinstance(node, ast.UnaryOp):
            operation = unary.get(type(node.op))
            if operation is None:
                raise ValueError()
            return operation(calculate(node.operand))

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError()
            function = functions.get(node.func.id)
            if function is None or len(node.args) != 1:
                raise ValueError()
            return function(calculate(node.args[0]))

        raise ValueError()

    open_brackets = expression.count("(")
    close_brackets = expression.count(")")

    if open_brackets != close_brackets:
        expression += ")" * (open_brackets - close_brackets) 

       
    result = calculate(ast.parse(expression, mode="eval"))

    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError()

    return result


def format_result(result):
    if isinstance(result, float):
        result = round(result, 10)
        if result.is_integer():
            result = int(result)
    return str(result)


# --------------------------------------------------
# WIDGETS
# --------------------------------------------------

class KeyButton(Button):
    """Rounded key with a soft glow that fades in on press.

    Pass ``icon`` ("history", "ruler" or "scan") to draw a small vector
    glyph instead of (or alongside) the text label. Icons are drawn with
    Line/RoundedRectangle so they look identical on every device, with
    no dependency on a font having the right glyph.
    """

    GLOW_PAD = dp(10)
    ICON_LINE_WIDTH = dp(1.6)

    def __init__(self, text, kind="num", font_size="24sp", icon=None, **kwargs):
        super().__init__(text=text, **kwargs)

        normal, pressed, foreground = KEY_STYLES[kind]
        self._normal = normal
        self._pressed = pressed
        self._icon = icon
        self._icon_graphics = {}

        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = foreground
        self.font_size = font_size
        self.bold = kind in ("op", "eq", "func")

        with self.canvas.before:
            # Soft halo, larger than the key and invisible until pressed.
            self._glow_color = Color(*GLOW_COLOR[:3], 0)
            self._glow_rect = RoundedRectangle(pos=self.pos, size=self.size)

            # The key itself.
            self._color = Color(*normal)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size)

            # An optional vector icon drawn on top of the key fill.
            if icon:
                self._icon_color = Color(*foreground)
                self._icon_graphics = self._build_icon_graphics(icon)

        self.bind(pos=self._redraw, size=self._redraw, state=self._on_state)
        self._redraw()

    def _build_icon_graphics(self, icon):
        width = self.ICON_LINE_WIDTH

        if icon == "history":
            return {
                "arc": Line(width=width, cap="round", joint="round"),
                "arrow": Line(width=width, cap="round", joint="round"),
            }

        if icon == "ruler":
            return {
                "body": Line(width=width, cap="round"),
                "ticks": [Line(width=width, cap="round") for _ in range(4)],
            }

        if icon == "scan":
            return {
                "frame": Line(width=width, joint="round"),
                "spark_h": Line(width=width, cap="round"),
                "spark_v": Line(width=width, cap="round"),
            }

        if icon == "swap":
            return {
                "top": Line(width=width, cap="round", joint="round"),
                "bottom": Line(width=width, cap="round", joint="round"),
            }

        if icon == "back":
            return {"chevron": Line(width=width, cap="round", joint="round")}

        if icon in ("arrow_up", "arrow_down"):
            return {
                "stem": Line(width=width, cap="round"),
                "head": Line(width=width, cap="round", joint="round"),
            }

        if icon == "haptic":
            return {
                "phone": Line(width=width, joint="round"),
                "wave_left": Line(width=width, cap="round"),
                "wave_right": Line(width=width, cap="round"),
            }

        return {}

    def _redraw(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._rect.radius = [min(self.width, self.height) * 0.38]

        self._glow_rect.pos = (
            self.x - self.GLOW_PAD,
            self.y - self.GLOW_PAD,
        )
        self._glow_rect.size = (
            self.width + self.GLOW_PAD * 2,
            self.height + self.GLOW_PAD * 2,
        )
        self._glow_rect.radius = [
            min(self._glow_rect.size) * 0.38
        ]

        if self._icon:
            self._update_icon()

    def _update_icon(self):
        cx, cy = self.center
        size = min(self.width, self.height)

        if self._icon == "history":
            self._update_history_icon(cx, cy, size)
        elif self._icon == "ruler":
            self._update_ruler_icon(cx, cy, size)
        elif self._icon == "scan":
            self._update_scan_icon(cx, cy, size)
        elif self._icon == "swap":
            self._update_swap_icon(cx, cy, size)
        elif self._icon == "back":
            self._update_back_icon(cx, cy, size)
        elif self._icon in ("arrow_up", "arrow_down"):
            self._update_vertical_arrow_icon(cx, cy, size, self._icon)
        elif self._icon == "haptic":
            self._update_haptic_icon(cx, cy, size)

    def _update_history_icon(self, cx, cy, size):
        radius = size * 0.28
        start_deg, end_deg = 55, 330

        self._icon_graphics["arc"].circle = (
            cx, cy, radius, start_deg, end_deg, 48
        )

        start_rad = math.radians(start_deg)
        tip_x = cx + radius * math.cos(start_rad)
        tip_y = cy + radius * math.sin(start_rad)

        wing = size * 0.11
        tangent = start_rad + math.radians(90)

        wing1_x = tip_x - wing * math.cos(tangent - 0.6)
        wing1_y = tip_y - wing * math.sin(tangent - 0.6)
        wing2_x = tip_x - wing * math.cos(tangent + 0.6)
        wing2_y = tip_y - wing * math.sin(tangent + 0.6)

        self._icon_graphics["arrow"].points = [
            wing1_x, wing1_y, tip_x, tip_y, wing2_x, wing2_y,
        ]

    def _update_ruler_icon(self, cx, cy, size):
        half = size * 0.30
        x1, y1 = cx - half, cy - half
        x2, y2 = cx + half, cy + half

        self._icon_graphics["body"].points = [x1, y1, x2, y2]

        tick_len = size * 0.10
        positions = (0.18, 0.36, 0.54, 0.72)

        for tick, t in zip(self._icon_graphics["ticks"], positions):
            bx = x1 + (x2 - x1) * t
            by = y1 + (y2 - y1) * t
            tick.points = [
                bx - tick_len * 0.5, by + tick_len * 0.5,
                bx + tick_len * 0.5, by - tick_len * 0.5,
            ]

    def _update_scan_icon(self, cx, cy, size):
        side = size * 0.52
        x = cx - side / 2
        y = cy - side / 2
        radius = side * 0.22

        self._icon_graphics["frame"].rounded_rectangle = (
            x, y, side, side, radius
        )

        spark_x = x + side * 0.82
        spark_y = y + side * 0.18
        spark = size * 0.09

        self._icon_graphics["spark_h"].points = [
            spark_x - spark, spark_y, spark_x + spark, spark_y,
        ]
        self._icon_graphics["spark_v"].points = [
            spark_x, spark_y - spark, spark_x, spark_y + spark,
        ]

    def _update_swap_icon(self, cx, cy, size):
        half = size * 0.22
        arrow = size * 0.09

        top_y = cy + half * 0.55
        self._icon_graphics["top"].points = [
            cx - half, top_y,
            cx + half, top_y,
            cx + half - arrow, top_y + arrow,
        ]

        bottom_y = cy - half * 0.55
        self._icon_graphics["bottom"].points = [
            cx + half, bottom_y,
            cx - half, bottom_y,
            cx - half + arrow, bottom_y - arrow,
        ]

    def _update_back_icon(self, cx, cy, size):
        # A simple "<" chevron for the converter's back button.
        half = size * 0.20
        self._icon_graphics["chevron"].points = [
            cx + half, cy + half,
            cx - half, cy,
            cx + half, cy - half,
        ]

    def _update_vertical_arrow_icon(self, cx, cy, size, icon):
        # A stem with an arrowhead, pointing up or down — used for the
        # converter keypad's increment/decrement keys.
        half = size * 0.24
        wing = size * 0.10

        if icon == "arrow_up":
            tip_y, base_y = cy + half, cy - half
        else:
            tip_y, base_y = cy - half, cy + half

        self._icon_graphics["stem"].points = [cx, base_y, cx, tip_y]

        wing_y = tip_y - wing if icon == "arrow_up" else tip_y + wing
        self._icon_graphics["head"].points = [
            cx - wing, wing_y, cx, tip_y, cx + wing, wing_y,
        ]

    def _update_haptic_icon(self, cx, cy, size):
        # A small phone outline with short "vibration" ticks on each
        # side, like a standard vibrate-mode icon.
        phone_w = size * 0.26
        phone_h = size * 0.46
        x = cx - phone_w / 2
        y = cy - phone_h / 2
        radius = phone_w * 0.3

        self._icon_graphics["phone"].rounded_rectangle = (
            x, y, phone_w, phone_h, radius
        )

        wave_x_offset = phone_w * 0.75
        wave_len = size * 0.14

        self._icon_graphics["wave_left"].points = [
            cx - wave_x_offset, cy - wave_len / 2,
            cx - wave_x_offset, cy + wave_len / 2,
        ]
        self._icon_graphics["wave_right"].points = [
            cx + wave_x_offset, cy - wave_len / 2,
            cx + wave_x_offset, cy + wave_len / 2,
        ]

    def _on_state(self, *args):
        pressed = self.state == "down"
        target_color = self._pressed if pressed else self._normal
        target_glow = GLOW_ALPHA if pressed else 0

        if pressed:
            app = App.get_running_app()
            if app:
                app.trigger_haptic()

        Animation.cancel_all(self._color)
        Animation.cancel_all(self._glow_color)
        Animation(
            r=target_color[0], g=target_color[1], b=target_color[2],
            d=0.05 if pressed else 0.18,
        ).start(self._color)
        Animation(
            a=target_glow,
            d=0.05 if pressed else 0.22,
        ).start(self._glow_color)

    def set_style(self, kind):
        normal, pressed, foreground = KEY_STYLES[kind]
        self._normal = normal
        self._pressed = pressed
        self.color = foreground
        if self._icon and hasattr(self, "_icon_color"):
            self._icon_color.rgba = foreground
        if self.state != "down":
            self._color.rgb = normal[:3]


def add_rounded_bg(widget, color, radius):
    with widget.canvas.before:
        Color(*color)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])

    widget.bind(
        pos=lambda w, v: setattr(rect, "pos", v),
        size=lambda w, v: setattr(rect, "size", v),
    )


def right_label(**kwargs):
    label = Label(halign="right", **kwargs)
    label.bind(size=lambda obj, value: setattr(obj, "text_size", value))
    return label


# --------------------------------------------------
# APP
# --------------------------------------------------

class CalculatorApp(App):
    SCI_ROW_HEIGHT = dp(46)
    SCI_SPACING = dp(10)

    def build(self):
        Window.clearcolor = BG

        if platform not in ("android", "ios"):
            Window.size = (400, 780)

        self.expression = ""
        self.cursor_index = 0
        self._updating_expression = False
        self.history = []
        self.scientific_visible = False 
        self.just_calculated = False
        self._backspace_long_press = False
        self._backspace_clock = None
        self._copy_clock = None

        self.history_file = Path(self.user_data_dir) / "history.json"
        self.settings_file = Path(self.user_data_dir) / "settings.json"

        self.load_history()
        self.load_settings()

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(16), dp(14), dp(16), dp(16)],
            spacing=dp(10),
        )

        root.add_widget(self.build_top_bar())
        root.add_widget(self.build_display())
        root.add_widget(self.build_scientific())
        root.add_widget(self.build_keypad())

        self.build_history_view()
        self.refresh_history()
        self.build_unit_converter_view()
        self.apply_saved_settings()
        self.update_display()

        return root

    def on_stop(self):
        # Belt-and-braces: make sure the latest state is saved even if
        # something skipped an explicit save_settings() call earlier.
        self.save_settings()

    # ---------------- Top bar ----------------

    def build_top_bar(self):
        bar = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))

        self.history_button = KeyButton("", "pill", icon="history",
                                        size_hint_x=None, width=dp(44))
        self.history_button.bind(on_release=self.open_history)

        self.converter_button = KeyButton("", "pill", icon="ruler",
                                          size_hint_x=None, width=dp(44))
        self.converter_button.bind(on_release=self.open_converter)

        self.scientific_button = KeyButton("", "pill", icon="scan",
                                           size_hint_x=None, width=dp(44))
        self.scientific_button.bind(on_release=self.toggle_scientific)

        self.haptics_button = KeyButton("", "pill", icon="haptic",
                                        size_hint_x=None, width=dp(44))
        self.haptics_button.bind(on_release=self.toggle_haptics)
        # self.settings is already loaded by the time this runs (see
        # build()'s call order), so this reflects the saved state
        # immediately rather than defaulting to "off" for a frame.
        if self.settings.get("haptics_enabled", True):
            self.haptics_button.set_style("pill_active")

        bar.add_widget(self.history_button)
        bar.add_widget(self.converter_button)
        bar.add_widget(Widget())
        bar.add_widget(self.haptics_button)
        bar.add_widget(self.scientific_button)
        return bar

    # ---------------- Display ----------------
    def _on_expression_cursor(self, instance, cursor):
         if not self._updating_expression:
            self.cursor_index = cursor[0]

    def _restore_expression_cursor(self, dt):
        index = max(
            0, min(self.cursor_index, len(self.expression))
        )
        self.expression_label.cursor = (index, 0)        

    def build_display(self):
        display = BoxLayout(orientation="vertical", size_hint_y=0.30,
                            padding=[dp(6), 0, dp(6), 0], spacing=dp(2))

        self.expression_label = TextInput(
            text="",
            readonly=False,
            multiline=False,
            halign="right",
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=TEXT,
            cursor_color=(1, 1, 1, 1),
            cursor_width=dp(2),
            cursor_blink=True,
            keyboard_mode="managed",
            font_size="52sp",
            padding=[dp(4), dp(10), dp(4), dp(10)],
            size_hint_y=0.62,
        )
        self.expression_label.bind(
            cursor=self._on_expression_cursor
        )
        self.preview_label = right_label(
            text="", color=MUTED, font_size="26sp", valign="middle",
            size_hint_y=0.24,
        )

        # Long-press the result to copy it to the clipboard.
       
        display.add_widget(self.expression_label)
        display.add_widget(self.preview_label)
        return display

    # ---------------- Scientific rows ----------------

    def build_scientific(self):
        self.scientific_grid = GridLayout(
            cols=4, spacing=self.SCI_SPACING,
            size_hint_y=None, height=0,
        )
        self.scientific_height = (
            self.SCI_ROW_HEIGHT * 4 + self.SCI_SPACING * 3
        )

        keys = [
            ("sin", "sin("), ("cos", "cos("), ("tan", "tan("), ("√", "sqrt("),
            ("x²", "^2"), ("xʸ", "^"), ("log", "log("), ("ln", "ln("),
            ("1/x", "1/("), ("n!", "factorial("), ("e", "e"), ("π", "π"),
            ("+/−", "+/−"),
        ]

        for label, value in keys:
            button = KeyButton(label, "sci", font_size="17sp")
            if label == "+/−":
                button.bind(on_release=lambda *a: self.negate())
            else:
                button.bind(on_release=lambda inst, v=value: self.add_input(v))

            self.scientific_grid.add_widget(button)

        self.scientific_grid.opacity = 0
        self.scientific_grid.disabled = True
        return self.scientific_grid

    # ---------------- Main keypad ----------------

    def build_keypad(self):
        keypad = GridLayout(cols=4, spacing=dp(10), size_hint_y=0.62)

        keys = [
            ("C", "func"), ("⌫", "func"), ("( )", "func"), ("%", "func"),
            ("7", "num"), ("8", "num"), ("9", "num"), ("÷", "op"),
            ("4", "num"), ("5", "num"), ("6", "num"), ("×", "op"),
            ("1", "num"), ("2", "num"), ("3", "num"), ("−", "op"),
            ("0", "num"), (".", "num"), ("+", "op"),("=", "eq"),
        ]

        for label, kind in keys:
            if label in ("C", "⌫"):
              kind = "pastel_red"

            button = KeyButton(label, kind)

            if label == "C":
                button.bind(on_release=lambda *a: self.clear())
            elif label == "⌫":
                button.font_name = SYMBOL_FONT
                # A quick tap backspaces one character; holding it
                # down clears the whole expression instead.
                button.bind(
                    on_press=self.start_backspace_hold,
                    on_release=self.end_backspace_hold,
                )
            elif label == "( )":
                button.bind(on_release=lambda *a: self.add_parenthesis())
            elif label == "+/−":
                button.bind(on_release=lambda *a: self.negate())
            elif label == "=":
                button.bind(on_release=lambda *a: self.calculate())
            else:
                button.bind(on_release=lambda instance, v=label: self.add_input(v))

            keypad.add_widget(button)

        return keypad

        # ---------------- Panel animations ----------------

    def animate_panel_open(self, panel, direction):
        if panel.parent:
            return
        panel.open()

        content = panel.children[0]
        target_x = content.x

        content.x = (
            -content.width if direction == "left"
            else Window.width
        )

        Animation.cancel_all(content)
        Animation(
            x=target_x,
            d=0.28,
            t="out_cubic",
        ).start(content)

    def animate_panel_close(self, panel, direction):
        if not panel.parent:
            return

        content = panel.children[0]
        target_x = (
            -content.width if direction == "left"
            else Window.width
        )

        Animation.cancel_all(content)

        animation = Animation(
            x=target_x,
            d=0.24,
            t="in_cubic",
        )
        animation.bind(on_complete=lambda *a: panel.dismiss())
        animation.start(content)

        Clock.schedule_once(lambda dt: panel.dismiss(), 0.32)

    def collapse_scientific(self):
        if not self.scientific_visible:
            return

        self.scientific_visible = False
        Animation.cancel_all(self.scientific_grid)
        self.scientific_grid.disabled = True

        Animation(
            height=0,
            opacity=0,
            d=0.22,
            t="out_cubic",
        ).start(self.scientific_grid)

        self.scientific_button.set_style("pill")

    def close_history(self, *args):
        self.animate_panel_close(self.history_view, "left")

    def close_converter(self, *args):
        self.animate_panel_close(self.converter_view, "right")

    # ---------------- History overlay ----------------

    def build_history_view(self):
        self.history_view = ModalView(
            size_hint=(None, None),
            size=(Window.width * 0.88, Window.height * 0.72),
            auto_dismiss=False,
            background="",
            background_color=(0, 0, 0, 0),
            overlay_color=(0, 0, 0, 0.55),
        )

        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        add_rounded_bg(content, PANEL, dp(22))

        header = BoxLayout(size_hint_y=None, height=dp(40))
        title = Label(text="History", color=TEXT, font_size="18sp",
                      bold=True, halign="left")
        title.bind(size=lambda obj, value: setattr(obj, "text_size", value))

        clear_button = KeyButton(
            "Clear", "pill",
            font_size="14sp", 
            size_hint_x=None,
            width=dp(78),
        )
        clear_button.bind(on_release=self.clear_history)

        close_button = KeyButton(
            "×", "pill",
            font_size="22sp",
            size_hint_x=None,
            width=dp(40),
        )
        close_button.bind(on_release=self.close_history)

        header.add_widget(title)
        header.add_widget(clear_button)
        header.add_widget(close_button)

        self.history_list = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.history_list.bind(minimum_height=self.history_list.setter("height"))

        scroll = ScrollView()
        scroll.add_widget(self.history_list)

        content.add_widget(header)
        content.add_widget(scroll)
        self.history_view.add_widget(content)

    def open_history(self, *args):
        if self.converter_view.parent:
            self.converter_view.dismiss()

        self.collapse_scientific()
        self.refresh_history()

        self.animate_panel_open(self.history_view, "left")

    def use_history_entry(self, entry):
        self.expression = entry["result"]
        self.just_calculated = True
        self.update_display()
        self.close_history()

    def refresh_history(self):
        self.history_list.clear_widgets()

        if not self.history:
            empty = Label(text="No history yet", color=MUTED,
                          size_hint_y=None, height=dp(40))
            self.history_list.add_widget(empty)
            return

        for entry in self.history[:50]:
            item = Button(
                text=f"[color=94a0ad]{entry['expression']}[/color]\n"
                     f"[size=22sp]{entry['result']}[/size]",
                markup=True,
                halign="right",
                color=(0.35, 0.60, 1.0, 1),
                size_hint_y=None,
                height=dp(68),
                background_normal="",
                background_down="",
                background_color=(0, 0, 0, 0),
            )
            item.bind(size=lambda obj, value: setattr(obj, "text_size", (value[0] - dp(12), value[1])))
            item.bind(on_release=lambda inst, e=entry: self.use_history_entry(e))
            self.history_list.add_widget(item)

    # ---------------- Unit converter overlay ----------------

    def build_unit_converter_view(self):
        self.converter_view = ModalView(
            size_hint=(1, 1),
            auto_dismiss=False,
            background="",
            background_color=(0, 0, 0, 0),
            overlay_color=(0, 0, 0, 0),
        )

        content = BoxLayout(
            orientation="vertical",
            padding=[dp(16), dp(14), dp(16), dp(16)],
            spacing=dp(14),
        )
        add_rounded_bg(content, (0, 0, 0, 1), 0)

        content.add_widget(self._build_converter_header())
        content.add_widget(self._build_category_chip_row())
        content.add_widget(self._build_unit_row(is_from=True))
        content.add_widget(self._build_divider())
        content.add_widget(self._build_unit_row(is_from=False))
        content.add_widget(Widget())
        content.add_widget(self._build_converter_keypad())

        self.converter_view.add_widget(content)

        self.converter_value_text = "1"
        self.select_category(next(iter(UNIT_CATEGORIES)))

    def _build_converter_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))

        back_button = KeyButton("", "pill", icon="back",
                                size_hint_x=None, width=dp(36))
        back_button.bind(on_release=self.close_converter)

        title = Label(text="Unit converter", color=TEXT, font_size="18sp",
                      bold=True, halign="left")
        title.bind(size=lambda obj, value: setattr(obj, "text_size", value))

        header.add_widget(back_button)
        header.add_widget(title)
        return header

    def _build_category_chip_row(self):
        chip_scroll = ScrollView(size_hint_y=None, height=dp(42),
                                 do_scroll_y=False, bar_width=0)

        chip_row = BoxLayout(size_hint_x=None, spacing=dp(8))
        chip_row.bind(minimum_width=chip_row.setter("width"))

        self._category_chips = {}
        for name in UNIT_CATEGORIES:
            chip = KeyButton(name, "pill", font_size="14sp")
            chip.size_hint = (None, None)
            chip.height = dp(34)
            # Rough width estimate from the label length — avoids
            # relying on texture_size, which may not have been
            # computed yet at this point in widget construction.
            chip.width = dp(20) + len(name) * dp(8)
            chip.bind(on_release=lambda inst, n=name: self.select_category(n))
            self._category_chips[name] = chip
            chip_row.add_widget(chip)

        chip_scroll.add_widget(chip_row)
        return chip_scroll

    def _build_divider(self):
        line = Widget(size_hint_y=None, height=dp(1))
        with line.canvas:
            Color(1, 1, 1, 0.08)
            rect = Rectangle(pos=line.pos, size=line.size)
        line.bind(
            pos=lambda w, v: setattr(rect, "pos", v),
            size=lambda w, v: setattr(rect, "size", v),
        )
        return line

    def _build_unit_row(self, is_from):
        row = BoxLayout(orientation="vertical", size_hint_y=None,
                        height=dp(76), spacing=dp(4))

        spinner = Spinner(
            text="", values=[],
            size_hint=(None, None), size=(dp(170), dp(28)),
            background_normal="", background_down="",
            background_color=(0, 0, 0, 0),
            color=MUTED, font_size="15sp",
        )
        spinner.bind(text=lambda *a: self.on_unit_spinner_change())

        value_label = right_label(
            text="", color=TEXT,
            font_size="34sp" if is_from else "26sp",
        )

        value_box = BoxLayout(size_hint_y=None, height=dp(48),
                              padding=[dp(10), 0, dp(10), 0])
        if is_from:
            # Only the editable field gets the highlighted background.
            add_rounded_bg(value_box, (0.07, 0.19, 0.17, 1), dp(8))
        value_box.add_widget(value_label)

        row.add_widget(spinner)
        row.add_widget(value_box)

        if is_from:
            self.from_unit_spinner = spinner
            self.from_value_label = value_label
        else:
            self.to_unit_spinner = spinner
            self.to_value_label = value_label

        return row

    def _build_converter_keypad(self):
        keypad = GridLayout(cols=4, spacing=dp(10),
                            size_hint_y=None, height=dp(260))

        keys = [
            ("7", "num", "7"), ("8", "num", "8"),
            ("9", "num", "9"), ("⌫", "func", "⌫"),
            ("4", "num", "4"), ("5", "num", "5"),
            ("6", "num", "6"), ("C", "func", "C"),
            ("1", "num", "1"), ("2", "num", "2"),
            ("3", "num", "3"), ("arrow_up", "func", "↑"),
            ("+/-", "num", "+/-"), ("0", "num", "0"),
            (".", "num", "."), ("arrow_down", "func", "↓"),
        ]

        for label, kind, value in keys:
            if label in ("C", "⌫"):
                kind = "pastel_red"

            if label in ("arrow_up", "arrow_down"):
                button = KeyButton("", kind, icon=label)
            else:
                button = KeyButton(label, kind)

            if label == "⌫":
                # Match the main keypad: the glyph needs this font or
                # it renders as an empty box on most devices.
                button.font_name = SYMBOL_FONT

            button.bind(on_release=lambda inst, v=value: self.converter_keypad(v))
            keypad.add_widget(button)

        return keypad

    def open_converter(self, *args):
        if self.history_view.parent:
            self.history_view.dismiss()

        self.collapse_scientific()

        self.animate_panel_open(self.converter_view, "right")

    def select_category(self, name):
        self.converter_category = name
        names = list(UNIT_CATEGORIES[name])

        self.from_unit_spinner.values = names
        self.to_unit_spinner.values = names
        self.from_unit_spinner.text = names[0]
        self.to_unit_spinner.text = names[1] if len(names) > 1 else names[0]

        for chip_name, chip in self._category_chips.items():
            chip.set_style("pill_active" if chip_name == name else "pill")

        self.on_unit_spinner_change()

    def on_unit_spinner_change(self):
        self.update_converter_display()
        self.settings["converter_category"] = self.converter_category
        self.settings["converter_from_unit"] = self.from_unit_spinner.text
        self.settings["converter_to_unit"] = self.to_unit_spinner.text
        self.save_settings()

    def converter_keypad(self, key):
        text = self.converter_value_text

        if key == "C":
            text = "0"
        elif key == "⌫":
            text = text[:-1] or "0"
        elif key == "+/-":
            text = text[1:] if text.startswith("-") else (
                "-" + text if text != "0" else text
            )
        elif key == ".":
            if "." not in text:
                text += "."
        elif key in ("↑", "↓"):
            try:
                step = 1 if key == "↑" else -1
                text = format_result(float(text or 0) + step)
            except Exception:
                pass
        else:
            text = key if text == "0" else text + key

        self.converter_value_text = text
        self.update_converter_display()

    def update_converter_display(self):
        self.from_value_label.text = (
            f"{self.converter_value_text} {self.from_unit_spinner.text}"
        )

        try:
            value = float(self.converter_value_text or 0)
            result = convert_units(
                self.converter_category,
                value,
                self.from_unit_spinner.text,
                self.to_unit_spinner.text,
            )
            self.to_value_label.text = (
                f"{format_result(result)} {self.to_unit_spinner.text}"
            )
            self.to_value_label.color = TEXT
        except Exception:
            self.to_value_label.text = "Invalid input"
            self.to_value_label.color = ERROR

    # --------------------------------------------------
    # DISPLAY
    # --------------------------------------------------

    def update_display(self):
        text = self.expression

        # Keep the cursor within the expression.
        self.cursor_index = max(
            0, min(self.cursor_index, len(text))
        )

        # Update the expression without losing the cursor position.
        self._updating_expression = True

        try:
            self.expression_label.text = text
        finally:
            self._updating_expression = False

        # Restore the cursor position after updating the text.
        Clock.schedule_once(self._restore_expression_cursor, 0)

        self.expression_label.color = TEXT

        # Automatically adjust font size based on expression length.
        length = len(text)

        if length > 22:
            size = "24sp"
        elif length > 16:
            size = "30sp"
        elif length > 11:
            size = "38sp"
        elif length > 7:
            size = "46sp"
        else:
            size = "52sp"

        self.expression_label.font_size = size

        # Update the live calculation preview.
        self.preview_label.color = MUTED
        self.preview_label.text = self.live_preview()
        def _restore_expression_cursor(self, index):
            index = min(index, len(self.expression))
            self.expression_label.cursor = (index, 0)

    def live_preview(self):
        """Show the running answer in grey while the user is typing."""
        if not self.expression or self.just_calculated:
            return ""
        if self.expression[-1] in OPERATORS + ("(",):
            return ""
        if not re.search(r"[+−×÷^%(]|sin|cos|tan|sqrt|log|ln|factorial", self.expression):
            return ""

        try:
            return format_result(safe_evaluate(self.expression))
        except Exception:
            return ""

    # --------------------------------------------------
    # CLIPBOARD
    # --------------------------------------------------

    def _on_result_touch_down(self, instance, touch):
        if not instance.collide_point(*touch.pos):
            return False

        self._copy_clock = Clock.schedule_once(
            lambda dt: self.copy_result_to_clipboard(), 0.55
        )
        return True

    def _on_result_touch_up(self, instance, touch):
        if self._copy_clock:
            Clock.unschedule(self._copy_clock)
            self._copy_clock = None
        return False

    def copy_result_to_clipboard(self):
        try:
            Clipboard.copy(self.expression or "0")
        except Exception:
            return

        self.flash_copied_feedback()

    def flash_copied_feedback(self):
        previous_text = self.preview_label.text
        previous_color = self.preview_label.color

        self.preview_label.text = "Copied!"
        self.preview_label.color = GLOW_COLOR

        Clock.schedule_once(
            lambda dt: self._restore_preview_label(previous_text, previous_color),
            0.9,
        )

    def _restore_preview_label(self, text, color):
        self.preview_label.text = text
        self.preview_label.color = color

    # --------------------------------------------------
    # INPUT
    # --------------------------------------------------

    def add_input(self, value):
        self.insert_at_cursor(value)


    def insert_at_cursor(self, value):
        if self.just_calculated and value not in OPERATORS:
            self.expression = ""
            self.cursor_index = 0

        self.just_calculated = False

        if value == "%":
            value = "/100"

        index = self.cursor_index

        self.expression = (
            self.expression[:index]
            + value
            + self.expression[index:]
        )

        self.cursor_index = index + len(value)
        self.update_display()   

    def add_parenthesis(self):
        if self.just_calculated:
           self.expression = ""
           self.just_calculated = False

        opened = self.expression.count("(")
        closed = self.expression.count(")")
        last = self.expression[-1:] if self.expression else ""

        if opened > closed and (last.isdigit() or last in (")", "e", "π")):
            self.expression += ")"
        else:
            self.expression += "("

        self.update_display()

    def negate(self):
        wrapped = re.search(r"\(−(\d+\.?\d*)\)$", self.expression)
        plain = re.search(r"(\d+\.?\d*)$", self.expression)

        if wrapped:
            self.expression = (
                self.expression[:wrapped.start()] + wrapped.group(1)
            )
        elif plain:
            self.expression = (
                self.expression[:plain.start()] + f"(−{plain.group(1)})"
            )

        self.just_calculated = False
        self.update_display()

    def clear(self):
        self.expression = ""
        self.just_calculated = False
        self.update_display()

    def backspace(self):
        self.expression = self.expression[:-1]
        self.just_calculated = False
        self.update_display()

    def start_backspace_hold(self, *args):
        self._backspace_long_press = False
        self._backspace_clock = Clock.schedule_once(
            self._trigger_backspace_long_press, 0.55
        )

    def _trigger_backspace_long_press(self, dt):
        self._backspace_long_press = True
        self.clear()

    def end_backspace_hold(self, *args):
        if self._backspace_clock:
            Clock.unschedule(self._backspace_clock)
            self._backspace_clock = None

        # Only backspace on release if the hold never reached the
        # long-press threshold — otherwise this would both clear
        # everything AND then backspace once on release.
        if not self._backspace_long_press:
            self.backspace()

        self._backspace_long_press = False

    def calculate(self, *args):
        if not self.expression:
            return

        original = self.expression

        try:
            result = format_result(safe_evaluate(original))
        except Exception:
            self.preview_label.text = "Invalid format"
            self.preview_label.color = ERROR
            return

        self.history.insert(0, {"expression": original, "result": result})
        self.history = self.history[:100]
        self.save_history()
        self.refresh_history()

        self.expression = result
        self.just_calculated = True
        self.update_display()

    # --------------------------------------------------
    # TOGGLES
    # --------------------------------------------------

    def toggle_scientific(self, *args):
        if self.history_view.parent:
            self.history_view.dismiss()

        if self.converter_view.parent:
            self.converter_view.dismiss()

        self.scientific_visible = not self.scientific_visible

        Animation.cancel_all(self.scientific_grid)

        if self.scientific_visible:
            self.scientific_grid.disabled = False

            Animation(
                height=self.scientific_height,
                opacity=1,
                d=0.28,
                t="out_cubic",
            ).start(self.scientific_grid)


        else:
            self.scientific_grid.disabled = True

            Animation(
                height=0,
                opacity=0,
                d=0.25,
                t="out_cubic",
            ).start(self.scientific_grid)


        self.settings["scientific_visible"] = self.scientific_visible
        self.save_settings()

    # --------------------------------------------------
    # HISTORY STORAGE
    # --------------------------------------------------

    def load_history(self):
        try:
            if self.history_file.exists():
                self.history = json.loads(self.history_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.history = []

    def save_history(self):
        try:
            self.history_file.write_text(
                json.dumps(self.history, indent=4), encoding="utf-8"
            )
        except OSError:
            pass

    def clear_history(self, *args):
        self.history = []
        self.save_history()
        self.refresh_history()

    # --------------------------------------------------
    # SETTINGS STORAGE
    # Remembers the last-used converter category/units and whether
    # scientific mode was open, across app restarts.
    # --------------------------------------------------

    def load_settings(self):
        try:
            if self.settings_file.exists():
                self.settings = json.loads(self.settings_file.read_text(encoding="utf-8"))
            else:
                self.settings = {}
        except (OSError, json.JSONDecodeError):
            self.settings = {}

    def save_settings(self):
        try:
            self.settings_file.write_text(
                json.dumps(self.settings, indent=4), encoding="utf-8"
            )
        except OSError:
            pass

    def apply_saved_settings(self):
        category = self.settings.get("converter_category")

        if category in UNIT_CATEGORIES:
            self.select_category(category)

            units = list(UNIT_CATEGORIES[category])
            from_unit = self.settings.get("converter_from_unit")
            to_unit = self.settings.get("converter_to_unit")

            if from_unit in units:
                self.from_unit_spinner.text = from_unit
            if to_unit in units:
                self.to_unit_spinner.text = to_unit

        if self.settings.get("scientific_visible"):
            # Restore instantly, no slide-open animation, since this
            # is the app's starting state rather than a user action.
            self.scientific_visible = True
            self.scientific_grid.height = self.scientific_height
            self.scientific_grid.opacity = 1
            self.scientific_grid.disabled = False

    # --------------------------------------------------
    # HAPTICS
    # --------------------------------------------------

    def trigger_haptic(self):
        if self.settings.get("haptics_enabled", True):
            _vibrate_device()

    def toggle_haptics(self, *args):
        enabled = not self.settings.get("haptics_enabled", True)
        self.settings["haptics_enabled"] = enabled
        self.save_settings()

        self.haptics_button.set_style("pill_active" if enabled else "pill")

        if enabled:
            # Buzz once immediately so turning it on is itself the
            # confirmation that it's working.
            _vibrate_device()


if __name__ == "__main__":
    CalculatorApp().run()