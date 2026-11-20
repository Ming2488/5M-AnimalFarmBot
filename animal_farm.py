import ctypes
import sys
import threading
import time
from collections import namedtuple
from ctypes import wintypes
from pathlib import Path

# ต้องตั้งก่อนอย่างอื่น: ให้พิกัดเป็นพิกเซลจริงทุกจอ (กันคลิกเพี้ยนเวลามีหลายจอ/ซูม Windows)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import cv2
import keyboard
import numpy as np
from PIL import Image, ImageGrab

user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None

if user32 is not None:
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

# ==============================
# SETTINGS
# ==============================

BASE_DIR = Path(__file__).resolve().parent

BUY = str(BASE_DIR / "animal_buy_button.png")
FEED = str(BASE_DIR / "animal_feed_button.png")
COLLECT = str(BASE_DIR / "animal_collect_button.png")

BUY_CONFIDENCE = 0.75
CONFIDENCE = 0.88

CHECK_INTERVAL = 0.5

# ความเร็ว (หน่วยวินาที) ยิ่งน้อยยิ่งเร็ว ถ้าเกมเริ่มคลิกพลาดให้เพิ่มกลับ
CLICK_SETTLE = 0.02          # รอหลังเลื่อนเมาส์ไปที่ปุ่ม ก่อนกด
CLICK_HOLD = 0.02            # ระยะกดค้าง
AFTER_CLICK = 0.02           # รอหลังปล่อยเมาส์
BUY_WAIT = 0.2               # รอหลังกดซื้อแต่ละครั้ง ก่อนหาปุ่มซื้ออีกรอบ
CONFIRM_INTERVAL = 0.02      # เช็กว่าปุ่มหายหลังคลิกทุกกี่วินาที
FULL_SCAN_INTERVAL = 0.3     # สแกนทั้งหน้าต่างทุกกี่วินาที (ช้า ~0.3 วิ/ปุ่ม) ที่เหลือเช็กแค่จุดเดิม

AUTO_BUY = True              # False = ไม่ซื้อให้ (คุณซื้อเอง) บอทจะรอให้อาหาร/เก็บอย่างเดียว
IDLE_LIMIT = 45              # รอปุ่มให้อาหาร/เก็บสูงสุดกี่วินาที ถ้าไม่มีอะไรขึ้นเลยก็จบรอบ

OPEN_MENU_KEY = "h"          # ปุ่มเปิดเมนูฟาร์มในเกม
START_DELAY = 8              # วินาทีที่ให้คลิกกลับเข้าเกมหลังกด START

# ปุ่มลัดของบอท ใช้ Ctrl+Alt+ตัวอักษร จะได้ไม่ทับปุ่มในเกม
KEY_START = "ctrl+a"
KEY_STOP = "ctrl+s"
KEY_TEST = "ctrl+d"      # ทดสอบว่าหาปุ่มเจอไหม (ไม่คลิกอะไร)

# บอทจะค้นหาปุ่มเฉพาะ "หน้าต่างที่คุณคลิกค้างไว้ตอนครบ START_DELAY"
# ถ้าไม่ใช่หน้าต่างเกม (ชื่อไม่มีคำเหล่านี้) บอทจะไม่คลิกอะไรเลย
CHECK_GAME_TITLE = True
GAME_TITLE_KEYWORDS = ["fivem", "grand theft auto", "gta"]

stop_event = threading.Event()
running = False
GAME_RECT = None             # (left, top, width, height) ของหน้าต่างเกม

Box = namedtuple("Box", "left top width height")


# ==============================
# BASIC FUNCTIONS
# ==============================

def log(msg):
    print("[BOT]", msg, flush=True)


def wait(seconds):
    return not stop_event.wait(seconds)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def foreground_window():
    """คืนค่า (ชื่อหน้าต่าง, (left, top, width, height)) ของหน้าต่างที่ active อยู่"""
    hwnd = user32.GetForegroundWindow()
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value, (rect.left, rect.top,
                       rect.right - rect.left, rect.bottom - rect.top)


# ---- ส่งปุ่มแบบ scan code (เกมส่วนใหญ่รับแบบนี้) ----

SCAN_CODES = {
    "esc": 0x01, "enter": 0x1C, "space": 0x39,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14,
    "y": 0x15, "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22,
    "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30,
    "n": 0x31, "m": 0x32,
}

PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", InputUnion)]


KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002


def _send_scan(scan, up=False):
    extra = ctypes.c_ulong(0)
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    ii = InputUnion()
    ii.ki = KeyBdInput(0, scan, flags, 0, ctypes.pointer(extra))
    x = Input(1, ii)
    user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


def press_key(key, hold=0.08):
    scan = SCAN_CODES.get(key.lower())

    if scan is None or user32 is None:
        keyboard.send(key)
        return

    _send_scan(scan)
    time.sleep(hold)
    _send_scan(scan, up=True)


