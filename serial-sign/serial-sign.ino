/*******************************************************************
    TFT_eSPI button example for the ESP32 Cheap Yellow Display.

    https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display

    Written by Claus Näveke
    Github: https://github.com/TheNitek
 *******************************************************************/

// Make sure to copy the UserSetup.h file into the library as
// per the Github Instructions. The pins are defined in there.

// ----------------------------
// Standard Libraries
// ----------------------------

#include <SPI.h>

// ----------------------------
// Additional Libraries - each one of these will need to be installed.
// ----------------------------

#include <XPT2046_Touchscreen.h>

#include <TFT_eSPI.h>
// A library for interfacing with LCD displays
//
// Can be installed from the library manager (Search for "TFT_eSPI")
// https://github.com/Bodmer/TFT_eSPI

// ----------------------------
// Touch Screen pins
// ----------------------------

// The CYD touch uses some non default
// SPI pins

#define XPT2046_IRQ 36
#define XPT2046_MOSI 32
#define XPT2046_MISO 39
#define XPT2046_CLK 25
#define XPT2046_CS 33
// ----------------------------

SPIClass mySpi = SPIClass(VSPI);
XPT2046_Touchscreen ts(XPT2046_CS, XPT2046_IRQ);
TFT_eSPI tft = TFT_eSPI();

// byte1 is size, byte2 is bg
#define SERIAL_META_OFFSET 2
#define MESSAGE_MAX_LEN 512
char serialData[MESSAGE_MAX_LEN] = "1ANo Data";

void clearScreen() { tft.fillScreen(TFT_BLACK); }

void setup() {
  Serial.begin(115200);

  mySpi.begin(XPT2046_CLK, XPT2046_MISO, XPT2046_MOSI, XPT2046_CS);
  ts.begin(mySpi);
  ts.setRotation(1);

  // Start the tft display and set it to black
  tft.init();
  tft.invertDisplay(1);
  tft.setRotation(1);

  clearScreen();
}

#define DISP_HEIGHT 240
#define DISP_WIDTH 320

#define LINE_ANIM_TIMEOUT 10
#define LINE_WIDTH 25

int drawBgLineCurrentIndex = 0;
int drawBgLineMillis = 0;

void drawBgLine(int bgColor, int fgColor) {
  if (millis() - drawBgLineMillis > LINE_ANIM_TIMEOUT) {
    tft.fillRect(drawBgLineCurrentIndex, 0, LINE_WIDTH, DISP_HEIGHT, bgColor);
    drawBgLineCurrentIndex = (drawBgLineCurrentIndex + 2) % DISP_WIDTH;
    tft.fillRect(drawBgLineCurrentIndex, 0, LINE_WIDTH, DISP_HEIGHT, fgColor);
    drawBgLineMillis = millis();
  }
}

#define DRAW_BG_GRADIENT_ANIM_TIMEOUT 10

int drawBgGradientCurrentIndex = 0;
int drawBgGradientMillis = 0;

void drawBgGradient(int bgColor, int fgColor) {
  if (millis() - drawBgGradientMillis > DRAW_BG_GRADIENT_ANIM_TIMEOUT) {
    tft.fillRectHGradient(0 + drawBgGradientCurrentIndex, 0, DISP_WIDTH,
                          DISP_HEIGHT, bgColor, fgColor);
    drawBgGradientCurrentIndex = (drawBgGradientCurrentIndex + 2) % DISP_WIDTH;
    tft.fillRectHGradient(DISP_WIDTH - drawBgGradientCurrentIndex, 0,
                          DISP_WIDTH, DISP_HEIGHT, fgColor, bgColor);
    drawBgGradientMillis = millis();
  }
}

#define SQUARE_SIX_ANIM_TIMEOUT 500
int drawBgSquareSixCurrentIndex = 6;
int drawBgSquareSixMillis = 0;

void drawBgSquareSixSquares(int color) {
  int width = DISP_WIDTH / 3;
  int height = DISP_HEIGHT / 2;
  int x = 0;
  int y = 0;
  for (int i = 0; i < 6; i++) {
    if (i == drawBgSquareSixCurrentIndex) {
      tft.fillRoundRect(x + 5, y + 5, width - 10, height - 10, 10, color);
    }

    if (i == 2) {
      x = 0;
      y = height;
    } else {
      x += width;
    }
  }
}

