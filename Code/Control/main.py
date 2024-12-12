# FireFightPico2.py
# <CopyrightNotice>
# Copyright 2024 @barsteward
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.
# Note that this is very much a work-in-progress, thrown together in the few weeks prior to BSides London 2024 for a demo during my talk.
# The code is not well structured and could benefit from use of classes and generally being more pythonic, but it's working well enough for the demo, 
# so please submit a pull request if you refactor.
# This code imports phoenixAES and aeskeyschedule, to which I have made minor modifications to work in micropython, by removing dependency on enum, typing, and functools.
# </CopyrightNotice>
# @TODO: Too many global variables - create a Glitcher class instead!

from machine import UART, Pin, Timer, unique_id, reset
import time, utime
import select
import sys
from machine import mem32, mem16, mem8
import os
from machine import WDT
import micropython
import rp2
from machine import RTC
import random
import phoenixAES
from aeskeyschedule import reverse_key_schedule

# Watchdog Timer
#  This just uses a global object currently
# Set Watchdog Timer timeout in ms
#   1000ms is the minimum
#   8300ms is the maximum
#   Set to None to not set the WDT
wdt = None
Exception_trace = 0


# <Table>
# Configure pin usage and inter-Pi connections for the FIreFIght Mini v0.1 board (with table to show required jumper settings)
# -------------------------------------+-----------------------------------+-----------------------------------------+------------------------+
#           "Control" Pi Pico          |    First Board Jumper Required    |      Second Board Jumper Required       |    "Victim" Pi Pico    | 
# -------------------------------------+-----------------------------------+-----------------------------------------+------------------------+
#   Label           | GP# |   Pin  |Dir| Hdr|  Label  | No.|  Schematic ref| Hdr|     Label     | No.|  Schematic    | Connection |   Pin     |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_VICTIM_SWCLK     =  2  # Pin 4  |  O| P5 |  SWCLK  | -  | P5.5  - P5.6  | -  |       -       |    |       -       |   SWCLK    | Pi:J2.1   |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_VICTIM_SWDIO     =  3  # Pin 5  |I/O| P5 |  SWDIO  | -  | P5.1  - P5.2  | -  |       -       |    |       -       |   SWDIO    | Pi:J2.3   |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_VICTIM_GP1       =  6  # Pin 9  |I/O| J2 |   GP1   | 2  | J2.3  - J2.4  | -  |       -       | -  |       -       |    GP1     | Pi:Pin 2  |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_VICTIM_GP0       =  7  # Pin 10 |I/O| J2 |   GP0   | 1  | J2.1  - J2.2  | -  |       -       | -  |       -       |    GP0     | Pi:Pin 1  |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_UART0_TX         =  12 # Pin 16 |  O| J2 |   GP13  | 17 | J2.33 - J2.34 | -  |       -       | -  |       -       |   GP13     | Pi:Pin 17 |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_UART0_RX         =  13 # Pin 17 |I  | J2 |   GP12  | 16 | J2.31 - J2.32 | -  |       -       | -  |       -       |   GP12     | Pi:Pin 16 |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_LED_RED          =  14 # Pin 19 |  O| -  |    -    | -  |       -       | -  |       -       | -  |       -       |     -      |     -     |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_LED_GREEN        =  15 # Pin 20 |  O| -  |    -    | -  |       -       | -  |       -       | -  |       -       |     -      |     -     |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_LED_BLUE         =  16 # Pin 21 |  O| -  |    -    | -  |       -       | -  |       -       | -  |       -       |     -      |     -     |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_VICTIM_PWR       =  20 # Pin 26 |  O| J1 |  3V3_EN | -  | J1.1  - J1.2  | J8 |     3V3_EN    | 37 | J8.7  - J8.8  |   3V3_EN   | Pi:Pin 37 |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_GLITCH           =  21 # Pin 27 |  O| J6 |    -    | -  | J6.1  - J6.2  | J11| Wire on underside to Victim Pi:TP7 |  TP7 (1v1) | Pi:TP7    |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_VICTIM_RUN       =  22 # Pin 29 |I/O| J8 |   RUN   | 30 | J8.21 - J8.22 | -  |       -       | -  |       -       |    RUN     | Pi:Pin 30 |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_PICO_LED         =  25 # On Pico|  O| -  |    -    | -  |       -       | -  |       -       | -  |       -       |     -      |     -     |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_VICTIM_TRIG      =  26 # Pin 31 |I/O| J8 |   GP26  | 31 | J8.19 - J8.20 | -  |       -       | -  |       -       |    GP26    | Pi:Pin 31 |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
GP_EXT_TRIGGER_OUT  =  28 # Pin 34 |  O| -  |    -    | -  |       -       | -  |       -       | -  |       -       |(J12 Output)|     -     |
# ------------------+-----+--------+---+----+---------+----+---------------+----+---------------+----+---------------+------------+-----------+
# Default jumper settings: * indicates fitted jumper.
# ==============================================================
# J2 Left side of Victim Pico. (Left side is odd header pins numbers, right side is even):
# ==============================================================
#  J2.1-2:   "GP0" Do not fit
#  J2.3-4:   "GP1" Do not fit
# *J2.5-6:   "GND" Fit Jumper
#  J2.7-8:   "GP2" Do not fit
#  J2.9-10:  "GP3" Do not fit
# ____________________________
#  J2.11-12: "GP4" Do not fit
#  J2.13-14: "GP5" Do not fit
# *J2.15-16: "GND" Fit Jumper
#  J2.17-18: "GP6" Do not fit
#  J2.19-20: "GP7" Do not fit
# ____________________________
#  J2.21-22: "GP8"  Do not fit
#  J2.23-24: "GP9"  Do not fit
# *J2.25-26: "GND"  Fit Jumper
#  J2.27-28: "GP10" Do not fit
#  J2.29-30: "GP11" Do not fit
# ____________________________
# *J2.31-32: "GP12" Fit Jumper (Connects Victim UART0 Tx to Control UART0 Rx)
# *J2.33-34: "GP13" Fit Jumper (Connects Victim UART0 Rx to Control UART0 Tx)
# *J2.35-36: "GND"  Fit Jumper
# *J2.37-38: "GP14" Fit Jumper (GP14 Red LED)
# *J2.39-40: "GP15" Fit Jumper (GP15 Green LED)
# ___________________________________________________________________________
# 
# ============================================================================
# J8 (Left side is odd header pins numbers, right side is even):
# ============================================================================
#  J8.1-2:   "VBUS"     Do not fit
# *J8.3-4:   "VSYS"     Fit Jumper (Connects Victim VSYS to Control VSYS, via VSYS Bridge Jumper)
# *J8.5-6:   "GND"      Fit Jumper
# *J8.7-8:   "3V3_EN"   Fit Jumper (Connects Control GP20, via J1, to Victim 3V3_EN)
#  J8.9-10:  "3V3"      Do not fit
# ____________________________
#  J8.11-12: "ADC_VREF" Do not fit 
#  J8.13-14: "GP28"     Do not fit
# *J8.15-16: "AGND"     Fit Jumper
#  J8.17-18: "GP27"     Do not fit
# *J8.19-20: "GP26"     Fit Jumper (Victim Trigger, connects Victim GP26 to Control GP26)
# ____________________________
# *J8.21-22: "RUN"      Fit jumper (Connects Control GP22 to Victim RUN)
#  J8.23-24: "GP22"     Do not fit
# *J8.25-26: "GND"      Fit jumper
#  J8.27-28: "GP21"     Do not fit
#  J8.29-30: "GP20"     Do not fit
# ____________________________
#  J8.31-32: "GP19"     Do not fit
#  J8.33-34: "GP18"     Do not fit
# *J8.35-36: "GND"      Fit jumper
#  J8.37-38: "GP17"     Do not fit
# *J8.39-40: "GP16"     Fit jumper (Connects Victim GP16 to Blue LED)
# ============================================================================
# Other Jumpers
# ============================================================================
# *J1: "3V3 EN"        Fit after programming Victim (Connects Control GP20 to Victim )
# *J3  "Reset Control" Fit Jumper (Connects Control GP22 to Victim RUN)                                                                                                                                      
# *J4: "VSYS Bridge"   Fit Jumper (Connects Control VSYS to Victim VSYS)
# *J6: "J6"            Fit Jumper (Connects MOSFET output to pad on back of PCB, which should be connected to Victim TP7)
# ============================================================================
# Optional
#   Consider adding:
#     Pull-ups to GP12/GP13 to avoid UART seeing noise when not driven (will work without when Control and Victim both configure pins as UART)
#           [Note that P2 has 2 pull up and 2 pull downs]
#   100 ohm resistors instead of jumpers on P5 for SWCLK and SWDIO
#   Schottky diode instead of jumper on J4 for VSYS bridge to protect against different voltage levels 
# </Table>

# UART Port0 Configuration
UART0_BAUD_RATE = 115200
UART0_DATA_BITS = 8
UART0_PARITY    = None
UART0_STOP_BITS = 1

# Globals
PADS_BANK0_BASE = 0x40038000 # For Pi Pico2
PICO_LED = Pin(GP_PICO_LED, Pin.OUT)
LED_RED = Pin(GP_LED_RED, Pin.OUT, Pin.PULL_UP)
LED_GREEN = Pin(GP_LED_GREEN, Pin.OUT, Pin.PULL_UP)
LED_BLUE = Pin(GP_LED_BLUE, Pin.OUT, Pin.PULL_UP)

EXT_TRIGGER_OUT = Pin(GP_EXT_TRIGGER_OUT, Pin.OUT, value = 0)
GLITCH = Pin(GP_GLITCH, Pin.OUT, value = 0)
VICTIM_RUN = Pin(GP_VICTIM_RUN, Pin.OUT)    # Target Reset as output
VICTIM_RUN.value(0)                         # Hold Reset low
VICTIM_PWR = Pin(GP_VICTIM_PWR, Pin.OUT)    # GP_VICTIM_PWR (connects to Target 3V3_EN) as output
VICTIM_PWR.value(0)                         # 3V3 Off

LED_Timer = Timer()
StateMachineStatus=[0] * 12
SM0 = None
ClockFreq_MHz = 150.0
ClockDuration_ns = 1/ClockFreq_MHz*1000
MinimumDelayOffset_ns = 40
MinimumDelayOffset_clocks = round(MinimumDelayOffset_ns/ClockDuration_ns)
GlitchLength_clocks = 30
GlitchDelay_ns = 61953 # Was MinimumDelayOffset_ns but let's set to something with a chance of success
GlitchLength_ns = 513  # Was GlitchLength_clocks*ClockDuration_ns but let's set to something with a chance of success
GlitchDelay_clocks = round((GlitchDelay_ns-MinimumDelayOffset_ns)/ClockDuration_ns)
InputTriggerLevel = 1
GlitchOutputLevel = 1
LastException = None
LastExceptionTime = None
GlitchFiredOutput = 0x07  # bit 0='~', bit 1=Victim UART Data, bit 2=Reset Victim
VictimReadData = bytearray()
FaultyCiphertexts = []
SavedGlitchParameters = []
FaultyCiphertextGroups = []
RoundKeyPercentageFound = 0
R10KeyRecoveryAttempt  = '................................'
BaseKey             = '................................'
BaseKeyHexString = ""
GroupCount = [0]*4
GroupAttempts = 0
Results_red = 0
Results_green = 0
Results_orange = 0
Results_grey = 0
Results_cyan = 0

IntenseRed="\033[0;91m"         # Red
IntenseGreen="\033[0;92m"       # Green
IntenseCyan="\033[0;96m"        # Cyan
IntenseOrange="\x1B[38;5;216m"  # Orange
IntenseGrey="\033[0;37m"        # Grey
White="\033[1;37m"              # White
# Open UART0; USB-CDC port already available on stdin/out
uart0 = UART(0, baudrate=UART0_BAUD_RATE, tx=Pin(GP_UART0_TX), rx=Pin(GP_UART0_RX), bits=UART0_DATA_BITS, parity=UART0_PARITY, stop=UART0_STOP_BITS)

# Define a PIO function for waiting for input trigger L->H, then outputing a timed low pulse after specified delay
@rp2.asm_pio(set_init=(rp2.PIO.OUT_HIGH, rp2.PIO.IN_LOW), sideset_init=(rp2.PIO.OUT_HIGH, rp2.PIO.IN_HIGH))
def LowGlitchOutputOnLowToHighTriggerInput(): 
    set(pins, 1)      .side(1)           # Low pulse, so set output pin high initially
    # Setup delay...Wait for data in the TX FIFO representing the output length cycles, 
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=length, osr=length

    # and store it in x                                                  +------------+
    #                                                                    ^            v
    out(x, 32)                                 #                 osr=length, x=length

    jmp(x_dec, "lp_decrement_x") # Subtract one #                 osr=length, x=length-1
    label("lp_decrement_x")

    # Save length -1 in isr
    # It may seem odd to mov it to isr only for it to be moved back, 
    # but this is to allow subsequent loops to restore the value 
    mov(isr, x)                                 #                 osr=length, x=length-1, isr=length-1
    
    # Wait for data in the TX FIFO representing the trigger delay,
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=delay,     osr=delay,    x=length-1, isr=length-1

    # Use wrap_target() here to indicate where to loop (if remaining armed)     x=length-1 or 0,            
    wrap_target()                               #                 osr=delay,    x=?         , isr=length-1, y=?
    
    # copy trigger delay from osr into y                                +----------------------------------------+
    #                                                                   ^                                        v
    out(y, 32)                                  #                 osr=delay,    x=length-1, isr=length-1, y=delay
    
    # Copy back into OSR for use in the next round 
    mov(osr, y)

    # copy (length -1) from isr into x                                              +----------------+
    # (needed for all except first loop)                                              v                ^
    mov(x, isr)                                 #                 osr=delay,    x=length-1, isr=length-1, y=delay

    # Wait for the input trigger pin to be low
    wait(polarity = 0, src = pin, index = 0)

    # Then wait for the input trigger pin to go high
    wait(polarity = 1, src = pin, index = 0)

    # Begin Trigger delay
    label("lp_y_loop_here")      # v--<
    jmp(y_dec, "lp_y_loop_here") # >--^      Delay for y cycles                                               y--
    #                                                             osr=delay,    x=length-1, isr=length-1, y=0

    # Set pin low for x+1 cycles
    set(pins, 0)    .side(0)             # Set pin low
    label("lp_x_loop_here")      # v--<
    jmp(x_dec, "lp_x_loop_here") # >--^      Hold for x cycles                  x--
    #                                                             osr=delay,    x=0         , isr=length-1, y=0

    set(pins, 1)     .side(1)            # Set pin high        One additional cycle to set pin

    # Raise an interrupt to signal the glitch was actioned
    irq(rel(0))

    # Wait for the input trigger to go low again; 
    # !!! note RP2350-E9 errata which may require an additional external pull-down resistor !!!
    # https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf Appendix E: Errata
    wait(polarity = 0, src = pin, index = 0)
    
    label("stop_here")      # v--<
    jmp("stop_here")        # >--^  

# Define a PIO function for waiting for input trigger H->L, then outputing a timed low pulse after specified delay
@rp2.asm_pio(set_init=(rp2.PIO.OUT_HIGH, rp2.PIO.IN_HIGH), sideset_init=(rp2.PIO.OUT_HIGH, rp2.PIO.IN_HIGH))
def LowGlitchOutputOnHighToLowTriggerInput(): 
    set(pins, 1)      .side(1)           # Low pulse, so set output pin high initially
    # Setup delay...Wait for data in the TX FIFO representing the output length cycles, 
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=length, osr=length

    # and store it in x                                                  +------------+
    #                                                                    ^            v
    out(x, 32)                                 #                 osr=length, x=length

    jmp(x_dec, "lp_decrement_x") # Subtract one #                 osr=length, x=length-1
    label("lp_decrement_x")

    # Save length -1 in isr
    # It may seem odd to mov it to isr only for it to be moved back, 
    # but this is to allow subsequent loops to restore the value 
    mov(isr, x)                                 #                 osr=length, x=length-1, isr=length-1
    
    # Wait for data in the TX FIFO representing the trigger delay,
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=delay,     osr=delay,    x=length-1, isr=length-1

    # Use wrap_target() here to indicate where to loop (if remaining armed)     x=length-1 or 0,            
    wrap_target()                               #                 osr=delay,    x=?         , isr=length-1, y=?
    
    # copy trigger delay from osr into y                                +----------------------------------------+
    #                                                                   ^                                        v
    out(y, 32)                                  #                 osr=delay,    x=length-1, isr=length-1, y=delay
    
    # Copy back into OSR for use in the next round 
    mov(osr, y)

    # copy (length -1) from isr into x                                              +----------------+
    # (needed for all except first loop)                                              v                ^
    mov(x, isr)                                 #                 osr=delay,    x=length-1, isr=length-1, y=delay

    # Wait for the input trigger pin to be high
    wait(polarity = 1, src = pin, index = 0)

    # Then wait for the input trigger pin to go low
    wait(polarity = 0, src = pin, index = 0)

    # Begin Trigger delay
    label("lp_y_loop_here")      # v--<
    jmp(y_dec, "lp_y_loop_here") # >--^      Delay for y cycles                                               y--
    #                                                             osr=delay,    x=length-1, isr=length-1, y=0

    # Set pin low for x+1 cycles
    set(pins, 0)    .side(0)             # Set pin low
    label("lp_x_loop_here")      # v--<
    jmp(x_dec, "lp_x_loop_here") # >--^      Hold for x cycles                  x--
    #                                                             osr=delay,    x=0         , isr=length-1, y=0

    set(pins, 1)     .side(1)            # Set pin high        One additional cycle to set pin

    # Raise an interrupt to signal the glitch was actioned
    irq(rel(0))

    # Wait for the input trigger to go high again; 
    # !!! note RP2350-E9 errata which may require an additional external pull-down resistor !!!
    # https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf Appendix E: Errata
    wait(polarity = 1, src = pin, index = 0)
    
    label("stop_here")      # v--<
    jmp("stop_here")        # >--^  


