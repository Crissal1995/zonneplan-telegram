import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from zonneplan_telegram.api.hourly_prices.model import Prices


def generate_zonneplan_bar_chart(prices: Prices, output_path: str = "chart.png") -> Path:
    """Genera un grafico a barre in stile Zonneplan e restituisce il path dell'immagine."""

    # Prepara le liste per matplotlib
    times = []
    values = []
    colors = []

    now = datetime.datetime.now().astimezone()

    for item in prices:
        start = item.start_date.astimezone()
        price = item.price_cents

        times.append(start)
        values.append(price)

        # Stile Zonneplan: grigio per il passato, verde per il futuro/oggi
        if start < now:
            colors.append("#d0d0d0")  # Grigio chiaro (passato)
        else:
            colors.append("#4caf50")  # Verde (futuro/corrente)

    # Configurazione della figura (stile pulito, senza bordi pesanti)
    fig, ax = plt.subplots(figsize=(12, 6), dpi=200)

    # Disegna il grafico a barre con bordi arrotondati (width impostata per coprire l'ora/quarto d'ora)
    _bars = ax.bar(times, values, width=0.035, color=colors, edgecolor="none", capsize=4)

    # Rimuove i bordi superiori e laterali (spine) per un look minimalista
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cccccc")
    ax.spines["bottom"].set_color("#cccccc")

    # Griglia orizzontale sottile
    ax.yaxis.grid(visible=True, linestyle="-", alpha=0.3, color="#cccccc")
    ax.xaxis.grid(visible=False)
    ax.set_axisbelow(True)

    # Formattazione dell'asse X (mostra le ore in modo pulito)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))  # Un'etichetta ogni 3 ore

    # Margini ed estetica
    plt.xticks(fontsize=10, color="#666666")
    plt.yticks(fontsize=10, color="#666666")
    plt.ylabel("ct / kWh", fontsize=11, color="#666666", labelpad=10)

    # Ottimizza lo spazio
    plt.tight_layout()

    # Salva l'immagine
    output_file = Path(output_path)
    plt.savefig(output_file, format="png", bbox_inches="tight")
    plt.close(fig)

    return output_file
