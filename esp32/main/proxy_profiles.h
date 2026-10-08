/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    char ssid[33];
    char host[16];
    uint16_t port;
} muse_proxy_profile_t;

typedef enum { MUSE_ROUTE_BLOCKED = -1, MUSE_ROUTE_DIRECT = 0, MUSE_ROUTE_PROXY = 1 } muse_proxy_route_t;
/* Unconfigured SSIDs connect directly; invalid configured routes stay blocked. */
muse_proxy_route_t muse_proxy_route_current(muse_proxy_profile_t *out);
bool muse_proxy_profile_current(muse_proxy_profile_t *out);
bool passport_proxy_command(const char *line, bool whole);