# Define a PIO function for waiting for input trigger L->H, then outputing a timed high pulse after specified delay
@rp2.asm_pio(set_init=(rp2.PIO.OUT_LOW, rp2.PIO.IN_LOW), sideset_init=(rp2.PIO.OUT_LOW, rp2.PIO.IN_HIGH))
def HighGlitchOutputOnLowToHighTriggerInput(): 
    set(pins, 0)        .side(0)                # High pulse, so set output pin low initially
    # Setup delay...Wait for data in the TX FIFO representing the output length cycles, 
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=length, osr=length

    # and store it in x                                                  +------------+
    #                                                                    ^            v
    out(x, 32)                                 #                 osr=length, x=length
        
    jmp(x_dec, "lp_decrement_x") # Subtract one #                 osr=length, x=length-1
    label("lp_decrement_x")

    # Save length -1 in isr
    # It may seem odd to mov it to isr only for it to be moved back, 
    # but this is to allow subsequent loops to restore the value 
    mov(isr, x)                                 #                 osr=length, x=length-1, isr=length-1
    
    # Wait for data in the TX FIFO representing the trigger delay,
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=delay,     osr=delay,    x=length-1, isr=length-1

    # Use wrap_target() here to indicate where to loop (if remaining armed)     x=length-1 or 0,            
    wrap_target()                               #                 osr=delay,    x=?         , isr=length-1, y=?
    
    # copy trigger delay from osr into y                                +----------------------------------------+
    #                                                                   ^                                        v
    out(y, 32)                                  #                 osr=delay,    x=length-1, isr=length-1, y=delay
    
    # Copy back into OSR for use in the next round 
    mov(osr, y)

    # copy (length -1) from isr into x                                              +----------------+
    # (needed for all except first loop)                                              v                ^
    mov(x, isr)                                 #                 osr=delay,    x=length-1, isr=length-1, y=delay

    # Wait for the input trigger pin to be low
    wait(polarity = 0, src = pin, index = 0)

    # Then wait for the input trigger pin to go high
    wait(polarity = 1, src = pin, index = 0)

    # Begin Trigger delay
    label("lp_y_loop_here")      # v--<
    jmp(y_dec, "lp_y_loop_here") # >--^      Delay for y cycles                                               y--
    #                                                             osr=delay,    x=length-1, isr=length-1, y=0

    # Set pin high for x+1 cycles
    set(pins,1)           .side(1)       # Set pin high
    label("lp_x_loop_here")      # v--<
    jmp(x_dec, "lp_x_loop_here") # >--^      Hold for x cycles                  x--
    #                                                             osr=delay,    x=0         , isr=length-1, y=0

    set(pins, 0)          .side(0)       # Set pin low        One additional cycle to set pin

    # Raise an interrupt to signal the glitch was actioned
    irq(rel(0))

    # Wait for the input trigger to go low again; 
    # !!! note RP2350-E9 errata which may require an additional external pull-down resistor !!!
    # https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf Appendix E: Errata
    wait(polarity = 0, src = pin, index = 0)
    
    label("stop_here")      # v--<
    jmp("stop_here")        # >--^  


# Define a PIO function for waiting for input trigger H->L, then outputing a timed high pulse after specified delay
@rp2.asm_pio(set_init=(rp2.PIO.OUT_LOW, rp2.PIO.IN_HIGH), sideset_init=(rp2.PIO.OUT_LOW, rp2.PIO.IN_HIGH))
def HighGlitchOutputOnHighToLowTriggerInput(): 
    set(pins, 0)        .side(0)                # High pulse, so set output pin low initially
    # Setup delay...Wait for data in the TX FIFO representing the output length cycles, 
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=length, osr=length

    # and store it in x                                                  +------------+
    #                                                                    ^            v
    out(x, 32)                                 #                 osr=length, x=length
        
    jmp(x_dec, "lp_decrement_x") # Subtract one #                 osr=length, x=length-1
    label("lp_decrement_x")

    # Save length -1 in isr
    # It may seem odd to mov it to isr only for it to be moved back, 
    # but this is to allow subsequent loops to restore the value 
    mov(isr, x)                                 #                 osr=length, x=length-1, isr=length-1
    
    # Wait for data in the TX FIFO representing the trigger delay,
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=delay,     osr=delay,    x=length-1, isr=length-1

    # Use wrap_target() here to indicate where to loop (if remaining armed)     x=length-1 or 0,            
    wrap_target()                               #                 osr=delay,    x=?         , isr=length-1, y=?
    
    # copy trigger delay from osr into y                                +----------------------------------------+
    #                                                                   ^                                        v
    out(y, 32)                                  #                 osr=delay,    x=length-1, isr=length-1, y=delay
    
    # Copy back into OSR for use in the next round 
    mov(osr, y)

    # copy (length -1) from isr into x                                              +----------------+
    # (needed for all except first loop)                                              v                ^
    mov(x, isr)                                 #                 osr=delay,    x=length-1, isr=length-1, y=delay

    # Wait for the input trigger pin to be high
    wait(polarity = 1, src = pin, index = 0)

    # Then wait for the input trigger pin to go low
    wait(polarity = 0, src = pin, index = 0)

    # Begin Trigger delay
    label("lp_y_loop_here")      # v--<
    jmp(y_dec, "lp_y_loop_here") # >--^      Delay for y cycles                                               y--
    #                                                             osr=delay,    x=length-1, isr=length-1, y=0

    # Set pin high for x+1 cycles
    set(pins,1)           .side(1)       # Set pin high
    label("lp_x_loop_here")      # v--<
    jmp(x_dec, "lp_x_loop_here") # >--^      Hold for x cycles                  x--
    #                                                             osr=delay,    x=0         , isr=length-1, y=0

    set(pins, 0)          .side(0)       # Set pin low        One additional cycle to set pin

    # Raise an interrupt to signal the glitch was actioned
    irq(rel(0))

    # Wait for the input trigger to go high again; 
    # !!! note RP2350-E9 errata which may require an additional external pull-down resistor !!!
    # https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf Appendix E: Errata
    wait(polarity = 1, src = pin, index = 0)
    
    label("stop_here")      # v--<
    jmp("stop_here")        # >--^  

# Define a PIO function for waiting for input trigger L->H, then outputing a timed low pulse after specified delay
@rp2.asm_pio(set_init=(rp2.PIO.OUT_HIGH, rp2.PIO.IN_LOW), sideset_init=(rp2.PIO.OUT_HIGH, rp2.PIO.IN_HIGH))
def LowGlitchOutputOnLowToHighTriggerInputAutoRearm(): 
    set(pins, 1)      .side(1)           # Low pulse, so set output pin high initially
    # Setup delay...Wait for data in the TX FIFO representing the output length cycles, 
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=length, osr=length

    # and store it in x                                                  +------------+
    #                                                                    ^            v
    out(x, 32)                                 #                 osr=length, x=length

    jmp(x_dec, "lp_decrement_x") # Subtract one #                 osr=length, x=length-1
    label("lp_decrement_x")

    # Save length -1 in isr
    # It may seem odd to mov it to isr only for it to be moved back, 
    # but this is to allow subsequent loops to restore the value 
    mov(isr, x)                                 #                 osr=length, x=length-1, isr=length-1
    
    # Wait for data in the TX FIFO representing the trigger delay,
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=delay,     osr=delay,    x=length-1, isr=length-1

    # Use wrap_target() here to indicate where to loop (if remaining armed)     x=length-1 or 0,            
    wrap_target()                               #                 osr=delay,    x=?         , isr=length-1, y=?
    
    # copy trigger delay from osr into y                                +----------------------------------------+
    #                                                                   ^                                        v
    out(y, 32)                                  #                 osr=delay,    x=length-1, isr=length-1, y=delay
    
    # Copy back into OSR for use in the next round 
    mov(osr, y)

    # copy (length -1) from isr into x                                              +----------------+
    # (needed for all except first loop)                                              v                ^
    mov(x, isr)                                 #                 osr=delay,    x=length-1, isr=length-1, y=delay

    # Wait for the input trigger pin to be low
    wait(polarity = 0, src = pin, index = 0)

    # Then wait for the input trigger pin to go high
    wait(polarity = 1, src = pin, index = 0)

    # Begin Trigger delay
    label("lp_y_loop_here")      # v--<
    jmp(y_dec, "lp_y_loop_here") # >--^      Delay for y cycles                                               y--
    #                                                             osr=delay,    x=length-1, isr=length-1, y=0

    # Set pin low for x+1 cycles
    set(pins, 0)    .side(0)             # Set pin low
    label("lp_x_loop_here")      # v--<
    jmp(x_dec, "lp_x_loop_here") # >--^      Hold for x cycles                  x--
    #                                                             osr=delay,    x=0         , isr=length-1, y=0

    set(pins, 1)     .side(1)            # Set pin high        One additional cycle to set pin

    # Raise an interrupt to signal the glitch was actioned
    irq(rel(0))

    # Wait for the input trigger to go low again; 
    # !!! note RP2350-E9 errata which may require an additional external pull-down resistor !!!
    # https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf Appendix E: Errata
    wait(polarity = 0, src = pin, index = 0)
    
    # wrap here to auto-rearm: continues execution from wrap_target()
    wrap()

# Define a PIO function for waiting for input trigger H->L, then outputing a timed low pulse after specified delay
@rp2.asm_pio(set_init=(rp2.PIO.OUT_HIGH, rp2.PIO.IN_HIGH), sideset_init=(rp2.PIO.OUT_HIGH, rp2.PIO.IN_HIGH))
def LowGlitchOutputOnHighToLowTriggerInputAutoRearm(): 
    set(pins, 1)      .side(1)           # Low pulse, so set output pin high initially
    # Setup delay...Wait for data in the TX FIFO representing the output length cycles, 
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=length, osr=length

    # and store it in x                                                  +------------+
    #                                                                    ^            v
    out(x, 32)                                 #                 osr=length, x=length

    jmp(x_dec, "lp_decrement_x") # Subtract one #                 osr=length, x=length-1
    label("lp_decrement_x")

    # Save length -1 in isr
    # It may seem odd to mov it to isr only for it to be moved back, 
    # but this is to allow subsequent loops to restore the value 
    mov(isr, x)                                 #                 osr=length, x=length-1, isr=length-1
    
    # Wait for data in the TX FIFO representing the trigger delay,
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=delay,     osr=delay,    x=length-1, isr=length-1

    # Use wrap_target() here to indicate where to loop (if remaining armed)     x=length-1 or 0,            
    wrap_target()                               #                 osr=delay,    x=?         , isr=length-1, y=?
    
    # copy trigger delay from osr into y                                +----------------------------------------+
    #                                                                   ^                                        v
    out(y, 32)                                  #                 osr=delay,    x=length-1, isr=length-1, y=delay
    
    # Copy back into OSR for use in the next round 
    mov(osr, y)

    # copy (length -1) from isr into x                                              +----------------+
    # (needed for all except first loop)                                              v                ^
    mov(x, isr)                                 #                 osr=delay,    x=length-1, isr=length-1, y=delay

    # Wait for the input trigger pin to be high
    wait(polarity = 1, src = pin, index = 0)

    # Then wait for the input trigger pin to go low
    wait(polarity = 0, src = pin, index = 0)

    # Begin Trigger delay
    label("lp_y_loop_here")      # v--<
    jmp(y_dec, "lp_y_loop_here") # >--^      Delay for y cycles                                               y--
    #                                                             osr=delay,    x=length-1, isr=length-1, y=0

    # Set pin low for x+1 cycles
    set(pins, 0)    .side(0)             # Set pin low
    label("lp_x_loop_here")      # v--<
    jmp(x_dec, "lp_x_loop_here") # >--^      Hold for x cycles                  x--
    #                                                             osr=delay,    x=0         , isr=length-1, y=0

    set(pins, 1)     .side(1)            # Set pin high        One additional cycle to set pin

    # Raise an interrupt to signal the glitch was actioned
    irq(rel(0))

    # Wait for the input trigger to go high again; 
    # !!! note RP2350-E9 errata which may require an additional external pull-down resistor !!!
    # https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf Appendix E: Errata
    wait(polarity = 1, src = pin, index = 0)
    
    # wrap here to auto-rearm: continues execution from wrap_target()
    wrap()



# Define a PIO function for waiting for input trigger L->H, then outputing a timed high pulse after specified delay
@rp2.asm_pio(set_init=(rp2.PIO.OUT_LOW, rp2.PIO.IN_LOW), sideset_init=(rp2.PIO.OUT_LOW, rp2.PIO.IN_HIGH))
def HighGlitchOutputOnLowToHighTriggerInputAutoRearm(): 
    set(pins, 0)        .side(0)                # High pulse, so set output pin low initially
    # Setup delay...Wait for data in the TX FIFO representing the output length cycles, 
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=length, osr=length

    # and store it in x                                                  +------------+
    #                                                                    ^            v
    out(x, 32)                                 #                 osr=length, x=length
        
    jmp(x_dec, "lp_decrement_x") # Subtract one #                 osr=length, x=length-1
    label("lp_decrement_x")

    # Save length -1 in isr
    # It may seem odd to mov it to isr only for it to be moved back, 
    # but this is to allow subsequent loops to restore the value 
    mov(isr, x)                                 #                 osr=length, x=length-1, isr=length-1
    
    # Wait for data in the TX FIFO representing the trigger delay,
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=delay,     osr=delay,    x=length-1, isr=length-1

    # Use wrap_target() here to indicate where to loop (if remaining armed)     x=length-1 or 0,            
    wrap_target()                               #                 osr=delay,    x=?         , isr=length-1, y=?
    
    # copy trigger delay from osr into y                                +----------------------------------------+
    #                                                                   ^                                        v
    out(y, 32)                                  #                 osr=delay,    x=length-1, isr=length-1, y=delay
    
    # Copy back into OSR for use in the next round 
    mov(osr, y)

    # copy (length -1) from isr into x                                              +----------------+
    # (needed for all except first loop)                                              v                ^
    mov(x, isr)                                 #                 osr=delay,    x=length-1, isr=length-1, y=delay

    # Wait for the input trigger pin to be low
    wait(polarity = 0, src = pin, index = 0)

    # Then wait for the input trigger pin to go high
    wait(polarity = 1, src = pin, index = 0)

    # Begin Trigger delay
    label("lp_y_loop_here")      # v--<
    jmp(y_dec, "lp_y_loop_here") # >--^      Delay for y cycles                                               y--
    #                                                             osr=delay,    x=length-1, isr=length-1, y=0

    # Set pin high for x+1 cycles
    set(pins,1)           .side(1)       # Set pin high
    label("lp_x_loop_here")      # v--<
    jmp(x_dec, "lp_x_loop_here") # >--^      Hold for x cycles                  x--
    #                                                             osr=delay,    x=0         , isr=length-1, y=0

    set(pins, 0)          .side(0)       # Set pin low        One additional cycle to set pin

    # Raise an interrupt to signal the glitch was actioned
    irq(rel(0))

    # Wait for the input trigger to go low again; 
    # !!! note RP2350-E9 errata which may require an additional external pull-down resistor !!!
    # https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf Appendix E: Errata
    wait(polarity = 0, src = pin, index = 0)
    
    # wrap here to auto-rearm: continues execution from wrap_target()
    wrap()