# ---- เมาส์ (ทำเอง ใช้ได้ทุกจอ ไม่โดนจำกัดแค่จอหลัก) ----

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def click_box(box):
    if stop_event.is_set():
        return

    x = box.left + box.width // 2
    y = box.top + box.height // 2

    # FAILSAFE: ถ้าเมาส์อยู่มุมซ้ายบนสุดของจอหลัก ให้หยุดบอททันที
    cx, cy = cursor_pos()
    if cx <= 2 and cy <= 2:
        stop_event.set()
        log("FAILSAFE: เมาส์อยู่มุมซ้ายบน -> หยุดบอท")
        return

    # ถ้าเมาส์อยู่ที่ปุ่มอยู่แล้ว (เช่น กดซื้อซ้ำที่เดิม) ไม่ต้องขยับ
    if (cx, cy) != (x, y):
        user32.SetCursorPos(x + 2, y)
        time.sleep(0.01)
        user32.SetCursorPos(x, y)
        time.sleep(CLICK_SETTLE)

    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(CLICK_HOLD)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(AFTER_CLICK)


# ---- หารูปบนหน้าจอ (ค้นเฉพาะในหน้าต่างเกม ทุกจอ) ----
# จับคู่แบบ "สี" (ไม่ใช่ขาวดำ) เพราะปุ่มให้อาหาร(ส้ม)กับปุ่มเก็บ(เขียว)
# พอเป็นขาวดำแล้วหน้าตาคล้ายกันมาก จะสับสนกัน

_templates = {}


# ตัดขอบรูปปุ่มทิ้งกี่พิกเซล (ขอบมนของปุ่มซื้อมีสีพื้นหลังติดมา ทำให้คะแนนตก)
CROP_EDGE = {BUY: 6}


def load_template(path):
    if path not in _templates:
        tpl = cv2.cvtColor(
            np.array(Image.open(path).convert("RGB")), cv2.COLOR_RGB2BGR)
        c = CROP_EDGE.get(path, 0)
        if c:
            tpl = tpl[c:-c, c:-c]
        _templates[path] = np.ascontiguousarray(tpl)
    return _templates[path]


def grab_screen(region):
    left, top, w, h = region
    im = ImageGrab.grab(
        bbox=(left, top, left + w, top + h),
        all_screens=True
    )
    return cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR)


def _match(image, region, screen=None):
    """คืน (ตารางคะแนน, กว้างปุ่ม, สูงปุ่ม, region) หรือ None
    screen = ภาพที่แคปไว้แล้วของ GAME_RECT (ใช้ซ้ำเพื่อประหยัดเวลา)"""
    if region is None:
        region = GAME_RECT

    if region is None:
        return None

    tpl = load_template(image)
    th, tw = tpl.shape[:2]

    if region[2] < tw or region[3] < th:
        return None

    if screen is None or region is not GAME_RECT:
        screen = grab_screen(region)

    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    return res, tw, th, region


def find_one(image, region=None, confidence=CONFIDENCE, screen=None):
    if stop_event.is_set():
        return None

    m = _match(image, region, screen)

    if m is None:
        return None

    res, tw, th, region = m
    _, best, _, loc = cv2.minMaxLoc(res)

    if best < confidence:
        return None

    return Box(region[0] + loc[0], region[1] + loc[1], tw, th)


def find_all(image, confidence=CONFIDENCE, region=None, screen=None):
    if stop_event.is_set():
        return []

    m = _match(image, region, screen)

    if m is None:
        return []

    res, tw, th, region = m
    ys, xs = np.where(res >= confidence)

    candidates = sorted(
        zip(res[ys, xs].tolist(), xs.tolist(), ys.tolist()),
        reverse=True
    )[:500]

    accepted = []

    for score, x, y in candidates:
        if all(abs(x - ax) >= tw // 2 or abs(y - ay) >= th // 2
               for ax, ay in accepted):
            accepted.append((x, y))

    boxes = [Box(region[0] + x, region[1] + y, tw, th) for x, y in accepted]
    return sorted(boxes, key=lambda b: (b.top, b.left))


_last_box = {}


def find_fast(image, confidence=CONFIDENCE, full=True, screen=None):
    """เช็กรอบๆ จุดที่เจอปุ่มครั้งก่อนก่อน (เร็วมาก) ถ้าไม่เจอค่อยสแกนทั้งหน้าต่าง"""
    last = _last_box.get(image)

    if last is not None:
        region = (last.left - 20, last.top - 20,
                  last.width + 40, last.height + 40)
        box = find_one(image, region, confidence)

        if box is not None:
            _last_box[image] = box
            return box

    if not full:
        return None

    box = find_one(image, None, confidence, screen)

    if box is not None:
        _last_box[image] = box

    return box


