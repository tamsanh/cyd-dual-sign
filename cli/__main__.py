# main.py
import asyncio
import json
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Callable, Literal, Optional

import attrs
import cattrs
from attrs import asdict, define, field
from serial import Serial
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.events import Paste
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, Static
from yaml import safe_dump, safe_load

from .send import (
    AlignmentEnum,
    BackgroundEnum,
    ScreenEnum,
    StyleConfig,
    create_style_str,
)

LEFT_PORT = "/dev/cu.usbserial-1240"
RIGHT_PORT = "/dev/cu.usbserial-1230"


# ----------------------------
# Message bubble for the chat
# ----------------------------
class Message(Static):
    def __init__(self, role: str, content: str, **kwargs):
        self.role = role
        super().__init__(content, **kwargs)
        self.add_class(f"message-{role}")


# ----------------------------
# Helper types & parsing
# ----------------------------
@attrs.define
class TimeMessage:
    target_time: str
    message: str


def _parse_time_message(time_message: str) -> TimeMessage | None:
    time_match = re.match(r"(.*?)(\d\d:\d\d)$", time_message.strip())
    if time_match:
        # group(1) may have trailing whitespace; trim it
        return TimeMessage(time_match.group(2), time_match.group(1).rstrip())
    return None


# ----------------------------
# On-screen preview widget
# ----------------------------
class ScreenPreview(Static):
    """A lightweight, text-based preview of a physical LCD screen."""

    label: reactive[str] = reactive("LEFT")
    last_values: reactive[str] = reactive("")
    last_style: reactive[StyleConfig | None] = reactive(None)

    def __init__(self, label: str, **kwargs):
        super().__init__("", **kwargs)
        self.label = label
        self.set_class(True, "screen-preview")

    def update_preview(self, style: StyleConfig, values: str) -> None:
        """Called from the App thread to render a new preview frame."""
        self.last_style = style
        self.last_values = values
        # Render immediately
        self._render_now()

    # Small helper to approximate alignment within a fixed width "LCD"
    @staticmethod
    def _align(text: str, width: int, align: AlignmentEnum) -> str:
        text = text.strip()
        if len(text) > width:
            return text[:width]
        pad = width - len(text)
        if align == AlignmentEnum.CENTER:
            left = pad // 2
            right = pad - left
            return (" " * left) + text + (" " * right)
        return text + (" " * pad)

    def _render_now(self) -> None:
        style = self.last_style
        values = self.last_values

        # Fallbacks
        if style is None:
            self.update(f"[{self.label}] — waiting…")
            return

        # Approximate a 16x2 LCD view (first line text, second line style hint)
        WIDTH = 16

        # Background hint glyphs to suggest style; purely cosmetic
        bg_hint = {
            BackgroundEnum.SOLID: "█",
            BackgroundEnum.SQUARES: "▦",
        }.get(getattr(style, "bg", BackgroundEnum.SOLID), "█")

        # Foreground hint for "color" — we only show the letter here (no real colors)
        fg_hint = getattr(style, "fg", "1")
        # Alignment / size hints
        align = getattr(style, "alignment", AlignmentEnum.CENTER)
        size_hint = getattr(style, "font_size", 1)

        # First line is the "LCD" content, aligned
        line1 = self._align(values, WIDTH, align)

        # Second line: compact style diagnostics for visibility while debugging
        style_summary = f"{bg_hint} bg={getattr(style,'bg','?')} fg={fg_hint} sz={size_hint} al={align.name}"
        bot_text = self._align(style_summary[:WIDTH], WIDTH, AlignmentEnum.LEFT)
        bot = f"│{bot_text}│"

        # Build a small framed block
        lines = [
            f"╭─ {self.label} ─{'─'*(WIDTH- len(self.label) - 3)}╮",
            f"│{' ' * len(line1)} │",
            f"│{line1} │",
            f"│{' ' * len(line1)} │",
            f"╰{'─'*(WIDTH+1)}╯",
            bot,
        ]

        self.update("\n".join(lines))