# Define a PIO function for waiting for input trigger H->L, then outputing a timed high pulse after specified delay
@rp2.asm_pio(set_init=(rp2.PIO.OUT_LOW, rp2.PIO.IN_HIGH), sideset_init=(rp2.PIO.OUT_LOW, rp2.PIO.IN_HIGH))
def HighGlitchOutputOnHighToLowTriggerInputAutoRearm(): 
    set(pins, 0)        .side(0)                # High pulse, so set output pin low initially
    # Setup delay...Wait for data in the TX FIFO representing the output length cycles, 
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=length, osr=length

    # and store it in x                                                  +------------+
    #                                                                    ^            v
    out(x, 32)                                 #                 osr=length, x=length
        
    jmp(x_dec, "lp_decrement_x") # Subtract one #                 osr=length, x=length-1
    label("lp_decrement_x")

    # Save length -1 in isr
    # It may seem odd to mov it to isr only for it to be moved back, 
    # but this is to allow subsequent loops to restore the value 
    mov(isr, x)                                 #                 osr=length, x=length-1, isr=length-1
    
    # Wait for data in the TX FIFO representing the trigger delay,
    # then pull it into osr                               +-------------+
    #                                                     ^             v
    pull(ifempty,block)                         # FIFO=delay,     osr=delay,    x=length-1, isr=length-1

    # Use wrap_target() here to indicate where to loop (if remaining armed)     x=length-1 or 0,            
    wrap_target()                               #                 osr=delay,    x=?         , isr=length-1, y=?
    
    # copy trigger delay from osr into y                                +----------------------------------------+
    #                                                                   ^                                        v
    out(y, 32)                                  #                 osr=delay,    x=length-1, isr=length-1, y=delay
    
    # Copy back into OSR for use in the next round 
    mov(osr, y)

    # copy (length -1) from isr into x                                              +----------------+
    # (needed for all except first loop)                                              v                ^
    mov(x, isr)                                 #                 osr=delay,    x=length-1, isr=length-1, y=delay

    # Wait for the input trigger pin to be high
    wait(polarity = 1, src = pin, index = 0)

    # Then wait for the input trigger pin to go low
    wait(polarity = 0, src = pin, index = 0)

    # Begin Trigger delay
    label("lp_y_loop_here")      # v--<
    jmp(y_dec, "lp_y_loop_here") # >--^      Delay for y cycles                                               y--
    #                                                             osr=delay,    x=length-1, isr=length-1, y=0

    # Set pin high for x+1 cycles
    set(pins,1)           .side(1)       # Set pin high
    label("lp_x_loop_here")      # v--<
    jmp(x_dec, "lp_x_loop_here") # >--^      Hold for x cycles                  x--
    #                                                             osr=delay,    x=0         , isr=length-1, y=0

    set(pins, 0)          .side(0)       # Set pin low        One additional cycle to set pin

    # Raise an interrupt to signal the glitch was actioned
    irq(rel(0))

    # Wait for the input trigger to go high again; 
    # !!! note RP2350-E9 errata which may require an additional external pull-down resistor !!!
    # https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf Appendix E: Errata
    wait(polarity = 1, src = pin, index = 0)
    
    # wrap here to auto-rearm: continues execution from wrap_target()
    wrap()

def deactivate_state_machine(sm):
    #global LED_RED, LED_GREEN, LED_BLUE
    #LED_BLUE.value(0)
    # Deactivate state machine 0
    sm.active(0)
    UpdateStateMachineStatus()

def GlitchedCallback(sm):
    global uart0, GlitchFiredOutput
    global VictimReadData
    sm.active(0)
    if (GlitchFiredOutput & 0x01) == 0x01:
        sys.stdout.write('~') # Output a ~ to indicate that the glitch was triggered
    if (GlitchFiredOutput & 0x02) == 0x02:
        # Read UART data into buffer
        utime.sleep_us(5000) # wait for data
        (VictimDataLength, BytesStillAvailable) = ReadTargetBytesIntoBuffer(MaximumBufferSize = 1024, PrintNewData = False)
    if (GlitchFiredOutput & 0x04) == 0x04:
        # Assert reset
        ResetControl(Level = 0, SuppressResponse = True)

def Peek32(adr):
  return mem32[adr]
  
def Poke32(adr, val):
  mem32[adr] = val

def main():
    global EXT_TRIGGER_OUT, GLITCH, VICTIM_RUN, VICTIM_PWR
    # Setup initial pin states @TODO tidy up, decide initial states, and whether to initialise here or later
    EXT_TRIGGER_OUT = Pin(GP_EXT_TRIGGER_OUT, Pin.OUT, value = 0) # Set GP_EXT_TRIGGER_OUT as an output
    EXT_TRIGGER_OUT.value(0)                    # Set GP_EXT_TRIGGER_OUT low
    GLITCH = Pin(GP_EXT_TRIGGER_OUT, Pin.OUT, value = 0) # Set GLITCH as an output
    GLITCH.value(0)                    # Set GLITCH low
    
    # Start the onboard LED flashing to show the script is executing
    LED_Timer.init(freq=1, mode=Timer.PERIODIC, callback=tick)

    # Wait for a byte to be available on the USB CDC port - removed
    #while (sys.stdin in select.select([sys.stdin], [], [], 0)[0] == None):
    #    waiting = True

    LED_Timer.deinit()
    while True:
        # Enter Command Mode 
        CommandMode()

def tick(Timer):
    global PICO_LED
    global wdt
    try:
        PICO_LED.toggle()
        UpdateStateMachineStatus()
    except NameError:
        sys.stdout.write("PICO_LED.toggle failed")
        
    # If the watchdog timer has been enabled, tickle & feed it, it's a good dog.
    if wdt:
        wdt.feed()

def WelcomeToCommandMode():
    # Display welcome message @TODO: Update format and add response info. E&OE!
    sys.stdout.write("\n"
    "******* Commands: *********\n"
    " a       Arm glitcher\n"
    "           usage: a\n"
    "           response: ai#o#d#####l#####\n"
    "                     a=State machine active\n"
    "                      i[0|1]: Input Trigger Level needed: 0=H->L, 1=L->H\n"
    "                        o[0|1]: Glitch Output Level: 0=L, 1=H\n"
    "                          d#####: delay in ns (ascii decimal: 00040 to 436900)\n"
    "                                l#####: length: length in ns (ascii decimal: 00007 to 436900)\n"
    " b      Print board configuration information (for the FireFight v0.1 board)\n"
    " c      Command: send UART data with UART0\n"
    "           usage: c<byte count><data>\n"
    "                        will be prompted in ASCII for <byte count> (max 0xFF) and <data>, required in ASCII hex\n"
    "                   <byte count> 2 character ASCII hex\n"
    "                   <data> byte count characters of ASCII hex\n"
    " D      Set or query Glitch Delay and arm:\n"
    "           usage: d<?>|<##### delay>\n"
    "                       ? Queries Glitch Delay in ns (replies with ascii decimal 00040 to 436900)\n"
    "                       <##### length> Sets Glitch Delay in ns (ascii decimal: 00040 to 436900)\n" 
    "                           5 byte response for delay setting\n"
    "                           Note that this may be different to the requested value due to clock frequency\n"
    " d      Set or query Glitch Delay (do not arm):\n"
    "           usage: d<?>|<##### delay>\n"
    "                       ? Queries Glitch Delay in ns (replies with ascii decimal 00040 to 436900)\n"
    "                       <##### length> Sets Glitch Delay in ns (ascii decimal: 00040 to 436900)\n" 
    "                           5 byte response for delay setting\n"
    "                           Note that this may be different to the requested value due to clock frequency\n"
    " e      View Last Exception information:\n"
    "           usage e[?|c|#]\n"
    "                   ?  Print last exception\n"
    "                   c  Clear last exception\n"
    "                   #  Set exception printing level 0-2\n"
    " f      Fetch data from Victim\n"
    "           usage f\n"
    " g      GPIO:\n"
    "           usage: g<GPIO Number ##><c##|i|o|0|1|l|h|L|H|r>\n"
    "                   <GPIO Number ##>: 2 digit ASCII decimal \'00\' to \'29\' for QFN60 (e.g. Pi Pico2) or \'00\' to \'80\' for QFN80\n"         
    "                   c##  Configure, with value for specified pin (2 digit ASCII hex), or \'??\' to read config\n"
    "                           bit 7   (Mask 0x80): Output Disable\n"
    "                           bit 6   (Mask 0x40): Input Enable\n"
    "                           bit 5:4 (Mask 0x30): Drive Strength (00=2mA, 01=4mA, 10=8mA, 11=12mA\n"
    "                           bit 3:  (Mask 0x08): Pull-Up Enable\n"
    "                           bit 2:  (Mask 0x04): Pull-Down Enable\n"
    "                           bit 1:  (Mask 0x02): Schmitt Trigger Enable\n"
    "                           bit 0:  (Mask 0x01): Slew Rate Control (1=Fast, 0=Slow)\n"
    "                   i or o      Set pin input or output\n"
    "                                   Response: i###\n"
    "                                             <## GPIO number>\n"
    "                                               <#> Level\n"
    "                   0, l, or L      Set pin low (assumes already configured as output)\n"
    "                                   Response: g##0\n"
    "                                             <## GPIO number>\n"
    "                                                0 Level low\n"
    "                   1, h, or H      Set pin high (assumes already configured as output)\n"
    "                                   Response: g##1\n"
    "                                             <## GPIO number>\n"
    "                                                1 Level high\n"
    "                   r  Read pin (if configured as output, this returns the last set value, not the pin level)\n"
    "                                   Response: r###\n"
    "                                             <## GPIO number>\n"
    "                                               <#> Level: 0 or 1\n"
    "                   a  Read all pin values (if configured as output, this returns the last set value, not the pin level)\n"
    "                                   Response (for each GPIO)\n:"
    "                                             GP## = #\n"
    "                                                    # Level 0 or 1\n"
    " h or ? Help: Display this help screen\n"
    " I      Set Trigger Input Level and arm\n"
    "           usage: i[0|1|l|L|h|H]\n"
    "                    0, l, or L:  High to low edge triggered\n"
    "                    1, h, or H:  Low to high edge triggered\n"
    " i      Set Trigger Input Level (do not arm)\n"
    "           usage: i[0|1|l|h]\n"
    "                    0, l, or L:  High to low edge triggered\n"
    "                    1, h, or H:  Low to high edge triggered\n"
    " L      Set or query Glitch Length and arm:\n"
    "           usage: l<?>|<##### length>\n"
    "                       ? Queries Glitch Length in ns (replies with ascii decimal 00007 to 436900)\n"
    "                       <##### length> Sets Glitch Length in ns (ascii decimal: 00007 to 436900)\n" 
    "                           5 byte response for delay setting\n"
    "                           Note that this may be different to the requested value due to clock frequency\n"
    " l      Set or query Glitch Length (do not arm):\n"
    "           usage: l<?>|<##### length>\n"
    "                       ? Queries Glitch Length in ns (replies with ascii decimal 00007 to 436900)\n"
    "                       <##### length> Sets Glitch Length in ns (ascii decimal: 00007 to 436900)\n" 
    "                           5 byte response for delay setting\n"
    "                           Note that this may be different to the requested value due to clock frequency\n"
    " m      Look at Pico memory"
    "           usage: l<Read Width><Address>\n"
    "               <Read Width>: 1|2|4 (byte width for read)\n"
    "               <Address>: ######## (8 character ASCII hex address)\n"
    " n      Pi Pico info\n"
    "           usage: n\n"
    " O      Set Glitch Output Level and arm\n"
    "           usage: o[0|1|l|h|L|H]\n"
    "                    0 or l or L:  Glitch output level low\n"
    "                    1 or h or H:  Glitch output level high\n"
    " o      Set Glitch Output Level (do not arm)\n"
    "           usage: o[0|1|l|h|L|H]\n"
    "                    0 or l or L:  Glitch output level low\n"
    "                    1 or h or H:  Glitch output level high\n"
    " p      Print Pi Pico Python Script\n"
    "           usage: p\n"
    " r      Reset Target Control:\n"
    "           usage: r<[0|1|l|h|L|H]>\n"
    "                    0 or l or L:    Target Reset Low\n"
    "                    1 or h or H:    Vcc High\n"
    " s      State Machine Status:\n"
    "           usage: s#\n"
    "                   # in range 0 - 7\n"
    " t      Full Trigger Control \n"
    "                  (output to GP21 and GP28 with options for trigger level and delay/length):\n"
    "           usage: t[l|h|dl|dh|q|?]<##### delay><##### length>\n"
    "                   0 or l or L:    Trigger Low\n"
    "                   1 or h or H:    Trigger High\n"
    "                   dl Trigger length Low\n"
    "                   dh Trigger length High\n"  
    "                       For dl|dh options:\n"
    "                           <##### delay> delay in ns (ascii decimal: 00040 to 436900)\n"
    "                           <##### length> length in ns (ascii decimal: 00007 to 436900)\n" 
    "                           Note: These times will be rounded to nearest achievable value with\n"
    "                                 integer number of clocks. At 150MHz, each clock is 6.66666ns\n"
    "                       10 byte response: 5 bytes each for delay and length setting\n"
    "                       Note that these may be different to the requested values due to clock frequency\n"
    "                   q   Quit SM0 execution\n"
    "                   ?   Print the trigger parameters\n"
    "                       Format: [a|-]i[0|1]o[0|1]d#####l#####\n"
    "                                a=State machine active\n"
    "                                -=State machine inactive\n"
    "                                    i[0|1]: Input Trigger Level needed: 0=H->L, 1=L->H\n"
    "                                          o[0|1]: Glitch Output Level: 0=L, 1=H\n"
    "                                                d#####: delay in ns (ascii decimal: 00040 to 436900)\n"
    "                                                      l#####: length: length in ns (ascii decimal: 00007 to 436900)\n"
    "           For simple glitching use 'd', 'l', and 'a' commands to control delay length and arming\n"
    " v     VCC:\n"
    "           usage: v<[0|1|l|h|L|H]>\n"
    "                  0 or l or L:    Vcc Low\n"
    "                  1 or h or H:    Vcc High\n"
    " w     Enable Watchdog Timer\n"
    "           usage: w\n"
    " x     execute attack\n"
    "           usage x\n"
    " X     Exit: reboot Pi Pico\n"
    "           usage: X\n"
    " z     Shortcut to r0 v0 a v1 r1 which resets the target and arms the glitcher\n"
    "           usage: z\n"
    "           Response: r0v0av1r1\n"
    " :     Check connected\n"
    "           usage: :\n"
    "           Response: )\n"
    " -     Clear Control UART buffer\n"
    "           usage -\n"
    " @     Print Copyright Info\n"
    "  LED commands:\n"
    "           Commands in the range 0x20 to 0x27 are used to control the LEDs,\n"
    "           with the lowest 3 bits representing each colour (0=off, 1 = on)\n"
    "           b2: Red LED\n"
    "           b1: Green LED\n"
    "           b0: Blue LED\n"
    "       Character Dec Hex   Bin      b2-b0  Red Green Blue\n"
    "       --------------------------------------------------\n"
    "       <space>   32  0x20  00100000 000     0    0     0 \n"
    "       !         33  0x21  00100001 001     0    0     1 \n"
   "       \"         34  0x22  00100010 010     0    1     0 \n"
    "       #         35  0x23  00100011 011     0    1     1 \n"
    "       $         36  0x24  00100100 100     1    0     0 \n"
    "       %         37  0x25  00100101 101     1    0     1 \n"
    "       &         38  0x26  00100110 110     1    1     0 \n"
    "       '         39  0x27  00100111 111     1    1     1 \n"

    " **************************** Important Commands **********************************\n"
    " ? or h    Help\n"
    " x         Execute DFA attack demo\n"
    " z         Reboot victim board and arm glitcher using current glitch parameters \n"
    " v0        Disable victim 3v3\n"
    " v1        Enable victim 3v3\n"
    " r0        Assert victim reset (RUN = low)\n"
    " r1        Release victim reset (RUN = high)\n"
    " i         Set Trigger Input Level (do not arm)\n"
    " o         Set Set Glitch Output Level (do not arm)\n"
    " d         Set Glitch Delay (do not arm)\n"
    " l         Set Glitch Length (do not arm)\n"
    " a         Arm\n"
    " tq        Disarm\n"
    " t?        Print the trigger parameters\n"
    " b         Print the board config info (GPIO and jumper usage instructions)\n"
    "\n"
    "(Note that '>' is the command prompt indicating readiness for the next command)\n\n"
    "+================================= Example use ===========================================================+\n"
    "| Command | Response            | Action                                                                  |\n"
    "+=========+=====================+=========================================================================+\n"
    "| x       | Prompts for params  | Execute the DFA attack demo                                             |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| z       | a>                  | Reboot victim board and arm glitcher using current glitch parameters    |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| r0      | r0>                 | Assert victim reset low (RUN = Low)                                     |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| v0      | v0>                 | Disable victim 3V3 (3V3_EN = Low)                                       |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| t?      | -i1o1d00040l00200>  | Prints trigger parameters:                                              |\n"
    "|         |                     |       glitcher not armed, input high triggered,                         |\n"
    "|         |                     |       output high during glitch, delay 40ns, length 200ns               |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| i1      | i1>                 | Sets input trigger to be low to high edge transition                    |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| o1      | o1>                 | Sets glitch output to be high during glitch                             |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| d12345  | d12347>             | Requests delay of 12345ns, response confirms set at closest: 12347ns    |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| l00234  | l00233>             | Requests delay of 00234ns, response confirms set at closest: 00233ns    |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| t?      | -i1o1d12347l00233>  | Prints trigger parameters:                                              |\n"
    "|         |                     |     glitcher not armed, input high triggered,                           |\n"
    "|         |                     |     output high during glitch, delay 12347ns, length 233ns              |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| a       | ai1o1d12347l00233>  | Arms glitcher, and response confirms glitcher armed and above parameters|\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| t?      | ai1o1d12347l00233>  | Prints trigger parameters:                                              |\n"
    "|         |                     |      glitcher armed, input high triggered,                              |\n"
    "|         |                     |      output high during glitch, delay 12347ns, length 233ns             |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| v1      | v1>                 | Enable victim 3v3                                                       |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    "| r1      | r1>                 | Release victim reset                                                    |\n"
    "+---------+---------------------+-------------------------------------------------------------------------+\n"
    )