def wait_until_missing(image, region=None, timeout=15,
                       confidence=CONFIDENCE):
    end = time.time() + timeout

    while time.time() < end:
        if stop_event.is_set():
            return False

        if find_one(image, region, confidence) is None:
            return True

        wait(CONFIRM_INTERVAL)

    return False


# ==============================
# TEST MODE - ไม่คลิกอะไรทั้งนั้น
# ==============================

def test_screen():
    title, rect = foreground_window()
    log(f"TEST: หน้าต่างที่ active = '{title}'  ตำแหน่ง/ขนาด = {rect}")

    ImageGrab.grab(all_screens=True).save(
        str(BASE_DIR / "debug_all_screens.png"))

    if rect[2] > 0 and rect[3] > 0:
        left, top, w, h = rect
        ImageGrab.grab(
            bbox=(left, top, left + w, top + h), all_screens=True
        ).save(str(BASE_DIR / "debug_window.png"))

    for name, path, need in (
        ("BUY", BUY, BUY_CONFIDENCE),
        ("FEED", FEED, CONFIDENCE),
        ("COLLECT", COLLECT, CONFIDENCE),
    ):
        m = _match(path, rect)

        if m is None:
            log(f"TEST {name}: หน้าต่างเล็กกว่ารูปปุ่ม ค้นไม่ได้")
            continue

        res, tw, th, _ = m
        _, best, _, loc = cv2.minMaxLoc(res)
        verdict = "FOUND" if best >= need else "NOT FOUND"
        log(f"TEST {name}: คะแนนสูงสุด {best:.2f} "
            f"(ต้อง >= {need}) -> {verdict}")

    log("TEST: เปิด debug_window.png / debug_all_screens.png ดูว่าเป็นภาพเกมจริงไหม "
        "(ถ้าดำ = เกมเป็น Fullscreen ให้เปลี่ยนเป็น Borderless)")


def test_thread():
    try:
        test_screen()
    except Exception as e:
        log(f"TEST ERROR: {e!r}")


# ==============================
# 1. BUY UNTIL NO BUTTON
# ==============================

def buy_animals():
    log("BUY START")

    count = 0
    missing = 0

    while not stop_event.is_set():

        button = find_fast(BUY, BUY_CONFIDENCE)

        if stop_event.is_set():
            break

        if button is None:
            missing += 1
            log(f"BUY NOT FOUND {missing}/3")

            if missing >= 3:
                break

            wait(0.2)
            continue

        missing = 0

        log("BUY BUTTON FOUND")
        click_box(button)

        if stop_event.is_set():
            break

        count += 1
        log(f"BUY CLICKED: {count}")

        # รอเกมประมวลผลก่อนค้นหาปุ่มอีกครั้ง
        if not wait(BUY_WAIT):
            break

    log(f"BUY FINISHED: {count} CLICKS")


# ==============================
# 2. FEED + COLLECT LOOP (รอปุ่มจนกว่าจะไม่มีอะไรขึ้นอีก)
# ==============================

def farm_loop():
    log("FEED/COLLECT LOOP START")

    feeds = 0
    collects = 0
    unconfirmed = 0

    last_full = 0.0
    last_activity = time.time()
    last_report = 0

    while not stop_event.is_set():

        found = None

        # 1) เช็กจุดเดิมก่อน (เร็ว) ลำดับ: เก็บของก่อน แล้วค่อยให้อาหาร
        for name, image in (("COLLECT", COLLECT), ("FEED", FEED)):
            box = find_fast(image, full=False)

            if box is not None:
                found = (name, image, box)
                break

        # 2) ไม่เจอจุดเดิม -> สแกนทั้งหน้าต่าง (ช้ากว่า เลยทำเป็นช่วงๆ)
        if found is None and time.time() - last_full >= FULL_SCAN_INTERVAL:
            screen = grab_screen(GAME_RECT)

            for name, image in (("COLLECT", COLLECT), ("FEED", FEED)):
                box = find_fast(image, screen=screen)

                if box is not None:
                    found = (name, image, box)
                    break

            last_full = time.time()

        if found is None:
            idle = time.time() - last_activity

            if idle >= IDLE_LIMIT:
                log("ไม่มีปุ่มขึ้นมานานแล้ว -> จบรอบ")
                break

            if idle - last_report >= 10:
                last_report = int(idle)
                log(f"WAITING FOR BUTTON... {int(idle)}/{IDLE_LIMIT}s")

            wait(0.05)
            continue

        name, image, target = found

        region = (
            target.left - 30,
            target.top - 30,
            target.width + 60,
            target.height + 60
        )

        log(f"{name} BUTTON FOUND")
        click_box(target)

        if stop_event.is_set():
            break

        if name == "COLLECT":
            collects += 1
            log(f"COLLECT CLICKED: {collects}")
        else:
            feeds += 1
            log(f"FEED CLICKED: {feeds}")

        # คลิกแล้วปุ่มต้องหายไป ถ้าไม่หาย = เกมอาจไม่รับคลิก
        if wait_until_missing(image, region, timeout=10):
            unconfirmed = 0
        else:
            if stop_event.is_set():
                break

            unconfirmed += 1
            log(f"{name} คลิกแล้วปุ่มไม่หาย ({unconfirmed}/3)")

            if unconfirmed >= 3:
                log("คลิก 3 ครั้งติดแล้วปุ่มไม่หาย -> เกมอาจไม่รับคลิกจากบอท "
                    "(ลองรันแบบ Administrator / ตั้งเกมเป็น Borderless)")
                stop_event.set()
                break

        last_activity = time.time()
        last_report = 0

    log(f"LOOP FINISHED: FEED {feeds} / COLLECT {collects}")


