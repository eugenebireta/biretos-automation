import requests
import json
from math import radians, sin, cos, sqrt, atan2
from dotenv import load_dotenv
import os

# ==== Настройки API ====
load_dotenv()

INS_DOMAIN = os.getenv("INSALES_DOMAIN")
INS_ID = os.getenv("INSALES_ID")
INS_PASS = os.getenv("INSALES_PASS")

# Автофикс: если случайно используется bireta.ru
if INS_DOMAIN and "bireta.ru" in INS_DOMAIN:
    INS_DOMAIN = "myshop-bsu266.myinsales.ru"

CDEK_CLIENT_ID = os.getenv("CDEK_CLIENT_ID")
CDEK_CLIENT_SECRET = os.getenv("CDEK_CLIENT_SECRET")
CDEK_API = "https://api.cdek.ru/v2"
GEOCODE_API = "https://nominatim.openstreetmap.org/search"

print("Проверка переменных из .env:")
print("INS_DOMAIN =", INS_DOMAIN)
print("INSALES_ID =", INS_ID)
print("INSALES_PASS =", "*" * len(INS_PASS))
print("CDEK_CLIENT_ID =", CDEK_CLIENT_ID)
print("CDEK_CLIENT_SECRET =", "*" * len(CDEK_CLIENT_SECRET))

# Поле "Номер для отслеживания заказа СДЭК"
INSALES_TRACK_FIELD_ID = 21837095   


# ==== Авторизация в СДЭК ====
def cdek_token():
    url = f"{CDEK_API}/oauth/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": CDEK_CLIENT_ID,
        "client_secret": CDEK_CLIENT_SECRET
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]


# ==== Заказы InSales ====
def get_ready_orders():
    url = f"https://{INS_ID}:{INS_PASS}@{INS_DOMAIN}/admin/orders.json?per_page=10"
    r = requests.get(url)
    r.raise_for_status()
    orders = r.json()

    ready_orders = []
    for o in orders:
        status = o.get("custom_status", {}).get("permalink", "")
        if status == "gotov-k-otpravke":
            if o.get("shipping_address"):
                ready_orders.append(o)
    return ready_orders


def get_client(client_id):
    url = f"https://{INS_ID}:{INS_PASS}@{INS_DOMAIN}/admin/clients/{client_id}.json"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()


# ==== Запись трек-номера ====
def update_order_field(order_id, field_id, value):
    url = f"https://{INS_ID}:{INS_PASS}@{INS_DOMAIN}/admin/orders/{order_id}/fields/{field_id}.json"
    payload = {"field_value": {"value": value}}
    r = requests.put(url, json=payload)
    r.raise_for_status()
    return r.json()


# ==== Геокодирование ====
def geocode(addr):
    headers = {"User-Agent": "MyCDEKIntegration/1.0 (email@example.com)"}
    r = requests.get(GEOCODE_API, params={"q": addr, "format": "json", "limit": 1}, headers=headers)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"Не удалось геокодировать адрес: {addr}")
    return float(data[0]["lat"]), float(data[0]["lon"])


# ==== Инструменты для ПВЗ ====
def get_city_code(token, city):
    url = f"{CDEK_API}/location/cities?country_codes=RU&city={city}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()[0]["code"]


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1) * cos(phi2) * sin(dl/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def nearest_pvz(token, address, city):
    lat, lon = geocode(address)
    city_code = get_city_code(token, city)
    url = f"{CDEK_API}/deliverypoints?city_code={city_code}&is_reception=true"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    points = r.json()
    best, dist = None, 1e9
    for p in points:
        if "location" in p:
            plat, plon = p["location"]["latitude"], p["location"]["longitude"]
            d = haversine(lat, lon, plat, plon)
            if d < dist:
                dist, best = d, p
    return best, city_code


# ==== Создание заказа в СДЭК ====
def create_cdek_order(token, order, pvz, city_code):
    # Клиент
    client_id = order["client"]["id"]
    client = get_client(client_id)

    def get_client_field_value(client, field_identifier):
        """Достаём значение из client['fields_values'] по идентификатору поля"""
        for fv in client.get("fields_values", []):
            if fv.get("client_field_permalink") == field_identifier:
                return fv.get("value", "")
        return ""

    # Используем идентификаторы напрямую
    org = get_client_field_value(client, "urlico")
    inn = get_client_field_value(client, "inn")
    addr = order["shipping_address"].get("full_delivery_address")

    # Товары
    items = []
    total_weight = 0
    for li in order["order_lines"]:
        weight = li.get("grams") or 100
        qty = li["quantity"]
        total_weight += weight * qty
        items.append({
            "ware_key": li["sku"],
            "name": li["title"],
            "cost": li["sale_price"],
            "weight": weight,
            "amount": qty,
            "payment": {"value": 0}
        })

    payload = {
        "number": str(order["id"]),
        "tariff_code": 136,
        "shipment_point": "CHEL172",
        "recipient": {
            "name": client["name"],
            "company": org,
            "tin": inn,
            "email": client["email"],
            "phones": [{"number": order["shipping_address"].get("phone")}]
        },
        "delivery_point": pvz["code"],
        "packages": [
            {
                "number": "1",
                "weight": total_weight or 1000,
                "length": 40,
                "width": 30,
                "height": 10,
                "items": items
            }
        ]
    }

    url = f"{CDEK_API}/orders"
    headers = {"Authorization": f"Bearer {token}"}

    print("== Отправляем заказ в СДЭК ==")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    r = requests.post(url, headers=headers, json=payload)
    if r.status_code >= 400:
        print("❌ Ошибка ответа от СДЭК:")
        print(r.text)
        r.raise_for_status()
    return r.json()


# ==== MAIN ====
if __name__ == "__main__":
    token = cdek_token()
    print("✅ Токен СДЭК получен")

    ready_orders = get_ready_orders()
    print(f"📦 Найдено заказов 'Готов к отправке': {len(ready_orders)}")

    results = []
    for order in ready_orders:
        try:
            addr = order["shipping_address"].get("full_delivery_address")
            city = order["shipping_address"].get("city")
            pvz, city_code = nearest_pvz(token, addr, city)
            print(f"📍 Заказ {order['id']}: ближайший ПВЗ {pvz['code']} {pvz['location']['address']}")

            created = create_cdek_order(token, order, pvz, city_code)
            cdek_number = created.get("entity", {}).get("cdek_number")

            if cdek_number:
                update_order_field(order["id"], INSALES_TRACK_FIELD_ID, cdek_number)
                print(f"✅ СДЭК заказ создан, трек-номер {cdek_number} записан в заказ {order['id']}")

            results.append({"order": order, "cdek": created})
        except Exception as e:
            print(f"❌ Ошибка при обработке заказа {order['id']}: {e}")

    with open("last_orders.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("💾 Результаты сохранены в last_orders.json")