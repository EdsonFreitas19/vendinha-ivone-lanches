# Ivone Lanches — cardápio online

Cardápio com filtro por categoria, detalhe do item com foto, pedido pelo WhatsApp e
painel de administração (itens com foto, preço, categoria, disponibilidade e estoque).

Tecnologia: Python + Flask + SQLite (um único processo, sem build).

## Rodar no Windows (PowerShell)

Dentro da pasta `ivone-lanches`:

```powershell
py -m pip install -r requirements.txt
$env:ADMIN_PASSWORD = "escolha-uma-senha"
$env:WHATSAPP_NUMBER = "5581999999999"
py app.py
```

Abra http://127.0.0.1:5000 (evite a porta 6000: o Chrome bloqueia).
O login fica em `/login` (usuário padrão: `ivone`).

- As variáveis `$env:...` valem só para aquela janela do PowerShell; defina de novo ao reabrir.
- Se `py` não for reconhecido, instale o Python (python.org/downloads) marcando **Add python.exe to PATH**.
- Em Mac/Linux: troque `$env:X = "y"` por `export X="y"` e `py` por `python3`.

## Atualizando de uma versão anterior

Basta substituir os arquivos. O banco de dados (`data/`) é mantido e atualizado sozinho:
os itens antigos continuam à venda, sem controle de estoque.

## Estoque e disponibilidade

Cada item tem duas coisas independentes:

- **Disponível para venda** (sim/não): vale para qualquer item. Indisponível aparece cinza no cardápio.
- **Controlar quantidade em estoque** (opcional): use em itens comprados prontos (ex.: lolita).
  Informe a quantidade; quando chega a 0 o item aparece como **Esgotado**, e o cliente não
  consegue pedir mais do que existe. Itens feitos na hora (ex.: cachorro-quente) ficam sem esse
  controle e usam só disponível/indisponível.

No painel, itens com estoque têm um campo para atualizar a quantidade rapidamente.
O estoque **não** baixa sozinho quando alguém pede pelo WhatsApp (o pedido ainda precisa ser
confirmado por você): ajuste a quantidade no painel depois de confirmar.

## Pedido pelo WhatsApp

O cliente toca no item, escolhe a quantidade, monta o pedido e toca em
"Enviar pedido pelo WhatsApp": abre a conversa com você já com a lista e o total.
O pagamento (ex.: Pix) é combinado ali. Sem `WHATSAPP_NUMBER` configurado, o cliente monta o pedido
mas o botão de envio fica desativado.

## Variáveis de ambiente

| Variável | Para que serve |
|---|---|
| `ADMIN_PASSWORD` | Senha da administradora (obrigatória) |
| `ADMIN_USER` | Usuário (padrão `ivone`) |
| `WHATSAPP_NUMBER` | Número que recebe os pedidos: só dígitos, com 55 + DDD (ex.: `5581999999999`) |
| `DATA_DIR` | Pasta do banco + fotos (na nuvem, aponte para um disco persistente) |
| `COOKIE_SECURE` | `1` quando o site estiver em HTTPS |
| `SECRET_KEY` | Opcional; se ausente é gerada e guardada em `DATA_DIR` |

## Colocar na nuvem

O projeto já tem `Dockerfile`. Qualquer serviço que rode contêiner serve
(Render, Railway, Fly.io, um VPS...). Pontos importantes:

1. Configure `ADMIN_PASSWORD` e `WHATSAPP_NUMBER` nas variáveis do serviço.
2. **Monte um disco/volume persistente em `/data`.** Sem isso, o banco e as fotos
   somem a cada novo deploy (discos de contêiner são temporários).
3. Mantenha 1 instância (SQLite não é feito para várias réplicas ao mesmo tempo).

## Pagamento online (próximo passo)

Quando quiser cobrar dentro do site: Pix com QR Code, ou um provedor (Mercado Pago, Asaas,
Pagar.me) com confirmação automática. Isso exige guardar os pedidos no banco (o que também
permitiria baixar o estoque automaticamente).
