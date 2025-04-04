import machine
import utime
import ujson

# --- Configuration ---

# Setup UART0: adjust TX/RX pins as needed (e.g., GP0 for TX and GP1 for RX)
uart = machine.UART(0, baudrate=115200, tx=machine.Pin(16), rx=machine.Pin(17))

# Define PWM output pins for 8 channels (adjust pin numbers as needed)
pwm_pin_numbers = [0, 2, 4, 6, 8, 10, 12, 14]
pwm_channels = []

# PWM frequency for servos/ESCs is typically 50Hz (period = 20,000 µs)
PWM_FREQ = 50

# --- Initialize PWM channels ---
for pin_num in pwm_pin_numbers:
    pin = machine.Pin(pin_num)
    pwm = machine.PWM(pin)
    pwm.freq(PWM_FREQ)
    pwm_channels.append(pwm)

def pulse_to_duty(pulse_us):
    """
    Convert pulse width in microseconds to a 16-bit duty value.
    For 50 Hz, period = 20,000 µs.
    """
    period_us = 20000  # 20 ms period at 50 Hz
    duty = int((pulse_us / period_us) * 65535)
    # Clamp the value to the 16-bit range
    if duty < 0:
        duty = 0
    elif duty > 65535:
        duty = 65535
    return duty

def update_pwms(motor_values):
    """
    Expects motor_values to be a list of 8 pulse widths (in microseconds).
    Updates each PWM channel accordingly.
    """
    for ch in range(8):
        pulse = motor_values[ch]
        duty = pulse_to_duty(pulse)
        pwm_channels[ch].duty_u16(duty)
        # Optionally print debug info:
        uart.write("Channel {}: pulse {} µs => duty {}".format(ch, pulse, duty))

# --- LED Blinking Setup ---
# On the Raspberry Pi Pico the built-in LED is usually on GP25.
led = machine.Pin(25, machine.Pin.OUT)
blink_interval_ms = 500  # Blink every 500 milliseconds
last_toggle = utime.ticks_ms()

# --- Main Loop ---
while True:
    # LED blink handling (non-blocking)
    current_time = utime.ticks_ms()
    if utime.ticks_diff(current_time, last_toggle) >= blink_interval_ms:
        led.toggle()
        last_toggle = current_time

    # Check for incoming UART data
    if uart.any():
        # Read a line (assumes messages end with newline)
        line = uart.readline()
        if line:
            try:
                # Remove any extra whitespace/newline characters
                data_str = line.strip()
                # Parse JSON; expecting: {"motor_values": [val0, val1, ..., val7]}
                data = ujson.loads(data_str)
                motor_values = data.get("motor_values", [])
                if isinstance(motor_values, list) and len(motor_values) == 8:
                    update_pwms(motor_values)
                    # Send an acknowledgment back over UART:
                    uart.write("Updated motor frequencies\n")
                else:
                    uart.write("Error: Expected 8 motor values\n")
            except Exception as e:
                uart.write("JSON parse error\n")
                print("JSON parse error:", e)
    utime.sleep(0.01)

