# FoloToy Muse Proxy

当前版本：**V0.1.0** · [更新日志](CHANGELOG.md)

为 **FoloToy AI Passport** 定制的 Muse 固件：连接手机热点，通过手机共享的 HTTP 代理访问 Muse，按住 OK 说话，松开后发送，在设备屏幕上阅读两行文字回复。

基于 [facebookincubator/muse-gadget-sdk](https://github.com/facebookincubator/muse-gadget-sdk) 修改，源码基线为 `86cf33fb4092ba700b4dc33928966d1bcb31556d`。这是个人维护的适配版本，与 FoloToy、Meta 无官方关联。

## 适用设备

- FoloToy AI Passport：ESP32-C3、8 MB Flash、无 PSRAM。
- 已在这一型号上刷入并验证连接 Muse；其他 FoloToy 型号没有验证。
- 编译环境：ESP-IDF **v6.0.1**、Python 3。
- 使用你自己的 Muse 账号和 [Gadget SDK token](https://gadgets.muse.ai/settings/sdk-tokens)，并遵守 [SDK 使用条款](https://gadgets.muse.ai/sdk-terms)。

## 这个版本改了什么

| 功能 | 本版行为 |
| --- | --- |
| 手机共享代理 | Muse API 和控制连接支持 HTTP CONNECT 代理，TLS 证书验证保持开启 |
| 多热点配置 | 最多保存 4 组热点名称、代理 IPv4 地址和端口，按 Wi-Fi SSID 精确匹配 |
| 动态网关 | 代理地址支持 `gateway`，使用设备当前 Wi-Fi 网关；也可填写固定 IPv4 |
| 代理失败处理 | 使用下面的代理构建脚本时，无匹配配置或代理失败会阻止相应 Muse 连接，不自动直连 |
| 回复接收 | 此板型的加密接收缓冲从约 13 KiB 扩展至 18 KiB，覆盖常规 16 KiB 数据块及封装开销 |
| 内存使用 | 原地解密并单独保留重组缓冲，接收缓冲总占用比原布局减少约 2 KiB |
| 中文显示 | 两行一页，按第 1、2 行 → 第 3、4 行翻页，不重复上一页第二行 |
| 阅读时间 | 每个完整两行页按原始阅读速率前进，停留时间约为原单行页的两倍 |
| USB 管理 | 通过串口查看、设置、删除代理配置及重启设备 |

保留官方 BLE 配对流程和按住录音、松开发送的操作。主任务栈需配置为 12288 字节，以容纳代理连接路径。

## 网络如何连接

```text
FoloToy AI Passport
  └─ 手机 Wi-Fi 热点
      └─ 手机的 HTTP 代理共享端口
          └─ 手机代理客户端 → Muse
```

设备不运行 VLESS、Reality 或 Vision。这些协议由手机的代理客户端负责；设备只连接其提供的 HTTP CONNECT 代理。

**这不是设备全流量 VPN。** 本版接入的是 Muse API 与控制通道，不保证所有系统服务或其他功能的流量都经代理。

## 编译

先获取源码，安装并激活 ESP-IDF v6.0.1。从仓库根目录开始：

```sh
. "$IDF_PATH/export.sh"
cd esp32

# 首次生成本机配置并打开配置界面。
idf.py -B build-muse-ai-passport \
  -DIDF_TARGET=esp32c3 \
  -DSDKCONFIG=build-muse-ai-passport/sdkconfig \
  '-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;devices/sdkconfig.muse;devices/sdkconfig.muse-ai-passport' \
  menuconfig
```

在配置界面中搜索并设置：

- `GADGET_SDK_TOKEN`：填入你自己的 token。
- `ESP_MAIN_TASK_STACK_SIZE`：设为 `12288`。

保存后使用本项目的构建脚本，启用按热点匹配的代理模式：

```sh
./tools/muse/build-ai-passport-proxy.sh
```

脚本要求 `build-muse-ai-passport/sdkconfig` 已存在。不要把个人构建配置、包含 token 的二进制或完整闪存备份提交到仓库。

## 刷入与配对

刷机前先用对应设备的工具备份原固件和配置。以下命令仅适用于上述 AI Passport，串口名请替换为实际值：

```sh
# 在 esp32 目录中执行。
cd build-muse-ai-passport
python -m esptool --chip esp32c3 -p /dev/cu.usbmodem1101 -b 460800 \
  --before default-reset --after hard-reset write-flash @flash_args
```

本项目的刷机参数不擦除 NVS；从当前 Muse 版本更新时可保留配置。跨 FoloToy 官方固件与 Muse 切换时，不应假定分区和配置兼容，也不要只替换应用分区。请分别保存私人完整备份，按各自固件的恢复流程操作。

在 Muse App 的设备设置中启用开发者模式，搜索并配对 `MuseGadget` 设备，按 App 提示确认配对、设置 Wi-Fi。随后通过 USB 添加对应热点的代理配置。

## 使用 .env 管理本机配置

仓库提供 `.env.example`，本机使用 `.env`。`.env` 已被 Git 忽略，不要强制添加或打包上传；`.env.example` 保持空凭据即可提交。

```sh
# 在仓库根目录；已有 .env 时不要覆盖。
cp .env.example .env
chmod 600 .env
python -m pip install pyserial
```

编辑 `.env`，填写 `SERIAL_PORT`、`WIFI_1_SSID`、`WIFI_1_PASSWORD`、`WIFI_1_PROXY_HOST` 和 `WIFI_1_PROXY_PORT`。第二台手机填 `WIFI_2_`，最多 4 组。配置只在本机读取，不做 shell 执行或变量展开。

```sh
# 只检查配置，不连接设备，也不显示密码。
python tools/configure.py check

# 保存所有非空热点对应的代理配置，并连接第 1 组 Wi-Fi。
python tools/configure.py apply --slot 1

# 切到第 2 组时再执行。
python tools/configure.py apply --slot 2
```

工具复用当前固件的 USB 配置命令，无需为了使用 `.env` 重刷固件。空 SSID 的槽位不会写入，也不会删除设备已有配置；删除请使用下面的 `proxy.py delete`。每次 `apply` 只提交所选热点的 Wi-Fi 凭据，代理配置则提交所有非空槽位。首次 Muse 配对仍需在 App 中完成。

串口打开可能让设备重启。工具等候启动并检查配置命令回执；回执成功只代表设备接受了命令，不代表 Wi-Fi 或 Muse 已连接成功。中途失败可能已有部分配置写入，修正后可重试。

可选：在 `.env` 填入自己的 `MUSE_SDK_TOKEN`，先按上文生成 `sdkconfig`，再执行：

```sh
python tools/configure.py build-config
cd esp32
./tools/muse/build-ai-passport-proxy.sh
```

`build-config` 只更新本机私有构建配置和主任务栈，不会把 SDK token 发往设备配对接口。重新编译的固件仍包含此 token，因此不能公开上传生成的 `.bin`。

## 配置手机代理

在手机代理客户端中启用 HTTP 代理共享，确保热点下的设备可以访问该监听端口。代理 IP 和端口以你的实际配置为准；手机切换网络时，App 显示的地址不一定就是热点下可访问的地址。

下面的热点名和地址均为示例。在仓库根目录执行，Python 环境需要 `pyserial`：

```sh
# 手机 A：代理运行在当前热点网关。
python esp32/tools/muse/proxy.py --port /dev/cu.usbmodem1101 set \
  --slot 1 --ssid 'Phone-A' --host gateway --proxy-port 1082

# 手机 B：使用固定地址；请替换成实际可达的代理地址。
python esp32/tools/muse/proxy.py --port /dev/cu.usbmodem1101 set \
  --slot 2 --ssid 'Phone-B' --host 172.20.10.1 --proxy-port 1082

# 查看保存的配置、当前匹配情况。
python esp32/tools/muse/proxy.py --port /dev/cu.usbmodem1101 list
python esp32/tools/muse/proxy.py --port /dev/cu.usbmodem1101 status

# 配置修改后重启，使已存在的连接使用新配置。
python esp32/tools/muse/proxy.py --port /dev/cu.usbmodem1101 reboot
```

删除配置：`python esp32/tools/muse/proxy.py --port /dev/cu.usbmodem1101 delete --slot 2`。

SSID 区分大小写，两台手机请使用不同的热点名称。`gateway` 仅适用于代理确实监听在网关地址的情况。目前不支持需要用户名、密码认证的 HTTP 代理。

## 使用

1. 连接已配置的热点，开启手机代理共享，等待设备连接 Muse。
2. 按住 OK／对话键，等待进入收音状态后说话。
3. 松开结束录音并发送。
4. 在屏幕上阅读两行文字回复；菜单打开时，OK 用于选择菜单项。

**当前版本不播放 Muse 的语音回复。** App 能播放音频附件，不代表本固件已接入该音频的下载和播放。

## 已知限制

- 无 PSRAM，接收和文字缓存仍有大小上限；扩大缓冲不等于支持无限长回复。
- 手机热点可用不代表代理共享端口可用，需分别检查。
- 设备上线不代表每轮任务已完成；若 Muse 需要授权或处理较久，请同时查看 App。
- 不包含家庭网络隧道，也不改变手机代理客户端的上游协议。
- 完整闪存镜像含 Wi-Fi、配对和登录凭据，仅用于个人恢复，不能作为公共 Release 附件。

## 测试

完成一次固件构建后，可以运行官方 host tests 与新增回归测试：

```sh
cd esp32
python -m unittest discover -s tests -p 'test_*.py'
```

本次开发环境最近一次结果为 200 项测试：199 项通过，1 项因缺少依赖跳过；固件编译通过，实机恢复联网。分页回归测试覆盖两行翻页、不重复及最后不足一页的情况。完整语音播报尚未实现。

## 上游与许可

保留 [上游说明](README.upstream.md) 和 [ESP32 开发文档](esp32/README.md)。项目基于 Apache-2.0，详见 [LICENSE](LICENSE)。minimp3、字体和其他第三方组件保留各自许可；Jollybot 头像不在 Apache-2.0 授权范围内，见 [上游头像目录](esp32/avatar)。

仓库中的 `esp32/dev_signing_key.pem` 是上游公开的开发签名测试密钥，不是生产私钥，不应用于生产签名。
