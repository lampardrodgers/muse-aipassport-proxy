"""Compile the actual profile storage/selection code with fake NVS and Wi-Fi."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JSON = Path(os.environ.get('CJSON_SOURCE_DIR', ROOT / 'managed_components/espressif__cjson/cJSON'))

class ProxyProfilesTest(unittest.TestCase):
    def test_persistence_selection_validation_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / 'lwip').mkdir()
            (out / 'lwip/inet.h').write_text('#include <arpa/inet.h>\n')
            (out / 'lwip/sockets.h').write_text('#include <sys/socket.h>\n')
            (out / 'esp_wifi.h').write_text('''#include <stdint.h>
#define ESP_OK 0
typedef struct { uint8_t ssid[33]; } wifi_ap_record_t;
int esp_wifi_sta_get_ap_info(wifi_ap_record_t *ap);
''')
            (out / 'esp_netif.h').write_text('#include <stdint.h>\ntypedef int esp_netif_t;\ntypedef struct { struct { uint32_t addr; } gw; } esp_netif_ip_info_t;\nesp_netif_t *esp_netif_get_handle_from_ifkey(const char *key);\nint esp_netif_get_ip_info(esp_netif_t *netif, esp_netif_ip_info_t *info);\n')
            (out / 'test.c').write_text(r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "proxy_profiles.c"
static char store[4][512];
static char current[33];
static bool connected = true, fail_save;
static uint32_t gateway_ip;
static int netif;
esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) { (void)key; return &netif; }
int esp_netif_get_ip_info(esp_netif_t *n, esp_netif_ip_info_t *info) { (void)n; info->gw.addr=gateway_ip; return 0; }
int esp_wifi_sta_get_ap_info(wifi_ap_record_t *ap) {
    memcpy(ap->ssid, current, 33); return connected ? 0 : -1;
}
static int index_for(const char *key) { return key[6] - '1'; }
bool config_get_str(const char *key, char *out, size_t size) {
    const char *s=store[index_for(key)];
    if (!s[0] || strlen(s)>=size) return false;
    strcpy(out,s); return true;
}
bool config_set_str(const char *key, const char *value) {
    if (fail_save) return false;
    strcpy(store[index_for(key)],value); return true;
}
bool config_erase_key(const char *key) { store[index_for(key)][0]=0; return true; }
int main(void) {
    muse_proxy_profile_t p;
    strcpy(current,"phone A");
    assert(muse_proxy_route_current(&p)==MUSE_ROUTE_DIRECT);
    assert(passport_proxy_command("proxy.set={\"slot\":1,\"ssid\":\"phone A\",\"host\":\"172.20.10.1\",\"port\":1082}",true));
    assert(muse_proxy_profile_current(&p) && p.port==1082);
    assert(!strcmp(p.host,"172.20.10.1"));
    passport_proxy_command("proxy.set={\"slot\":2,\"ssid\":\"手机 B\",\"host\":\"192.168.43.1\",\"port\":7890}",true);
    strcpy(current,"手机 B");
    assert(muse_proxy_profile_current(&p) && p.port==7890);
    connected=false; assert(muse_proxy_route_current(&p)==MUSE_ROUTE_BLOCKED); connected=true;
    strcpy(current,"unknown"); assert(muse_proxy_route_current(&p)==MUSE_ROUTE_DIRECT);
    strcpy(current,"phone A "); assert(!muse_proxy_profile_current(&p));
    char saved[512]; strcpy(saved,store[0]);
    const char *invalid[]={
      "proxy.set={\"slot\":1,\"ssid\":\"phone A\",\"host\":\"127.0.0.1\",\"port\":80}",
      "proxy.set={\"slot\":1,\"ssid\":\"phone A\",\"host\":\"999.1.1.1\",\"port\":80}",
      "proxy.set={\"slot\":1,\"ssid\":\"phone A\",\"host\":\"1.1.1.1\",\"port\":0}",
      "proxy.set={\"slot\":1,\"ssid\":\"phone A\",\"host\":\"1.1.1.1\",\"port\":65536}",
      "proxy.set={\"slot\":1,\"ssid\":\"phone A\",\"host\":\"1.1.1.1\",\"port\":1.5}",
      "proxy.set={\"slot\":1,\"ssid\":\"手机 B\",\"host\":\"1.1.1.1\",\"port\":80}",
      "proxy.set={\"slot\":1}", "proxy.set={", "proxy.set={} trailing"
    };
    for (unsigned i=0;i<sizeof(invalid)/sizeof(*invalid);++i) {
        passport_proxy_command(invalid[i],true); assert(!strcmp(saved,store[0]));
    }
    passport_proxy_command("proxy.delete=1",false); assert(!strcmp(saved,store[0]));
    fail_save=true;
    passport_proxy_command("proxy.set={\"slot\":1,\"ssid\":\"phone A\",\"host\":\"1.1.1.1\",\"port\":80}",true);
    assert(!strcmp(saved,store[0])); fail_save=false;
    strcpy(current,"phone A");
    assert(muse_proxy_profile_current(&p) && p.port==1082);
    passport_proxy_command("proxy.delete=1",true);
    assert(!muse_proxy_profile_current(&p));
    strcpy(store[0],"{broken"); assert(muse_proxy_route_current(&p)==MUSE_ROUTE_BLOCKED); store[0][0]=0;
    assert(!passport_proxy_command("heap",true));
    passport_proxy_command("proxy.set={\"slot\":3,\"ssid\":\"phone A\",\"host\":\"gateway\",\"port\":1082}",true);
    gateway_ip=inet_addr("172.20.10.1");
    assert(muse_proxy_profile_current(&p) && !strcmp(p.host,"172.20.10.1"));
    gateway_ip=inet_addr("192.168.43.1");
    assert(muse_proxy_profile_current(&p) && !strcmp(p.host,"192.168.43.1"));
    gateway_ip=0; assert(muse_proxy_route_current(&p)==MUSE_ROUTE_BLOCKED);
    passport_proxy_command("proxy.direct={\"ssid\":\"phone A\"}",true);
    assert(muse_proxy_route_current(&p)==MUSE_ROUTE_DIRECT);
    strcpy(current,"手机 B");
    assert(muse_proxy_route_current(&p)==MUSE_ROUTE_PROXY);


    return 0;
}
''')
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror', '-I',str(out),'-I',str(ROOT/'main'),'-I',str(JSON), str(out/'test.c'), str(JSON/'cJSON.c'),'-o',str(out/'test')],check=True,capture_output=True)
            result=subprocess.run([str(out/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