def PrintPicoInfo():
    s = unique_id()
    print("\ns/n: 0x", end="")
    for b in s:
        print(('00'+hex(b)[2:])[-2:], end="")
    print()
    print("Downloaded script info")
    PrintTextBlocks("Version")
    print("Filesystem info: ", os.listdir())
    print("/main.py size: ", os.stat("/main.py")[6])
    print("/main.py date/time: ", end = "")
    file_time = os.stat("/main.py")[8]
    file_localtime_array = time.localtime(file_time)
    file_year = file_localtime_array[0]
    file_month = file_localtime_array[1]
    file_day = file_localtime_array[2]
    file_hour = file_localtime_array[3]
    file_minute = file_localtime_array[4]
    file_second = file_localtime_array[5]
    print("Modified {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d} \n".format(file_year, file_month, file_day, file_hour, file_minute, file_second))
    print("This is distributed under the GNU General Public License V3\n")
    print("For details see the licence notice in the source code, or use the @ command\n")

def GPIO_Command():
    global PADS_BANK0_BASE
    # @TODO: Read the number of GPIOs and use that instead of limiting to 29
    NumberOfGPIOs = 29 # For QFP60
    #sys.stdout.write('g')
    #Read 2 byte ASCII decimal GPIO number (decimal used to match Pico markings & docs)
    argument_tens = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    if argument_tens == 'a': #Read all pins
        sys.stdout.write("\n")
        for i in range(NumberOfGPIOs):
            sys.stdout.write(f"GP{i:02} = {Pin(i).value()}\n")
        return
    argument_units = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    gp_number = int(argument_tens + argument_units)
    if gp_number>NumberOfGPIOs:
        raise Exception("Invalid GPIO number")
    # Read byte to indicate which GPIO operation
    gpio_operation = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    if gpio_operation == 'c':
        # Configure GPIO pin
        # Read config (2 characters for an ascii hex byte: hex used to match datasheet and only use 2 characters)
        gpio_config_high_nibble = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
        gpio_config_low_nibble  = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
        gpio_config = int(gpio_config_high_nibble + gpio_config_low_nibble, 16)
        # Write pin configuration into the pads bank 0 register for that pin
        Poke32(PADS_BANK0_BASE + 4 + gp_number*4, gpio_config)
    elif gpio_operation == 'o':
        # Set pin as output
        Pin(gp_number, mode=Pin.OUT)
        sys.stdout.write(f"o{gp_number:02}{Pin(gp_number).value()}")
    elif gpio_operation == 'i':
        # Set pin as input
        Pin(gp_number, mode=Pin.IN)
        sys.stdout.write(f"i{gp_number:02}{Pin(gp_number).value()}")
    elif gpio_operation == 'r':
        # Read pin
        sys.stdout.write(f"r{gp_number:02}{Pin(gp_number).value()}")
    elif IsHigh(gpio_operation):
        # Set pin high
        Pin(gp_number, mode=Pin.OUT).on()
        sys.stdout.write(f"g{gp_number:02}{Pin(gp_number).value()}")
    elif IsLow(gpio_operation):
        # Set pin low
        Pin(gp_number, mode=Pin.OUT).off()
        sys.stdout.write(f"g{gp_number:02}{Pin(gp_number).value()}")
    else:
        raise Exception("Invalid GPIO operation")

def PrintPython():
    f = open('/main.py', 'r')
    for line in f:
        print(line.strip())
    f.close()

def PrintTextBlocks(LocatorText):
    # Prints all lines in main.py between HTML style start and end comments.
    print("")
    printline = False
    f = open('/main.py', 'r')
    while True:
        line = f.readline()
        if not line:
            break
        lstripline = line.lstrip(' \t') # strip whitespace
        if len(lstripline):
            if  lstripline[0] == "#" and "</"+LocatorText+">" in lstripline: # Look for comment lines with </LocatorText> 
                # Stop printing lines. Note that this is before the similar test to start printing lines to avoid printing the start/end marker lines
                printline = False
            if printline:
                print(line, end="")
            if  lstripline[0] == "#" and "<"+LocatorText+">" in lstripline: # Look for comment lines with <LocatorText>
                printline = True # Start printing lines
    f.close()

def ResetControl(Level=None, SuppressResponse=False):
    # Wait for command argument
    if Level is None:
        Level = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    if IsLow(Level):
        VICTIM_RUN = Pin(GP_VICTIM_RUN, Pin.OUT)
        VICTIM_RUN.value(0)
        if not SuppressResponse:
            sys.stdout.write('r0')
    elif IsHigh(Level):
        VICTIM_RUN = Pin(GP_VICTIM_RUN, Pin.OUT)
        VICTIM_RUN.value(1)
        if not SuppressResponse:
            sys.stdout.write('r1')
    else:
        raise Exception("Invalid argument")

def VoltageControl(Level=None, SuppressResponse = False):
    # Wait for command argument
    if Level is None:
        Level = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    if IsLow(Level):
        VICTIM_PWR = Pin(GP_VICTIM_PWR, Pin.OUT)
        VICTIM_PWR.value(0)
        if not SuppressResponse:
            sys.stdout.write('v0')
    elif IsHigh(Level):
        VICTIM_PWR = Pin(GP_VICTIM_PWR, Pin.OUT)
        VICTIM_PWR.value(1)
        if not SuppressResponse:
            sys.stdout.write('v1')
    else:
        raise Exception("Invalid argument")
    
def SetGlitchLength_ns(Candidate_GlitchLength_ns = None, CheckOnly = False, ReplyLevel=1):
    global ClockDuration_ns 
    global GlitchLength_clocks
    global GlitchLength_ns

    # Convert to closest number of clocks 
    Resultant_GlitchLength_clocks = round(Candidate_GlitchLength_ns/ClockDuration_ns)

    if (Resultant_GlitchLength_clocks < 1) or (Resultant_GlitchLength_clocks > 0xFFFF):
        # @TODO Use a ReplyLevel to decide whether to output?
        raise Exception(f"Invalid length: must be between {round(ClockDuration_ns)} ns and {round(0xFFFF*ClockDuration_ns)} ns\n")
    
    # Calculate Candidate_GlitchLength_ns from the Candidate_GlitchLength_clocks and ClockDuration_ns
    Resultant_GlitchLength_ns = Resultant_GlitchLength_clocks*ClockDuration_ns

    # set GlitchLength_ns (Global) unless CheckOnly argument not False
    if CheckOnly == False:
        GlitchLength_ns = Resultant_GlitchLength_ns
        # Set GlitchLength_clocks (Global)
        GlitchLength_clocks = Resultant_GlitchLength_clocks
    return Resultant_GlitchLength_ns

def SetGlitchLength(Candidate_GlitchLength_ns = None, ArmStateMachine=None, ReplyLevel=1):
    global GlitchLength_ns

    if Candidate_GlitchLength_ns is None:
        # Get length from host: up to 5 Ascii decimal characters plus optional \r
        #     Note: Can be entered with fewer characters if terminated with \r
        lengthstring_ns = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
        if lengthstring_ns != '?':
            lengthstring_ns += WaitAndReadHostBytes(Count=4, AllowEarlyAbort = True, Attempts = None, ForwardBytesFromTarget = False)
            # Convert from string to int and raise exception if conversion from string fails
            Candidate_GlitchLength_ns = int(lengthstring_ns)
            # Set the closest to the requested glitch length (will also set GlitchLength_ns global)
            SetGlitchLength_ns(Candidate_GlitchLength_ns, CheckOnly=False)
            if StateMachineStatus[0] == 1 and ArmStateMachine != False:
                # Was already armed and ArmStateMachine argument does not disallow it, so call Arm again to update the state machine
                Arm(ReplyLevel=1)

            if ArmStateMachine == True:
                Arm(ReplyLevel=1)

    # Print 'l' and the GlitchLength_ns, rounded to the closest ns as a 5 character ascii decimal
    sys.stdout.write(f"l{round(GlitchLength_ns):05}")

def SetGlitchDelay(Candidate_GlitchDelay_ns = None, ArmStateMachine=None, ReplyLevel=1):
    global MinimumDelayOffset_ns, GlitchDelay_ns, GlitchDelay_clocks

    if Candidate_GlitchDelay_ns is None:
        # Get delay from host: up to 5 Ascii decimal characters plus optional \r
        #     Note: Can be entered with fewer characters if terminated with \r
        delaystring_ns = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
        if delaystring_ns != '?':
            delaystring_ns += WaitAndReadHostBytes(Count=4, AllowEarlyAbort = True, Attempts = None, ForwardBytesFromTarget = False)       
            # Convert from string to int and raise exception if conversion from string fails
            Candidate_GlitchDelay_ns = int(delaystring_ns)
            # Set the closest to the requested glitch length (will also set ResultantGlitchDelay_ns global)
            SetGlitchDelay_ns(Candidate_GlitchDelay_ns, CheckOnly=False)
    if StateMachineStatus[0] == 1 and  ArmStateMachine != False:
        # Was already armed and ArmStateMachine argument does not disallow it, so call Arm again to update the state machine
        Arm(ReplyLevel=1)

    if ArmStateMachine == True:
        Arm(ReplyLevel=1)

    # Print 'd' and the GlitchDelay_ns, rounded to the closest ns as a 5 character ascii decimal
    sys.stdout.write(f"d{round(GlitchDelay_ns):05}")
    

def SetGlitchDelay_ns(RequestedGlitchDelay_ns, CheckOnly = False, ReplyLevel=1):
    global ClockDuration_ns 
    global GlitchDelay_ns, GlitchDelay_clocks
    global MinimumDelayOffset_ns
    
    # Convert to closest number of clocks 
    Candidate_GlitchDelay_clocks = round((RequestedGlitchDelay_ns-MinimumDelayOffset_ns)/ClockDuration_ns)
    # Calculate Candidate_GlitchDelay_ns from the Candidate_GlitchDelay_clocks, ClockDuration_ns and MinimumDelayOffset_ns
    Candidate_GlitchDelay_ns = Candidate_GlitchDelay_clocks*ClockDuration_ns + MinimumDelayOffset_ns

    if (Candidate_GlitchDelay_ns<MinimumDelayOffset_ns) or (Candidate_GlitchDelay_clocks < 0) or (Candidate_GlitchDelay_clocks > 0xFFFF):
        # @TODO Use a ReplyLevel to decide whether to output
        raise Exception(f"Invalid delay: must be between {round(MinimumDelayOffset_ns)} ns and {round(0xFFFF*ClockDuration_ns)} ns\n")
    
    # set GlitchDelay_ns (Global) and GlitchDelay_clocks (Global) unless CheckOnly argument not False
    if CheckOnly == False:
        GlitchDelay_ns = Candidate_GlitchDelay_ns
        # Set GlitchDelay_clocks (Global)
        GlitchDelay_clocks = Candidate_GlitchDelay_clocks
    return GlitchDelay_ns

def Arm(ReplyLevel=1):
    global SM0, StateMachineStatus
    global GlitchDelay_clocks, GlitchLength_clocks
    global EXT_TRIGGER_OUT, GLITCH, VICTIM_TRIG
    global InputTriggerLevel, GlitchOutputLevel # Use the global settings for polarity of input and output
    global LED_RED, LED_GREEN, LED_BLUE

    deactivate_state_machine(rp2.StateMachine(0))
    if SM0 is not None:
        SM0.active(0)
        MyPIO=rp2.PIO(0)
        MyPIO.remove_program()

    if InputTriggerLevel == 0:
        VICTIM_TRIG = Pin(GP_VICTIM_TRIG, Pin.IN, Pin.PULL_UP)
    elif InputTriggerLevel == 1:
        VICTIM_TRIG = Pin(GP_VICTIM_TRIG, Pin.IN, Pin.PULL_DOWN)
    if GlitchOutputLevel == 0:
        # Set GP_EXT_TRIGGER_OUT and GLITCH pin high initially to avoid unexpected behaviour
        EXT_TRIGGER_OUT = Pin(GP_EXT_TRIGGER_OUT, Pin.OUT, Pin.PULL_UP)
        EXT_TRIGGER_OUT.value(1)
        GLITCH = Pin(GP_GLITCH, Pin.OUT, Pin.PULL_UP)
        GLITCH.value(1)
        # Construct the low_pulse StateMachine, binding GLITCH and EXT_TRIGGER_OUT to the set pin.
        if InputTriggerLevel == 0:
            SM0 = rp2.StateMachine(0, LowGlitchOutputOnHighToLowTriggerInput, set_base=GLITCH, in_base=VICTIM_TRIG, sideset_base=EXT_TRIGGER_OUT) 
        elif InputTriggerLevel == 1:
            SM0 = rp2.StateMachine(0, LowGlitchOutputOnLowToHighTriggerInput, set_base=GLITCH, in_base=VICTIM_TRIG, sideset_base=EXT_TRIGGER_OUT) 
    elif GlitchOutputLevel == 1:
        # Set GP_EXT_TRIGGER_OUT and GLITCH pin low initially to avoid unexpected behaviour
        EXT_TRIGGER_OUT = Pin(GP_EXT_TRIGGER_OUT, Pin.OUT, Pin.PULL_DOWN)
        EXT_TRIGGER_OUT.value(0)
        GLITCH = Pin(GP_GLITCH, Pin.OUT, Pin.PULL_DOWN)
        GLITCH.value(0)
        # Construct the high_pulse StateMachine, binding GLITCH and EXT_TRIGGER_OUT to the set pin.
        if InputTriggerLevel == 0:
            SM0 = rp2.StateMachine(0, HighGlitchOutputOnHighToLowTriggerInput, set_base=GLITCH, in_base=VICTIM_TRIG, sideset_base=EXT_TRIGGER_OUT) 
        elif InputTriggerLevel == 1:
            SM0 = rp2.StateMachine(0, HighGlitchOutputOnLowToHighTriggerInput, set_base=GLITCH, in_base=VICTIM_TRIG, sideset_base=EXT_TRIGGER_OUT) 

    SM0.irq(GlitchedCallback)
    # Load the pulse length cycle count into FIFO
    SM0.put(GlitchLength_clocks)
    # Load the delay length cycle count into FIFO
    SM0.put(GlitchDelay_clocks)
    # Start the state machine
    SM0.active(1)
    # Update the StateMachineStatus global
    StateMachineStatus[0] = 1
    # The state machine will now initiate the timed pulse each time the VICTIM_TRIG goes low->high 
    if ReplyLevel>2:
        # verbose reply output
        sys.stdout.write(f"\nState Machine armed:\n"
            "Input Trigger Level = {InputTriggerLevel}, Glitch Output Level = {GlitchOutputLevel}\n"
            "Glitch delay={MinimumDelayOffset_ns+GlitchDelay_clocks*ClockDuration_ns:.0f} ns\n"
            "              ({GlitchDelay_clocks} clocks = {GlitchDelay_clocks*ClockDuration_ns:.0f} ns, plus Delay Correction {MinimumDelayOffset_ns} ns)\n"
            "Glitch length={GlitchLength_clocks*ClockDuration_ns:.0f} ns\n"
            "               ({GlitchLength_clocks} clocks)\n"
            )
    elif ReplyLevel == 2:
        sys.stdout.write(f"ai{InputTriggerLevel}o{GlitchOutputLevel}d{MinimumDelayOffset_ns+GlitchDelay_clocks*ClockDuration_ns:05.0f}l{GlitchLength_clocks*ClockDuration_ns:05.0f}")
    elif ReplyLevel == 1:
        sys.stdout.write("a")
    elif ReplyLevel == 0:
        pass

def SetInputTriggerLevel(LevelToSetTo = None, ArmStateMachine=None, ReplyLevel = 1):
    global InputTriggerLevel
    if LevelToSetTo is None:
        # Wait for command argument
        LevelToSetTo = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)

    if IsLow(LevelToSetTo):
        InputTriggerLevel = 0 # H->L
    elif IsHigh(LevelToSetTo):
        InputTriggerLevel = 1 # L->H
    else:
        sys.stdout.write('!')
        return

    if ReplyLevel >= 1:
        sys.stdout.write(f"i{InputTriggerLevel}")
    if StateMachineStatus[0] == 1 and ArmStateMachine != False:
        # Was already armed and ArmStateMachine argument does not disallow it, so call Arm again to update the state machine
        Arm(ReplyLevel=1)

    if ArmStateMachine == True:
        Arm(ReplyLevel=1)

def SetGlitchOutputLevel(LevelToSetTo = None, ArmStateMachine=None, ReplyLevel = 1):
    global GlitchOutputLevel
    if LevelToSetTo is None:
        # Wait for command argument
        LevelToSetTo = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    if IsLow(LevelToSetTo):
        GlitchOutputLevel = 0 # H->L
    elif IsHigh(LevelToSetTo):
        GlitchOutputLevel = 1 # L->H
    else:
        sys.stdout.write('!')
        return

    if ReplyLevel >= 1:
        sys.stdout.write(f"o{GlitchOutputLevel}")
    if StateMachineStatus[0] == 1 and ArmStateMachine != False:
        # Was already armed and ArmStateMachine argument does not disallow it, so call Arm again to update the state machine
        Arm(ReplyLevel=1)

    if ArmStateMachine == True:
        Arm(ReplyLevel=1)

