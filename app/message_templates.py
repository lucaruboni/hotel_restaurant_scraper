"""Template del messaggio di primo contatto, uno per profilo commerciale.

Un punto di partenza da modificare a mano prima di inviarlo, non un testo
da spedire così com'è: ogni lead merita almeno una riga di aggancio vera
(qualcosa vista sul sito, un dettaglio della struttura). Il posizionamento
riflette l'offerta di BLU — siti, automazioni, consulenza AI — non un'agenzia
generica: se l'offerta cambia, questo è l'unico file da aggiornare.
"""

from scraper.categories import CATEGORY_GROUP

TEMPLATE_PER_GRUPPO = {
    "ricettivo": (
        "Ciao, sono {mittente} di BLU — un collettivo che si occupa di siti, "
        "automazioni e presenza online per attività ricettive. Ho visto {nome}"
        "{zona_frase} e volevo capire come gestite oggi le prenotazioni dirette "
        "e la presenza sui social: spesso c'è margine per ridurre la dipendenza "
        "dalle OTA con poco sforzo. Vi va una chiamata di 15 minuti questa "
        "settimana?"
    ),
    "professionisti": (
        "Ciao, sono {mittente} di BLU. Ci occupiamo di siti, automazioni e "
        "consulenza AI per studi professionali. Molti studi come {nome}"
        "{zona_frase} perdono contatti utili per un sito poco curato o per "
        "processi manuali che si potrebbero automatizzare — mi piacerebbe "
        "capire come lavorate oggi e se ha senso una chiacchierata di 15 "
        "minuti."
    ),
    "ecommerce": (
        "Ciao, sono {mittente} di BLU. Lavoriamo con piccoli produttori per "
        "portare online la vendita diretta — sito, automazioni, presenza "
        "social — senza passare dalla grande distribuzione. Avete già "
        "considerato l'e-commerce per {nome}, o l'idea è stata accantonata "
        "per mancanza di tempo? Mi piacerebbe fare due chiacchiere."
    ),
}

DEFAULT_MITTENTE = "[il tuo nome]"


def genera_messaggio_contatto(lead, mittente: str = "") -> str:
    """Messaggio di primo contatto per un lead, pronto da rifinire a mano."""
    gruppo = CATEGORY_GROUP.get(lead.categoria, "ricettivo")
    modello = TEMPLATE_PER_GRUPPO.get(gruppo, TEMPLATE_PER_GRUPPO["ricettivo"])
    zona_frase = f" a {lead.zona.title()}" if lead.zona else ""
    return modello.format(
        mittente=mittente or DEFAULT_MITTENTE,
        nome=lead.nome,
        zona_frase=zona_frase,
    )
