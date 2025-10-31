import argparse
import sys
from enum import Enum
from typing import Literal, NamedTuple

import serial

L_PORT = "/dev/cu.usbserial-21430"
R_PORT = "/dev/cu.usbserial-2140"
BAUD = 115200

NUM_FONT_CONFIGS = 8


class HelpDefaultParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write("error: %s\n" % message)
        self.print_help()
        sys.exit(2)


class ScreenEnum(Enum):
    LEFT = "left"
    RIGHT = "right"


class ColorEnum(Enum):
    RED = "r"
    GREEN = "g"
    BLUE = "b"
    PURPLE = "p"
    WHITE = "w"
    YELLOW = "y"
    BLACK = "0"

    @classmethod
    def choices(cls):
        return [x.value for x in list(cls)]


class BackgroundEnum(Enum):
    SOLID = "0"
    SQUARES = "s"


class AlignmentEnum(Enum):
    LEFT = "0"
    CENTER = "1"


Color = Literal[
    "R",
    "G",
    "B",
    "P",
    "Y",
    "0",
    "1",
    "W",
]


class StyleConfig(NamedTuple):
    b: BackgroundEnum
    bb: Color
    bf: Color
    fc: Color
    fs: int
    fa: AlignmentEnum


def create_style_str(conf: StyleConfig) -> str:
    return f"{conf.b.value}{conf.bb}{conf.bf}{conf.fa.value}{conf.fs}{conf.fc}"


def send(screen: ScreenEnum, conf: StyleConfig):
    values = sys.stdin.read()

    port = L_PORT
    if screen == ScreenEnum.RIGHT:
        port = R_PORT

    ser = serial.Serial(port, BAUD)
    writable = f"{create_style_str(conf)}{values}@@"
    ser.write(writable.encode())
    ser.close()


if __name__ == "__main__":
    arg_parser = HelpDefaultParser()
    arg_parser.add_argument(
        "-b",
        type=BackgroundEnum,
        choices=list(BackgroundEnum),
        help="Background style",
        default=BackgroundEnum.SOLID,
    )
    arg_parser.add_argument(
        "-bb",
        choices=ColorEnum.choices(),
        help="Background's back color",
        default=ColorEnum.BLACK.value,
    )
    arg_parser.add_argument(
        "-bf",
        choices=ColorEnum.choices(),
        help="Background's front color",
        default=ColorEnum.RED.value,
    )
    arg_parser.add_argument(
        "screen",
        type=ScreenEnum,
        choices=list(ScreenEnum),
        help="Where to send the data to",
    )
    arg_parser.add_argument(
        "-fc",
        choices=ColorEnum.choices(),
        help="Font color",
        default=ColorEnum.WHITE.value,
    )
    arg_parser.add_argument(
        "-fs",
        type=int,
        choices=list(range(NUM_FONT_CONFIGS)),
        help="Font size",
        default=3,
    )
    arg_parser.add_argument(
        "-fa",
        type=AlignmentEnum,
        choices=list(AlignmentEnum),
        help="Font alignment",
        default=AlignmentEnum.CENTER,
    )

    parsed_args = arg_parser.parse_args(sys.argv[1:])

    send(parsed_args.screen, parsed_args)
