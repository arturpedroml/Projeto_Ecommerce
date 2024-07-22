from django.shortcuts import redirect, reverse # type: ignore
from django.views.generic import ListView, DetailView
from django.views import View
from django.contrib import messages
from produto.models import Variacao
from .models import Pedido, ItemPedido
from utils import utils
from .forms import MetodoPagamentoForm
from gerencianet import Gerencianet
from dotenv import load_dotenv
import os
import qrcode
import logging

logger = logging.getLogger(__name__)

load_dotenv()


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
                request.session['metodo_pagamento'] = metodo_pagamento
                if metodo_pagamento == 'pix':
                    chave_pix = "SUA_CHAVE_PIX"
                    valor = self.object.total # type: ignore
                    descricao = f"Pedido {self.object.pk}"
                    # Gerar cobrança Pix com Gerencianet
                    client_id = os.getenv('GN_CLIENT_ID')
                    client_secret = os.getenv('GN_CLIENT_SECRET')
                    gn = Gerencianet({
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'sandbox': True  # Mude para False em produção
                    })
                    body = {
                        "calendario": {"expiracao": 3600},
                        "valor": {"original": f"{valor:.2f}"},
                        "chave": chave_pix,
                        "solicitacaoPagador": descricao,
                    }
                    response = gn.pix_create_immediate_charge({}, body) # type: ignore
                    qrcode_data = response['loc']['qrcode']
                    qr = qrcode.make(qrcode_data)
                    qr_path = f"qrcodes/pix_{self.object.pk}.png"
                    qr.save(qr_path)
                    return redirect(reverse('pedido:confirmacao_pagamento', kwargs={'pk': self.object.pk}))
                else:
                    # Outros métodos de pagamento
                    pass
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