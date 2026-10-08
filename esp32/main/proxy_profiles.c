/* SPDX-License-Identifier: Apache-2.0 */
#include "proxy_profiles.h"
#include "config_store.h"
#include "cJSON.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PROFILE_COUNT 4
#define PROFILE_JSON_MAX 512

static bool parse_profile(const cJSON *json, muse_proxy_profile_t *out)
{
    const cJSON *ssid = cJSON_GetObjectItemCaseSensitive(json, "ssid");
    const cJSON *host = cJSON_GetObjectItemCaseSensitive(json, "host");
    const cJSON *port = cJSON_GetObjectItemCaseSensitive(json, "port");
    struct in_addr addr;
    if (!cJSON_IsObject(json) || !cJSON_IsString(ssid) || !cJSON_IsString(host)
        || !cJSON_IsNumber(port) || !ssid->valuestring[0]
        || strlen(ssid->valuestring) > 32 || strlen(host->valuestring) > 15
        || port->valuedouble < 1 || port->valuedouble > 65535
        || port->valuedouble != port->valueint) return false;
    if (strcmp(host->valuestring, "gateway")) {
        if (inet_pton(AF_INET, host->valuestring, &addr) != 1) return false;
        uint32_t ip = ntohl(addr.s_addr);
        if ((ip >> 24) == 0 || (ip >> 24) == 127 || (ip >> 24) >= 224) return false;
    }
    memset(out, 0, sizeof(*out));
    strcpy(out->ssid, ssid->valuestring);
    strcpy(out->host, host->valuestring);
    out->port = (uint16_t)port->valueint;
    return true;
}

static void slot_key(int slot, char key[16])
{
    snprintf(key, 16, "proxy_%d", slot);
}

static bool load_profile(int slot, muse_proxy_profile_t *out)
{
    char key[16], buf[PROFILE_JSON_MAX];
    slot_key(slot, key);
    if (!config_get_str(key, buf, sizeof(buf))) return false;
    cJSON *json = cJSON_ParseWithOpts(buf, NULL, true);
    bool ok = parse_profile(json, out);
    cJSON_Delete(json);
    return ok;
}

muse_proxy_route_t muse_proxy_route_current(muse_proxy_profile_t *out)
{
    if (!out) return MUSE_ROUTE_BLOCKED;
    memset(out, 0, sizeof(*out));
    wifi_ap_record_t ap = {0};
    if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) return MUSE_ROUTE_BLOCKED;
    char ssid[33] = {0};
    memcpy(ssid, ap.ssid, 32);
    muse_proxy_profile_t p;
    for (int slot = 1; slot <= PROFILE_COUNT; ++slot) {
        char key[16], raw[PROFILE_JSON_MAX];
        slot_key(slot, key);
        if (!config_get_str(key, raw, sizeof(raw))) continue;
        cJSON *json = cJSON_ParseWithOpts(raw, NULL, true);
        bool valid = parse_profile(json, &p);
        cJSON_Delete(json);
        if (!valid) return MUSE_ROUTE_BLOCKED;
        if (!strcmp(p.ssid, ssid)) {
            if (!strcmp(p.host, "gateway")) {
                esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
                esp_netif_ip_info_t info = {0};
                if (!netif || esp_netif_get_ip_info(netif, &info) != ESP_OK) return MUSE_ROUTE_BLOCKED;
                uint32_t ip = ntohl(info.gw.addr);
                if ((ip >> 24) == 0 || (ip >> 24) == 127 || (ip >> 24) >= 224) return MUSE_ROUTE_BLOCKED;
                struct in_addr gateway = { .s_addr = info.gw.addr };
                if (!inet_ntop(AF_INET, &gateway, p.host, sizeof(p.host))) return MUSE_ROUTE_BLOCKED;
            }
            *out = p;
            return MUSE_ROUTE_PROXY;
        }
    }
    return MUSE_ROUTE_DIRECT;
}

bool muse_proxy_profile_current(muse_proxy_profile_t *out)
{
    return muse_proxy_route_current(out) == MUSE_ROUTE_PROXY;
}

