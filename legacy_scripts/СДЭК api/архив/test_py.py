import requests

url = "https://api.cdek.ru/v2/oauth/token"
data = {
    "grant_type": "client_credentials",
    "client_id": "Av97LAxNuLouH8KLjfRB8gsBPYhV2X7d",
    "client_secret": "2A5RSwcPAZK4DG3Vbj498unIdkyhmXj4"
}

res = requests.post(url, json=data)
print(res.status_code)
print(res.json())