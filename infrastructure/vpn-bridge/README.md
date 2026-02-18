# Stable Bridge Architecture

Windows PC → Xray → Moscow VPS → WireGuard → USA VPS → Internet (USA IP)

## Развертывание

### 1. VPS США (`216.9.227.124`)
```
ssh root@216.9.227.124
wg genkey | tee usa-private.key | wg pubkey > usa-public.key
cp wg-usa-server.conf /etc/wireguard/wg0.conf
# Вставить приватный ключ в секцию [Interface]
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0
```

### 2. VPS Москва (`dev.bireta.ru`)
```
ssh root@dev.bireta.ru
wg genkey | tee msk-private.key | wg pubkey > msk-public.key
cp wg-msk-client.conf /etc/wireguard/wg0.conf
# Вставить приватный ключ и публичный ключ США
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0

# Установка Xray
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
cp xray-msk-config.json /usr/local/etc/xray/config.json
systemctl enable xray
systemctl start xray
```

### 3. Windows PC
```
# Установить Xray-core
# Скопировать xray-windows-client.json в C:\xray\config.json
xray.exe -config C:\xray\config.json
# В Cursor указать SOCKS5 proxy 127.0.0.1:10808
```

## Проверка
- На Москве: `curl --interface wg0 ifconfig.me` → должен показать IP США.
- На Windows: `curl -x socks5://127.0.0.1:10808 ifconfig.me` → должен показать IP США.

## Откат
1. Остановить Xray на Windows — трафик пойдет напрямую.
2. Остановить WireGuard на Москве — SSH доступ сохранится через основной интерфейс.
3. Остановить WireGuard на США — трафик вернется к текущей архитектуре.