static void print_profile(int slot, const muse_proxy_profile_t *p)
{
    cJSON *json = cJSON_CreateObject();
    if (!json) return;
    cJSON_AddNumberToObject(json, "slot", slot);
    cJSON_AddStringToObject(json, "ssid", p->ssid);
    cJSON_AddStringToObject(json, "host", p->host);
    cJSON_AddNumberToObject(json, "port", p->port);
    char *encoded = cJSON_PrintUnformatted(json);
    if (encoded) printf("@proxy.profile %s\n", encoded);
    free(encoded);
    cJSON_Delete(json);
}

bool passport_proxy_command(const char *line, bool whole)
{
    if (strncmp(line, "proxy", 5)) return false;
    if (!whole) {
        puts("@proxy.error line too long");
    } else if (!strcmp(line, "proxy.list")) {
        muse_proxy_profile_t p;
        for (int slot = 1; slot <= PROFILE_COUNT; ++slot)
            if (load_profile(slot, &p)) print_profile(slot, &p);
        puts("@proxy.list done");
    } else if (!strcmp(line, "proxy.status")) {
        muse_proxy_profile_t p;
        muse_proxy_route_t route = muse_proxy_route_current(&p);
        if (route == MUSE_ROUTE_PROXY) print_profile(0, &p);
        else if (route == MUSE_ROUTE_DIRECT) puts("@proxy.status direct");
        else puts("@proxy.status blocked: Wi-Fi unavailable or invalid proxy configuration");
    } else if (!strncmp(line, "proxy.direct=", 13)) {
        cJSON *json = cJSON_ParseWithOpts(line + 13, NULL, true);
        const cJSON *ssid = cJSON_GetObjectItemCaseSensitive(json, "ssid");
        bool ok = cJSON_IsString(ssid) && ssid->valuestring[0]
                  && strlen(ssid->valuestring) <= 32;
        if (ok) {
            for (int slot = 1; slot <= PROFILE_COUNT; ++slot) {
                muse_proxy_profile_t p;
                if (load_profile(slot, &p) && !strcmp(p.ssid, ssid->valuestring)) {
                    char key[16]; slot_key(slot, key);
                    if (!config_erase_key(key)) ok = false;
                }
            }
        }
        cJSON_Delete(json);
        puts(ok ? "@proxy.ok direct; reboot to close existing sessions"
                : "@proxy.error invalid SSID or save failed");
    } else if (!strncmp(line, "proxy.delete=", 13)) {
        const char *s = line + 13;
        if (s[0] >= '1' && s[0] <= '4' && !s[1]) {
            char key[16];
            slot_key(s[0] - '0', key);
            puts(config_erase_key(key) ? "@proxy.ok deleted; reboot to close existing sessions"
                                      : "@proxy.error save failed");
        } else puts("@proxy.error slot must be 1..4");
    } else if (!strncmp(line, "proxy.set=", 10)) {
        cJSON *json = cJSON_ParseWithOpts(line + 10, NULL, true);
        const cJSON *slot = cJSON_GetObjectItemCaseSensitive(json, "slot");
        muse_proxy_profile_t p, existing;
        bool valid = cJSON_IsNumber(slot) && slot->valuedouble >= 1
            && slot->valuedouble <= PROFILE_COUNT
            && slot->valuedouble == slot->valueint && parse_profile(json, &p);
        if (valid) {
            for (int i = 1; i <= PROFILE_COUNT; ++i)
                if (i != slot->valueint && load_profile(i, &existing)
                    && !strcmp(existing.ssid, p.ssid)) valid = false;
        }
        if (!valid) puts("@proxy.error invalid profile or duplicate SSID");
        else {
            char key[16];
            slot_key(slot->valueint, key);
            char *encoded = cJSON_PrintUnformatted(json);
            bool saved = encoded && strlen(encoded) < PROFILE_JSON_MAX
                         && config_set_str(key, encoded);
            free(encoded);
            puts(saved ? "@proxy.ok saved; reboot to close existing sessions"
                       : "@proxy.error save failed");
        }
        cJSON_Delete(json);
    } else puts("@proxy.error use proxy.list/status/set=/delete=");
    fflush(stdout);
    return true;
}
