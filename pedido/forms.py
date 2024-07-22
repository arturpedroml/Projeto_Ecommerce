from django import forms

class MetodoPagamentoForm(forms.Form):
    METODOS_PAGAMENTO = [
        ('cartao_credito', 'Cartão de Crédito'),
        ('boleto', 'Boleto'),
        ('pix', 'Pix'),
        ('paypal', 'PayPal'),
        # Adicione outros métodos de pagamento conforme necessário
    ]
    metodo_pagamento = forms.ChoiceField(choices=METODOS_PAGAMENTO, widget=forms.Select(attrs={'class': 'form-control'}))
