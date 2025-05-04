#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont

# Setup path for Waveshare libraries
libdir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "lib"
)
if os.path.exists(libdir):
    sys.path.append(libdir)

from TP_lib import epd2in13_V3, epdconfig, gt1151
from py532lib.i2c import *
from py532lib.frame import *
from py532lib.constants import *

# Constants
EPD_WIDTH = 250
EPD_HEIGHT = 122
BUTTON_WIDTH = 190
BUTTON_HEIGHT = 40
BUTTON_X = (EPD_WIDTH - BUTTON_WIDTH) // 2
font = ImageFont.load_default()

# Global state
yes_uid = None
no_uid = None
quiz_started = False
score = 0
question_index = 0

# Quiz data
quiz = [
    {"question": "Is the Earth round?", "correct": "YES"},
    {"question": "Is 2+2 equal to 4?", "correct": "YES"},
    {"question": "Is the sky green?", "correct": "NO"},
]


# Helper functions
def draw_button(draw, text, y):
    draw.rectangle(
        [BUTTON_X, y, BUTTON_X + BUTTON_WIDTH, y + BUTTON_HEIGHT], outline=0, width=1
    )
    text_x = BUTTON_X + (BUTTON_WIDTH - len(text) * 6) // 2
    text_y = y + (BUTTON_HEIGHT - 10) // 2
    draw.text((text_x, text_y), text, font=font, fill=0)


def create_screen(title, buttons, y_title=5):
    print(f"create screen: {title}, button: {buttons}, y_title: {y_title}")
    image = Image.new("1", (EPD_WIDTH, EPD_HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    draw.text((10, y_title), title, font=font, fill=0)
    for i, label in enumerate(buttons):
        draw_button(draw, label, 30 + i * (BUTTON_HEIGHT + 10))
    return image


def display_screen(epd, image):
    epd.display(epd.getbuffer(image))


def touch_within(x, y, button_y):
    return (
        BUTTON_X <= x <= BUTTON_X + BUTTON_WIDTH
        and button_y <= y <= button_y + BUTTON_HEIGHT
    )


def uid_to_str(uid):
    return ":".join(format(x, "02X") for x in uid[:10]) if uid else ""


def scan_nfc_tag(prompt):
    img = Image.new("1", (EPD_WIDTH, EPD_HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    draw.text((10, 50), prompt, font=font, fill=0)
    display_screen(epd, img)
    while True:
        uid = pn532.read_mifare().get_data()
        if uid:
            uid_str = uid_to_str(uid)
            print(f"{prompt} -> {uid_str}")
            return uid_str


# NFC setup
pn532 = Pn532_i2c()
pn532.SAMconfigure()

# E-paper init
epd = epd2in13_V3.EPD()
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)

# Touch init
gt = gt1151.GT1151()
GT_Dev = gt1151.GT_Development()
GT_Old = gt1151.GT_Development()
gt.GT_Init()


# Screens
def get_score_screen(score, total):
    return create_screen(f"Score: {score}/{total}", ["Restart Quiz", "Exit"])


def get_quiz_screen():
    q = quiz[question_index]
    return create_screen(f"{q['question']}", ["Answer YES", "Answer NO"])


screens = {
    "start": create_screen(
        "NFC Quiz System", ["Start Quiz", "Register Tags", "View Score"]
    ),
    "register": create_screen("Register NFC Tags", ["Scan YES Tag", "Scan NO Tag"]),
    "correct": create_screen("Correct Answer!", ["Next"]),
    "wrong": create_screen("Wrong Answer!", ["Retry"]),
}

# Show start screen
display_screen(epd, screens["start"])

# Touch event loop using gt1151
flag_t = 1


def pthread_irq():
    global flag_t
    while flag_t == 1:
        if gt.digital_read(gt.INT) == 0:
            GT_Dev.Touch = 1
        else:
            GT_Dev.Touch = 0


t = threading.Thread(target=pthread_irq)
t.daemon = True
t.start()

try:
    while True:
        gt.GT_Scan(GT_Dev, GT_Old)
        if GT_Dev.TouchpointFlag:
            GT_Dev.TouchpointFlag = 0
            x, y = GT_Dev.X[0], GT_Dev.Y[0]
            print(f"Touch at x={x}, y={y}")

            if not quiz_started:
                print("button pressed, quiz not started")
                if touch_within(x, y, 30):
                    print("Is this the start quiz button?")
                    print(yes_uid)
                    print(no_uid)
                    if yes_uid and no_uid:
                        print("tags already registered")
                        quiz_started = True
                        question_index = 0
                        score = 0
                        display_screen(epd, get_quiz_screen())
                    else:
                        print("Tags not yet registered")
                        display_screen(epd, screens["register"])
                elif touch_within(x, y, 80):
                    print("Is this the register button?")
                    display_screen(epd, screens["register"])
                    yes_uid = scan_nfc_tag("Scan YES tag")
                    no_uid = scan_nfc_tag("Scan NO tag")
                    display_screen(epd, screens["start"])
                elif touch_within(x, y, 130):
                    print("scores screen")
                    display_screen(epd, get_score_screen(score, len(quiz)))
            else:
                print("button pressed, quiz already started")
                print("Waiting for tag to answer...")
                uid = pn532.read_mifare().get_data()
                if uid:
                    uid_str = uid_to_str(uid)
                    user_answer = (
                        "YES"
                        if uid_str == yes_uid
                        else "NO" if uid_str == no_uid else None
                    )
                    if user_answer:
                        correct = quiz[question_index]["correct"]
                        if user_answer == correct:
                            score += 1
                            display_screen(epd, screens["correct"])
                        else:
                            display_screen(epd, screens["wrong"])
                        time.sleep(2)
                        question_index += 1
                        if question_index < len(quiz):
                            display_screen(epd, get_quiz_screen())
                        else:
                            quiz_started = False
                            display_screen(epd, get_score_screen(score, len(quiz)))
        time.sleep(0.1)
except KeyboardInterrupt:
    print("Exiting...")
    epd.init()
    epd.Clear(0xFF)
    epd.sleep()
    flag_t = 0
    t.join()
