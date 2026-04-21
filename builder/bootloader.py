# Copyright 2019-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
from os.path import isfile, join

from SCons.Script import Import, Return

Import("env")

board = env.BoardConfig()
platform = env.PioPlatform()
core = board.get("build.core", "")

target = (
    board.get("build.mcu").lower()
    if board.get("build.mcu", "")
    else env.subst("$BOARD").lower()
)

def get_suitable_optiboot_binary(framework_dir, board_config):
    mcu = board_config.get("build.mcu", "").lower()
    f_cpu = board_config.get("build.f_cpu", "16000000L").upper()
    uart = board_config.get("hardware.uart", "uart0").upper()
    bootloader_led = board_config.get("bootloader.led_pin", "").upper()
    if core == "MightyCore" and board_config.get("build.variant", "") == "bobuino":
        bootloader_led = "B7"
    bootloader_file = "optiboot_flash_%s_%s_%s_%s_%s.hex" % (
        mcu,
        uart,
        board_config.get("bootloader.speed", env.subst("$UPLOAD_SPEED")),
        f_cpu,
        bootloader_led,
    )
    bootloader_path = join(
        framework_dir,
        "bootloaders",
        "optiboot_flash",
        "bootloaders",
        mcu,
        f_cpu,
        bootloader_file,
    )

    if isfile(bootloader_path):
        return bootloader_path

    return bootloader_path.replace(".hex", "_BIGBOOT.hex")


def get_suitable_urboot_binary(framework_dir, board_config):
    mcu = board_config.get("build.mcu", "").lower()
    f_cpu = int(board_config.get("build.f_cpu", "16000000L").strip("UL"))
    oscillator = board_config.get("hardware.oscillator", "external").lower()
    bootloader_speed = board_config.get("bootloader.speed", env.subst("$UPLOAD_SPEED"))

    if core == "MicroCore":
        bootloader_file = "urboot_attiny13a.hex"
        bootloader_led = board_config.get("bootloader.led_pin", "no-led").lower()
        f_cpu_error = float(board_config.get("hardware.f_cpu_error", "0.0"))
        uart_pins = board_config.get("bootloader.uart_pins", "swio_rxb1_txb0").lower()
        if oscillator == "internal":
            clock_speed = f_cpu + int(f_cpu_error / 100 * f_cpu)
        else:
            clock_speed = f_cpu

        bootloader_path = join(
            framework_dir,
            "bootloaders",
            "urboot",
            "watchdog_1_s",
            "%s_oscillator" % oscillator,
            "%d_hz" % clock_speed,
            "%s_baud" % bootloader_speed,
            uart_pins,
            bootloader_led,
            bootloader_file,
        )

        if -10.00 > f_cpu_error > 10.00 or f_cpu_error % 1.25 != 0.0:
            sys.stderr.write(
                "Error: invalid f_cpu factor %.2f. Must me in steps of ±1.25 and within ±10.00\n"
                % f_cpu_error
            )
            env.Exit(1)

    elif core in ("MightyCore", "MegaCore", "MiniCore", "MajorCore"):
        bootloader_file = "urboot_%s_pr_ee_ce.hex" % mcu
        user_led = board_config.get("bootloader.led_pin", "no-led").lower()
        if(user_led != "no-led"):
            bootloader_led = "led+%s" % board_config.get("bootloader.led_pin", "").lower()
        else:
            bootloader_led = "no-led"
        uart = board_config.get("hardware.uart", "uart0").lower()
        uart_pins = board_config.get("bootloader.%s_pins" % uart, "")

        # UART2 and UART3 on the ATmega640/1280/2560 don't have autobaud support
        if mcu in ("atmega640", "atmega1280", "atmega2560") and uart in ("uart2", "uart3"):
            bootloader_path = join(
                framework_dir,
                "bootloaders",
                "urboot",
                mcu,
                "watchdog_1_s",
                "%s_oscillator" % oscillator,
                "%d_hz" % f_cpu,
                "%s_baud" % bootloader_speed,
                uart_pins,
                bootloader_led,
                bootloader_file,
            )
        else:
            bootloader_path = join(
                framework_dir,
                "bootloaders",
                "urboot",
                mcu,
                "watchdog_1_s",
                "autobaud",
                uart_pins,
                bootloader_led,
                bootloader_file,
            )

    else:
        sys.stderr.write(
            "Error: Urboot support is not implemented for target %s and core %s\n"
            % (mcu, core)
        )
        env.Exit(1)

    return bootloader_path


framework_dir = ""
if env.get("PIOFRAMEWORK", []):
    framework_dir = platform.get_package_dir(
        platform.frameworks[env.get("PIOFRAMEWORK")[0]]["package"]
    )