def SanitiseLowOrHigh(input, ExclamationOnError = True, ExceptionOnError = False):
    output = None # Default if conversion fails
    if IsLow(input):
        output = 0
    elif IsHigh(input):
        output = 1
    else:
        if ExclamationOnError:
            sys.stdout.write('!')
        if ExceptionOnError:
            raise Exception("Invalid input to SanitiseLowOrHigh")
    return output

def IsHigh(input, ExclamationOnError = False, ExceptionOnError = True):
    if ('0' == input) or (0 == input) or ('l' == input) or ('L' == input):
        return(False)
    elif ('1' == input) or (1 == input) or ('h' == input) or ('H' == input):
        return(True)
    else:
        if ExclamationOnError:
            sys.stdout.write('!')
        if ExceptionOnError:
            raise Exception("Invalid input to IsHigh")

def IsLow(input, ExclamationOnError = False, ExceptionOnError = True):
    if ('0' == input) or (0 == input) or ('l' == input) or ('L' == input):
        return(True)
    elif ('1' == input) or (1 == input) or ('h' == input) or ('H' == input):
        return(False)
    else:
        if ExclamationOnError:
            sys.stdout.write('!')
        if ExceptionOnError:
            raise Exception("Invalid input to IsLow")

def TriggerOutputControl(command):
    global SM0, StateMachineStatus
    global GlitchDelay_clocks, GlitchLength_clocks
    global EXT_TRIGGER_OUT, GLITCH, VICTIM_TRIG
    global InputTriggerLevel, GlitchOutputLevel # Use the global settings for polarity of input and output
    global MinimumDelayOffset_ns, ClockDuration_ns
    verbose=False

    # Wait for command argument
    argument = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    if IsLow(argument, ExclamationOnError = False, ExceptionOnError = False):
        EXT_TRIGGER_OUT = Pin(GP_EXT_TRIGGER_OUT, Pin.OUT)
        EXT_TRIGGER_OUT.value(0)
        GLITCH = Pin(GP_GLITCH, Pin.OUT)
        GLITCH.value(0)
    if IsHigh(argument, ExclamationOnError = False, ExceptionOnError = False):
        EXT_TRIGGER_OUT = Pin(GP_EXT_TRIGGER_OUT, Pin.OUT)
        EXT_TRIGGER_OUT.value(1)
        GLITCH = Pin(GP_GLITCH, Pin.OUT)
        GLITCH.value(1)
    elif 'd' == argument:
        # Read and sanitise an input byte
        RequestedInputTriggerLevel = SanitiseLowOrHigh(WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False), ExclamationOnError=True, ExceptionOnError=True)
        SetInputTriggerLevel(LevelToSetTo = RequestedInputTriggerLevel, ReplyLevel = 1)

        # Read and sanitise an input byte
        RequestedGlitchOutputLevel = SanitiseLowOrHigh(WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False), ExclamationOnError=True, ExceptionOnError=True)
        SetGlitchOutputLevel(LevelToSetTo = RequestedGlitchOutputLevel, ReplyLevel = 1)
 
        SetGlitchDelay()
        SetGlitchLength()
 
        VICTIM_TRIG = Pin(GP_VICTIM_TRIG, Pin.IN, Pin.PULL_DOWN)
        Arm(ReplyLevel=1)
        # The state machine will now initiate the timed pulse each time the VICTIM_TRIG goes low->high 
        if verbose:
            sys.stdout.write(f"\nState Machine armed: Glitch delay={MinimumDelayOffset_ns+GlitchDelay_clocks*ClockDuration_ns:.0f} ns ({GlitchDelay_clocks} clocks = {GlitchDelay_clocks*ClockDuration_ns:.0f} ns, plus Delay Correction {MinimumDelayOffset_ns} ns), Glitch length={GlitchLength_clocks*ClockDuration_ns:.0f} ns ({GlitchLength_clocks} clocks)\n")
        #else:
        #    sys.stdout.write(f"i{InputTriggerLevel}o{GlitchOutputLevel}d{MinimumDelayOffset_ns+GlitchDelay_clocks*ClockDuration_ns:05.0f}l{GlitchLength_clocks*ClockDuration_ns:05.0f}")
    elif 'q' == argument:
        deactivate_state_machine(rp2.StateMachine(0))
    elif '?' == argument:
        if StateMachineStatus[0] == 1:
            smState='a'
        else:
            smState = '-'
        sys.stdout.write(f"{smState}i{InputTriggerLevel}o{GlitchOutputLevel}d{MinimumDelayOffset_ns+GlitchDelay_clocks*ClockDuration_ns:05.0f}l{GlitchLength_clocks*ClockDuration_ns:05.0f}")
    else:
        raise Exception("Invalid argument")

def EnableWDT():
    # Enable the watchdog timer - this cannot be disabled until next power on reset!
    # This feature is to avoid getting stuck if the pico itself crashes.
    # Important that this defaults off at power-on, and enabled with a command, otherwise reprogramming gets "interesting"
    # Enable the WDT (8.3 seconds) @TODO: Update for Pico 2?
    #   1000ms is the minimum
    #   8300ms is the maximum
    wdt = WDT(timeout=8300)
    # Tickle the watchdog with wdt.feed()
    wdt.feed()

def SendUartCommand():
    #User defined command
    sys.stdout.write('Byte Count? (ascii Hex nn)\n0x')
    CountUpperNibble = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    CountLowerNibble = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    sys.stdout.write('\nEnter custom command in ascii hex')
    commandbytecount=int(CountUpperNibble+CountLowerNibble,16)
    CommandByteArray = bytearray()
    for x in range(commandbytecount):
        sys.stdout.write('\nEnter Byte ')
        sys.stdout.write(': 0x')
        CommandByteUpperNibble = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
        CommandByteLowerNibble = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
        sys.stdout.write('    ')
        sys.stdout.write(CommandByteUpperNibble+CommandByteLowerNibble)
        CommandByteValue = int(CommandByteUpperNibble+CommandByteLowerNibble,16)
        CommandByteArray.append(CommandByteValue)
    sys.stdout.write('Sending...')
    SendCommandToTarget(CommandByteArray, InterbyteDelay=True, WaitUntilLastByteIsReadBack=False, EchoToHost = True)

def ReadPicoMemory():
    " l      Look at Pico memory"
    "           usage: l<Read Width><Address>\n"
    "               <Read Width>: 1|2|4 (byte width for read)\n"
    "               <Address>: ######## (8 character ASCII hex address)\n"
    ReadWidth = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
    if ReadWidth not in ['1', '2', '4']:
        raise Exception("Invalid read width")
    # Read address
    AddressString = ''
    for i in range(8):
        nibble = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
        if nibble not in ['0','1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'A', 'B', 'C', 'D', 'E', 'F']:
            raise Exception("Invalid address")
        AddressString += nibble
        Address = int(AddressString, 16)
    sys.stdout.write(':')
    if ReadWidth == '4':
        sys.stdout.write(f"{mem32[Address]:#0{10}x}")
    elif ReadWidth == '2':
        sys.stdout.write(f"{mem16[Address]:#0{10}x}")
    elif ReadWidth == '1':        
        sys.stdout.write(f"{mem8[Address]:#0{10}x}")

def StateMachineInfo():
    # Get which SM from host
    index = int(WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False))
    UpdateStateMachineStatus()
    # See if the SM is running: 0=not running, 1 = running
    sys.stdout.write(str(StateMachineStatus[index]))

def PrintLastException():
    global LastException, LastExceptionTime
    PrintDateTime(LastExceptionTime)
    sys.stdout.write("Exception Name: "+ type(LastException).__name__)
    sys.print_exception(LastException)

def UpdateStateMachineStatus():
    PIO0_CTRL = mem32[0x50200000]
    PIO1_CTRL = mem32[0x50300000]
    status = ((PIO1_CTRL & 0x0000000F)<<4) + (PIO0_CTRL & 0x0000000F)
    for i in range(8):
        StateMachineStatus[i] = (status & 0x00000001)

def ReadTargetBytesIntoBuffer(MaximumBufferSize = 1024, PrintNewData = False):
    global VictimReadData
    MaxReads = 10
    while MaxReads & uart0.any():
        MaxReads -=1
        if len(VictimReadData)+uart0.any() < MaximumBufferSize:
            NewData = uart0.read(uart0.any())
            if PrintNewData == True:
                sys.stdout.write(f"Read {len(NewData)} bytes: ")
                for byte in NewData:
                    sys.stdout.write(f"{byte:02x}") # Send it to host
                sys.stdout.write("\n")
            VictimReadData.extend(NewData) # Read uart0 data and append to VictimReadData
    return (len(VictimReadData), uart0.any())

def InterpretReponse(GreenData, Data, PrintResult = True):
    global FaultyCiphertexts, FaultyCiphertextGroups, RoundKeyPercentageFound, R10KeyRecoveryAttempt, BaseKey, BaseKeyHexString, GroupAttempts
    global Results_red, Results_green, Results_orange, Results_grey, Results_cyan, GroupCount
    unmatched_count = 0
    unmatched=[0]*16
    group_errorcount = [0]*4
    group = -1
    OutputResultToLEDs = True
    unique = False
    ResultFormat = None

    if len(GreenData)<16:
        raise Exception("Invalid GreenData Length")
    if len(Data) == 0:
        result = "grey"
        if OutputResultToLEDs:
            LED_RED.value(0)
            LED_GREEN.value(0)
            LED_BLUE.value(0)
        Results_grey += 1
        ResultFormat = IntenseGrey
    elif len(Data) >= 16:
        if Data[:16] == GreenData[:16]:
            result = "green"
            if OutputResultToLEDs:
                LED_RED.value(0)
                LED_GREEN.value(1)
                LED_BLUE.value(0)
            Results_green += 1
            ResultFormat = IntenseGreen
        else:
            # Work out which bytes are affected: build an unmatched list
            for index in range (16):
                if GreenData[index] != Data[index]:
                    unmatched[index] = 1
                    unmatched_count = unmatched_count + 1
                else:
                    unmatched[index] = 0
            # Check each of the column groups for errors
            for index in range (16):
                if unmatched[index] == 1:
                    if index in   [0, 7, 10, 13]: # Group 0 
                        group_errorcount[0] += 1
                    elif index in [1, 4, 11, 14]: # Group 1
                        group_errorcount[1] += 1
                    elif index in [2, 5, 8,  15]: # Group 2
                        group_errorcount[2] += 1
                    elif index in [3, 6, 9,  12]: # Group 3
                        group_errorcount[3] += 1
            # We're only interested in results which affect 4 bytes in a single group, so test for each group
            if (group_errorcount[0] == 4) and (group_errorcount[1] + group_errorcount[2] + group_errorcount[3]) == 0:
                group = 0
            elif (group_errorcount[1] == 4) and (group_errorcount[0] + group_errorcount[2] + group_errorcount[3]) == 0:
                group = 1
            elif (group_errorcount[2] == 4) and (group_errorcount[0] + group_errorcount[1] + group_errorcount[3]) == 0:
                group = 2
            elif (group_errorcount[3] == 4) and (group_errorcount[0] + group_errorcount[1] + group_errorcount[2]) == 0:
                group = 3
            
            # group will be -1 unless it's the result we want
            if group != -1:
                result = "red"
                if OutputResultToLEDs:
                    LED_RED.value(1)
                    LED_GREEN.value(0)
                    LED_BLUE.value(0)
                Results_red += 1
                ResultFormat = IntenseRed

                # Append this faulty ciphertext to the list of faulty ciphertexts, if unique
                if Data[0:16] not in FaultyCiphertexts:
                    unique = True
                    FaultyCiphertexts.append(Data[0:16])
                    FaultyCiphertextGroups.append(group)
                    
                    GroupCount[group] += 1
                    if GroupAttempts==0 and (GroupCount[group]<2):
                        GroupAttempts = 25
                    elif (GroupCount[group] == 2):
                        GroupAttempts = 0
            else:
                result = "orange"
                if OutputResultToLEDs:
                    LED_RED.value(0)
                    LED_GREEN.value(1)
                    LED_BLUE.value(1)
                Results_orange += 1
                ResultFormat = IntenseOrange

    else:
        result = "cyan"
        if OutputResultToLEDs:
            LED_RED.value(0)
            LED_GREEN.value(0)
            LED_BLUE.value(1)
        Results_cyan += 1
        ResultFormat = IntenseCyan
    
    if PrintResult == True:
        sys.stdout.write(f"\n{ResultFormat}{VictimReadData.hex()}                                 \n{result}     {White}\n")

    return (result, group, unique)