void drawBgSquareSix(int bgColor, int fgColor) {
  if (millis() - drawBgSquareSixMillis > SQUARE_SIX_ANIM_TIMEOUT) {
    drawBgSquareSixSquares(bgColor);
    drawBgSquareSixCurrentIndex = (drawBgSquareSixCurrentIndex + 1) % 6;
    drawBgSquareSixMillis = millis();
    drawBgSquareSixSquares(fgColor);
  }
}

#define Mono24Size3Height 81
#define Mono24Size3MaxChars 4

#define Mono18Size3Height 69
#define Mono18Size3MaxChars 5

#define Mono24Size2Height 58
#define Mono24Size2MaxChars 6

#define Mono18Size2Height 46
#define Mono18Size2MaxChars 8

#define Mono24Size1Height 30
#define Mono24Size1MaxChars 11 // Could be 12

#define Mono18Size1Height 23
#define Mono18Size1MaxChars 16

#define Mono12Size1Height 15
#define Mono12Size1MaxChars 24

#define NEWLINE_BYTE 13

void drawMessage(const GFXfont *font, int size, int textHeight) {
  tft.setTextColor(TFT_WHITE);
  tft.setTextSize(size);
  tft.setFreeFont(font);
  int y = 0;
  int lineIndex = 0;

  char line[128];
  for (int i = SERIAL_META_OFFSET; i <= strlen(serialData); i++) {
    if (serialData[i] == NEWLINE_BYTE) {
      line[lineIndex] = '\0';
      tft.drawString(line, 0, y);
      y += textHeight;
      lineIndex = 0;
      line[lineIndex] = '\0';
    } else {
      line[lineIndex] = serialData[i];
      lineIndex += 1;
    }
    if (serialData[i] == '\0') {
      tft.drawString(line, 0, y);
      break;
    }
  }
}

void drawMessageBasic(const GFXfont *font, int size) {
  tft.setTextColor(TFT_WHITE);
  tft.setTextSize(size);
  tft.setFreeFont(font);
  tft.drawString(serialData, 0, 0);
  tft.drawString(String(strlen(serialData)), 0, 90);
}

int currentRotation = 1;

// 400 <= p.y < 3700
// 400 <= p.x < 3700

#define FINGERNAIL_TOUCH_PRESSURE 1800

bool wasTouched = false;
int touchTimeoutMillis = 0;

void manageTouchRotation() {
  if (ts.tirqTouched() && ts.touched() &&
      (millis() - touchTimeoutMillis > 1500)) {
    clearScreen();
    TS_Point p = ts.getPoint();
    if (p.z > FINGERNAIL_TOUCH_PRESSURE) {
      currentRotation = (currentRotation + 2) % 4;
      tft.setRotation(currentRotation);
      ts.setRotation(currentRotation);
      touchTimeoutMillis = millis();
    }
  }
}

#define BACKSPACE_BYTE 127
#define SENTINEL_BYTE 64
// SENTINEL_BYTE == '@'

int serialCurrentIndex = 0;
bool serialPrevByteWasSentinel = false;

void manageSerialData() {
  if (Serial.available()) {
    clearScreen();
    int byte = Serial.read();
    Serial.print(char(byte));
    if (byte == BACKSPACE_BYTE) {
      serialCurrentIndex -= 1;
      serialData[serialCurrentIndex] = '\0';
    } else {
      serialData[serialCurrentIndex] = char(byte);
      serialCurrentIndex += 1;
    }
    if (byte == '@' && !serialPrevByteWasSentinel) {
      serialPrevByteWasSentinel = true;
    } else if (byte == '@' && serialPrevByteWasSentinel) {
      // Erase previous two @s and end message
      serialCurrentIndex -= 1;
      serialData[serialCurrentIndex] = '\0';
      serialCurrentIndex -= 1;
      serialData[serialCurrentIndex] = '\0';
      serialCurrentIndex = 0;
      serialPrevByteWasSentinel = false;
    }
  }
}

void loop() {
  // drawBgSquareSix(TFT_BLACK, TFT_RED);
  // drawBgGradient(TFT_BLACK, TFT_RED);
  drawMessage(&FreeMonoBold12pt7b, 1, Mono12Size1Height);
  // drawMessageBasic(&FreeMonoBold24pt7b, 2);
  manageTouchRotation();
  manageSerialData();
}
