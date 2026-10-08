import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('configure', Path(__file__).resolve().parents[1] / 'tools/configure.py')
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)


class ConfigureTest(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text(text)
            return cfg.read_env(path)

    def test_password_is_literal_not_shell(self):
        env = self.parse('WIFI_1_SSID="Phone A"\nWIFI_1_PASSWORD=\'a # $HOME $(echo nope)\'\n')
        self.assertEqual(env['WIFI_1_PASSWORD'], 'a # $HOME $(echo nope)')
        self.assertEqual(cfg.profiles(env)[0][0]['host'], 'gateway')

    def test_reject_serial_command_injection(self):
        with self.assertRaises(ValueError):
            self.parse('WIFI_1_PASSWORD="hello\\n>proxy.delete=1"')

    def test_reject_duplicate_settings(self):
        with self.assertRaises(ValueError):
            self.parse('WIFI_1_SSID=A\nWIFI_1_SSID=B')

    def test_distinct_hotspots_and_ports(self):
        env = self.parse('WIFI_1_SSID=A\nWIFI_2_SSID=B\nWIFI_2_PROXY_HOST=172.20.10.1\nWIFI_2_PROXY_PORT=1083')
        self.assertEqual([item[0]['slot'] for item in cfg.profiles(env)], [1, 2])
        self.assertEqual(cfg.profiles(env)[1][0]['port'], 1083)
        env['WIFI_2_SSID'] = 'A'
        with self.assertRaises(ValueError):
            cfg.profiles(env)

    def test_utf8_ssid_length_and_bad_port(self):
        with self.assertRaises(ValueError):
            cfg.profiles({'WIFI_1_SSID': '中' * 11})
        with self.assertRaises(ValueError):
            cfg.profiles({'WIFI_1_SSID': 'A', 'WIFI_1_PROXY_PORT': '65536'})

    def test_usb_password_ack_without_echoing_password(self):
        class FakeSerial:
            def reset_input_buffer(self): pass
            def write(self, wire): self.wire = wire
            def flush(self): pass
            def readline(self): return b'I (100) muse_ble: cmd wifi.pass -> ok\n'
        device = FakeSerial()
        cfg.command(device, 'wifi.pass=test-password', 'cmd wifi.pass ->')
        self.assertEqual(device.wire, b'>wifi.pass=test-password\n')


if __name__ == '__main__':
    unittest.main()