# ==============================
# MAIN BOT
# ==============================

def run_bot():
    global running, GAME_RECT

    try:
        log(f"START IN {START_DELAY} SECONDS")
        log("PLEASE CLICK FIVE M GAME WINDOW NOW")

        if not wait(START_DELAY):
            return

        title, rect = foreground_window()
        log(f"ACTIVE WINDOW: '{title}'  {rect}")

        if CHECK_GAME_TITLE and not any(
                k in title.lower() for k in GAME_TITLE_KEYWORDS):
            log("หน้าต่างที่ active ไม่ใช่เกม -> ยกเลิก (ไม่คลิกอะไร)")
            log("ให้คลิกที่หน้าต่างเกมหลังกด START "
                "หรือแก้ GAME_TITLE_KEYWORDS / CHECK_GAME_TITLE ด้านบนไฟล์")
            return

        GAME_RECT = rect

        menu_open = any(
            find_one(img, confidence=conf) is not None
            for img, conf in ((BUY, BUY_CONFIDENCE),
                              (FEED, CONFIDENCE),
                              (COLLECT, CONFIDENCE))
        )

        if menu_open:
            log("เมนูฟาร์มเปิดอยู่แล้ว -> ไม่กดปุ่มเปิดเมนูซ้ำ (กันมันปิด)")
        else:
            log(f"SENDING {OPEN_MENU_KEY.upper()} TO ACTIVE WINDOW")
            press_key(OPEN_MENU_KEY)
            log("KEY SENT - WAITING FOR FARM MENU")

            if not wait(3):
                return

        if AUTO_BUY:
            buy_animals()

        if not stop_event.is_set():
            farm_loop()

        if stop_event.is_set():
            log("BOT STOPPED")
        else:
            log("CYCLE FINISHED")

    except Exception as e:
        log(f"ERROR: {e!r}")

    finally:
        running = False
        log("BOT READY")


# ==============================
# START / STOP
# ==============================

def start():
    global running

    log(f"{KEY_START.upper()} PRESSED")

    if running:
        log("BOT ALREADY RUNNING")
        return

    stop_event.clear()
    running = True

    threading.Thread(target=run_bot, daemon=True).start()


def stop():
    if stop_event.is_set():
        return

    stop_event.set()
    log("STOP REQUESTED")


def test():
    threading.Thread(target=test_thread, daemon=True).start()


# ==============================
# PROGRAM START
# ==============================

if __name__ == "__main__":

    missing_images = [
        image for image in [BUY, FEED, COLLECT]
        if not Path(image).exists()
    ]

    if missing_images:
        print("MISSING IMAGES:")
        for image in missing_images:
            print(image)

        input("Press Enter to exit...")
        raise SystemExit

    print("==============================")
    print("  FIVE M ANIMAL FARM BOT")
    print("==============================")
    print(f"{KEY_START.upper()} = START")
    print(f"{KEY_STOP.upper()} = STOP")
    print("ESC = STOP")
    print(f"{KEY_TEST.upper()} = TEST (หาปุ่มเจอไหม ไม่คลิก)")
    print("FAILSAFE = MOVE MOUSE TOP LEFT (จอหลัก)")
    print("==============================")

    if not is_admin():
        print("[WARN] ไม่ได้รันแบบ Administrator -> ถ้า FiveM รันแบบ admin")
        print("[WARN] บอทจะกดปุ่ม/คลิกเข้าเกมไม่ได้ (Windows บล็อก)")

    keyboard.add_hotkey(KEY_START, start)
    keyboard.add_hotkey(KEY_STOP, stop)
    keyboard.add_hotkey(KEY_TEST, test)

    log("READY - รอกดปุ่ม")

    keyboard.wait()