def ExecuteAttack():
    global GlitchDelay_ns, GlitchLength_ns
    global LastException
    global Exception_trace, LastExceptionTime
    global VictimReadData
    global GlitchFiredOutput
    global Results_red, Results_green, Results_orange, Results_grey, Results_cyan
    global FaultyCiphertexts, FaultyCiphertextGroups, GroupCount, GroupAttempts, SavedGlitchParameters
    RoundKeyPercentageFound = 0
    GlitchFiredOutput = 0x01
    GreenData = bytearray()
    GroupCount = [0]*4
    unmatched_count = 0
    unmatched=[0]*16

    # Set Defaults appropriate for board
    s = unique_id()
    if s == bytearray.fromhex("c8e9a2bb52085458"): # FIreFIght Mini V0.1 board #1
        MinimumDelay = 59300
        MaximumDelay = 62000
        MinimumLength = 633
        MaximumLength = 687
        Repeats = 20000
    elif s == bytearray.fromhex("9ee79376cb9f7f3b"): # FIreFIght Mini V0.1 board #3
        MinimumDelay = 58700
        MaximumDelay = 62700
        MinimumLength = 747
        MaximumLength = 767
        Repeats = 20000
    elif s == bytearray.fromhex("671e02f82e016886"): # FIreFIght Mini V0.1 board #4
        MinimumDelay = 58700
        MaximumDelay = 62000
        MinimumLength = 727
        MaximumLength = 760
        Repeats = 20000
    elif s == bytearray.fromhex("8b09b39c5d619ece"): # FIreFIght Mini V0.1 board #5
        MinimumDelay = 58700
        MaximumDelay = 62000
        MinimumLength = 450
        MaximumLength = 550
        Repeats = 20000
    elif s == bytearray.fromhex("0c3211a8c1ee8fa7"): # FIreFIght Original V0.1 board #0
        MinimumDelay = 58700
        MaximumDelay = 63460
        MinimumLength = 527
        MaximumLength = 573
        Repeats = 10000
    else:
        sys.stdout.write(f"Board ID: {s.hex()}\n")
        MinimumDelay = 58000
        MaximumDelay = 63500
        MinimumLength = 500
        MaximumLength = 800
        Repeats = 50000

    # Initialise values each time ExecuteAttack is run
    Results_red = 0
    Results_green = 0
    Results_orange = 0
    Results_grey = 0
    Results_cyan = 0
    unique = False
    SavedGlitchParameters = []
    FaultyCiphertexts = []
    RedResultMinDelay = None
    RedResultMaxDelay = None
    RedResultMinLength = None
    RedResultMaxLength = None
    GreenResultMinDelay = None
    GreenResultMaxDelay = None
    GreenResultMinLength = None
    GreenResultMaxLength = None
    GreyResultMinDelay = None
    GreyResultMaxDelay = None
    GreyResultMinLength = None
    GreyResultMaxLength = None
    Group0ResultMinDelay = None
    Group0ResultMaxDelay = None
    Group1ResultMinDelay = None
    Group1ResultMaxDelay = None
    Group2ResultMinDelay = None
    Group2ResultMaxDelay = None
    Group3ResultMinDelay = None
    Group3ResultMaxDelay = None
    GreenMaxReadAttempts = 0
    RedMaxReadAttempts = 0
    GreyMaxReadAttempts = 0
    GreenMinReadAttempts = 999
    RedMinReadAttempts = 999
    GreyMinReadAttempts = 999
    TooManyCiphertexts = False
    RereadsRequired = 0
    
    random.seed()
    sys.stdout.write("\033[2J\033[H") # Clear Screen
    sys.stdout.write("\nDFA Demo:\nPlease enter FIreFIght glitch parameters...\n")
    try:
        sys.stdout.write(f"Minimum Glitch Delay in ns from trigger (ascii decimal: 00040 to 436900, or Enter to use default {MinimumDelay} ns): ")
        MinimumDelay = int(WaitAndReadHostBytes(Count=5, AllowEarlyAbort = True, Attempts = None, ForwardBytesFromTarget = False))
    except Exception as e:
        pass
    try:
        sys.stdout.write(f"\nMaximum Delay (ascii decimal: 00040 to 436900, or Enter to use default {MaximumDelay} ns): ")
        MaximumDelay = int(WaitAndReadHostBytes(Count=5, AllowEarlyAbort = True, Attempts = None, ForwardBytesFromTarget = False))
    except Exception as e:
        pass
    try:
        sys.stdout.write(f"\nMinimum Length (ascii decimal: 00007 to 436900, or Enter to use default {MinimumLength} ns): ")
        MinimumLength = int(WaitAndReadHostBytes(Count=5, AllowEarlyAbort = True, Attempts = None, ForwardBytesFromTarget = False))
    except Exception as e:
        pass
    try:
        sys.stdout.write(f"\nMaximum Length (ascii decimal: 00007 to 436900, or Enter to use default {MaximumLength} ns): ")
        MaximumLength = int(WaitAndReadHostBytes(Count=5, AllowEarlyAbort = True, Attempts = None, ForwardBytesFromTarget = False))
    except Exception as e:
        pass
    try:
        sys.stdout.write(f"\nRepeats (or Enter to use default {Repeats}): ")
        Repeats = int(WaitAndReadHostBytes(Count=5, AllowEarlyAbort = True, Attempts = None, ForwardBytesFromTarget = False))
    except Exception as e:
        pass
    sys.stdout.write(f"\nDelay={MinimumDelay} to {MaximumDelay} ns\nLength={MinimumLength} to {MaximumLength} ns, \nRepeats={Repeats}\n")

    try:
        # Clear the UART buffer of any data
        while(uart0.any()):
            uart0.read(uart0.any())
        VictimReadData = bytearray() # Clear VictimReadData
        # Set RUN low
        ResetControl(Level=0, SuppressResponse=True)
        # Set 3V3_EN High
        VoltageControl(Level=1, SuppressResponse=True)
        sys.stdout.write("\033[2J\033[H[") # Clear Screen
        for attempt in range(Repeats):
            # Clear UART Rx buffer
            while(uart0.any()):
                uart0.read(uart0.any())
            if GroupAttempts == 0:
                # Generate random parameters within the specified ranges
                RndDelayCandidate = random.randrange(MinimumDelay, MaximumDelay+1)
                RndLengthCandidate = random.randrange(MinimumLength, MaximumLength+1)
                # Set glitch parameters
                SetGlitchDelay_ns(RndDelayCandidate, ReplyLevel = 0)
                SetGlitchLength_ns(RndLengthCandidate, ReplyLevel = 0)
            else:
                GroupAttempts -= 1
            
            if attempt<=1:
                sys.stdout.write("\033[2J")  # Clear Screen           
            if attempt == 0:
                sys.stdout.write(f"\033[H[Getting expected ciphertext - will not arm glitcher\n    ")
            if attempt>=1:
                sys.stdout.write(f"\033[H[{attempt}] Delay={round(GlitchDelay_ns)}, Length={round(GlitchLength_ns)} ns                                                 \n   ")

            # Reset the target
            ResetControl(Level = 0, SuppressResponse = True)
            
            # Setup read timeout parameters
            MaxAttempts = 250
            ReadAttempt = 0

            # Switch off the LEDs
            LED_RED.value(0)
            LED_GREEN.value(0)
            LED_BLUE.value(0)

            # Arm the glitcher
            if attempt>0:
                Arm(ReplyLevel = 0)
            # Release reset
            ResetControl(Level = 1, SuppressResponse = True)
            utime.sleep_us(21000)
            # Check for data with a read timeout...
            while((uart0.any() < 16) and (ReadAttempt<MaxAttempts)):
                utime.sleep_us(87) # one byte @ 115200bps
                ReadAttempt += 1
            sys.stdout.write(f" ReadAttempts {ReadAttempt}   Available {uart0.any()}   ")
            # Expecting ~ to confirm glitch to be sent to host (not seen on UART0 as it originates from this Control Pico)
            # then encryption output should be avaialable in Rx buffer from victim
            (VictimDataLength, BytesStillAvailable) = ReadTargetBytesIntoBuffer(MaximumBufferSize = 1024, PrintNewData = False)
            # Safety net, re-read if bytes still available - shouldn't be needed
            if BytesStillAvailable:
                sys.stdout.write(f" Still available {BytesStillAvailable}   re-read;")
                RereadsRequired += 1
                (VictimDataLength, BytesStillAvailable) = ReadTargetBytesIntoBuffer(MaximumBufferSize = 1024, PrintNewData = False)
            sys.stdout.write(f" Still available {BytesStillAvailable}                               \n")
            # Set RUN low
            ResetControl(Level=0, SuppressResponse=True)
            # Truncate the response to 16 bytes (the victim sends additional bytes)
            if VictimDataLength>16:
                VictimReadData = VictimReadData[:16]
                VictimDataLength = 16
            if attempt==0:
                GreenData = VictimReadData[:16]
                sys.stdout.write(f"Expected Ciphertext: {GreenData} ({len(GreenData)} bytes)\n")   
                if len(GreenData)<16:
                    sys.stdout.write(f"Error reading expected Ciphertext: {VictimReadData.hex()}, Bytes available {uart0.any()}\n")
                    break
            
            unmatched_count = 0
            for index in range (16):
                if len(VictimReadData)>index and len(GreenData)>index:
                    if GreenData[index] != VictimReadData[index]:
                        unmatched[index] = 1
                        unmatched_count += 1
                    else:
                        unmatched[index] = 0
                else:
                        unmatched[index] = 1

            unique = False
            (result, group, unique) = InterpretReponse(GreenData, VictimReadData, PrintResult = True)
            if result == 'red':
                try:
                    # If more than ~512 reds, memory allocation may fail so just fail silently and continue
                    SavedGlitchParameters.append(f"{round(GlitchDelay_ns)}, {round(GlitchLength_ns)},   {group}, {VictimReadData.hex()}")
                except:
                    TooManyCiphertexts = True
                    pass
                RedResultMinDelay    = round(GlitchDelay_ns)  if RedResultMinDelay     is None else min(RedResultMinDelay,    round(GlitchDelay_ns)) 
                RedResultMaxDelay    = round(GlitchDelay_ns)  if RedResultMaxDelay     is None else max(RedResultMaxDelay,    round(GlitchDelay_ns)) 
                RedResultMinLength   = round(GlitchLength_ns) if RedResultMinLength    is None else min(RedResultMinLength,   round(GlitchLength_ns)) 
                RedResultMaxLength   = round(GlitchLength_ns) if RedResultMaxLength    is None else max(RedResultMaxLength,   round(GlitchLength_ns)) 
                if group == 0:
                    Group0ResultMinDelay = round(GlitchDelay_ns)  if Group0ResultMinDelay  is None else min(Group0ResultMinDelay, round(GlitchDelay_ns))
                    Group0ResultMaxDelay = round(GlitchDelay_ns)  if Group0ResultMaxDelay  is None else max(Group0ResultMaxDelay, round(GlitchDelay_ns)) 
                if group == 1:
                    Group1ResultMinDelay = round(GlitchDelay_ns)  if Group1ResultMinDelay  is None else min(Group1ResultMinDelay, round(GlitchDelay_ns))
                    Group1ResultMaxDelay = round(GlitchDelay_ns)  if Group1ResultMaxDelay  is None else max(Group1ResultMaxDelay, round(GlitchDelay_ns)) 
                if group == 2:
                    Group2ResultMinDelay = round(GlitchDelay_ns)  if Group2ResultMinDelay  is None else min(Group2ResultMinDelay, round(GlitchDelay_ns))
                    Group2ResultMaxDelay = round(GlitchDelay_ns)  if Group2ResultMaxDelay  is None else max(Group2ResultMaxDelay, round(GlitchDelay_ns)) 
                if group == 3:
                    Group3ResultMinDelay = round(GlitchDelay_ns)  if Group3ResultMinDelay  is None else min(Group3ResultMinDelay, round(GlitchDelay_ns))
                    Group3ResultMaxDelay = round(GlitchDelay_ns)  if Group3ResultMaxDelay  is None else max(Group3ResultMaxDelay, round(GlitchDelay_ns))
                RedMaxReadAttempts = max(RedMaxReadAttempts, ReadAttempt)
                RedMinReadAttempts = min(RedMinReadAttempts, ReadAttempt)
                
            elif result == 'green':
                GreenResultMinDelay  = round(GlitchDelay_ns)  if GreenResultMinDelay  is None else min(GreenResultMinDelay,  round(GlitchDelay_ns)) 
                GreenResultMaxDelay  = round(GlitchDelay_ns)  if GreenResultMaxDelay  is None else max(GreenResultMaxDelay,  round(GlitchDelay_ns)) 
                GreenResultMinLength = round(GlitchLength_ns) if GreenResultMinLength is None else min(GreenResultMinLength, round(GlitchLength_ns)) 
                GreenResultMaxLength = round(GlitchLength_ns) if GreenResultMaxLength is None else max(GreenResultMaxLength, round(GlitchLength_ns)) 
                GreenMaxReadAttempts = max(GreenMaxReadAttempts, ReadAttempt)
                GreenMinReadAttempts = min(GreenMinReadAttempts, ReadAttempt)
            elif result == 'grey':
                GreyResultMinDelay   = round(GlitchDelay_ns)  if GreyResultMinDelay   is None else min(GreyResultMinDelay,   round(GlitchDelay_ns)) 
                GreyResultMaxDelay   = round(GlitchDelay_ns)  if GreyResultMaxDelay   is None else max(GreyResultMaxDelay,   round(GlitchDelay_ns)) 
                GreyResultMinLength  = round(GlitchLength_ns) if GreyResultMinLength  is None else min(GreyResultMinLength,  round(GlitchLength_ns)) 
                GreyResultMaxLength  = round(GlitchLength_ns) if GreyResultMaxLength  is None else max(GreyResultMaxLength,  round(GlitchLength_ns))
                GreyMaxReadAttempts = max(GreyMaxReadAttempts, ReadAttempt)
                GreyMinReadAttempts = min(GreyMinReadAttempts, ReadAttempt)

            # Don't print totals for the first "attempt" which is just to get the normal ciphertext
            if attempt>0:
                sys.stdout.write(f"\nGroup = {group:>2} errorcount = {unmatched_count:>5}        \n") # Send it to host
                sys.stdout.write(f"Group 0: {GroupCount[0]:>4}\nGroup 1: {GroupCount[1]:>4}\nGroup 2: {GroupCount[2]:>4}\nGroup 3: {GroupCount[3]:>4}\n")
                sys.stdout.write(f"{IntenseRed}Red (4 byte corruption pattern):  {Results_red:>4}\n{IntenseGreen}Green (Normal output):            {Results_green:>4}\n{IntenseOrange}Orange (Other corruption):        {Results_orange:>4}\n{IntenseGrey}Grey (No response):               {Results_grey:>4}\n{IntenseCyan}Cyan (Response length <16 bytes): {Results_cyan:>4}{White}\n")
            
            # Don't bother trying to recover the key if we already have 75% but are still waiting for at least 2 unique ciphertexts in each group, but do try if unique even if <2 per group to show % progress 
            TryKeyRecovery = (result == 'red') and (unique == True) and not ((RoundKeyPercentageFound == 75) and ((GroupCount[0]<2) or (GroupCount[1]<2) or (GroupCount[2]<2) or (GroupCount[3]<2)))

            # Uncomment next line to only try key recovery if we have at least 2 unique faulty ciphertexts from each group. This will be faster but will not show key recovery progress so early
            #TryKeyRecovery = TryKeyRecovery and (GroupCount[0]>1) and (GroupCount[1]>1) and (GroupCount[2]>1) and (GroupCount[3]>1)

            if TryKeyRecovery:
                # Try R10 key recovery
                R10KeyRecoveryAttempt = phoenixAES.crack_bytes(FaultyCiphertexts, GreenData, lastroundkeys=[], encrypt=True, outputbeforelastrounds=False, verbose=1)
                if R10KeyRecoveryAttempt:
                    # At least some key bytes found; update the RoundKeyPercentageFound 
                    RoundKeyPercentageFound = round((32-R10KeyRecoveryAttempt.count('.'))/32*100)
                    if RoundKeyPercentageFound == 100:
                        BaseKey = reverse_key_schedule(bytearray.fromhex(R10KeyRecoveryAttempt), 10)
                        BaseKeyHexString = str(BaseKey)[2:-1]
                else:
                    R10KeyRecoveryAttempt  = '................................'        
                sys.stdout.write(f"{White}R10 Key Percentage found = {RoundKeyPercentageFound}%  {R10KeyRecoveryAttempt}\n")

                if (RoundKeyPercentageFound == 100) or (attempt == (Repeats - 1)):
                    # Output results
                    sys.stdout.write(f"{IntenseGreen}Normal Ciphertext Output:\n        {GreenData.hex()}")
                    #for byte in GreenData:
                    #    sys.stdout.write(f"{byte:02x}") # Send it to host
                    sys.stdout.write(f"\n{IntenseRed}4-byte group faulted Ciphertexts:")
                    
                    # Order output by group and colour code the eroneous bytes
                    for groupvalue in range(4):
                        for i in range(len(FaultyCiphertextGroups)):
                            if FaultyCiphertextGroups[i] == groupvalue:
                                sys.stdout.write(f"\n{White}Group:{groupvalue} ")
                                for j in range(16):
                                    if GreenData[j] != FaultyCiphertexts[i][j]:
                                        colour=IntenseRed
                                    else:
                                        colour=IntenseGreen
                                    sys.stdout.write(f"{colour}{FaultyCiphertexts[i][j]:02x}") # Send it to host
                    sys.stdout.write(f"{White}\n")

                    if RoundKeyPercentageFound == 100:
                        sys.stdout.write(f"{IntenseGreen}*******************************************************************************\n")
                        sys.stdout.write(f"** Recovered Base Key: \'{IntenseRed}{BaseKeyHexString}\' {White}({BaseKey.hex()}) {IntenseGreen}**\n")
                        sys.stdout.write( "*******************************************************************************\n")
                        sys.stdout.write(f"**        (Audience astounded - now wait for applause to finish)             **\n")
                        sys.stdout.write(f"*******************************************************************************{White}\n")
                        for ledflash in range(50):
                            LED_RED.value(ledflash % 2)
                            LED_GREEN.value(ledflash % 2)
                            LED_BLUE.value(ledflash % 2)
                            time.sleep(0.1)
                        break

            VictimReadData = bytearray() # Clear Victim ReadData
        sys.stdout.write(f"\nView {len(SavedGlitchParameters)} result details? (y/n)")
        ResultDetailsResponse = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False, StoreBytesFromTarget = True)
        if  ResultDetailsResponse == 'y' or ResultDetailsResponse == '\x0A' or ResultDetailsResponse == '\x0D':
            sys.stdout.write(f"\nDelay, Len, Grp, Faulty Ciphertext\n")
            for i in range(len(SavedGlitchParameters)):
                sys.stdout.write(f"{SavedGlitchParameters[i]}\n") # Send it to host        # Reset to defaults
            if RedResultMinDelay:   sys.stdout.write(f"{IntenseRed  }Red:   Delay = {RedResultMinDelay  } to {RedResultMaxDelay  } ns, Length  = {RedResultMinLength  } to {RedResultMaxLength  } ns\n")
            if Group0ResultMinDelay: sys.stdout.write(f"{IntenseRed }       Group0: {Group0ResultMinDelay  } to {Group0ResultMaxDelay  } ns\n")
            if Group1ResultMinDelay: sys.stdout.write(f"{IntenseRed }       Group1: {Group1ResultMinDelay  } to {Group1ResultMaxDelay  } ns\n")
            if Group2ResultMinDelay: sys.stdout.write(f"{IntenseRed }       Group2: {Group2ResultMinDelay  } to {Group2ResultMaxDelay  } ns\n")
            if Group3ResultMinDelay: sys.stdout.write(f"{IntenseRed }       Group3: {Group3ResultMinDelay  } to {Group3ResultMaxDelay  } ns\n")
            if GreenResultMinDelay: sys.stdout.write(f"{IntenseGreen}Green: Delay = {GreenResultMinDelay} to {GreenResultMaxDelay} ns, Length  = {GreenResultMinLength} to {GreenResultMaxLength} ns\n")
            if GreyResultMinDelay:  sys.stdout.write(f"{IntenseGrey }Grey:  Delay = {GreyResultMinDelay } to {GreyResultMaxDelay } ns, Length  = {GreyResultMinLength } to {GreyResultMaxLength } ns\n")
            if TooManyCiphertexts: sys.stdout.write("Truncated: too many ciphertexts\n")
            sys.stdout.write(f"Read Attempts: Red {RedMinReadAttempts} - {RedMaxReadAttempts}, Green {GreenMinReadAttempts} - {GreenMaxReadAttempts}, Grey {GreyMinReadAttempts} - {GreyMaxReadAttempts}\n")
            sys.stdout.write(f"Re-reads Required: {RereadsRequired}\n")
        sys.stdout.write(f"{White}")

        SavedGlitchParameters.clear()
        FaultyCiphertexts.clear()
        FaultyCiphertextGroups.clear()
        GlitchFiredOutput = 0x07
        # Set RUN low
        ResetControl(Level=0, SuppressResponse=True)
        # Set 3V3_EN Low
        VoltageControl(Level=0, SuppressResponse=True)
        # Clear the UART buffer of any data
        while(uart0.any()):
            uart0.read(uart0.any())

    except Exception as e:
        sys.stdout.write("\n!!!!!!!! Error !!!!!!!!!\n")
        LastException = e
        rtc=RTC()
        LastExceptionTime = rtc.datetime()
        if Exception_trace == 2:
            sys.stdout.write("Exception Name: "+ type(e).__name__)
            sys.print_exception(e)