# ----------------------------
# Screen + sending logic
# ----------------------------
@attrs.define
class Screen:
    port: str
    pos: ScreenEnum
    # Callback invoked whenever a frame is "sent" so the UI can mirror it.
    # This MUST be thread-safe (i.e., schedule work on the Textual thread).
    ui_callback: Optional[Callable[[StyleConfig, str], None]] = None

    current_style: StyleConfig = StyleConfig(
        BackgroundEnum.SOLID,
        "0",
        "0",
        "W",
        2,
        AlignmentEnum.CENTER,
    )
    current_values: str = ""
    prev_values: str = ""
    prev_style: StyleConfig | None = None

    def _emit_ui(self, style: StyleConfig, values: str) -> None:
        """Safely notify the UI preview that a new frame is available."""
        try:
            if self.ui_callback is not None:
                self.ui_callback(style, values)
        except Exception:
            # Never fail the hardware send because UI preview failed.
            pass

    def _send(self, style: StyleConfig, values: str):
        self.prev_style = self.current_style
        self.prev_values = self.current_values

        self.current_style = style
        self.current_values = values

        # 1) Update UI preview first (fast, local)
        self._emit_ui(style, values)

        # 2) Attempt to write to the physical device
        try:
            BAUD = 115200
            # Using context manager ensures close() on error
            with Serial(self.port, BAUD, timeout=1) as ser:
                writable = f"{create_style_str(style)}{values}@@"
                ser.write(writable.encode())
        except Exception:
            print(f"Error: Failed to send to eye on {self.port}")

    def send(self, style: StyleConfig, values: str):
        # Keep hardware I/O off the UI thread.
        threading.Thread(target=self._send, args=(style, values), daemon=True).start()


ScreenState = Literal[
    "eyes",
    "left_timer",
    "right_timer",
    "left_static",
    "right_static",
    "on_call",
]


@attrs.define
class Screens:
    left_screen: Screen
    right_screen: Screen
    state: ScreenState = "eyes"

    state_change = threading.Event()
    thread: Thread | None = None

    def _stop_thread(self):
        if self.thread and self.thread.is_alive():
            self.state_change.set()
            self.thread.join(timeout=1.0)
        self.state_change.clear()

    def count_down(self, user_message: str):
        self._stop_thread()
        self.thread = threading.Thread(
            target=self._count_down, args=(user_message,), daemon=True
        )
        self.thread.start()

    def _count_down(self, user_message: str):
        time_msg = _parse_time_message(user_message)
        assert time_msg

        target_time = datetime.strptime(time_msg.target_time, "%H:%M").time()
        target_datetime = datetime.combine(datetime.now().date(), target_time)

        if target_datetime <= datetime.now():
            target_datetime += timedelta(days=1)

        style = StyleConfig(
            BackgroundEnum.SQUARES,
            "0",
            "R",
            "W",
            5,
            AlignmentEnum.CENTER,
        )

        prev_minutes_left = None
        while True:
            if self.state_change.is_set():
                break
            seconds_left = max(
                0, int((target_datetime - datetime.now()).total_seconds())
            )
            minutes_left = seconds_left // 60

            # Update once per minute (and at start)
            if prev_minutes_left != minutes_left:
                label = f"{time_msg.message} {minutes_left} Min".strip()
                self.right_screen.send(style, label)
                prev_minutes_left = minutes_left

            if seconds_left <= 0:
                break

            time.sleep(1)

    def on_call(self):
        self._stop_thread()
        self.thread = threading.Thread(target=self._on_call, daemon=True)
        self.thread.start()

    def _on_call(self):
        style = StyleConfig(
            BackgroundEnum.SQUARES,
            "0",
            "R",
            "W",
            5,
            AlignmentEnum.CENTER,
        )
        self.left_screen.send(style, "ON")
        self.right_screen.send(style, "CALL")

    def static(self, target: ScreenEnum, msg: str):
        self._stop_thread()
        self.thread = threading.Thread(
            target=self._static, args=(target, msg), daemon=True
        )
        self.thread.start()

    def get_screen(self, target: ScreenEnum):
        target_screen = {
            ScreenEnum.LEFT: self.left_screen,
            ScreenEnum.RIGHT: self.right_screen,
        }
        return target_screen[target]

    def _static(self, target: ScreenEnum, msg: str):
        style = StyleConfig(
            BackgroundEnum.SOLID,
            "0",
            "0",
            "1",
            4,
            AlignmentEnum.CENTER,
        )
        screen = self.get_screen(target)
        screen.send(style, msg)

    def eyes(self):
        self.state = "eyes"
        t = threading.Thread(target=self._eyes, daemon=True)
        self.thread = t
        self.thread.start()

    def _eyes(self):
        self.state_change.clear()

        eye_style = StyleConfig(
            BackgroundEnum.SOLID,
            "0",
            "0",
            "1",
            8,
            AlignmentEnum.CENTER,
        )

        eyes_open_shape = "o"
        eyes_close_shape = "-"

        while self.state == "eyes" and not self.state_change.is_set():
            self.left_screen.send(eye_style, eyes_open_shape)
            self.right_screen.send(eye_style, eyes_open_shape)

            eyes_open_time = random.randint(0, 15)
            if self.state_change.wait(eyes_open_time):
                break

            self.left_screen.send(eye_style, eyes_close_shape)
            self.right_screen.send(eye_style, eyes_close_shape)

            eyes_close_time = random.randint(0, 2)
            if self.state_change.wait(eyes_close_time):
                break


