import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import ticker

from zonneplan_telegram.api.hourly_prices.model import Prices


def generate_zonneplan_bar_chart(prices: Prices, output_path: str = "chart.png") -> Path:
    """Genera un grafico a barre in stile Zonneplan con l'ora corrente colorata di verde."""

    times = []
    values = []
    colors = []

    now_local = datetime.datetime.now().astimezone()

    for item in prices:
        start_local = item.start_date.astimezone()
        end_local = item.end_date.astimezone()
        price = item.price_cents

        times.append(start_local)
        values.append(price)

        # Stile Zonneplan: grigio per il passato, verde per il futuro/oggi
        # Una barra è grigia (passata) SOLO SE l'intero intervallo è già concluso (end_local <= now_local).
        # Se ci troviamo dentro l'intervallo (start <= now < end) o è futuro, diventa verde.
        if end_local <= now_local:
            colors.append("#d0d0d0")  # Grigio (già passato)
        else:
            colors.append("#4caf50")  # Verde (ora in corso / futuro)

    # Configurazione della figura
    fig, ax = plt.subplots(figsize=(12, 6), dpi=200)

    # Disegna il grafico a barre
    ax.bar(times, values, width=0.035, color=colors, edgecolor="none")

    ax.yaxis.set_major_locator(ticker.MultipleLocator(5))

    # Stile minimalista pulito
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cccccc")
    ax.spines["bottom"].set_color("#cccccc")

    ax.yaxis.grid(visible=True, linestyle="-", alpha=0.3, color="#cccccc")
    ax.xaxis.grid(visible=False)
    ax.set_axisbelow(True)

    # Formattazione dell'asse X vincolata all'ora locale
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H", tz=now_local.tzinfo))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))

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