def CommandMode():
    global LED_Timer
    global wdt
    global uart0
    global LastException
    global Exception_trace, LastExceptionTime
    global VictimReadData
    
    ExitCommandMode = False

    # Start the LED flashing to show the script is executing
    LED_Timer.init(freq=4, mode=Timer.PERIODIC, callback=tick)
    sys.stdout.write('Welcome to the FIreFIght Control interface\n')
    sys.stdout.write('Press ? for help, or x to start the DFA attack demo\n')
    while ExitCommandMode == False:
        try:
            if uart0.any():
                sys.stdout.write('+') # command prompt to indicate Target bytes available
            else:
                sys.stdout.write(">") # command prompt
            command = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False, StoreBytesFromTarget = True)
            if command == 'a':
                Arm(ReplyLevel = 2)
            elif command == 'b':  # Print board config info
                PrintTextBlocks("Table")
            elif command == 'c':  # User defined UART comms to send to victim
                SendUartCommand()
            elif command == 'd':  # Set or get Glitch Delay
                SetGlitchDelay()
            elif command == 'D':  # Set or get Glitch Delay
                SetGlitchDelay(ArmStateMachine=True)
            elif command == 'e':  # View/clear last exception, or set Exception_trace level
                argument = WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False)
                if argument == '?':
                    PrintLastException()
                elif argument == 'c':
                    LastException = None
                    LastExceptionTime = None
                elif argument in ['0', '1', '2']:
                    Exception_trace = int(argument)
                else:
                    sys.stdout.write('!') # Write ! without logging as a new exception
            elif command == 'f':  # Fetch data from target and upload to host
                (VictimDataLength, BytesStillAvailable) = ReadTargetBytesIntoBuffer(MaximumBufferSize = 1024, PrintNewData = True)
                sys.stdout.write(VictimReadData) # Send it to host
                VictimReadData = bytearray() # Clear Victim ReadData
            elif command == 'g':  # GPIO Control
                GPIO_Command()
            elif  command == 'h' or command == 'H' or command == '?': # Help Menu
                WelcomeToCommandMode()
            elif command == 'i':  # 
                SetInputTriggerLevel(LevelToSetTo = None, ReplyLevel = 1)
            elif command == 'I':  # 
                SetInputTriggerLevel(LevelToSetTo = None, ArmStateMachine=True, ReplyLevel = 1)
            elif command == 'l':  # Set or get Glitch Length
                SetGlitchLength()
            elif command == 'L':  # Set or get Glitch Length
                SetGlitchLength(ArmStateMachine=True)
            elif command == 'm':  # look at Pico Memory
                ReadPicoMemory()
            elif command == 'n':  # Print Pi Pico iNfo
                PrintPicoInfo()
            elif command == 'o':
                SetGlitchOutputLevel(ReplyLevel = 1)
            elif command == 'O':
                SetGlitchOutputLevel(ArmStateMachine=True, ReplyLevel = 1)
            elif command == 'p':  # Print Pi Pico Python script
                PrintPython()
            elif command == 'r':  # Reset Control
                ResetControl()
            elif command == 's':  # State Machine Info
                StateMachineInfo()
            elif command == 't':  # Trigger control
                TriggerOutputControl('t')
            elif command == 'v':  # Victim Vcc Control
                VoltageControl()
            elif command == 'w':  # Enable Watchdog
                EnableWDT()
            elif command == 'X':  # Exit: reboot pico
                reset()
            elif command == 'x':  # Execute DFA attack
                ExecuteAttack()
            elif command == 'z':  # Reboot victim and arm glitcher
                ResetControl(Level = 0, SuppressResponse = True)
                # Could also kill power
                #VoltageControl(Level = 0, SuppressResponse = True)
                Arm(ReplyLevel = 1)
                # And restore power if needed
                #VoltageControl(Level = 1, SuppressResponse = True)
                ResetControl(Level = 1, SuppressResponse = True)
            elif command == ':':  # Check comms between host and control Pico is OK
                sys.stdout.write(")") # complete the smiley
            elif command == '-':  # Clear the UART input buffer
                while(uart0.any()):
                    uart0.read(uart0.any())
            elif command == '@':
                PrintTextBlocks("CopyrightNotice")
            elif command == '^':
                print(os.listdir())
                print("\nEnter Filename of Python script to execute: ")
                # Execute local python script 
                python_filename = WaitAndReadHostBytes(Count=32, AllowEarlyAbort = True, Attempts = None, ForwardBytesFromTarget = False)
                exec(open(python_filename).read())
            elif (ord(command) >= 0x20) and (ord(command) <= 0x27): # Set all LEDs in a single byte command
                LED_RED.value(ord(command)>>2 & 0x01)
                LED_GREEN.value(ord(command)>>1 & 0x01)
                LED_BLUE.value(ord(command) & 0x01)
            else:
                raise Exception("Invalid Command")
            
            # ReadTargetBytesIntoBuffer
            (VictimDataLength, BytesStillAvailable) = ReadTargetBytesIntoBuffer(MaximumBufferSize = 1024, PrintNewData = False)
            
        except Exception as e:
            # Clear any data from host in buffer so they aren't interpreted as the next command 
            for i in range(5):
                WaitAndReadHostByte(Attempts = 5, ForwardBytesFromTarget = False)
            # Indicate an error by returning '!'
            sys.stdout.write("!")

            # Store this as the last exception
            LastException = e
            rtc=RTC()
            LastExceptionTime = rtc.datetime()
            # Only print the exception trace if Exception_trace == 2
            if Exception_trace == 2:
                sys.stdout.write("Exception Name: "+ type(e).__name__)
                sys.print_exception(e)
            # Drop through back to the command loop
    LED_Timer.deinit()

def zerofill(value, filled_width):
    value_string = str(value)
    return '{:0>{w}}'.format(value_string, w=filled_width)

def PrintDateTime(rtc_data = None):
    rtc=RTC()
    now = rtc.datetime()
    sys.stdout.write(    f"\nCurrent Date/Time: {now[0]:04}/{now[1]:02}/{now[2]:02} {now[4]:02}:{now[5]:02}:{now[6]:02}")
    # (year, month, day, weekday, hour, minute, second, ms)
    if rtc_data:
        sys.stdout.write(f"\nEvent Date/Time:   {rtc_data[0]:04}/{rtc_data[1]:02}/{rtc_data[2]:02} {rtc_data[4]:02}:{rtc_data[5]:02}:{rtc_data[6]:02}\n")
    else:
        sys.stdout.write("\nNo Stored Events\n")

def WaitAndReadHostByte(Attempts = None, ForwardBytesFromTarget = False, StoreBytesFromTarget = False):
    # ForwardBytesFromTarget will send data received from victim to the host via USB immediately
    # StoreBytesFromTarget will add them to the VictimReadData bytearray for later transmission
    # ForwardBytesFromTarget takes priority if both are True

    global VictimReadData
    global VictimReadDataFull
    HostDataByte = None
    if None == Attempts:
        # Wait forever for a byte from the host to be available, then read it.
        while None == HostDataByte:
            if (sys.stdin in select.select([sys.stdin], [], [], 0)[0]):
                HostDataByte = sys.stdin.read(1) # Read one byte
            elif ForwardBytesFromTarget and uart0.any():        # UART0 data available
                sys.stdout.write(uart0.read(uart0.any())) # Read available UART0 bytes and write to the USBCDC port
            elif StoreBytesFromTarget:
                if len(VictimReadData)+uart0.any() < 1024:
                    VictimReadData.extend(uart0.read(uart0.any())) # Read uart0 data and append to VictimReadData
    elif Attempts > 0:
        # Wait Try to read a byte until maximum attempts reached
        while (None == HostDataByte) and (Attempts > 0):
            Attempts -= 1
            if (sys.stdin in select.select([sys.stdin], [], [], 0)[0]):
                HostDataByte = sys.stdin.read(1) # Read one byte
            elif ForwardBytesFromTarget and uart0.any():        # UART0 data available
                sys.stdout.write(uart0.read(uart0.any())) # Read available UART0 bytes and write to the USBCDC port
            else:
                utime.sleep_us(250)

    # Return either the read byte or None if no byte read within maximum attempt limit
    return HostDataByte

def WaitAndReadHostBytes(Count=1, AllowEarlyAbort = False, Attempts = None, ForwardBytesFromTarget = False):
    bytesread=""
    for i in range(Count):
        byteread = WaitAndReadHostByte(Attempts = Attempts, ForwardBytesFromTarget = ForwardBytesFromTarget)
        if AllowEarlyAbort and ((byteread == '\r') or byteread == '\n'):
            # Early abort
            break
        bytesread += byteread
    return bytesread

def SendCommandToTarget(CommandByteArray, InterbyteDelay=True, WaitUntilLastByteIsReadBack=True, EchoToHost = True):
    global uart0
    BytesWritten = 0
    ByteRead = None
    if WaitUntilLastByteIsReadBack:
        # Clear the read buffer from Target first
        while uart0.any():
            # Read one byte
            ByteRead = uart0.read(1)
            if EchoToHost and (not ByteRead is None):
                # Echo it to the host
                sys.stdout.write(ByteRead)
    
    for cur_byte in CommandByteArray:
        BytesWritten = uart0.write(bytes([cur_byte]))
        if 1 == BytesWritten:
            BytesWritten += 1
        else:
            # The write failed
            sys.stdout.write('Write Failed')
            return None
        
        if InterbyteDelay:
            utime.sleep_us(86)
        
        # If we're waiting until the last byte is sent
        if WaitUntilLastByteIsReadBack:
            ReadAttempt = 0
            ByteRead = None
            while (ReadAttempt < 1000) and (bytes([cur_byte]) != ByteRead):
                ReadAttempt += 1
                if uart0.any():
                    ByteRead = uart0.read(1)
                    if len(ByteRead)>1:
                        sys.stdout.write("!! ByteRead>1 !!")
                    if EchoToHost and (not ByteRead is None):
                        # Echo it to the host
                        sys.stdout.write(ByteRead)
            if (ReadAttempt >= 1000) and (bytes([cur_byte]) != ByteRead):
                sys.stdout.write('\r\n!!SendCommandToTarget Reached Max ReadAttempt\r\n')
                sys.stdout.write('(Ensure target is powered)!!\r\n')
    
    return ByteRead

# Call main()
while(True):
    try:
        main()
    except Exception as e:
        sys.stdout.write("!")
        LastException = e
        rtc=RTC()
        LastExceptionTime = rtc.datetime() # relative to power up unless date/time set
        if Exception_trace == 2:
            sys.stdout.write("Exception Name: "+ type(e).__name__)
            sys.print_exception(e)

