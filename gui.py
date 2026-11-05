"""Interface graphique CustomTkinter de L'Observatoire Météo.

Lancer :  python gui.py
"""
import csv
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

try:
    import tkintermapview
    import tkintermapview.map_widget as map_widget_module
    import requests
    import requests_cache
    from types import SimpleNamespace

    # TkinterMapView uses a generic User-Agent by default. OpenStreetMap
    # requires desktop applications to identify themselves and cache tiles.
    _tile_session = requests_cache.CachedSession(
        cache_name="observatoire_meteo_tiles",
        backend="sqlite",
        expire_after=7 * 24 * 60 * 60,
        cache_control=True,
    )

    def _identified_tile_request(url, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["User-Agent"] = "ObservatoireMeteo/1.0 (desktop application)"
        return _tile_session.get(url, headers=headers, **kwargs)

    # Patch only the HTTP client used by the map widget, not the weather API.
    map_widget_module.requests = SimpleNamespace(
        get=_identified_tile_request,
        exceptions=requests.exceptions,
    )
except ImportError:  # La carte reste facultative si ses dépendances manquent.
    tkintermapview = None

import client
import database
import pipeline
import weather_features
import reporting
import radar_service

# ------------------------------------------------------------------ palette
BG = "#0b0e1a"
SIDEBAR = "#10142a"
CARD = "#171c36"
CARD_HOVER = "#1d2344"
BORDER = "#262d55"
TEXT = "#eef0ff"
SOFT = "#b9c0ea"
MUTED = "#7f89bd"
ACCENT = "#6c8cff"
GOOD = "#4cd7a8"
BAD = "#ff6b81"
FONT = "Segoe UI"

TEMP_STOPS = [
    (-10, "#7aa2ff"), (0, "#5ac8fa"), (10, "#4cd7a8"),
    (20, "#ffd166"), (30, "#ff8a4c"), (40, "#ff4d4d"),
]


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(c1: str, c2: str, t: float) -> str:
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def temp_color(t: float) -> str:
    """Couleur dégradée du bleu glacé au rouge brûlant selon la température."""
    if t <= TEMP_STOPS[0][0]:
        return TEMP_STOPS[0][1]
    for (t0, c0), (t1, c1) in zip(TEMP_STOPS, TEMP_STOPS[1:]):
        if t <= t1:
            return blend(c0, c1, (t - t0) / (t1 - t0))
    return TEMP_STOPS[-1][1]


def wind_color(v: float) -> str:
    if v < 20: return GOOD
    if v < 40: return "#ffd166"
    if v < 60: return "#ff8a4c"
    return BAD


def wind_info(v: float):
    if v < 12:
        return "Calme", GOOD
    if v < 29:
        return "Brise légère", GOOD
    if v < 50:
        return "Vent modéré", "#ffd166"
    if v < 75:
        return "Vent fort", "#ff8a4c"
    return "Tempête", BAD


def fmt_dt(s: str, fmt: str = "%d/%m %H:%M") -> str:
    try:
        return datetime.fromisoformat(s).strftime(fmt)
    except ValueError:
        return s


def font(size: int, weight: str = "normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


# ------------------------------------------------------------------ graphique
class LineChart(tk.Canvas):
    """Courbe lissée dessinée à la main (aucune dépendance à matplotlib), avec infobulle."""

    PAD_L, PAD_R, PAD_T, PAD_B = 46, 22, 22, 34

    def __init__(self, master, **kw):
        super().__init__(master, bg=CARD, highlightthickness=0, **kw)
        self.points: list[tuple[str, float]] = []
        self.color = ACCENT
        self._coords: list[tuple[float, float]] = []
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self.delete("tip"))

    def set_data(self, points, color):
        self.points, self.color = points, color
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 120 or h < 100:
            return
        if not self.points:
            self.create_text(w / 2, h / 2, text="Pas encore de relevés",
                             fill=MUTED, font=(FONT, 12))
            return

        vals = [v for _, v in self.points]
        lo, hi = min(vals), max(vals)
        if hi - lo < 2:
            mid = (hi + lo) / 2
            lo, hi = mid - 1, mid + 1
        pad = (hi - lo) * 0.18
        lo, hi = lo - pad, hi + pad

        x0, x1 = self.PAD_L, w - self.PAD_R
        y0, y1 = self.PAD_T, h - self.PAD_B
        n = len(self.points)

        for i in range(5):                                   # grille + axe Y
            y = y0 + (y1 - y0) * i / 4
            self.create_line(x0, y, x1, y, fill=BORDER, dash=(2, 4))
            self.create_text(x0 - 10, y, text=f"{hi - (hi - lo) * i / 4:.0f}°",
                             fill=MUTED, anchor="e", font=(FONT, 9))

        def px(i):
            return x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0.5)

        def py(v):
            return y1 - (y1 - y0) * (v - lo) / (hi - lo)

        self._coords = [(px(i), py(v)) for i, (_, v) in enumerate(self.points)]

        if n > 1:                                            # aire sous la courbe
            poly = [c for xy in self._coords for c in xy]
            poly += [self._coords[-1][0], y1, self._coords[0][0], y1]
            self.create_polygon(poly, fill=blend(CARD, self.color, 0.16), outline="")
            flat = [c for xy in self._coords for c in xy]
            self.create_line(*flat, fill=blend(CARD, self.color, 0.35), width=7,
                             smooth=True, capstyle="round")
            self.create_line(*flat, fill=self.color, width=3, smooth=True, capstyle="round")

        for x, y in self._coords:                            # points
            self.create_oval(x - 4.5, y - 4.5, x + 4.5, y + 4.5,
                             fill=self.color, outline=CARD, width=2)

        idx = sorted({0, n // 2, n - 1})                     # axe X
        for i in idx:
            anchor = "w" if i == 0 and n > 1 else ("e" if i == n - 1 and n > 1 else "center")
            self.create_text(self._coords[i][0], y1 + 18, text=self.points[i][0],
                             fill=MUTED, anchor=anchor, font=(FONT, 9))

    def _hover(self, e):
        self.delete("tip")
        if not self._coords:
            return
        i = min(range(len(self._coords)), key=lambda k: abs(self._coords[k][0] - e.x))
        x, y = self._coords[i]
        label, val = self.points[i]
        self.create_line(x, self.PAD_T, x, self.winfo_height() - self.PAD_B,
                         fill=SOFT, dash=(3, 3), tags="tip")
        self.create_oval(x - 7, y - 7, x + 7, y + 7, fill=TEXT, outline=self.color,
                         width=3, tags="tip")
        bw, bh = 118, 46
        bx = min(max(x - bw / 2, 4), self.winfo_width() - bw - 4)
        by = y - bh - 16 if y - bh - 16 > 4 else y + 16
        self.create_rectangle(bx, by, bx + bw, by + bh, fill="#0b0e1a",
                              outline=self.color, width=1, tags="tip")
        self.create_text(bx + bw / 2, by + 14, text=label, fill=MUTED,
                         font=(FONT, 9), tags="tip")
        self.create_text(bx + bw / 2, by + 32, text=f"{val:.1f} °C", fill=TEXT,
                         font=(FONT, 12, "bold"), tags="tip")


# ------------------------------------------------------------------ widgets
class StatCard(ctk.CTkFrame):
    def __init__(self, master, title: str):
        super().__init__(master, fg_color=CARD, corner_radius=20,
                         border_width=1, border_color=BORDER)
        self.bar = ctk.CTkFrame(self, width=34, height=4, corner_radius=2, fg_color=ACCENT)
        self.bar.grid(row=0, column=0, sticky="w", padx=20, pady=(18, 0))
        ctk.CTkLabel(self, text=title.upper(), font=font(11, "bold"),
                     text_color=MUTED).grid(row=1, column=0, sticky="w", padx=20, pady=(10, 0))
        self.value = ctk.CTkLabel(self, text="–", font=font(34, "bold"), text_color=TEXT)
        self.value.grid(row=2, column=0, sticky="w", padx=20)
        self.sub = ctk.CTkLabel(self, text="", font=font(12), text_color=MUTED)
        self.sub.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 18))

    def set(self, value: str, sub: str = "", color: str = ACCENT):
        self.bar.configure(fg_color=color)
        self.value.configure(text=value)
        self.sub.configure(text=sub)


