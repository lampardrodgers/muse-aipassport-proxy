/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    char ssid[33];
    char host[16];
    uint16_t port;
} muse_proxy_profile_t;

/* No match, disconnected Wi-Fi or invalid config always fails closed. */
bool muse_proxy_profile_current(muse_proxy_profile_t *out);
bool passport_proxy_command(const char *line, bool whole);
