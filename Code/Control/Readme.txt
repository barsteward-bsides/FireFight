The FIreFIght board holds 2 Pi Pico2 boards, one referred to as the "Control" (on the left side), and one referred to as the "Victim" (On the right hand side)
Solder the two 20-pin headers pins on the underside of both Pico2 boards (or buy Pico2 H when available).
Place solder blob on Victim Pico TP7 (Lowest test point on underside of board, unlabelled, with 2 small holes).
Solder flying wire to TP7 - best to run this along the board and superglue it too, to avoid placing stress on TP7 during the next steps.
When the glue is dry, insert both Pico2 boards into the FIreFIght Mini boards, taking care to route the wire from victim TP7 carefully through PCB cut-out immediately below it, and making sure to place the usb port at the top of the PCB, near the BSides logo.
Solder the flying wire from victim TP7 to the large rectangular pad on the underside of the Firefight PCB, just below the cut-out.
Check or populate the jumpers as follows: * indicates fitted jumper.
==============================================================
J2 Left side of Victim Pico. (Left side is odd header pins numbers, right side is even):
==============================================================
 J2.1-2:   "GP0" Do not fit
 J2.3-4:   "GP1" Do not fit
*J2.5-6:   "GND" Fit Jumper
 J2.7-8:   "GP2" Do not fit
 J2.9-10:  "GP3" Do not fit
___________________________
 J2.11-12: "GP4" Do not fit
 J2.13-14: "GP5" Do not fit
*J2.15-16: "GND" Fit Jumper
 J2.17-18: "GP6" Do not fit
 J2.19-20: "GP7" Do not fit
___________________________
 J2.21-22: "GP8"  Do not fit
 J2.23-24: "GP9"  Do not fit
*J2.25-26: "GND"  Fit Jumper
 J2.27-28: "GP10" Do not fit
 J2.29-30: "GP11" Do not fit
___________________________
*J2.31-32: "GP12" Fit Jumper (Connects Victim UART0 Tx to Control UART0 Rx)
*J2.33-34: "GP13" Fit Jumper (Connects Victim UART0 Rx to Control UART0 Tx)
*J2.35-36: "GND"  Fit Jumper
*J2.37-38: "GP14" Fit Jumper (GP14 Red LED)
*J2.39-40: "GP15" Fit Jumper (GP15 Green LED)
___________________________

============================================================================
J8 (Left side is odd header pins numbers, right side is even):
============================================================================
 J8.1-2:   "VBUS"     Do not fit
*J8.3-4:   "VSYS"     Fit Jumper (Connects Victim VSYS to Control VSYS, via VSYS Bridge Jumper)
*J8.5-6:   "GND"      Fit Jumper
*J8.7-8:   "3V3_EN"   Fit Jumper (Connects Control GP20, via J1, to Victim 3V3_EN)
 J8.9-10:  "3V3"      Do not fit
___________________________
 J8.11-12: "ADC_VREF" Do not fit 
 J8.13-14: "GP28"     Do not fit
*J8.15-16: "AGND"     Fit Jumper
 J8.17-18: "GP27"     Do not fit
*J8.19-20: "GP26"     Fit Jumper (Victim Trigger, connects Victim GP26 to Control GP26)
___________________________
*J8.21-22: "RUN"      Fit jumper (Connects Control GP22 to Victim RUN)
 J8.23-24: "GP22"     Do not fit
*J8.25-26: "GND"      Fit jumper
 J8.27-28: "GP21"     Do not fit
 J8.29-30: "GP20"     Do not fit
___________________________
 J8.31-32: "GP19"     Do not fit
 J8.33-34: "GP18"     Do not fit
*J8.35-36: "GND"      Fit jumper
 J8.37-38: "GP17"     Do not fit
*J8.39-40: "GP16"     Fit jumper (Connects Victim GP16 to Blue LED)
___________________________

========================================
Other Jumpers
========================================
*J1: "3V3 EN"        Will Fit Jumper later, after programming Victim (Connects Control GP20 to Victim )
*J3  "Reset Control" Fit Jumper (Connects Control GP22 to Victim RUN)                                                                                                                                      
*J4: "VSYS Bridge"   Fit Jumper (Connects Control VSYS to Victim VSYS)
*J6: "J6"            Fit Jumper (Connects MOSFET output to pad on back of PCB, which should be connected to Victim TP7)


Victim Programming:
Ensure J1 is not fitted, then hold Victim BOOTSEL button whilst plugging in microUSB cable to Victim
Drag "Victim\SW_AES\build\SW_AES.uf2" onto the newly appeared RP2350 drive (which will then disconnect)
The 3 Victim LEDs should light up.
Unplug the USB cable and fit the J1 jumper.

Control Programming:
Hold Control BOOTSEL button whilst plugging in microUSB cable to Control.
Drag "RPI_PICO2-20241025-v1.24.0.uf2" onto the newly appeared RP2350 drive (which will then disconnect).
Open TeraTerm (or any other UART terminal) and identify the newly appeared COM port. Close TeraTerm
Edit Line 6 of "downloadToControlPico.bat" to set the COM port, e.g. : set USE_COMPORT=COM9
Save "downloadToControlPico.bat"
Run "downloadToControlPico.bat", to copy the required Python files onto the Control Pico 2
At the >>> prompt press Ctrl+d
Wait for the message "Welcome to the FIreFIght Control interface
                      Press ? for help, or x to start the DFA attack demo"
The green LED on the Control Pico2 board should begin flashing
At the > prompt, press x
Press Enter 5 times to accept the default glitch parameters



