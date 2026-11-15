"""Vigia das visitas de sábado ao Palácio de São Bento — versão para o GitHub Actions.

Faz o mesmo que a versão do Mac, mas:
- não usa Porta-chaves nem notificações do macOS;
- os dados pessoais vêm de variáveis de ambiente (segredos do repositório),
  para nada de pessoal ficar no código público;
- avisa por e-mail (SMTP) e, se existir NTFY_TOPIC, por push no telemóvel (ntfy.sh).
"""

import html
import json
import os
import re
import smtplib
import sys
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

URL = "https://www.parlamento.pt/EspacoCidadao/Paginas/visitas-palacio-sabado.aspx"
ESTADO = Path(__file__).resolve().parent / "estado.json"

# Segredos (Settings → Secrets and variables → Actions). Nunca escritos aqui.
SMTP_UTILIZADOR = os.environ.get("SMTP_UTILIZADOR", "")
SMTP_PALAVRA_PASSE = os.environ.get("SMTP_PALAVRA_PASSE", "")
EMAIL_DESTINO = os.environ.get("EMAIL_DESTINO", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")


def registar(linha):
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z {linha}", flush=True)


def descarregar(url):
    pedido = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(pedido, timeout=30) as resposta:
        return resposta.read().decode("utf-8", errors="ignore")


def para_texto(html_bruto):
    sem_tags = re.sub(r"<[^>]+>", " ", html_bruto)
    return re.sub(r"\s+", " ", html.unescape(sem_tags)).replace("​", "").strip()


def ler_pagina():
    bruto = descarregar(URL)
    texto = para_texto(bruto)
    inicio = texto.find("Conteúdo da Página")
    fim = texto.find("Venha conhecer")
    if inicio != -1 and fim != -1:
        texto = texto[inicio + len("Conteúdo da Página"):fim].strip()
    links = re.findall(r'https://(?:docs\.google\.com/forms|forms\.gle)[^"\'<> ]*',
                       html.unescape(bruto))
    return texto, sorted(set(links))


def formulario_aberto(link):
    pagina = descarregar(link)
    return "Já não é possível" not in pagina and "no longer accepting" not in pagina


def enviar_email(assunto, corpo):
    if not (SMTP_UTILIZADOR and SMTP_PALAVRA_PASSE and EMAIL_DESTINO):
        registar("e-mail não configurado (faltam segredos)")
        return
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_UTILIZADOR
        msg["To"] = EMAIL_DESTINO
        msg["Subject"] = assunto
        msg.set_content(corpo)
        with smtplib.SMTP("smtp.mail.me.com", 587, timeout=30) as servidor:
            servidor.starttls()
            servidor.login(SMTP_UTILIZADOR, SMTP_PALAVRA_PASSE)
            servidor.send_message(msg)
        registar("e-mail enviado")
    except Exception as erro:
        registar(f"ERRO no e-mail: {erro!r}")


def enviar_push(titulo, corpo, link=None):
    if not NTFY_TOPIC:
        return
    try:
        # Os cabeçalhos HTTP só aceitam ASCII; por isso o título vai sem acentos.
        cabecalhos = {"Title": titulo.encode("ascii", "ignore").decode(),
                      "Priority": "urgent"}
        if link:
            cabecalhos["Click"] = link
        pedido = urllib.request.Request("https://ntfy.sh/" + NTFY_TOPIC,
                                        data=corpo.encode("utf-8"), headers=cabecalhos)
        urllib.request.urlopen(pedido, timeout=30).read()
        registar("push enviado")
    except Exception as erro:
        registar(f"ERRO no push: {erro!r}")


def avisar(titulo, texto, links=()):
    corpo = f"{texto}\n\nPágina: {URL}\n" + "".join(f"Formulário: {l}\n" for l in links)
    enviar_push(titulo, texto[:300], links[0] if links else URL)
    enviar_email(titulo, corpo)


def main():
    antes = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    texto, links = ler_pagina()
    formularios = {link: formulario_aberto(link) for link in links}

    abertos_novos = [l for l, aberto in formularios.items()
                     if aberto and not antes.get("formularios", {}).get(l, False)]

    if abertos_novos:
        registar(f"ABERTO: {abertos_novos}")
        avisar("Parlamento: INSCRICOES ABERTAS!", texto, abertos_novos)
    elif antes and texto != antes.get("texto"):
        registar(f"MUDOU: {texto}")
        avisar("Parlamento: a pagina das visitas mudou", texto)
    else:
        registar("sem novidades")

    ESTADO.write_text(json.dumps({"texto": texto, "formularios": formularios},
                                 ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if "--testar-aviso" in sys.argv:
        avisar("Teste: vigia do Parlamento", "Se recebeste isto, o aviso funciona.")
        sys.exit()
    try:
        main()
    except Exception as erro:
        registar(f"ERRO: {erro!r}")
