import asyncio
import json
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Literal

import attrs
import cattrs
from attrs import asdict, define, field
from serial import Serial
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.events import Paste
from textual.reactive import reactive
from textual.theme import Theme
from textual.widgets import Footer, Header, Input, Static
from yaml import safe_dump, safe_load

from send import (
    AlignmentEnum,
    BackgroundEnum,
    ScreenEnum,
    StyleConfig,
    create_style_str,
)

LEFT_PORT = "/dev/cu.usbserial-1240"
RIGHT_PORT = "/dev/cu.usbserial-1230"


class Message(Static):

    def __init__(self, role: str, content: str, **kwargs):
        self.role = role
        super().__init__(content, **kwargs)
        self.add_class(f"message-{role}")


@attrs.define
class TimeMessage:
    target_time: str
    message: str


def _parse_time_message(time_message: str) -> TimeMessage | None:
    time_match = re.match(r"(.*?)(\d\d:\d\d)$", time_message)
    if time_match:
        return TimeMessage(time_match.group(2), time_match.group(1))
    return None


@attrs.define
class Screen:
    port: str
    pos: ScreenEnum
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

    def _send(self, style: StyleConfig, values: str):
        self.prev_style = self.current_style
        self.prev_values = self.current_values

        self.current_style = style
        self.current_values = values

        try:
            BAUD = 115200
            ser = Serial(self.port, BAUD)
            writable = f"{create_style_str(style)}{values}@@"
            ser.write(writable.encode())
            ser.close()
        except Exception:
            print("Error: Failed to send to eye")

    def send(self, style: StyleConfig, values: str):
        threading.Thread(target=self._send, args=(style, values)).start()


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
        if self.thread:
            self.state_change.set()
            self.thread.join(999)
        self.state_change.clear()

    def count_down(self, user_message: str):
        self._stop_thread()
        self.thread = threading.Thread(target=self._count_down, args=(user_message,))
        self.thread.start()

    def _count_down(self, user_message: str):
        time_msg = _parse_time_message(user_message)
        assert time_msg

        target_time = datetime.strptime(time_msg.target_time, "%H:%M").time()
        target_datetime = datetime.combine(datetime.now().date(), target_time)

        if target_datetime < datetime.now():
            target_datetime += timedelta(days=1)

        seconds_left = int((target_datetime - datetime.now()).total_seconds())

        style = StyleConfig(
            BackgroundEnum.SQUARES,
            "0",
            "R",
            "W",
            5,
            AlignmentEnum.CENTER,
        )

        prev_minutes_left = -1
        while seconds_left > 0:
            seconds_left = int((target_datetime - datetime.now()).total_seconds())
            minutes_left = seconds_left / 60
            time.sleep(1)
            seconds_left -= 1
            if prev_minutes_left != minutes_left:
                message = f"{time_msg.message.strip()} {minutes_left} Min"
                self.right_screen.send(style, message)
                prev_minutes_left = minutes_left

    def on_call(self):
        self._stop_thread()
        self.thread = threading.Thread(target=self._on_call)
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
        self.thread = threading.Thread(target=self._static, args=(target, msg))
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
        t = threading.Thread(target=self._eyes)
        self.thread = t
        self.thread.start()

    def _eyes(self):
        print("go")
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

        while self.state == "eyes":
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


class SignCLI(App):
    CSS_PATH = "main.tcss"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
    ]

    screens: Screens

    def compose(self) -> ComposeResult:

        yield Header(show_clock=True, name="NORTH CLI")
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
        self.left_screen = Screen(LEFT_PORT, ScreenEnum.LEFT)
        self.right_screen = Screen(RIGHT_PORT, ScreenEnum.RIGHT)
        self.screens = Screens(self.left_screen, self.right_screen)

    def on_resize(self) -> None:
        self.update_dividers()

    def update_dividers(self) -> None:
        # Custom dividers for text input and chat
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
        if user_message.strip().lower() == "eyes":
            return "EYES"
        if user_message.strip().lower() == "call":
            return "SHOW_CALL"
        time_msg = re.search(r"\d\d:\d\d$", user_message)
        if time_msg:
            return "SHOW_COUNTDOWN"
        if user_message.startswith("!"):
            return "SHOW_STATIC_MESSAGE_LEFT"
        return "SHOW_STATIC_MESSAGE_RIGHT"

    async def reduce_action(self, action: Action, user_message: str):
        match action:
            case "EYES":
                self.screens.eyes()
            case "SHOW_STATIC_MESSAGE_LEFT":
                self.screens.static(ScreenEnum.LEFT, user_message)
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
