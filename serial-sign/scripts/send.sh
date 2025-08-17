#!/bin/bash

L_PORT=/dev/cu.usbserial-21430
R_PORT=/dev/cu.usbserial-2110
BAUD=115200

function send {
    for session in $(screen -ls | grep -o "[0-9]\+."${NAME}); do
        screen -S "${session}" -dm -L -port $PORT $BAUD;
        screen -S "${session}" -p 0 -X stuff "$1"
        exit 0;
    done;

    screen -S ${NAME} -dm -L -port $PORT $BAUD;

    for session in $(screen -ls | grep -o "[0-9]\+."${NAME}); do
        screen -S "${session}" -dm -L -port $PORT $BAUD;
        screen -S "${session}" -p 0 -X stuff "$1"
        break;
    done;

    for session in $(screen -ls | grep -o "[0-9]\+."${NAME}); do
        screen -S "${session}" -X kill
    done;
}

PORT=${L_PORT} NAME=left send "00006WOK?@@"