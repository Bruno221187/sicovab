# Controle Sicovab – SBR

Sistema simples (Python + Streamlit + SQLite) que substitui a planilha *Validação Sicovab SBR.xlsm*.
Na nuvem, cada pessoa acessa pelo endereço do Streamlit Cloud. O `iniciar.bat` abre o sistema só no próprio computador.

## 1. Instalação (uma vez só)

1. Instale o **Python 3.12** em https://www.python.org/downloads/
   Na primeira tela do instalador, marque **"Add python.exe to PATH"**.
2. Copie esta pasta para o computador que vai rodar o sistema (ex.: `C:\ControleSicovab`).
3. Abra o `.streamlit\secrets.toml` no Bloco de Notas e **troque os nomes e as senhas iniciais** dos usuários
   (uma diferente para cada pessoa). No primeiro acesso o sistema obriga cada um a criar a própria senha (mínimo 8 caracteres).
4. Dê dois cliques em **`iniciar.bat`**. Na primeira vez ele baixa o que precisa (alguns minutos, precisa de internet).
   O navegador abre sozinho em http://localhost:8501.

## 2. Trazer os dados da planilha atual (uma vez só)

Com o sistema instalado, dê dois cliques em **`migrar_planilha.bat`**, arraste a planilha `.xlsm` para a janela e tecle Enter.
Isso traz: Notas Sicovab, NBS, NBS Jack, Estoque, **Follow UP Vidros**, Notas não localizadas (com a Obs) e
Notas rejeitadas (com data e motivo).

## 3. Uso no dia a dia

| Tela | Quem vê | Para quê |
|---|---|---|
| **Painel** | com login* | Resumo: notas por status, vencimentos, pendências por fornecedor, estoque e Follow UP |
| **Estoque Sicovab** | com login* | Consultar com filtros e **exportar para Excel** |
| **Importar relatórios** | administradores** | Enviar os Excel do Sicovab, do NBS e do Follow UP (pode mandar vários de uma vez) |
| **Notas Sicovab** | com login | Conferência; aba **Aceitar no Sicovab** com as chaves prontas para copiar; marcar notas como aceita, rejeitada ou não localizada; desfazer |
| **Follow UP Vidros** | com login | Lançar peças (avisa serial repetido e se o serial existe no estoque), editar, excluir, importar em lote |
| **Histórico** | com login | Quem fez o quê e quando (o backup completo só aparece para administradores**) |

\* Enquanto `exigir_login = true` nos segredos (padrão).  \*\* Lista `administradores` nos segredos; se estiver vazia, todos os usuários logados.

Rotina:
1. Importar **Notas Sicovab + NBS** → em **Notas Sicovab > Aceitar no Sicovab**, copiar cada chave, dar o aceite no Sicovab e marcar como feito.
2. Depois dos aceites, baixar e importar o **Estoque Sicovab** e o **Follow UP Vidros**.

Importar o Follow UP pela tela *Importar relatórios* **substitui** todo o Follow UP do sistema pelo arquivo.
Para só acrescentar peças novas, use *Follow UP Vidros > Importar em lote*.

## 4. Acessar de outro computador

Use o endereço do sistema na nuvem (Streamlit Cloud). Por segurança, o `iniciar.bat` só abre o sistema
no próprio computador (http://localhost:8501): ele não fica visível para a rede.

**Segurança do login:** depois de 5 senhas erradas seguidas, o usuário fica bloqueado por 5 minutos
(isso fica registrado no Histórico).

## 5. Regras de status das notas

Na ordem em que são checadas:

1. **Rejeitada** / **Aceita** – marcada por um usuário (Aceita = já foi dado o aceite no Sicovab; some no próximo relatório).
2. **Aceitar / Parcial / Divergente** – a nota entrou no NBS (mesmo CNPJ + mesmo número). Compara a soma das
   quantidades do NBS com o saldo do Sicovab: igual = Aceitar, menor = Parcial, maior = Divergente.
3. **Não localizada** – marcada por um usuário e ainda sem entrada no NBS.
4. **Verificar fornecedor** – o número da nota existe no NBS, mas com outro fornecedor.
5. **Verificar NBS Jack** – só aparece no NBS Jack.
6. **Não recebido** – nenhum dos casos acima.

**Expira em** = data da carga + `prazo_aceite_dias` (config.toml).

## 6. Onde ficam os dados

- Banco: `dados\sicovab.db`. **Copie esta pasta `dados` para o backup da empresa.**
- A cada importação o sistema guarda uma cópia automática em `dados\backups` (mantém as 30 últimas).
- Para voltar um backup: feche o sistema, troque `dados\sicovab.db` pela cópia desejada (renomeando) e abra de novo.

## 7. Configurações (`config.toml`)

Prazo de aceite, dias de alerta, dias para considerar estoque parado, usuários/senhas,
motivos de rejeição e opções de Obs. Depois de salvar, é só recarregar a página.