if core != "TinyCore":
    bootloader_path = board.get("bootloader.file", "")
    bootloader_type = None
    if core in ("MiniCore", "MegaCore", "MightyCore", "MajorCore", "MicroCore"):
        if not isfile(bootloader_path):
            bootloader_type = board.get("bootloader.type", "urboot").lower()
            if bootloader_type == "urboot" or core == "MicroCore":
                bootloader_path = get_suitable_urboot_binary(framework_dir, board)
            else:
                bootloader_path = get_suitable_optiboot_binary(framework_dir, board)
    else:
        if not isfile(bootloader_path):
            bootloader_path = join(framework_dir, "bootloaders", bootloader_path)

        if not board.get("bootloader", {}):
            sys.stderr.write("Error: missing bootloader configuration!\n")
            env.Exit(1)

    if not isfile(bootloader_path):
        sys.stderr.write("Error: Couldn't find bootloader image %s\n" % bootloader_path)
        env.Exit(1)

    print("Using bootloader image:\n%s" % bootloader_path)

    fuses_action = env.SConscript("fuses.py", exports="env")

    if bootloader_type in ("no_bootloader", "urboot"):
        lock_bits = board.get("bootloader.lock_bits", "0xFF")
        unlock_bits = board.get("bootloader.unlock_bits", "0xFF")
    else:
        lock_bits = board.get("bootloader.lock_bits", "0x0F")
        unlock_bits = board.get("bootloader.unlock_bits", "0x3F")

    env.Replace(
        BOOTUPLOADER="avrdude",
        BOOTUPLOADERFLAGS=[
            "-p",
            "$BOARD_MCU",
            "-C",
            join(env.PioPlatform().get_package_dir("tool-avrdude") or "", "avrdude.conf"),
        ],
        BOOTFLAGS=['-Uflash:w:%s:i' % bootloader_path, "-Ulock:w:%s:m" % lock_bits],
        UPLOADBOOTCMD="$BOOTUPLOADER $BOOTUPLOADERFLAGS $UPLOAD_FLAGS $BOOTFLAGS",
    )

else: # TinyCore
    if board.get("bootloader.type", "no_bootloader").lower() == "no_bootloader":
        sys.stderr.write("Error: No bootloader specified in platformio.ini - use board_bootloader.type = urboot\n")
        env.Exit(1)

    fuses_action = env.SConscript("fuses.py", exports="env")
    bootloader_led = board.get("bootloader.led_pin", "noled").lower()
    f_cpu = int(board.get("build.f_cpu", "").strip("UL"))
    lock_bits = board.get("bootloader.lock_bits", "0xFF")
    unlock_bits = board.get("bootloader.unlock_bits", "0xFF")

    no_hw_uart = (
        "attiny25", "attiny45", "attiny85",
        "attiny24", "attiny44", "attiny84",
        "attiny261", "attiny461", "attiny861",
        "attiny48", "attiny88",
        "attiny43", "attiny43u",
        "attiny26"
    )
    if target in no_hw_uart:
        def format_f_cpu(f_cpu):
            v = int(str(f_cpu))
            return f"{v/1000000:g}MHz" if v >= 1000000 else f"{v/1000:g}kHz"

        def osc_comp(x):
            if not (-10 <= x <= 10) or (x * 100) % 125 != 0:
                sys.stderr.write("Error: invalid f_cpu factor %.2f. Must be in steps of ±1.25 and within ±10.00\n" % x)
                env.Exit(1)
            return chr(ord('a') + int(round((x + 10) / 1.25)))
        
        uart_pins = board.get("bootloader.uart_pins", "")
        baudrate = board.get("bootloader.speed", "")
        f_cpu_error = float(board.get("hardware.f_cpu_error", "0.0"))
        urboot_str = f"-Uurboot:1s_pr_{bootloader_led}_{uart_pins}_{baudrate}baud_{osc_comp(f_cpu_error)}{format_f_cpu(f_cpu)}"
    else:
        uart = board.get("hardware.uart", "uart0").lower()
        urboot_str = f"-Uurboot:1s_pr_{bootloader_led}_autobaud_{uart}"

    env.Replace(
        BOOTUPLOADER="avrdude",
        BOOTUPLOADERFLAGS=[
            "-p",
            "$BOARD_MCU",
            "-C",
            join(env.PioPlatform().get_package_dir("tool-avrdude") or "", "avrdude.conf"),
        ],
        BOOTFLAGS=['%s' % urboot_str, "-Ulock:w:%s:m" % lock_bits],
        UPLOADBOOTCMD="$BOOTUPLOADER $BOOTUPLOADERFLAGS $UPLOAD_FLAGS $BOOTFLAGS",
    )


if env.subst("$UPLOAD_PROTOCOL") != "custom":
    env.Append(BOOTUPLOADERFLAGS=["-c", "$UPLOAD_PROTOCOL"])
else:
    print(
        "Warning: The `custom` upload protocol is used! The upload and fuse flags may "
        "conflict!\nMore information: "
        "https://docs.platformio.org/en/latest/platforms/atmelavr.html"
        "#overriding-default-bootloader-command\n"
    )

bootloader_actions = [
    fuses_action,
    env.VerboseAction("$UPLOADBOOTCMD", "Uploading bootloader"),
]

Return("bootloader_actions")
