import requests
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
import os

def formata_preco(val):
    return f'R$ {val:.2f}'.replace('.', ',')

def cart_total_qtd(carrinho):
    return sum([item['quantidade'] for item in carrinho.values()])


def cart_totals(carrinho):
    return sum(
        [
            item.get('preco_quantitativo_promocional')
            if item.get('preco_quantitativo_promocional')
            else item.get('preco_quantitativo')
            for item
            in carrinho.values()
        ]
    )

PIX_NEON_CLIENT_ID = os.getenv('PIX_NEON_CLIENT_ID')
PIX_NEON_CLIENT_SECRET = os.getenv('PIX_NEON_CLIENT_SECRET')
PIX_NEON_API_URL = os.getenv('PIX_NEON_API_URL')

def get_pix_token():
    url = f"{PIX_NEON_API_URL}/oauth/token"
    payload = {
        'grant_type': 'client_credentials',
        'client_id': PIX_NEON_CLIENT_ID,
        'client_secret': PIX_NEON_CLIENT_SECRET
    }
    response = requests.post(url, data=payload)
    response_data = response.json()
    return response_data['access_token']

def create_pix_charge(valor, descricao):
    token = get_pix_token()
    url = f"{PIX_NEON_API_URL}/v1/pix/charges"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'calendario': {'expiracao': 3600},
        'valor': {'original': f'{valor:.2f}'},
        'chave': 'SUA_CHAVE_PIX',
        'solicitacaoPagador': descricao,
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

def generate_qr_code(data):
    qr = qrcode.make(data)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return ContentFile(buffer.getvalue(), name="qr_code.png")