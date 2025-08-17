#include <SPI.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>

#define XPT2046_IRQ 36
#define XPT2046_MOSI 32
#define XPT2046_MISO 39
#define XPT2046_CLK 25
#define XPT2046_CS 33

SPIClass mySpi = SPIClass(VSPI);
XPT2046_Touchscreen ts(XPT2046_CS, XPT2046_IRQ);
TFT_eSPI tft = TFT_eSPI();

// BG_RENDERER, BG_BG_COLOR, BG_FG_COLOR, FONT_ALIGNMENT, FONT_SIZE, FONT_COLOR
#define CONFIG_OPTION_COUNT 6
#define MESSAGE_MAX_LEN 512

char serialData[MESSAGE_MAX_LEN] = "00006RNo\nData";
char newSerialData[MESSAGE_MAX_LEN] = {'\0'};

typedef struct {
  const GFXfont *font;
  int size;
  int height;
  int maxChars;
} MessageSizeConfig;

typedef void (*DrawBg)(int bgColor, int fgColor);

typedef struct {
  int bgColor;
  int fgColor;
  int bgDrawer;
} BackgroundConfig;

typedef struct {
  MessageSizeConfig fontConfig;
  int fontColor;
  int fontAlignment;
  BackgroundConfig bgConfig;
} StyleConfig;

void clearScreen() { tft.fillScreen(TFT_BLACK); }

void setup() {
  Serial.begin(115200);

  mySpi.begin(XPT2046_CLK, XPT2046_MISO, XPT2046_MOSI, XPT2046_CS);
  ts.begin(mySpi);
  ts.setRotation(currentRotation);

  // Start the tft display and set it to black
  tft.init();
  tft.invertDisplay(1);
  tft.setRotation(currentRotation);

  clearScreen();
}

#define DISP_HEIGHT 240
#define DISP_WIDTH 320
#define CENTER_X 160
#define CENTER_Y 120

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

#define DRAW_BG_SOLID 0
#define DRAW_BG_SQUARE_SIX 1

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

