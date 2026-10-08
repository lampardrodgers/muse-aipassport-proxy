#!/usr/bin/env python3
"""Read a private .env without executing it; provision Wi-Fi/proxy over USB."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]


def read_env(path):
    result = {}
    for number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in result:
            raise ValueError(f'Invalid or duplicate setting at line {number}')
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                raise ValueError(f'Invalid quoted value at line {number}') from None
        elif value.startswith("'"):
            if len(value) < 2 or not value.endswith("'"):
                raise ValueError(f'Invalid quoted value at line {number}')
            value = value[1:-1]
        if not isinstance(value, str) or any(c in value for c in '\r\n\x00'):
            raise ValueError(f'Unsupported control character at line {number}')
        result[key] = value
    return result


def profiles(env):
    result = []
    for slot in range(1, 5):
        prefix = f'WIFI_{slot}_'
        ssid = env.get(prefix + 'SSID', '')
        if not ssid:
            continue
        password = env.get(prefix + 'PASSWORD', '')
        host = env.get(prefix + 'PROXY_HOST', 'gateway')
        port = int(env.get(prefix + 'PROXY_PORT', '1082'))
        if not 1 <= len(ssid.encode()) <= 32 or len(password.encode()) > 63:
            raise ValueError(f'Invalid Wi-Fi length in slot {slot}')
        if host != 'gateway':
            try:
                addr = ipaddress.IPv4Address(host)
            except ValueError:
                raise ValueError(f'Invalid proxy address in slot {slot}') from None
            if int(addr) >> 24 in (0, 127) or int(addr) >> 24 >= 224:
                raise ValueError(f'Invalid proxy address in slot {slot}')
        if not 1 <= port <= 65535:
            raise ValueError(f'Invalid proxy port in slot {slot}')
        result.append((dict(slot=slot, ssid=ssid, host=host, port=port), password))
    if len({p['ssid'] for p, _ in result}) != len(result):
        raise ValueError('Each profile must use a distinct SSID')
    return result


def command(device, value, marker):
    wire = ('>' + value + '\n').encode()
    if len(wire) > 900:
        raise ValueError('Command exceeds console capacity')
    device.reset_input_buffer()
    device.write(wire)
    device.flush()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        line = device.readline().decode(errors='replace').strip()
        # Never print raw device logs; they can contain SSIDs or credentials.
        if line.startswith('@proxy.error'):
            raise RuntimeError('Device rejected proxy configuration')
        if marker in line:
            if ' -> error:' in line:
                raise RuntimeError('Device rejected Wi-Fi configuration')
            if marker.startswith('@proxy.') or line.endswith(' -> ok'):
                return
    raise RuntimeError('No acknowledgement from device; configuration may be partially applied')


def apply(env, selected):
    import serial
    items = profiles(env)
    current = next((item for item in items if item[0]['slot'] == selected), None)
    if current is None:
        raise ValueError('Selected Wi-Fi slot has no SSID')
    port = env.get('SERIAL_PORT', '')
    if not port:
        raise ValueError('SERIAL_PORT is required')
    with serial.Serial(port=None, baudrate=115200, timeout=.2, write_timeout=3) as device:
        device.dtr = False
        device.rts = False
        device.port = port
        device.open()
        # Opening native USB may reset the board; wait until its console is ready.
        time.sleep(12)
        for profile, _ in items:
            command(device, 'proxy.set=' + json.dumps(profile, ensure_ascii=False), '@proxy.ok')
        profile, password = current
        command(device, 'wifi.ssid=' + profile['ssid'], 'cmd wifi.ssid=')
        command(device, 'wifi.pass=' + password, 'cmd wifi.pass ->')
        command(device, 'wifi.connect', 'cmd wifi.connect=')
    print('Proxy profiles saved and selected Wi-Fi connection requested. Pairing still uses the Muse App.')
    print('A command acknowledgement does not verify Internet access. Check the device connection status.')


def build_config(env):
    path = ROOT / 'esp32/build-muse-ai-passport/sdkconfig'
    if not path.exists():
        raise ValueError('Generate sdkconfig using the README instructions first')
    token = env.get('MUSE_SDK_TOKEN', '')
    if not token or not re.fullmatch(r'mgst_[A-Za-z0-9_-]+', token):
        raise ValueError('MUSE_SDK_TOKEN is missing or invalid')
    updates = {'CONFIG_GADGET_SDK_TOKEN': json.dumps(token),
               'CONFIG_ESP_MAIN_TASK_STACK_SIZE': '12288',
               'CONFIG_MAIN_TASK_STACK_SIZE': '12288'}
    lines = [line for line in path.read_text().splitlines()
             if line.partition('=')[0] not in updates]
    path.chmod(0o600)
    path.write_text('\n'.join(lines + [key + '=' + val for key, val in updates.items()]) + '\n')
    print('Private build configuration updated; token was not printed. Rebuild to apply it.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'apply', 'build-config'])
    parser.add_argument('--env', type=Path, default=ROOT / '.env')
    parser.add_argument('--slot', type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()
    try:
        env = read_env(args.env)
        if args.action == 'check':
            print(f'Configuration parsed; {len(profiles(env))} Wi-Fi/proxy profile(s). No device changes.')
        elif args.action == 'apply':
            apply(env, args.slot)
        else:
            build_config(env)
    except (OSError, ValueError, RuntimeError) as error:
        # Numeric conversion errors may contain user input; do not echo them.
        if isinstance(error, ValueError) and str(error).startswith('invalid literal'):
            raise SystemExit('A numeric setting is invalid') from None
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