class CityRow(ctk.CTkFrame):
    def __init__(self, master, nom, temp, selected, on_click):
        super().__init__(master, fg_color=CARD if selected else "transparent",
                         corner_radius=12, height=46)
        self.selected = selected
        self.grid_columnconfigure(0, weight=1)
        self.name = ctk.CTkLabel(self, text=nom, anchor="w", font=font(14, "bold" if selected else "normal"),
                                 text_color=TEXT if selected else SOFT)
        self.name.grid(row=0, column=0, sticky="w", padx=(14, 6), pady=11)
        self.temp = ctk.CTkLabel(self, text="–" if temp is None else f"{temp:.0f}°",
                                 font=font(14, "bold"),
                                 text_color=MUTED if temp is None else temp_color(temp))
        self.temp.grid(row=0, column=1, padx=(6, 14))
        for w in (self, self.name, self.temp):
            w.bind("<Button-1>", lambda e, n=nom: on_click(n))
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _enter(self, _):
        if not self.selected:
            self.configure(fg_color=CARD_HOVER)

    def _leave(self, _):
        if not self.selected:
            self.configure(fg_color="transparent")


# ------------------------------------------------------------------ application
class App(ctk.CTk):
    AUTO_MS = 15 * 60 * 1000

    def __init__(self):
        super().__init__(fg_color=BG)
        ctk.set_appearance_mode("dark")
        self.title("Observatoire Météo")
        self.geometry("1240x800")
        self.minsize(1020, 680)

        self.current: str | None = None
        self.busy = False
        self._q: queue.Queue = queue.Queue()
        self._toast_job = None
        self._radar_frames = []
        self._radar_playing = False
        self._radar_job = None
        self.alerts_enabled = False

        database.init_db()
        self.alerts_enabled = database.get_setting("windows_alerts", "0") == "1"
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self._build_map_view()

        self.reload_cities()
        villes = self._villes()
        if villes:
            self.select_city(villes[0]["nom"])
        else:
            self._show_empty(True)

        self.after(100, self._poll)
        self.after(self.AUTO_MS, self._auto_tick)
        self.after(30_000, self._alert_tick)

    # ---------------------------------------------------------- construction
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=300, fg_color=SIDEBAR, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(4, weight=1)

        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=24, pady=(28, 0))
        ctk.CTkLabel(brand, text="Observatoire", font=font(26, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(brand, text="Météo en temps réel · Open-Meteo", font=font(12),
                     text_color=MUTED).pack(anchor="w")

        self.entry = ctk.CTkEntry(sb, placeholder_text="Ajouter une ville…", height=44,
                                  corner_radius=14, fg_color=CARD, border_color=BORDER,
                                  border_width=1, text_color=TEXT, font=font(14))
        self.entry.grid(row=1, column=0, sticky="ew", padx=24, pady=(28, 10))
        self.entry.bind("<Return>", lambda e: self.add_city())

        self.add_btn = ctk.CTkButton(sb, text="＋  Ajouter / actualiser", height=44,
                                     corner_radius=14, fg_color=ACCENT, hover_color="#5878e6",
                                     font=font(14, "bold"), command=self.add_city)
        self.add_btn.grid(row=2, column=0, sticky="ew", padx=24)

        ctk.CTkLabel(sb, text="VILLES SUIVIES", font=font(11, "bold"),
                     text_color=MUTED).grid(row=3, column=0, sticky="w", padx=26, pady=(28, 6))

        self.city_list = ctk.CTkScrollableFrame(sb, fg_color="transparent",
                                                scrollbar_button_color=BORDER,
                                                scrollbar_button_hover_color=MUTED)
        self.city_list.grid(row=4, column=0, sticky="nsew", padx=(14, 8))
        self.city_list.grid_columnconfigure(0, weight=1)

        foot = ctk.CTkFrame(sb, fg_color="transparent")
        foot.grid(row=5, column=0, sticky="ew", padx=24, pady=(10, 24))
        foot.grid_columnconfigure(0, weight=1)
        self.map_btn = ctk.CTkButton(foot, text="⌖  Carte interactive", height=40,
                                     corner_radius=12, fg_color=ACCENT, hover_color="#5878e6",
                                     text_color=TEXT, font=font(13, "bold"), command=self.show_map)
        self.map_btn.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.all_btn = ctk.CTkButton(foot, text="⟳  Tout actualiser", height=40,
                                     corner_radius=12, fg_color=CARD, hover_color=CARD_HOVER,
                                     border_width=1, border_color=BORDER, text_color=SOFT,
                                     font=font(13, "bold"), command=self.refresh_all)
        self.all_btn.grid(row=1, column=0, sticky="ew")
        self.auto = ctk.CTkSwitch(foot, text="Actualisation auto (15 min)", font=font(12),
                                  text_color=MUTED, progress_color=ACCENT)
        self.auto.grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.forecast_btn = ctk.CTkButton(foot, text="☼  Prévisions & alertes", height=40,
                                          corner_radius=12, fg_color=CARD, hover_color=CARD_HOVER,
                                          border_width=1, border_color=BORDER, text_color=SOFT,
                                          font=font(13, "bold"), command=self.show_forecast)
        self.forecast_btn.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.export_btn = ctk.CTkButton(foot, text="↓  Exporter l'historique CSV", height=36,
                                        corner_radius=12, fg_color=CARD, hover_color=CARD_HOVER,
                                        border_width=1, border_color=BORDER, text_color=SOFT,
                                        font=font(12), command=self.export_csv)
        self.export_btn.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.radar_btn = ctk.CTkButton(foot, text="◉  Radar des précipitations", height=36,
            corner_radius=12, fg_color=CARD, hover_color=CARD_HOVER, border_width=1,
            border_color=BORDER, text_color=SOFT, font=font(12), command=self.show_radar)
        self.radar_btn.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.compare_btn = ctk.CTkButton(foot, text="⇄  Comparer les villes", height=36,
            corner_radius=12, fg_color=CARD, hover_color=CARD_HOVER, border_width=1,
            border_color=BORDER, text_color=SOFT, font=font(12), command=self.show_city_comparison)
        self.compare_btn.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self.alert_center_btn = ctk.CTkButton(foot, text="⚠  Centre de vigilance", height=36,
            corner_radius=12, fg_color=CARD, hover_color=CARD_HOVER, border_width=1,
            border_color=BORDER, text_color=SOFT, font=font(12), command=self.show_alert_center)
        self.alert_center_btn.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self.alert_switch = ctk.CTkSwitch(foot, text="Notifications Windows", font=font(12),
            text_color=MUTED, progress_color=ACCENT, command=self.toggle_alerts)
        self.alert_switch.grid(row=8, column=0, sticky="w", pady=(10, 0))
        if self.alerts_enabled:
            self.alert_switch.select()

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=32, pady=28)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        self.main = main

        # en-tête
        head = ctk.CTkFrame(main, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        self.city_label = ctk.CTkLabel(head, text="", font=font(36, "bold"), text_color=TEXT, anchor="w")
        self.city_label.grid(row=0, column=0, sticky="w")
        self.meta_label = ctk.CTkLabel(head, text="", font=font(13), text_color=MUTED, anchor="w")
        self.meta_label.grid(row=1, column=0, sticky="w")
        right = ctk.CTkFrame(head, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        self.progress = ctk.CTkProgressBar(right, mode="indeterminate", width=120, height=6,
                                           progress_color=ACCENT, fg_color=BORDER)
        self.progress.grid(row=0, column=0, padx=(0, 16))
        self.progress.grid_remove()
        self.refresh_btn = ctk.CTkButton(right, text="⟳  Actualiser", width=140, height=42,
                                         corner_radius=14, fg_color=CARD, hover_color=CARD_HOVER,
                                         border_width=1, border_color=BORDER, text_color=TEXT,
                                         font=font(13, "bold"), command=self.refresh_current)
        self.refresh_btn.grid(row=0, column=1)
        self.history_period = ctk.CTkOptionMenu(right, values=["24 h", "7 jours", "30 jours", "1 an"],
            width=105, height=38, fg_color=CARD, button_color=BORDER, button_hover_color=CARD_HOVER,
            command=self.change_history_period)
        self.history_period.set("7 jours")
        self.history_period.grid(row=0, column=2, padx=(10, 0))

        # cartes
        cards = ctk.CTkFrame(main, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", pady=(22, 18))
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1, uniform="cards")
        self.c_temp = StatCard(cards, "Température")
        self.c_wind = StatCard(cards, "Vent")
        self.c_avg = StatCard(cards, "Moyenne")
        self.c_range = StatCard(cards, "Min / Max")
        for i, c in enumerate((self.c_temp, self.c_wind, self.c_avg, self.c_range)):
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 0 if i == 3 else 7))

        # graphique + tableau
        bottom = ctk.CTkFrame(main, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="nsew")
        bottom.grid_columnconfigure(0, weight=3)
        bottom.grid_columnconfigure(1, weight=2, minsize=280)
        bottom.grid_rowconfigure(0, weight=1)

        chart_panel = ctk.CTkFrame(bottom, fg_color=CARD, corner_radius=20,
                                   border_width=1, border_color=BORDER)
        chart_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        chart_panel.grid_columnconfigure(0, weight=1)
        chart_panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(chart_panel, text="Évolution de la température", font=font(15, "bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 0))
        self.chart = LineChart(chart_panel)
        self.chart.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 12))

        table_panel = ctk.CTkFrame(bottom, fg_color=CARD, corner_radius=20,
                                   border_width=1, border_color=BORDER)
        table_panel.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        table_panel.grid_columnconfigure(0, weight=1)
        table_panel.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(table_panel, text="Derniers relevés", font=font(15, "bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 8))
        hdr = ctk.CTkFrame(table_panel, fg_color="transparent")
        hdr.grid(row=1, column=0, sticky="ew", padx=22)
        for c, (t, a) in enumerate((("DATE", "w"), ("TEMP.", "e"), ("VENT", "e"))):
            hdr.grid_columnconfigure(c, weight=1)
            ctk.CTkLabel(hdr, text=t, font=font(10, "bold"), text_color=MUTED,
                         anchor=a).grid(row=0, column=c, sticky=a)
        self.table = ctk.CTkScrollableFrame(table_panel, fg_color="transparent",
                                            scrollbar_button_color=BORDER,
                                            scrollbar_button_hover_color=MUTED)
        self.table.grid(row=2, column=0, sticky="nsew", padx=(12, 6), pady=(4, 12))
        self.table.grid_columnconfigure(0, weight=1)

        # message
        self.toast_label = ctk.CTkLabel(main, text="", font=font(13, "bold"), text_color=GOOD, anchor="w")
        self.toast_label.grid(row=3, column=0, sticky="ew", pady=(12, 0))

        # état vide
        self.empty = ctk.CTkLabel(
            self, text="Aucune ville pour l'instant\n\nTape un nom dans la barre de gauche\npuis clique sur « Ajouter / actualiser »",
            font=font(18), text_color=MUTED, justify="center")

    def _build_map_view(self):
        """Construit la page cartographique dans la fenêtre principale."""
        self.map_view = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.map_view.grid(row=0, column=1, sticky="nsew", padx=32, pady=28)
        self.map_view.grid_columnconfigure(0, weight=1)
        self.map_view.grid_rowconfigure(1, weight=1)
        self.map_view.grid_remove()

        header = ctk.CTkFrame(self.map_view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.grid_columnconfigure(0, weight=1)
        self.map_metric = ctk.StringVar(value="Température")
        ctk.CTkOptionMenu(header, values=["Température", "Vent"], variable=self.map_metric,
                          width=120, height=36, command=lambda _v: self.refresh_map()).grid(
                              row=0, column=1, rowspan=2, padx=8, sticky="e")
        ctk.CTkLabel(header, text="Carte météorologique", font=font(30, "bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Clique sur un marqueur pour consulter le dernier relevé",
                     font=font(13), text_color=MUTED).grid(row=1, column=0, sticky="w")
        ctk.CTkButton(header, text="↩  Tableau de bord", width=160, height=40,
                      corner_radius=12, fg_color=CARD, hover_color=CARD_HOVER,
                      border_width=1, border_color=BORDER, text_color=TEXT,
                      font=font(13, "bold"), command=self.show_dashboard).grid(
                          row=0, column=2, rowspan=2, sticky="e")

        map_panel = ctk.CTkFrame(self.map_view, fg_color=CARD, corner_radius=20,
                                 border_width=1, border_color=BORDER)
        map_panel.grid(row=1, column=0, sticky="nsew")
        map_panel.grid_rowconfigure(0, weight=1)
        map_panel.grid_columnconfigure(0, weight=1)

        if tkintermapview is None:
            ctk.CTkLabel(
                map_panel,
                text="La carte nécessite tkintermapview.\n\nInstalle les dépendances avec :\npip install -r requirements.txt",
                font=font(16), text_color=SOFT, justify="center",
            ).grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
            self.map_widget = None
            return

        self.map_widget = tkintermapview.TkinterMapView(
            map_panel, corner_radius=16, use_database_only=False
        )
        self.map_widget.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        ctk.CTkLabel(
            map_panel, text="© OpenStreetMap contributors",
            font=font(10), text_color=SOFT, fg_color=CARD,
            corner_radius=6,
        ).place(relx=0.99, rely=0.985, anchor="se")
        self.map_widget.set_tile_server(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=19
        )
        self.map_widget.set_position(46.603354, 1.888334)
        self.map_widget.set_zoom(6)
        self.refresh_map()

    def show_map(self):
        self.main.grid_remove()
        self.map_view.grid()
        self.refresh_map()

    def show_dashboard(self):
        self.map_view.grid_remove()
        self.main.grid()

    def refresh_map(self):
        """Recharge les marqueurs depuis les villes et relevés présents dans SQLite."""
        if self.map_widget is None:
            return
        self.map_widget.delete_all_marker()
        conn = database.get_connection()
        try:
            villes = database.lister_villes(conn)
            for ville in villes:
                releves = database.releves_ville(conn, ville["nom"], 1)
                if releves:
                    releve = releves[0]
                    temperature = releve["temperature"]
                    vent = releve["vitesse_vent"]
                    details = (
                        f"{ville['nom']}\n"
                        f"Température : {temperature:.1f} °C\n"
                        f"Vent : {vent:.0f} km/h\n"
                        f"Relevé : {fmt_dt(releve['date_heure'])}"
                    )
                    color = wind_color(vent) if getattr(self, "map_metric", None) and self.map_metric.get() == "Vent" else temp_color(temperature)
                else:
                    details = f"{ville['nom']}\nAucun relevé disponible"
                    color = MUTED
                self.map_widget.set_marker(
                    ville["latitude"], ville["longitude"], text=details,
                    marker_color_circle=color, marker_color_outside=TEXT,
                )
        finally:
            conn.close()
        if villes:
            self.map_widget.set_position(villes[0]["latitude"], villes[0]["longitude"])
            self.map_widget.set_zoom(5 if len(villes) > 1 else 8)

    # ---------------------------------------------------------- données
    def _villes(self):
        conn = database.get_connection()
        try:
            return database.lister_villes(conn)
        finally:
            conn.close()

    def reload_cities(self, select: str | None = None):
        conn = database.get_connection()
        try:
            villes = database.lister_villes(conn)
            last = {v["nom"]: (database.releves_ville(conn, v["nom"], 1) or [None])[0] for v in villes}
        finally:
            conn.close()
        if select:
            self.current = select
        for w in self.city_list.winfo_children():
            w.destroy()
        for i, v in enumerate(villes):
            r = last[v["nom"]]
            CityRow(self.city_list, v["nom"], r["temperature"] if r else None,
                    v["nom"].lower() == (self.current or "").lower(),
                    self.select_city).grid(row=i, column=0, sticky="ew", pady=2)

    def select_city(self, nom: str):
        self.current = nom
        self._show_empty(False)
        self.reload_cities()
        self.show_city(nom)

    def _show_empty(self, on: bool):
        if on:
            self.main.grid_remove()
            self.empty.grid(row=0, column=1)
        else:
            self.empty.grid_remove()
            self.main.grid()

    def show_city(self, nom: str):
        conn = database.get_connection()
        try:
            period = self.history_period.get() if getattr(self, "history_period", None) else "7 jours"
            days = {"24 h": 1, "7 jours": 7, "30 jours": 30, "1 an": 365}.get(period, 7)
            rows = database.historique_ville(conn, nom, days, 5000)
            stats = database.stats_ville(conn, nom)
            ville = next((v for v in database.lister_villes(conn)
                          if v["nom"].lower() == nom.lower()), None)
        finally:
            conn.close()

        self.city_label.configure(text=nom)
        meta = ""
        if ville:
            ns = "N" if ville["latitude"] >= 0 else "S"
            eo = "E" if ville["longitude"] >= 0 else "O"
            meta = f"{abs(ville['latitude']):.2f}°{ns}  ·  {abs(ville['longitude']):.2f}°{eo}"
        if rows:
            meta += f"  ·  {stats['nb_releves']} relevé(s)  ·  dernier : {fmt_dt(rows[0]['date_heure'])}"
        self.meta_label.configure(text=meta)

        if rows:
            last = rows[0]
            t, v = last["temperature"], last["vitesse_vent"]
            label, wcol = wind_info(v)
            self.c_temp.set(f"{t:.1f}°C", "Dernier relevé", temp_color(t))
            self.c_wind.set(f"{v:.0f} km/h", label, wcol)
            self.c_avg.set(f"{stats['temperature_moyenne']:.1f}°C",
                           f"sur {stats['nb_releves']} relevé(s)",
                           temp_color(stats["temperature_moyenne"]))
            amp = stats["temperature_max"] - stats["temperature_min"]
            self.c_range.set(f"{stats['temperature_min']:.0f}° / {stats['temperature_max']:.0f}°",
                             f"amplitude {amp:.1f}°", ACCENT)
            self.chart.set_data([(fmt_dt(r["date_heure"]), r["temperature"]) for r in reversed(rows)],
                                temp_color(t))
        else:
            for c in (self.c_temp, self.c_wind, self.c_avg, self.c_range):
                c.set("–", "Aucun relevé", MUTED)
            self.chart.set_data([], ACCENT)

        for w in self.table.winfo_children():
            w.destroy()
        for i, r in enumerate(rows[:40]):
            row = ctk.CTkFrame(self.table, fg_color=CARD_HOVER if i % 2 == 0 else "transparent",
                               corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", pady=1)
            for c in range(3):
                row.grid_columnconfigure(c, weight=1, uniform="t")
            ctk.CTkLabel(row, text=fmt_dt(r["date_heure"]), font=font(12), text_color=SOFT,
                         anchor="w").grid(row=0, column=0, sticky="w", padx=(10, 0), pady=6)
            ctk.CTkLabel(row, text=f"{r['temperature']:.1f}°", font=font(12, "bold"),
                         text_color=temp_color(r["temperature"]),
                         anchor="e").grid(row=0, column=1, sticky="e")
            ctk.CTkLabel(row, text=f"{r['vitesse_vent']:.0f} km/h", font=font(12),
                         text_color=SOFT, anchor="e").grid(row=0, column=2, sticky="e", padx=(0, 10))

    # ---------------------------------------------------------- actions asynchrones
    def _run(self, func, on_done):
        if self.busy:
            return
        self._set_busy(True)

        def worker():
            try:
                self._q.put((on_done, func(), None))
            except Exception as e:               # noqa: BLE001 - remonté à l'interface
                self._q.put((on_done, None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            while True:
                cb, res, err = self._q.get_nowait()
                self._set_busy(False)
                cb(res, err)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.add_btn, self.refresh_btn, self.all_btn):
            b.configure(state=state)
        if busy:
            self.progress.grid()
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_remove()

    def _error_text(self, err: Exception) -> str:
        return str(err) if isinstance(err, client.ApiError) else f"Erreur : {err}"

    def add_city(self):
        nom = self.entry.get().strip()
        if not nom:
            self.toast("Écris le nom d'une ville.", BAD)
            return
        self._fetch(nom)

    def refresh_current(self):
        if self.current:
            self._fetch(self.current)

    def _fetch(self, nom: str):
        def done(res, err):
            if err:
                self.toast(self._error_text(err), BAD)
                return
            vrai_nom, nouveau = res
            self.entry.delete(0, "end")
            self._show_empty(False)
            self.current = vrai_nom
            self.reload_cities()
            self.show_city(vrai_nom)
            self.refresh_map()
            self.toast("Nouveau relevé enregistré ✓" if nouveau
                       else "Déjà à jour : relevé de cette heure déjà en base", GOOD if nouveau else SOFT)

        self._run(lambda: pipeline.collecter_ville(nom), done)

    def refresh_all(self):
        noms = [v["nom"] for v in self._villes()]
        if not noms:
            self.toast("Aucune ville à actualiser.", BAD)
            return

        def work():
            ok = ko = 0
            for n in noms:
                try:
                    pipeline.collecter_ville(n)
                    ok += 1
                except client.ApiError:
                    ko += 1
            return ok, ko

        def done(res, err):
            if err:
                self.toast(self._error_text(err), BAD)
                return
            ok, ko = res
            self.reload_cities()
            if self.current:
                self.show_city(self.current)
            self.refresh_map()
            self.toast(f"{ok} ville(s) actualisée(s)" + (f", {ko} en échec" if ko else " ✓"),
                       GOOD if not ko else BAD)

        self._run(work, done)

    def change_history_period(self, _value=None):
        if self.current:
            self.show_city(self.current)

    def export_csv(self):
        if not self.current:
            self.toast("Sélectionne une ville avant l'export.", BAD)
            return
        days = {"24 h": 1, "7 jours": 7, "30 jours": 30, "1 an": 365}.get(self.history_period.get(), 7)
        path = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("Fichier CSV", "*.csv")], initialfile=f"historique_{self.current}.csv")
        if not path:
            return
        conn = database.get_connection()
        try:
            rows = database.historique_ville(conn, self.current, days, 10000)
        finally:
            conn.close()
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["Ville", "Date et heure", "Temperature (C)", "Vent (km/h)"])
            writer.writerows([[r["ville"], r["date_heure"], r["temperature"], r["vitesse_vent"]] for r in rows])
        self.toast(f"Export CSV créé : {len(rows)} relevé(s).", GOOD)

    def show_forecast(self):
        nom = self.current
        if not nom:
            villes = self._villes()
            nom = villes[0]["nom"] if villes else None
        if not nom:
            self.toast("Ajoute d'abord une ville.", BAD)
            return
        conn = database.get_connection()
        try:
            ville = next((v for v in database.lister_villes(conn) if v["nom"].lower() == nom.lower()), None)
        finally:
            conn.close()
        if not ville:
            self.toast("Ville introuvable dans la base locale.", BAD)
            return
        window = ctk.CTkToplevel(self)
        window.title(f"Prévisions météo · {nom}")
        window.geometry("900x760")
        window.minsize(720, 560)
        window.configure(fg_color=BG)
        window.transient(self)
        self.forecast_window = window
        content = ctk.CTkScrollableFrame(window, fg_color=BG, corner_radius=0)
        content.pack(fill="both", expand=True, padx=20, pady=18)
        content.grid_columnconfigure(0, weight=1)
        self.forecast_content = content
        self._forecast_data = None
        self.forecast_status = ctk.CTkLabel(content, text="Chargement des prévisions…",
                                            font=font(15), text_color=SOFT)
        self.forecast_status.grid(row=0, column=0, sticky="w", pady=12)
        actions = ctk.CTkFrame(content, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=8)
        ctk.CTkButton(actions, text="Exporter le bulletin PDF", fg_color=ACCENT,
                      command=self.export_pdf).pack(side="right")
        def load():
            forecast = weather_features.get_forecast(ville["latitude"], ville["longitude"])
            try:
                air = weather_features.get_air_quality(ville["latitude"], ville["longitude"])
            except weather_features.WeatherServiceError:
                air = None
            return forecast, air
        self._run(load, lambda result, error: self._forecast_loaded(nom, result, error))

    def _forecast_loaded(self, nom, result, error):
        if not hasattr(self, "forecast_window") or not self.forecast_window.winfo_exists():
            return
        if error:
            self.forecast_status.configure(text=f"Échec du chargement : {error}")
            return
        forecast, air = result
        self._forecast_data = (nom, forecast, air)
        content = self.forecast_content
        current = forecast.get("current", {})
        daily = forecast.get("daily", {})
        air_current = air.get("current", {}) if air else {}
        aqi = air_current.get("european_aqi")
        aqi_label, aqi_color = weather_features.air_quality_label(aqi)
        self.forecast_status.configure(text=f"{nom} · Prévisions Open-Meteo sur 7 jours")
        current_text = (f"{current.get('temperature_2m','—')} °C · Ressenti {current.get('apparent_temperature','—')} °C\n"
            f"Humidité {current.get('relative_humidity_2m','—')} % · Vent {current.get('wind_speed_10m','—')} km/h · "
            f"Rafales {current.get('wind_gusts_10m','—')} km/h · Pression {current.get('pressure_msl','—')} hPa")
        ctk.CTkLabel(content, text=current_text, font=font(17, "bold"), text_color=TEXT,
                     justify="left").grid(row=2, column=0, sticky="w", pady=10)
        alerts = []
        if float(current.get("wind_speed_10m") or 0) >= 60: alerts.append("Vent fort actuellement.")
        if float(current.get("temperature_2m") or 99) <= 0: alerts.append("Température sous 0 °C : risque de gel.")
        if aqi is not None and float(aqi) > 80: alerts.append(f"Qualité de l'air dégradée (indice {aqi}).")
        for i, day in enumerate(daily.get("time", [])):
            def dval(key):
                values = daily.get(key, [])
                return values[i] if i < len(values) else None
            if dval("precipitation_probability_max") is not None and dval("precipitation_probability_max") >= 70:
                alerts.append(f"{day} : risque élevé de pluie ({dval('precipitation_probability_max')} %).")
            if dval("wind_speed_10m_max") is not None and dval("wind_speed_10m_max") >= 60:
                alerts.append(f"{day} : vent soutenu ({dval('wind_speed_10m_max')} km/h).")
            if dval("uv_index_max") is not None and dval("uv_index_max") >= 8:
                alerts.append(f"{day} : indice UV élevé ({dval('uv_index_max')}).")
            if dval("temperature_2m_min") is not None and dval("temperature_2m_min") <= -2:
                alerts.append(f"{day} : gel possible ({dval('temperature_2m_min')} °C).")
            if dval("temperature_2m_max") is not None and dval("temperature_2m_max") >= 35:
                alerts.append(f"{day} : forte chaleur ({dval('temperature_2m_max')} °C).")
        ctk.CTkLabel(content, text="ALERTES INDICATIVES\n" + ("\n".join("⚠ " + a for a in alerts[:12]) if alerts else
            "Aucun seuil de vigilance interne détecté."), font=font(13), text_color="#ffd166",
            justify="left", wraplength=820).grid(row=3, column=0, sticky="ew", pady=10)
        air_text = (f"QUALITÉ DE L'AIR · {aqi_label}\nIndice européen : {aqi if aqi is not None else '—'} · "
            f"PM2.5 : {air_current.get('pm2_5','—')} µg/m³ · PM10 : {air_current.get('pm10','—')} µg/m³ · "
            f"NO₂ : {air_current.get('nitrogen_dioxide','—')} µg/m³ · Ozone : {air_current.get('ozone','—')} µg/m³")
        ctk.CTkLabel(content, text=air_text, font=font(13), text_color=aqi_color,
                     justify="left", wraplength=820).grid(row=4, column=0, sticky="ew", pady=10)
        ctk.CTkLabel(content, text="PRÉVISIONS QUOTIDIENNES · 7 JOURS", font=font(15, "bold"),
                     text_color=TEXT).grid(row=5, column=0, sticky="w", pady=(16, 6))
        for i, day in enumerate(daily.get("time", [])):
            def val(key):
                values = daily.get(key, [])
                return values[i] if i < len(values) else "—"
            line = (f"{day} · {weather_features.weather_code_label(val('weather_code'))} · "
                f"{val('temperature_2m_min')} / {val('temperature_2m_max')} °C · "
                f"Pluie {val('precipitation_probability_max')} % ({val('precipitation_sum')} mm) · "
                f"Vent {val('wind_speed_10m_max')} km/h · UV {val('uv_index_max')} · "
                f"Lever {val('sunrise')} · Coucher {val('sunset')}")
            ctk.CTkLabel(content, text=line, font=font(12), text_color=SOFT,
                         anchor="w", wraplength=830).grid(row=6+i, column=0, sticky="ew", pady=5)
        ctk.CTkLabel(content, text="PRÉVISIONS HORAIRES · 24 PROCHAINES HEURES",
                     font=font(15, "bold"), text_color=TEXT).grid(row=13, column=0, sticky="w", pady=(18, 6))
        hourly = forecast.get("hourly", {})
        for i, hour in enumerate(hourly.get("time", [])[:24]):
            def hval(key):
                values = hourly.get(key, [])
                return values[i] if i < len(values) else "—"
            line = (f"{hour.replace('T',' ')} · {hval('temperature_2m')} °C · "
                f"Pluie {hval('precipitation_probability')} % ({hval('precipitation')} mm) · "
                f"Vent {hval('wind_speed_10m')} km/h · UV {hval('uv_index')}")
            ctk.CTkLabel(content, text=line, font=font(11), text_color=SOFT,
                         anchor="w").grid(row=14+i, column=0, sticky="ew", pady=3)
        ctk.CTkLabel(content, text="Les seuils de vigilance sont indicatifs et ne remplacent pas les alertes officielles de Météo-France.",
                     font=font(10), text_color=MUTED, wraplength=820).grid(row=38, column=0, sticky="w", pady=16)

    def export_pdf(self):
        if not self._forecast_data:
            self.toast("Charge d'abord les prévisions.", BAD)
            return
        nom, forecast, air = self._forecast_data
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
            filetypes=[("Document PDF", "*.pdf")], initialfile=f"bulletin_meteo_{nom}.pdf")
        if not path: return
        try:
            reporting.create_pdf_report(nom, forecast, air, path)
        except Exception as exc:
            self.toast(f"Échec de création du PDF : {exc}", BAD)
            return
        self.toast("Bulletin PDF créé ✓", GOOD)

    def _alert_tick(self):
        if self.alerts_enabled and not self.busy:
            self._check_alerts(manual=False)
        self.after(20 * 60 * 1000, self._alert_tick)

    def show_radar(self):
        if self.busy:
            self.toast("Une opération est déjà en cours.", SOFT)
            return
        cities = self._villes()
        if not cities:
            self.toast("Ajoute une ville avant d'ouvrir le radar.", BAD)
            return
        city = next((item for item in cities if item["nom"] == self.current), cities[0])
        window = ctk.CTkToplevel(self)
        window.title(f"Radar des précipitations · {city['nom']}")
        window.geometry("760x720")
        window.minsize(620, 620)
        window.configure(fg_color=BG)
        window.transient(self)
        self.radar_window = window
        window.protocol("WM_DELETE_WINDOW", self._close_radar)
        ctk.CTkLabel(window, text=f"Radar des précipitations · {city['nom']}",
                     font=font(22, "bold"), text_color=TEXT).pack(pady=(18, 4))
        self.radar_status = ctk.CTkLabel(window, text="Chargement des images radar…",
                                         font=font(12), text_color=SOFT)
        self.radar_status.pack(pady=(0, 10))
        self.radar_image_label = ctk.CTkLabel(window, text="Téléchargement…",
            width=512, height=512, fg_color=CARD, corner_radius=12)
        self.radar_image_label.pack(padx=18, pady=8)
        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.pack(fill="x", padx=28, pady=8)
        ctk.CTkButton(controls, text="◀", width=44, command=lambda: self._show_radar_frame(
            max(0, self.radar_index - 1))).pack(side="left", padx=4)
        self.radar_play_btn = ctk.CTkButton(controls, text="▶ Lecture", width=110,
                                             command=self.toggle_radar_playback)
        self.radar_play_btn.pack(side="left", padx=4)
        ctk.CTkButton(controls, text="▶|", width=44, command=lambda: self._show_radar_frame(
            min(len(self._radar_frames) - 1, self.radar_index + 1))).pack(side="left", padx=4)
        self.radar_slider = ctk.CTkSlider(controls, from_=0, to=1, number_of_steps=1,
            command=lambda value: self._show_radar_frame(int(float(value))))
        self.radar_slider.pack(side="left", fill="x", expand=True, padx=12)
        ctk.CTkLabel(window,
            text="Radar RainViewer · Fond © OpenStreetMap contributors",
            font=font(10), text_color=MUTED).pack(pady=(0, 12))
        self.radar_index = 0
        self._run(lambda: radar_service.get_radar_animation(city["latitude"], city["longitude"]),
                  self._radar_loaded)

    def _radar_loaded(self, frames, error):
        if not hasattr(self, "radar_window") or not self.radar_window.winfo_exists():
            return
        if error:
            self.radar_status.configure(text=f"Radar indisponible : {error}")
            self.radar_image_label.configure(text="Aucune image disponible", image=None)
            return
        self._radar_frames = frames
        self.radar_index = len(frames) - 1
        self.radar_slider.configure(to=max(1, len(frames) - 1),
                                    number_of_steps=max(1, len(frames) - 1))
        self.radar_slider.set(self.radar_index)
        self._show_radar_frame(self.radar_index)

    def _show_radar_frame(self, index):
        if not self._radar_frames or not hasattr(self, "radar_window") or not self.radar_window.winfo_exists():
            return
        self.radar_index = max(0, min(int(index), len(self._radar_frames) - 1))
        frame = self._radar_frames[self.radar_index]
        self._radar_image = ctk.CTkImage(light_image=frame["image"], dark_image=frame["image"],
                                         size=(512, 512))
        self.radar_image_label.configure(image=self._radar_image, text="")
        stamp = datetime.fromtimestamp(frame["time"]).strftime("%d/%m/%Y à %H:%M")
        self.radar_status.configure(text=f"Image {self.radar_index + 1}/{len(self._radar_frames)} · {stamp}")
        if abs(float(self.radar_slider.get()) - self.radar_index) > 0.01:
            self.radar_slider.set(self.radar_index)

    def toggle_radar_playback(self):
        self._radar_playing = not self._radar_playing
        self.radar_play_btn.configure(text="Ⅱ Pause" if self._radar_playing else "▶ Lecture")
        if self._radar_playing:
            self._radar_tick()
        elif self._radar_job:
            self.after_cancel(self._radar_job)
            self._radar_job = None

    def _radar_tick(self):
        if not self._radar_playing or not self._radar_frames:
            return
        self._show_radar_frame((self.radar_index + 1) % len(self._radar_frames))
        self._radar_job = self.after(800, self._radar_tick)

    def _close_radar(self):
        self._radar_playing = False
        if self._radar_job:
            self.after_cancel(self._radar_job)
            self._radar_job = None
        if hasattr(self, "radar_window") and self.radar_window.winfo_exists():
            self.radar_window.destroy()

    def show_city_comparison(self):
        if self.busy:
            self.toast("Une opération est déjà en cours.", SOFT)
            return
        cities = self._villes()
        if len(cities) < 2:
            self.toast("Ajoute au moins deux villes pour les comparer.", BAD)
            return
        window = ctk.CTkToplevel(self)
        window.title("Comparateur météorologique")
        window.geometry("1050x680")
        window.minsize(800, 540)
        window.configure(fg_color=BG)
        window.transient(self)
        self.compare_window = window
        header = ctk.CTkFrame(window, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(20, 8))
        ctk.CTkLabel(header, text="Comparateur de villes", font=font(24, "bold"),
                     text_color=TEXT).pack(side="left")
        self.compare_status = ctk.CTkLabel(window, text="Récupération des prévisions…",
                                           font=font(12), text_color=SOFT)
        self.compare_status.pack(anchor="w", padx=24, pady=(0, 8))
        self.compare_content = ctk.CTkScrollableFrame(window, fg_color=BG)
        self.compare_content.pack(fill="both", expand=True, padx=16, pady=12)
        def load():
            results = []
            for city in cities:
                try:
                    results.append((city["nom"], weather_features.get_forecast(
                        city["latitude"], city["longitude"]), None))
                except Exception as exc:
                    results.append((city["nom"], None, str(exc)))
            return results
        self._run(load, self._comparison_loaded)

    def _comparison_loaded(self, results, error):
        if not hasattr(self, "compare_window") or not self.compare_window.winfo_exists():
            return
        if error:
            self.compare_status.configure(text=f"Erreur : {error}")
            return
        for child in self.compare_content.winfo_children():
            child.destroy()
        headers = ["VILLE", "MAINTENANT", "MIN. 7 J", "MAX. 7 J", "PLUIE MAX.", "VENT MAX."]
        for col, title in enumerate(headers):
            ctk.CTkLabel(self.compare_content, text=title, font=font(11, "bold"),
                         text_color=MUTED).grid(row=0, column=col, sticky="ew", padx=8, pady=12)
            self.compare_content.grid_columnconfigure(col, weight=1)
        ok = 0
        for row, (name, forecast, error_text) in enumerate(results, start=1):
            card = ctk.CTkFrame(self.compare_content, fg_color=CARD, corner_radius=12)
            card.grid(row=row, column=0, columnspan=6, sticky="ew", padx=4, pady=5)
            for col in range(6):
                card.grid_columnconfigure(col, weight=1)
            if forecast is None:
                values = [name, "Indisponible", "—", "—", "—", error_text or "—"]
            else:
                current = forecast.get("current", {})
                daily = forecast.get("daily", {})
                mins = daily.get("temperature_2m_min", [])
                maxs = daily.get("temperature_2m_max", [])
                rains = daily.get("precipitation_probability_max", [])
                winds = daily.get("wind_speed_10m_max", [])
                values = [name, f"{current.get('temperature_2m','—')} °C",
                    f"{min(mins):.0f} °C" if mins else "—",
                    f"{max(maxs):.0f} °C" if maxs else "—",
                    f"{max(rains):.0f} %" if rains else "—",
                    f"{max(winds):.0f} km/h" if winds else "—"]
                ok += 1
            for col, value in enumerate(values):
                ctk.CTkLabel(card, text=str(value), font=font(12, "bold" if col == 0 else "normal"),
                             text_color=TEXT if col == 0 else SOFT, anchor="w").grid(
                                 row=0, column=col, sticky="ew", padx=8, pady=14)
        self.compare_status.configure(text=f"{ok}/{len(results)} villes comparées · prévisions sur 7 jours")

    def show_alert_center(self):
        if hasattr(self, "alert_window") and self.alert_window.winfo_exists():
            self.alert_window.lift()
            self._refresh_alert_list()
            return
        window = ctk.CTkToplevel(self)
        window.title("Centre de vigilance")
        window.geometry("820x650")
        window.minsize(680, 480)
        window.configure(fg_color=BG)
        window.transient(self)
        self.alert_window = window
        header = ctk.CTkFrame(window, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(20, 8))
        ctk.CTkLabel(header, text="Centre de vigilance", font=font(24, "bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkButton(header, text="Vérifier maintenant", fg_color=ACCENT,
                      command=self.check_alerts_now).pack(side="right")
        self.alert_status = ctk.CTkLabel(window,
            text="Alertes calculées à partir des prévisions Open-Meteo (non officielles).",
            font=font(12), text_color=MUTED)
        self.alert_status.pack(anchor="w", padx=24, pady=(0, 8))
        self.alert_content = ctk.CTkScrollableFrame(window, fg_color=BG)
        self.alert_content.pack(fill="both", expand=True, padx=16, pady=12)
        self._refresh_alert_list()

    def _refresh_alert_list(self):
        if not hasattr(self, "alert_window") or not self.alert_window.winfo_exists():
            return
        for child in self.alert_content.winfo_children():
            child.destroy()
        alerts = database.recent_alerts(60)
        if not alerts:
            ctk.CTkLabel(self.alert_content, text="Aucune alerte enregistrée.",
                         font=font(14), text_color=SOFT).pack(pady=24)
            return
        colors = {"danger": BAD, "warning": "#ffad66", "watch": "#ffd166"}
        for alert in alerts:
            card = ctk.CTkFrame(self.alert_content, fg_color=CARD, corner_radius=12)
            card.pack(fill="x", padx=4, pady=5)
            ctk.CTkLabel(card, text=f"{alert['ville']} · {alert['title']}",
                         font=font(13, "bold"), text_color=colors.get(alert["severity"], SOFT),
                         anchor="w").pack(fill="x", padx=14, pady=(12, 3))
            ctk.CTkLabel(card, text=f"{alert['message']}\n{alert['created_at']}",
                         font=font(11), text_color=SOFT, anchor="w", justify="left",
                         wraplength=730).pack(fill="x", padx=14, pady=(0, 12))

    def toggle_alerts(self):
        self.alerts_enabled = bool(self.alert_switch.get())
        database.set_setting("windows_alerts", "1" if self.alerts_enabled else "0")
        self.toast("Notifications météo activées." if self.alerts_enabled else
                   "Notifications météo désactivées.", GOOD if self.alerts_enabled else SOFT)
        if self.alerts_enabled:
            self.after(1000, self.check_alerts_now)

    def check_alerts_now(self):
        self._check_alerts(manual=True)

    def _check_alerts(self, manual=False):
        cities = self._villes()
        if not cities:
            if manual:
                self.toast("Aucune ville à surveiller.", BAD)
            return
        if self.busy:
            if manual:
                self.toast("Une opération est déjà en cours. Réessaie dans un instant.", SOFT)
            return
        def work():
            new_alerts = []
            for city in cities:
                try:
                    forecast = weather_features.get_forecast(city["latitude"], city["longitude"])
                    try:
                        air = weather_features.get_air_quality(city["latitude"], city["longitude"])
                    except weather_features.WeatherServiceError:
                        air = None
                    for item in weather_features.build_alerts(forecast, air):
                        key = f"{city['nom']}|{item['code']}|{item['validity']}"
                        created = datetime.now().isoformat(timespec="minutes")
                        if database.register_alert_once(key, city["nom"], item["code"], item["title"],
                                item["message"], item["severity"], created):
                            new_alerts.append((city["nom"], item))
                except weather_features.WeatherServiceError:
                    continue
            return new_alerts
        def done(result, error):
            if error:
                if hasattr(self, "alert_window") and self.alert_window.winfo_exists():
                    self.alert_status.configure(text=f"Vérification impossible : {error}")
                if manual:
                    self.toast(f"Échec de la vérification : {error}", BAD)
                return
            for city_name, item in result:
                self._notify_windows(city_name, item)
            self._refresh_alert_list()
            if hasattr(self, "alert_window") and self.alert_window.winfo_exists():
                self.alert_status.configure(text=f"Vérification terminée · {len(result)} nouvelle(s) alerte(s)")
            if manual:
                self.toast(f"Vérification terminée : {len(result)} nouvelle(s) alerte(s).",
                           GOOD if not result else "#ffd166")
        self._run(work, done)

    def _notify_windows(self, city_name, item):
        try:
            from winotify import Notification
            Notification(app_id="Observatoire Météo",
                title=f"{item['title']} · {city_name}", msg=item["message"]).show()
        except Exception:
            return

    def _auto_tick(self):
        if self.auto.get() and not self.busy:
            self.refresh_all()
        self.after(self.AUTO_MS, self._auto_tick)

    def toast(self, msg: str, color: str = GOOD):
        self.toast_label.configure(text=msg, text_color=color)
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(5000, lambda: self.toast_label.configure(text=""))


if __name__ == "__main__":
    App().mainloop()
