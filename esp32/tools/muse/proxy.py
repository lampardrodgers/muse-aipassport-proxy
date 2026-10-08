#!/usr/bin/env python3
"""Manage Wi-Fi-specific proxy profiles over the Passport USB console."""
import argparse
import ipaddress
import json
import time
import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='USB serial port')
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('list', 'status', 'reboot'):
        sub.add_parser(action)
    set_parser = sub.add_parser('set')
    set_parser.add_argument('--slot', type=int, choices=range(1, 5), required=True)
    set_parser.add_argument('--ssid', required=True)
    set_parser.add_argument('--host', required=True)
    set_parser.add_argument('--proxy-port', type=int, required=True)
    delete_parser = sub.add_parser('delete')
    delete_parser.add_argument('--slot', type=int, choices=range(1, 5), required=True)
    args = parser.parse_args()
    if args.action == 'set':
        if not 1 <= len(args.ssid.encode('utf-8')) <= 32 or '\x00' in args.ssid:
            parser.error('SSID must be 1..32 UTF-8 bytes, with no NUL')
        host = args.host
        if host != 'gateway':
            try:
                host = ipaddress.IPv4Address(host)
            except ipaddress.AddressValueError:
                parser.error('host must be an IPv4 address or gateway')
            first = int(host) >> 24
            if first in (0, 127) or first >= 224:
                parser.error('host must be reachable from the gadget')
        if not 1 <= args.proxy_port <= 65535:
            parser.error('proxy port must be 1..65535')
        payload = dict(slot=args.slot, ssid=args.ssid, host=str(host), port=args.proxy_port)
        command = 'proxy.set=' + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    elif args.action == 'delete':
        command = 'proxy.delete=' + str(args.slot)
    else:
        command = 'proxy.' + args.action
    with serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=3) as device:
        device.dtr = False
        device.rts = False
        device.port = args.port
        device.open()
        if args.action == 'reboot':
            device.rts = True
            time.sleep(0.1)
            device.rts = False
            print('Device reset requested')
            return
        device.reset_input_buffer()
        device.write(('>' + command + '\n').encode('utf-8'))
        device.flush()
        deadline = time.monotonic() + 10
        buf = bytearray()
        while time.monotonic() < deadline:
            buf.extend(device.read(1024))
            while b'\n' in buf:
                line, _, rest = buf.partition(b'\n')
                buf = bytearray(rest)
                line = line.decode('utf-8', errors='replace').strip()
                if not line.startswith('@proxy.'):
                    continue
                print(line)
                if line.startswith('@proxy.error'):
                    raise SystemExit(1)
                if (args.action == 'list' and line == '@proxy.list done'
                    or args.action == 'status'
                    or args.action in ('set', 'delete') and line.startswith('@proxy.ok')):
                    return
        raise SystemExit('No proxy acknowledgement; check firmware and USB connection')


if __name__ == '__main__':
    main()