Action = Literal[
    "SHOW_STATIC_MESSAGE_LEFT",
    "SHOW_STATIC_MESSAGE_RIGHT",
    "SHOW_COUNTDOWN",
    "EYES",
    "SHOW_CALL",
]


# ----------------------------
# Main Textual App
# ----------------------------
class SignCLI(App):
    CSS_PATH = "main.tcss"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
    ]

    # Previews
    left_preview: ScreenPreview
    right_preview: ScreenPreview

    # Physical screens + coordinator
    screens: Screens

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="NORTH CLI")

        # Top row: inline simulation of the two LCDs
        with Horizontal(id="preview-row"):
            with Vertical():
                self.left_preview = ScreenPreview("LEFT")
                yield self.left_preview
            with Vertical():
                self.right_preview = ScreenPreview("RIGHT")
                yield self.right_preview

        # Chat/messages and input
        with Container(id="chat-container"):
            yield VerticalScroll(id="messages")
        yield Static("", id="divider-top")
        with Container(id="input-container"):
            yield Static(">", id="prompt")
            yield Input(id="chat-input")
        yield Static("", id="divider-bottom")

    async def on_mount(self) -> None:
        self.query_one("#chat-input", Input).focus()
        self.update_dividers()

        # Thread-safe UI callbacks: schedule updates on the Textual thread
        def left_ui(style: StyleConfig, values: str) -> None:
            self.call_from_thread(self.left_preview.update_preview, style, values)

        def right_ui(style: StyleConfig, values: str) -> None:
            self.call_from_thread(self.right_preview.update_preview, style, values)

        # Hook screens to both serial ports and UI previews
        self.left_screen = Screen(LEFT_PORT, ScreenEnum.LEFT, ui_callback=left_ui)
        self.right_screen = Screen(RIGHT_PORT, ScreenEnum.RIGHT, ui_callback=right_ui)
        self.screens = Screens(self.left_screen, self.right_screen)

    def on_resize(self) -> None:
        self.update_dividers()

    def update_dividers(self) -> None:
        width = self.size.width
        divider_text = "─" * width
        self.query_one("#divider-top", Static).update(divider_text)
        self.query_one("#divider-bottom", Static).update(divider_text)

    async def add_message(
        self,
        typ: Literal["assistant", "user", "logo", "cmd", "error"],
        msg: str,
    ) -> None:
        msg_block = Message(typ, msg)
        messages_container = self.query_one("#messages", VerticalScroll)
        messages_container.scroll_end(animate=False)
        messages_container.mount(msg_block)
        messages_container.scroll_end(animate=False)

    def identify_action(self, user_message: str) -> Action:
        user_message = user_message.strip()
        if user_message.lower() == "eyes":
            return "EYES"
        if user_message.lower() == "call":
            return "SHOW_CALL"
        if re.search(r"\d\d:\d\d$", user_message):
            return "SHOW_COUNTDOWN"
        if user_message.startswith("!"):
            return "SHOW_STATIC_MESSAGE_LEFT"
        return "SHOW_STATIC_MESSAGE_RIGHT"

    async def reduce_action(self, action: Action, user_message: str):
        match action:
            case "EYES":
                self.screens.eyes()
            case "SHOW_STATIC_MESSAGE_LEFT":
                # Strip leading "!" so the actual message is clean on the device
                self.screens.static(ScreenEnum.LEFT, user_message.lstrip("!").strip())
            case "SHOW_STATIC_MESSAGE_RIGHT":
                self.screens.static(ScreenEnum.RIGHT, user_message)
            case "SHOW_CALL":
                self.screens.on_call()
            case "SHOW_COUNTDOWN":
                self.screens.count_down(user_message)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_message = event.value
        input_widget = self.query_one("#chat-input", Input)

        input_widget.value = ""
        current_action = self.identify_action(user_message)

        await self.reduce_action(current_action, user_message)
        await self.add_message("assistant", user_message)


if __name__ == "__main__":
    app = SignCLI()
    app.run()