int drawBgSolidDrawn = false;
void drawBgSolid(int bgColor, int fgColor) {
  if (!drawBgSolidDrawn) {
    tft.fillRect(0, 0, DISP_WIDTH, DISP_HEIGHT, bgColor);
    drawBgSolidDrawn = true;
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
  if (bgColor == fgColor) {
    return drawBgSolid(bgColor, fgColor);
  }
  if (millis() - drawBgSquareSixMillis > SQUARE_SIX_ANIM_TIMEOUT) {
    drawBgSquareSixSquares(bgColor);
    drawBgSquareSixCurrentIndex = (drawBgSquareSixCurrentIndex + 1) % 6;
    drawBgSquareSixMillis = millis();
    drawBgSquareSixSquares(fgColor);
  }
}

#define NEWLINE_BYTE 13

void drawStringMaybeCenter(char *str, int y, int alignment) {
  int width = tft.textWidth(str);
  if (width > DISP_WIDTH) {
    alignment = TC_DATUM;
  }

  tft.setTextDatum(alignment);
  if (alignment == TC_DATUM) {
    tft.drawString(str, CENTER_X, y);
  } else {
    tft.drawString(str, 0, y);
  }
}

void drawMessage(char *str, const GFXfont *font, int color, int size,
                 int fontHeight, int alignment) {
  return drawMessage(str, CONFIG_OPTION_COUNT, font, color, size, fontHeight,
                     alignment);
}

void drawMessage(char *str, int offset, const GFXfont *font, int color,
                 int size, int fontHeight, int alignment) {

  tft.setTextColor(color);
  tft.setTextSize(size);
  tft.setFreeFont(font);

  int linePadding = 10;
  int lineCount = 1;
  char line[128];
  for (int i = offset; i <= strlen(serialData); i++) {
    if (str[i] == NEWLINE_BYTE || str[i] == '\n') {
      lineCount += 1;
    }
  }

  int textHeight = lineCount * fontHeight + ((lineCount - 1) * linePadding);
  int y = CENTER_Y - textHeight / 2;

  if (lineCount % 3 == 0) {
    // We add an extra 1/2 because of the
    // text that falls right on the center
    y -= fontHeight / 2;
  }

  int lineIndex = 0;

  for (int i = offset; i <= strlen(str); i++) {
    if (str[i] == NEWLINE_BYTE || str[i] == '\n') {
      line[lineIndex] = '\0';
      drawStringMaybeCenter(line, y, alignment);
      y += fontHeight;
      y += linePadding;
      lineIndex = 0;
      line[lineIndex] = '\0';
    } else {
      line[lineIndex] = str[i];
      lineIndex += 1;
    }
    if (str[i] == '\0') {
      line[lineIndex] = '\0';
      drawStringMaybeCenter(line, y, alignment);
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

#ifndef IS_LEFT
int currentRotation = 1;
#else
int currentRotation = 3;
#endif

// 400 <= p.y < 3700
// 400 <= p.x < 3700

#define FINGERNAIL_TOUCH_PRESSURE 500

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

#define SERIAL_DATA_STATE_AWAITING 0
#define SERIAL_DATA_STATE_INPUTTING 1
#define SERIAL_DATA_STATE_FINISHED 2

int serialDataState = SERIAL_DATA_STATE_AWAITING;

void manageSerialData() {
  if (serialDataState == SERIAL_DATA_STATE_FINISHED) {
    serialDataState = SERIAL_DATA_STATE_AWAITING;
  }
  if (Serial.available()) {
    int byte = Serial.read();
    Serial.print(char(byte));
    serialDataState = SERIAL_DATA_STATE_INPUTTING;

    if (byte == BACKSPACE_BYTE) {
      clearScreen();
      serialCurrentIndex -= 1;
      newSerialData[serialCurrentIndex] = '\0';
    } else {
      if (byte == NEWLINE_BYTE) {
        clearScreen();
      }
      newSerialData[serialCurrentIndex] = char(byte);
      serialCurrentIndex += 1;
      newSerialData[serialCurrentIndex] = '\0';
    }
    if (byte == '@' && !serialPrevByteWasSentinel) {
      serialPrevByteWasSentinel = true;
    } else if (byte == '@' && serialPrevByteWasSentinel) {
      // Erase previous two @s and end message
      serialCurrentIndex -= 1;
      newSerialData[serialCurrentIndex] = '\0';
      serialCurrentIndex -= 1;
      newSerialData[serialCurrentIndex] = '\0';
      serialCurrentIndex = 0;
      serialPrevByteWasSentinel = false;
      strcpy(serialData, newSerialData);
      newSerialData[0] = '\0';
      clearScreen();
      serialDataState = SERIAL_DATA_STATE_FINISHED;
    }
  }
}

int parseColor(char c) {
  switch (c) {
  case 'R':
  case 'r':
    return TFT_RED;
  case 'G':
  case 'g':
    return TFT_GREEN;
  case 'B':
  case 'b':
    return TFT_BLUE;
  case 'P':
  case 'p':
    return TFT_PURPLE;
  case 'Y':
  case 'y':
    return TFT_GOLD;
  case '0':
    return TFT_BLACK;
  case '1':
  case 'W':
  case 'w':
    return TFT_WHITE;
  default:
    return TFT_WHITE;
  }
}

MessageSizeConfig fontConfigs[7] = {
    {&FreeMonoBold12pt7b, 1, 15, 23}, {&FreeMonoBold18pt7b, 1, 23, 15},
    {&FreeMonoBold24pt7b, 1, 30, 11}, {&FreeMonoBold18pt7b, 2, 46, 8},
    {&FreeMonoBold24pt7b, 2, 58, 6},  {&FreeMonoBold18pt7b, 3, 69, 5},
    {&FreeMonoBold24pt7b, 3, 81, 4},
};

int parseInt(char c) { return c - '0'; }
int parseAlignment(char c) {
  switch (c) {
  case 'l':
  case 'L':
    return TL_DATUM;
  default:
    return TC_DATUM;
  }
}

int parseBgDrawer(char c) {
  switch (c) {
  case 'S':
  case 's':
    return DRAW_BG_SQUARE_SIX;
  default:
    return DRAW_BG_SOLID;
  }
}

StyleConfig parseStyle(char *configData) {
  BackgroundConfig bgConfig = {
      parseColor(configData[1]),
      parseColor(configData[2]),
      parseBgDrawer(configData[0]),
  };

  MessageSizeConfig fontConfig = fontConfigs[parseInt(configData[4])];
  int fontColor = parseColor(configData[5]);
  int fontAlignment = parseAlignment(configData[3]);
  return {fontConfig, fontColor, fontAlignment, bgConfig};
}

void loop() {
  manageTouchRotation();
  manageSerialData();

  StyleConfig conf = parseStyle(serialData);
  switch (conf.bgConfig.bgDrawer) {
  case DRAW_BG_SOLID:
    drawBgSolid(conf.bgConfig.bgColor, conf.bgConfig.fgColor);
    break;
  case DRAW_BG_SQUARE_SIX:
    drawBgSquareSix(conf.bgConfig.bgColor, conf.bgConfig.fgColor);
    break;
  }

  drawMessage(serialData, conf.fontConfig.font, conf.fontColor,
              conf.fontConfig.size, conf.fontConfig.height, conf.fontAlignment);

  if (serialDataState == SERIAL_DATA_STATE_INPUTTING) {
    MessageSizeConfig fontConf = fontConfigs[0];
    drawBgSolid(TFT_BLACK, TFT_BLACK);
    drawMessage(newSerialData, 0, fontConf.font, TFT_DARKGREY, fontConf.size,
                fontConf.height, TL_DATUM);
  }

  if (serialDataState == SERIAL_DATA_STATE_FINISHED) {
    drawBgSolidDrawn = false;
  }
}