# <CopyrightNotice>
"""
                    GNU GENERAL PUBLIC LICENSE
                       Version 3, 29 June 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

                            Preamble

  The GNU General Public License is a free, copyleft license for
software and other kinds of works.

  The licenses for most software and other practical works are designed
to take away your freedom to share and change the works.  By contrast,
the GNU General Public License is intended to guarantee your freedom to
share and change all versions of a program--to make sure it remains free
software for all its users.  We, the Free Software Foundation, use the
GNU General Public License for most of our software; it applies also to
any other work released this way by its authors.  You can apply it to
your programs, too.

  When we speak of free software, we are referring to freedom, not
price.  Our General Public Licenses are designed to make sure that you
have the freedom to distribute copies of free software (and charge for
them if you wish), that you receive source code or can get it if you
want it, that you can change the software or use pieces of it in new
free programs, and that you know you can do these things.

  To protect your rights, we need to prevent others from denying you
these rights or asking you to surrender the rights.  Therefore, you have
certain responsibilities if you distribute copies of the software, or if
you modify it: responsibilities to respect the freedom of others.

  For example, if you distribute copies of such a program, whether
gratis or for a fee, you must pass on to the recipients the same
freedoms that you received.  You must make sure that they, too, receive
or can get the source code.  And you must show them these terms so they
know their rights.

  Developers that use the GNU GPL protect your rights with two steps:
(1) assert copyright on the software, and (2) offer you this License
giving you legal permission to copy, distribute and/or modify it.

  For the developers' and authors' protection, the GPL clearly explains
that there is no warranty for this free software.  For both users' and
authors' sake, the GPL requires that modified versions be marked as
changed, so that their problems will not be attributed erroneously to
authors of previous versions.

  Some devices are designed to deny users access to install or run
modified versions of the software inside them, although the manufacturer
can do so.  This is fundamentally incompatible with the aim of
protecting users' freedom to change the software.  The systematic
pattern of such abuse occurs in the area of products for individuals to
use, which is precisely where it is most unacceptable.  Therefore, we
have designed this version of the GPL to prohibit the practice for those
products.  If such problems arise substantially in other domains, we
stand ready to extend this provision to those domains in future versions
of the GPL, as needed to protect the freedom of users.

  Finally, every program is threatened constantly by software patents.
States should not allow patents to restrict development and use of
software on general-purpose computers, but in those that do, we wish to
avoid the special danger that patents applied to a free program could
make it effectively proprietary.  To prevent this, the GPL assures that
patents cannot be used to render the program non-free.

  The precise terms and conditions for copying, distribution and
modification follow.

                       TERMS AND CONDITIONS

  0. Definitions.

  "This License" refers to version 3 of the GNU General Public License.

  "Copyright" also means copyright-like laws that apply to other kinds of
works, such as semiconductor masks.

  "The Program" refers to any copyrightable work licensed under this
License.  Each licensee is addressed as "you".  "Licensees" and
"recipients" may be individuals or organizations.

  To "modify" a work means to copy from or adapt all or part of the work
in a fashion requiring copyright permission, other than the making of an
exact copy.  The resulting work is called a "modified version" of the
earlier work or a work "based on" the earlier work.

  A "covered work" means either the unmodified Program or a work based
on the Program.

  To "propagate" a work means to do anything with it that, without
permission, would make you directly or secondarily liable for
infringement under applicable copyright law, except executing it on a
computer or modifying a private copy.  Propagation includes copying,
distribution (with or without modification), making available to the
public, and in some countries other activities as well.

  To "convey" a work means any kind of propagation that enables other
parties to make or receive copies.  Mere interaction with a user through
a computer network, with no transfer of a copy, is not conveying.

  An interactive user interface displays "Appropriate Legal Notices"
to the extent that it includes a convenient and prominently visible
feature that (1) displays an appropriate copyright notice, and (2)
tells the user that there is no warranty for the work (except to the
extent that warranties are provided), that licensees may convey the
work under this License, and how to view a copy of this License.  If
the interface presents a list of user commands or options, such as a
menu, a prominent item in the list meets this criterion.

  1. Source Code.

  The "source code" for a work means the preferred form of the work
for making modifications to it.  "Object code" means any non-source
form of a work.

  A "Standard Interface" means an interface that either is an official
standard defined by a recognized standards body, or, in the case of
interfaces specified for a particular programming language, one that
is widely used among developers working in that language.

  The "System Libraries" of an executable work include anything, other
than the work as a whole, that (a) is included in the normal form of
packaging a Major Component, but which is not part of that Major
Component, and (b) serves only to enable use of the work with that
Major Component, or to implement a Standard Interface for which an
implementation is available to the public in source code form.  A
"Major Component", in this context, means a major essential component
(kernel, window system, and so on) of the specific operating system
(if any) on which the executable work runs, or a compiler used to
produce the work, or an object code interpreter used to run it.

  The "Corresponding Source" for a work in object code form means all
the source code needed to generate, install, and (for an executable
work) run the object code and to modify the work, including scripts to
control those activities.  However, it does not include the work's
System Libraries, or general-purpose tools or generally available free
programs which are used unmodified in performing those activities but
which are not part of the work.  For example, Corresponding Source
includes interface definition files associated with source files for
the work, and the source code for shared libraries and dynamically
linked subprograms that the work is specifically designed to require,
such as by intimate data communication or control flow between those
subprograms and other parts of the work.

  The Corresponding Source need not include anything that users
can regenerate automatically from other parts of the Corresponding
Source.

  The Corresponding Source for a work in source code form is that
same work.

  2. Basic Permissions.

  All rights granted under this License are granted for the term of
copyright on the Program, and are irrevocable provided the stated
conditions are met.  This License explicitly affirms your unlimited
permission to run the unmodified Program.  The output from running a
covered work is covered by this License only if the output, given its
content, constitutes a covered work.  This License acknowledges your
rights of fair use or other equivalent, as provided by copyright law.

  You may make, run and propagate covered works that you do not
convey, without conditions so long as your license otherwise remains
in force.  You may convey covered works to others for the sole purpose
of having them make modifications exclusively for you, or provide you
with facilities for running those works, provided that you comply with
the terms of this License in conveying all material for which you do
not control copyright.  Those thus making or running the covered works
for you must do so exclusively on your behalf, under your direction
and control, on terms that prohibit them from making any copies of
your copyrighted material outside their relationship with you.

  Conveying under any other circumstances is permitted solely under
the conditions stated below.  Sublicensing is not allowed; section 10
makes it unnecessary.

  3. Protecting Users' Legal Rights From Anti-Circumvention Law.

  No covered work shall be deemed part of an effective technological
measure under any applicable law fulfilling obligations under article
11 of the WIPO copyright treaty adopted on 20 December 1996, or
similar laws prohibiting or restricting circumvention of such
measures.

  When you convey a covered work, you waive any legal power to forbid
circumvention of technological measures to the extent such circumvention
is effected by exercising rights under this License with respect to
the covered work, and you disclaim any intention to limit operation or
modification of the work as a means of enforcing, against the work's
users, your or third parties' legal rights to forbid circumvention of
technological measures.

  4. Conveying Verbatim Copies.

  You may convey verbatim copies of the Program's source code as you
receive it, in any medium, provided that you conspicuously and
appropriately publish on each copy an appropriate copyright notice;
keep intact all notices stating that this License and any
non-permissive terms added in accord with section 7 apply to the code;
keep intact all notices of the absence of any warranty; and give all
recipients a copy of this License along with the Program.

  You may charge any price or no price for each copy that you convey,
and you may offer support or warranty protection for a fee.

  5. Conveying Modified Source Versions.

  You may convey a work based on the Program, or the modifications to
produce it from the Program, in the form of source code under the
terms of section 4, provided that you also meet all of these conditions:

    a) The work must carry prominent notices stating that you modified
    it, and giving a relevant date.

    b) The work must carry prominent notices stating that it is
    released under this License and any conditions added under section
    7.  This requirement modifies the requirement in section 4 to
    "keep intact all notices".

    c) You must license the entire work, as a whole, under this
    License to anyone who comes into possession of a copy.  This
    License will therefore apply, along with any applicable section 7
    additional terms, to the whole of the work, and all its parts,
    regardless of how they are packaged.  This License gives no
    permission to license the work in any other way, but it does not
    invalidate such permission if you have separately received it.

    d) If the work has interactive user interfaces, each must display
    Appropriate Legal Notices; however, if the Program has interactive
    interfaces that do not display Appropriate Legal Notices, your
    work need not make them do so.

  A compilation of a covered work with other separate and independent
works, which are not by their nature extensions of the covered work,
and which are not combined with it such as to form a larger program,
in or on a volume of a storage or distribution medium, is called an
"aggregate" if the compilation and its resulting copyright are not
used to limit the access or legal rights of the compilation's users
beyond what the individual works permit.  Inclusion of a covered work
in an aggregate does not cause this License to apply to the other
parts of the aggregate.

  6. Conveying Non-Source Forms.

  You may convey a covered work in object code form under the terms
of sections 4 and 5, provided that you also convey the
machine-readable Corresponding Source under the terms of this License,
in one of these ways:

    a) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by the
    Corresponding Source fixed on a durable physical medium
    customarily used for software interchange.

    b) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by a
    written offer, valid for at least three years and valid for as
    long as you offer spare parts or customer support for that product
    model, to give anyone who possesses the object code either (1) a
    copy of the Corresponding Source for all the software in the
    product that is covered by this License, on a durable physical
    medium customarily used for software interchange, for a price no
    more than your reasonable cost of physically performing this
    conveying of source, or (2) access to copy the
    Corresponding Source from a network server at no charge.

    c) Convey individual copies of the object code with a copy of the
    written offer to provide the Corresponding Source.  This
    alternative is allowed only occasionally and noncommercially, and
    only if you received the object code with such an offer, in accord
    with subsection 6b.

    d) Convey the object code by offering access from a designated
    place (gratis or for a charge), and offer equivalent access to the
    Corresponding Source in the same way through the same place at no
    further charge.  You need not require recipients to copy the
    Corresponding Source along with the object code.  If the place to
    copy the object code is a network server, the Corresponding Source
    may be on a different server (operated by you or a third party)
    that supports equivalent copying facilities, provided you maintain
    clear directions next to the object code saying where to find the
    Corresponding Source.  Regardless of what server hosts the
    Corresponding Source, you remain obligated to ensure that it is
    available for as long as needed to satisfy these requirements.

    e) Convey the object code using peer-to-peer transmission, provided
    you inform other peers where the object code and Corresponding
    Source of the work are being offered to the general public at no
    charge under subsection 6d.

  A separable portion of the object code, whose source code is excluded
from the Corresponding Source as a System Library, need not be
included in conveying the object code work.

  A "User Product" is either (1) a "consumer product", which means any
tangible personal property which is normally used for personal, family,
or household purposes, or (2) anything designed or sold for incorporation
into a dwelling.  In determining whether a product is a consumer product,
doubtful cases shall be resolved in favor of coverage.  For a particular
product received by a particular user, "normally used" refers to a
typical or common use of that class of product, regardless of the status
of the particular user or of the way in which the particular user
actually uses, or expects or is expected to use, the product.  A product
is a consumer product regardless of whether the product has substantial
commercial, industrial or non-consumer uses, unless such uses represent
the only significant mode of use of the product.

  "Installation Information" for a User Product means any methods,
procedures, authorization keys, or other information required to install
and execute modified versions of a covered work in that User Product from
a modified version of its Corresponding Source.  The information must
suffice to ensure that the continued functioning of the modified object
code is in no case prevented or interfered with solely because
modification has been made.

  If you convey an object code work under this section in, or with, or
specifically for use in, a User Product, and the conveying occurs as
part of a transaction in which the right of possession and use of the
User Product is transferred to the recipient in perpetuity or for a
fixed term (regardless of how the transaction is characterized), the
Corresponding Source conveyed under this section must be accompanied
by the Installation Information.  But this requirement does not apply
if neither you nor any third party retains the ability to install
modified object code on the User Product (for example, the work has
been installed in ROM).

  The requirement to provide Installation Information does not include a
requirement to continue to provide support service, warranty, or updates
for a work that has been modified or installed by the recipient, or for
the User Product in which it has been modified or installed.  Access to a
network may be denied when the modification itself materially and
adversely affects the operation of the network or violates the rules and
protocols for communication across the network.

  Corresponding Source conveyed, and Installation Information provided,
in accord with this section must be in a format that is publicly
documented (and with an implementation available to the public in
source code form), and must require no special password or key for
unpacking, reading or copying.

  7. Additional Terms.

  "Additional permissions" are terms that supplement the terms of this
License by making exceptions from one or more of its conditions.
Additional permissions that are applicable to the entire Program shall
be treated as though they were included in this License, to the extent
that they are valid under applicable law.  If additional permissions
apply only to part of the Program, that part may be used separately
under those permissions, but the entire Program remains governed by
this License without regard to the additional permissions.

  When you convey a copy of a covered work, you may at your option
remove any additional permissions from that copy, or from any part of
it.  (Additional permissions may be written to require their own
removal in certain cases when you modify the work.)  You may place
additional permissions on material, added by you to a covered work,
for which you have or can give appropriate copyright permission.

  Notwithstanding any other provision of this License, for material you
add to a covered work, you may (if authorized by the copyright holders of
that material) supplement the terms of this License with terms:

    a) Disclaiming warranty or limiting liability differently from the
    terms of sections 15 and 16 of this License; or

    b) Requiring preservation of specified reasonable legal notices or
    author attributions in that material or in the Appropriate Legal
    Notices displayed by works containing it; or

    c) Prohibiting misrepresentation of the origin of that material, or
    requiring that modified versions of such material be marked in
    reasonable ways as different from the original version; or

    d) Limiting the use for publicity purposes of names of licensors or
    authors of the material; or

    e) Declining to grant rights under trademark law for use of some
    trade names, trademarks, or service marks; or

    f) Requiring indemnification of licensors and authors of that
    material by anyone who conveys the material (or modified versions of
    it) with contractual assumptions of liability to the recipient, for
    any liability that these contractual assumptions directly impose on
    those licensors and authors.

  All other non-permissive additional terms are considered "further
restrictions" within the meaning of section 10.  If the Program as you
received it, or any part of it, contains a notice stating that it is
governed by this License along with a term that is a further
restriction, you may remove that term.  If a license document contains
a further restriction but permits relicensing or conveying under this
License, you may add to a covered work material governed by the terms
of that license document, provided that the further restriction does
not survive such relicensing or conveying.

  If you add terms to a covered work in accord with this section, you
must place, in the relevant source files, a statement of the
additional terms that apply to those files, or a notice indicating
where to find the applicable terms.

  Additional terms, permissive or non-permissive, may be stated in the
form of a separately written license, or stated as exceptions;
the above requirements apply either way.

  8. Termination.

  You may not propagate or modify a covered work except as expressly
provided under this License.  Any attempt otherwise to propagate or
modify it is void, and will automatically terminate your rights under
this License (including any patent licenses granted under the third
paragraph of section 11).

  However, if you cease all violation of this License, then your
license from a particular copyright holder is reinstated (a)
provisionally, unless and until the copyright holder explicitly and
finally terminates your license, and (b) permanently, if the copyright
holder fails to notify you of the violation by some reasonable means
prior to 60 days after the cessation.

  Moreover, your license from a particular copyright holder is
reinstated permanently if the copyright holder notifies you of the
violation by some reasonable means, this is the first time you have
received notice of violation of this License (for any work) from that
copyright holder, and you cure the violation prior to 30 days after
your receipt of the notice.

  Termination of your rights under this section does not terminate the
licenses of parties who have received copies or rights from you under
this License.  If your rights have been terminated and not permanently
reinstated, you do not qualify to receive new licenses for the same
material under section 10.

  9. Acceptance Not Required for Having Copies.

  You are not required to accept this License in order to receive or
run a copy of the Program.  Ancillary propagation of a covered work
occurring solely as a consequence of using peer-to-peer transmission
to receive a copy likewise does not require acceptance.  However,
nothing other than this License grants you permission to propagate or
modify any covered work.  These actions infringe copyright if you do
not accept this License.  Therefore, by modifying or propagating a
covered work, you indicate your acceptance of this License to do so.

  10. Automatic Licensing of Downstream Recipients.

  Each time you convey a covered work, the recipient automatically
receives a license from the original licensors, to run, modify and
propagate that work, subject to this License.  You are not responsible
for enforcing compliance by third parties with this License.

  An "entity transaction" is a transaction transferring control of an
organization, or substantially all assets of one, or subdividing an
organization, or merging organizations.  If propagation of a covered
work results from an entity transaction, each party to that
transaction who receives a copy of the work also receives whatever
licenses to the work the party's predecessor in interest had or could
give under the previous paragraph, plus a right to possession of the
Corresponding Source of the work from the predecessor in interest, if
the predecessor has it or can get it with reasonable efforts.

  You may not impose any further restrictions on the exercise of the
rights granted or affirmed under this License.  For example, you may
not impose a license fee, royalty, or other charge for exercise of
rights granted under this License, and you may not initiate litigation
(including a cross-claim or counterclaim in a lawsuit) alleging that
any patent claim is infringed by making, using, selling, offering for
sale, or importing the Program or any portion of it.

  11. Patents.

  A "contributor" is a copyright holder who authorizes use under this
License of the Program or a work on which the Program is based.  The
work thus licensed is called the contributor's "contributor version".

  A contributor's "essential patent claims" are all patent claims
owned or controlled by the contributor, whether already acquired or
hereafter acquired, that would be infringed by some manner, permitted
by this License, of making, using, or selling its contributor version,
but do not include claims that would be infringed only as a
consequence of further modification of the contributor version.  For
purposes of this definition, "control" includes the right to grant
patent sublicenses in a manner consistent with the requirements of
this License.

  Each contributor grants you a non-exclusive, worldwide, royalty-free
patent license under the contributor's essential patent claims, to
make, use, sell, offer for sale, import and otherwise run, modify and
propagate the contents of its contributor version.

  In the following three paragraphs, a "patent license" is any express
agreement or commitment, however denominated, not to enforce a patent
(such as an express permission to practice a patent or covenant not to
sue for patent infringement).  To "grant" such a patent license to a
party means to make such an agreement or commitment not to enforce a
patent against the party.

  If you convey a covered work, knowingly relying on a patent license,
and the Corresponding Source of the work is not available for anyone
to copy, free of charge and under the terms of this License, through a
publicly available network server or other readily accessible means,
then you must either (1) cause the Corresponding Source to be so
available, or (2) arrange to deprive yourself of the benefit of the
patent license for this particular work, or (3) arrange, in a manner
consistent with the requirements of this License, to extend the patent
license to downstream recipients.  "Knowingly relying" means you have
actual knowledge that, but for the patent license, your conveying the
covered work in a country, or your recipient's use of the covered work
in a country, would infringe one or more identifiable patents in that
country that you have reason to believe are valid.

  If, pursuant to or in connection with a single transaction or
arrangement, you convey, or propagate by procuring conveyance of, a
covered work, and grant a patent license to some of the parties
receiving the covered work authorizing them to use, propagate, modify
or convey a specific copy of the covered work, then the patent license
you grant is automatically extended to all recipients of the covered
work and works based on it.

  A patent license is "discriminatory" if it does not include within
the scope of its coverage, prohibits the exercise of, or is
conditioned on the non-exercise of one or more of the rights that are
specifically granted under this License.  You may not convey a covered
work if you are a party to an arrangement with a third party that is
in the business of distributing software, under which you make payment
to the third party based on the extent of your activity of conveying
the work, and under which the third party grants, to any of the
parties who would receive the covered work from you, a discriminatory
patent license (a) in connection with copies of the covered work
conveyed by you (or copies made from those copies), or (b) primarily
for and in connection with specific products or compilations that
contain the covered work, unless you entered into that arrangement,
or that patent license was granted, prior to 28 March 2007.

  Nothing in this License shall be construed as excluding or limiting
any implied license or other defenses to infringement that may
otherwise be available to you under applicable patent law.

  12. No Surrender of Others' Freedom.

  If conditions are imposed on you (whether by court order, agreement or
otherwise) that contradict the conditions of this License, they do not
excuse you from the conditions of this License.  If you cannot convey a
covered work so as to satisfy simultaneously your obligations under this
License and any other pertinent obligations, then as a consequence you may
not convey it at all.  For example, if you agree to terms that obligate you
to collect a royalty for further conveying from those to whom you convey
the Program, the only way you could satisfy both those terms and this
License would be to refrain entirely from conveying the Program.

  13. Use with the GNU Affero General Public License.

  Notwithstanding any other provision of this License, you have
permission to link or combine any covered work with a work licensed
under version 3 of the GNU Affero General Public License into a single
combined work, and to convey the resulting work.  The terms of this
License will continue to apply to the part which is the covered work,
but the special requirements of the GNU Affero General Public License,
section 13, concerning interaction through a network will apply to the
combination as such.

  14. Revised Versions of this License.

  The Free Software Foundation may publish revised and/or new versions of
the GNU General Public License from time to time.  Such new versions will
be similar in spirit to the present version, but may differ in detail to
address new problems or concerns.

  Each version is given a distinguishing version number.  If the
Program specifies that a certain numbered version of the GNU General
Public License "or any later version" applies to it, you have the
option of following the terms and conditions either of that numbered
version or of any later version published by the Free Software
Foundation.  If the Program does not specify a version number of the
GNU General Public License, you may choose any version ever published
by the Free Software Foundation.

  If the Program specifies that a proxy can decide which future
versions of the GNU General Public License can be used, that proxy's
public statement of acceptance of a version permanently authorizes you
to choose that version for the Program.

  Later license versions may give you additional or different
permissions.  However, no additional obligations are imposed on any
author or copyright holder as a result of your choosing to follow a
later version.

  15. Disclaimer of Warranty.

  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY
OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM
IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF
ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

  16. Limitation of Liability.

  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS
THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY
GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF
DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD
PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),
EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF
SUCH DAMAGES.

  17. Interpretation of Sections 15 and 16.

  If the disclaimer of warranty and limitation of liability provided
above cannot be given local legal effect according to their terms,
reviewing courts shall apply local law that most closely approximates
an absolute waiver of all civil liability in connection with the
Program, unless a warranty or assumption of liability accompanies a
copy of the Program in return for a fee.

                     END OF TERMS AND CONDITIONS

            How to Apply These Terms to Your New Programs

  If you develop a new program, and you want it to be of the greatest
possible use to the public, the best way to achieve this is to make it
free software which everyone can redistribute and change under these terms.

  To do so, attach the following notices to the program.  It is safest
to attach them to the start of each source file to most effectively
state the exclusion of warranty; and each file should have at least
the "copyright" line and a pointer to where the full notice is found.

    <one line to give the program's name and a brief idea of what it does.>
    Copyright (C) <year>  <name of author>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

Also add information on how to contact you by electronic and paper mail.

  If the program does terminal interaction, make it output a short
notice like this when it starts in an interactive mode:

    <program>  Copyright (C) <year>  <name of author>
    This program comes with ABSOLUTELY NO WARRANTY; for details type `show w'.
    This is free software, and you are welcome to redistribute it
    under certain conditions; type `show c' for details.

The hypothetical commands `show w' and `show c' should show the appropriate
parts of the General Public License.  Of course, your program's commands
might be different; for a GUI interface, you would use an "about box".

  You should also get your employer (if you work as a programmer) or school,
if any, to sign a "copyright disclaimer" for the program, if necessary.
For more information on this, and how to apply and follow the GNU GPL, see
<https://www.gnu.org/licenses/>.

  The GNU General Public License does not permit incorporating your program
into proprietary programs.  If your program is a subroutine library, you
may consider it more useful to permit linking proprietary applications with
the library.  If this is what you want to do, use the GNU Lesser General
Public License instead of this License.  But first, please read
<https://www.gnu.org/licenses/why-not-lgpl.html>.
"""
# </CopyrightNotice> 
"""
# <Version> 
30/11/2024  14:51           161,694 FireFightPico2.py
Download time: 2024-12-04 14:46:01,
# </Version> 
"""
