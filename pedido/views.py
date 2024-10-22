from django.shortcuts import redirect, reverse # type: ignore
from django.views.generic import ListView, DetailView
from django.views import View
from django.contrib import messages
from produto.models import Variacao
from .models import Pedido, ItemPedido
from utils import utils
from .forms import MetodoPagamentoForm
from utils.utils import create_pix_charge, generate_qr_code
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def get_neon_access_token():
        url = "https://api.neon.com.br/oauth/token"  # Verifique a documentação para a URL correta
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "client_credentials",
            "client_id": settings.PIX_NEON_CLIENT_ID,
            "client_secret": settings.PIX_NEON_CLIENT_SECRET,
            "scope": "pix.read pix.write"
        }
        response = requests.post(url, headers=headers, data=data)
        print(response.text)  # Adicione esta linha para depuração
        response_data = response.json()
        return response_data["access_token"]

class DispatchLoginRequiredMixin(View):
    def dispatch(self, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return redirect('perfil:criar')

        return super().dispatch(*args, **kwargs)

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs) # type: ignore
        qs = qs.filter(usuario=self.request.user)
        return qs


class Pagar(DispatchLoginRequiredMixin, DetailView):
    template_name = 'pedido/pagar.html'
    model = Pedido
    pk_url_kwarg = 'pk'
    context_object_name = 'pedido'

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = MetodoPagamentoForm(request.POST)
        if form.is_valid():
            metodo_pagamento = form.cleaned_data['metodo_pagamento']
            if metodo_pagamento == 'pix':
                try:
                    valor = self.object.total # type: ignore
                    descricao = f"Pedido {self.object.pk}"
                    pix_response = create_pix_charge(valor, descricao)
                    qr_code_data = pix_response['loc']['qrcode']
                    qr_code = generate_qr_code(qr_code_data)
                    self.object.qr_code.save(f"qr_code_{self.object.pk}.png", qr_code, save=True) # type: ignore
                    return redirect(reverse('pedido:confirmacao_pagamento', kwargs={'pk': self.object.pk}))
                except Exception as e:
                    logger.error(f"Error processing Pix payment: {e}")
                    messages.error(request, "Ocorreu um erro ao processar o pagamento. Por favor, tente novamente.")
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = MetodoPagamentoForm()
        return context
    
class ConfirmacaoPagamento(DetailView):
    template_name = 'pedido/confirmacao.html'
    model = Pedido
    pk_url_kwarg = 'pk'
    context_object_name = 'pedido'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qr_code_path = f'qrcodes/pix_{self.object.pk}.png' # type: ignore
        context['qr_code_url'] = qr_code_path
        context['metodo_pagamento'] = self.request.session.get('metodo_pagamento', '')
        return context

class SalvarPedido(View):
    template_name = 'pedido/pagar.html'

    def get(self, *args, **kwargs):
        if not self.request.user.is_authenticated:
            messages.error(
                self.request,
                'Você precisa fazer login.'
            )
            return redirect('perfil:criar')

        if not self.request.session.get('carrinho'):
            messages.error(
                self.request,
                'Seu carrinho está vazio.'
            )
            return redirect('produto:lista')

        carrinho = self.request.session.get('carrinho')
        carrinho_variacao_ids = [v for v in carrinho] # type: ignore
        bd_variacoes = list(
            Variacao.objects.select_related('produto')
            .filter(id__in=carrinho_variacao_ids)
        )

        for variacao in bd_variacoes:
            vid = str(variacao.id) # type: ignore

            estoque = variacao.estoque
            qtd_carrinho = carrinho[vid]['quantidade'] # type: ignore
            preco_unt = carrinho[vid]['preco_unitario'] # type: ignore
            preco_unt_promo = carrinho[vid]['preco_unitario_promocional'] # type: ignore

            error_msg_estoque = ''

            if estoque < qtd_carrinho:
                carrinho[vid]['quantidade'] = estoque # type: ignore
                carrinho[vid]['preco_quantitativo'] = estoque * preco_unt # type: ignore
                carrinho[vid]['preco_quantitativo_promocional'] = estoque * preco_unt_promo # type: ignore

                error_msg_estoque = 'Estoque insuficiente para alguns '\
                    'produtos do seu carrinho. '\
                    'Reduzimos a quantidade desses produtos. Por favor, '\
                    'verifique quais produtos foram afetados a seguir.'

            if error_msg_estoque:
                messages.error(
                    self.request,
                    error_msg_estoque
                )

                self.request.session.save()
                return redirect('produto:carrinho')

        qtd_total_carrinho = utils.cart_total_qtd(carrinho)
        valor_total_carrinho = utils.cart_totals(carrinho)

        pedido = Pedido(
            usuario=self.request.user,
            total=valor_total_carrinho,
            qtd_total=qtd_total_carrinho,
            status='C',
        )

        pedido.save()

        ItemPedido.objects.bulk_create(
            [
                ItemPedido(
                    pedido=pedido,
                    produto=v['produto_nome'],
                    produto_id=v['produto_id'],
                    variacao=v['variacao_nome'],
                    variacao_id=v['variacao_id'],
                    preco=v['preco_quantitativo'],
                    preco_promocional=v['preco_quantitativo_promocional'],
                    quantidade=v['quantidade'],
                    imagem=v['imagem'],
                ) for v in carrinho.values() # type: ignore
            ]
        )

        del self.request.session['carrinho']

        return redirect(
            reverse(
                'pedido:pagar',
                kwargs={
                    'pk': pedido.pk
                }
            )
        )


class Detalhe(DispatchLoginRequiredMixin, DetailView):
    model = Pedido
    context_object_name = 'pedido'
    template_name = 'pedido/detalhe.html'
    pk_url_kwarg = 'pk'


class Lista(DispatchLoginRequiredMixin, ListView):
    model = Pedido
    context_object_name = 'pedidos'
    template_name = 'pedido/lista.html'
    paginate_by = 10
    ordering = ['-id']