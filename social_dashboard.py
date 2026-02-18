import streamlit as st
import pandas as pd
import feedparser
import matplotlib.pyplot as plt
import urllib.parse
from pytrends.request import TrendReq
from atproto import Client
from wordcloud import WordCloud
from mwviews.api import PageviewsClient
from streamlit_autorefresh import st_autorefresh
from openai import OpenAI

# --- FUNKTION: KI-ANALYSE ---
def analyze_with_gpt(keyword, df_trends, df_news, df_wiki, df_social):
    # 1. Daten für den Prompt vorbereiten (Text zusammenbauen)
    
    # Trends: Letzter Wert
    trend_status = "Keine Daten"
    if not df_trends.empty:
        last_val = df_trends.iloc[-1][keyword]
        trend_status = f"Suchinteresse aktuell bei {last_val}/100"

    # Wiki: Summe
    wiki_stats = "Keine Daten"
    if not df_wiki.empty:
        wiki_stats = f"{df_wiki.sum().values[0]} Aufrufe in 30 Tagen"

    # News: Die 5 Schlagzeilen
    news_text = "\n".join([f"- {row['Titel']}" for i, row in df_news.iterrows()]) if not df_news.empty else "Keine News"

    # Social: Die 10 neuesten Posts
    social_text = "Keine Posts"
    if not df_social.empty:
        social_text = "\n".join([f"- {row['Inhalt']}" for i, row in df_social.head(10).iterrows()])

    # 2. Der Prompt (Der Befehl an die KI)
    system_prompt = "Du bist ein erfahrener PR- und Markt-Analyst. Analysiere die folgenden Daten kurz und prägnant."
    
    user_prompt = f"""
    Thema: {keyword}
    
    1. Google Trends Daten: {trend_status}
    2. Wikipedia Interesse: {wiki_stats}
    3. Aktuelle Schlagzeilen:
    {news_text}
    4. Social Media Stimmen (Bluesky):
    {social_text}
    
    Bitte erstelle eine Zusammenfassung in folgendem Format:
    ## 🧐 Management Summary
    [Ein Satz zur Gesamtlage: Hype, Krise oder Stabil?]
    
    ## 🔥 Stimmungslage
    [Zusammenfassung der Social Media Meinungen & News-Tonalität]
    
    ## ⚠️ Risikobewertung
    [Gibt es Shitstorm-Gefahr oder kritische News? Wenn ja, welche?]
    
    ## 💡 Handlungsempfehlung
    [Was sollte ein Marketing-Manager jetzt tun?]
    """

    # 3. Anfrage an OpenAI
    try:
        client = OpenAI(api_key=st.secrets["openai_api_key"])
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Schnell & günstig (oder "gpt-4o" für max. Intelligenz)
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"KI-Fehler: {e}. Hast du den OpenAI Key in den Secrets?"

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Social Radar 360°", layout="wide", page_icon="📡")

# Auto-Refresh alle 5 Minuten (300.000 ms)
count = st_autorefresh(interval=5 * 60 * 1000, key="dataframerefresh")

# --- 2. SIDEBAR & LOGIN (SECRETS) ---
st.sidebar.header("🔐 Login Status")

# Prüfen, ob Secrets vorhanden sind
if "bluesky_username" in st.secrets and "bluesky_password" in st.secrets:
    bsky_user = st.secrets["bluesky_username"]
    bsky_pass = st.secrets["bluesky_password"]
    st.sidebar.success("✅ Automatisch eingeloggt")
else:
    st.sidebar.info("Keine Secrets gefunden. Manuell einloggen:")
    bsky_user = st.sidebar.text_input("Bluesky Handle")
    bsky_pass = st.sidebar.text_input("App Password", type="password")

# --- 3. DATEN-FUNKTIONEN ---

@st.cache_data(ttl=3600)
def get_wiki_data(keyword):
    p = PageviewsClient(user_agent="Dashboard-User")
    try:
        wiki_term = keyword.replace(" ", "_").title()
        data = p.article_views('de.wikipedia', [wiki_term], granularity='daily')
        df = pd.DataFrame.from_dict(data, orient='index')
        df.index = pd.to_datetime(df.index)
        return df, wiki_term
    except Exception:
        return pd.DataFrame(), ""

def get_bluesky_posts(query, username, password):
    if not username or not password: return pd.DataFrame()
    try:
        client = Client()
        client.login(username, password)
        response = client.app.bsky.feed.search_posts(params={'q': query, 'limit': 20})
        posts_data = []
        if response.posts:
            for post in response.posts:
                posts_data.append({
                    "Autor": post.author.handle,
                    "Inhalt": post.record.text,
                })
        return pd.DataFrame(posts_data)
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_google_trends_data(keyword):
    try:
        pytrends = TrendReq(hl='de-DE', tz=60)
        pytrends.build_payload([keyword], cat=0, timeframe='today 1-m', geo='DE')
        data = pytrends.interest_over_time()
        return data if not data.empty else pd.DataFrame()
    except Exception: return pd.DataFrame()

def get_news_feed(keyword):
    encoded_keyword = urllib.parse.quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=de&gl=DE&ceid=DE:de"
    feed = feedparser.parse(rss_url)
    if not feed.entries: return pd.DataFrame()
    return pd.DataFrame([{"Titel": e.title, "Link": e.link} for e in feed.entries[:5]])

from fpdf import FPDF
import tempfile
from datetime import datetime

# --- FUNKTION: PDF REPORT ERSTELLEN ---
def create_pdf_report(keyword, df_trends, df_news, df_wiki, total_wiki_views):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # 1. Titel & Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Social Media Report: {keyword}", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10) # Zeilenumbruch

    # 2. Google Trends Chart (Neu zeichnen für PDF)
    if not df_trends.empty:
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt="1. Google Suchinteresse (30 Tage)", ln=True)
        
        # Chart mit Matplotlib erstellen
        plt.figure(figsize=(10, 5))
        plt.plot(df_trends.index, df_trends[keyword], color='blue', linewidth=2)
        plt.title(f"Suchvolumen für '{keyword}'")
        plt.grid(True, linestyle='--', alpha=0.5)
        
        # Temporär speichern
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            plt.savefig(tmpfile.name, bbox_inches='tight')
            plt.close() # Speicher freigeben
            
            # Bild ins PDF einfügen
            pdf.image(tmpfile.name, x=10, w=190)
        pdf.ln(5)

    # 3. Wikipedia Stats
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="2. Wikipedia Analyse", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Gesamte Aufrufe (letzte 30 Tage): {total_wiki_views:,}", ln=True)
    pdf.ln(5)

    # 4. Top News Headlines
    if not df_news.empty:
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt="3. Top Schlagzeilen", ln=True)
        pdf.set_font("Arial", size=10)
        
        for i, row in df_news.iterrows():
            # Titel bereinigen (FPDF mag manche Sonderzeichen nicht)
            clean_title = row['Titel'].encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 8, txt=f"- {clean_title}")
    
    # PDF als Byte-String zurückgeben
    return pdf.output(dest='S').encode('latin-1')

# --- 4. HAUPT-DASHBOARD UI ---
st.title("📡 Social Radar 360°")
st.caption("Live-Monitoring: Google, News, Wikipedia & Bluesky")

# WICHTIG: Das Input-Feld muss HIER stehen, BEVOR wir 'if keyword' nutzen!
keyword = st.text_input("Thema eingeben (z.B. Bitcoin, KI, Angela Merkel):", "Bitcoin")

if keyword:
    # --- GOOGLE TRENDS ---
    st.subheader(f"📈 Such-Interesse: {keyword}")
    df_trends = get_google_trends_data(keyword)
    if not df_trends.empty:
        st.line_chart(df_trends[keyword], color="#4285F4")
    else:
        st.warning("Keine Google-Daten.")

    st.markdown("---")

    if keyword:
    # ... (Dein bisheriger Code für Charts etc.) ...

    # --- KI ANALYSE BUTTON (NEU!) ---
    st.markdown("### 🤖 KI-Marktanalyse")
    
    # Wir nutzen st.expander, damit es aufgeräumt aussieht
    with st.expander("✨ Klicke hier für eine professionelle Einschätzung (Powered by AI)", expanded=False):
        if st.button("Analyse generieren"):
            with st.spinner("Die KI liest gerade die News und Posts..."):
                # Wir übergeben alle gesammelten Daten an die Funktion
                # ACHTUNG: Stelle sicher, dass du diese DFs vorher geladen hast!
                # (Am besten rufst du die KI-Funktion erst auf, nachdem du df_trends, df_news etc. geholt hast)
                
                # Falls die Variablen noch nicht da sind, holen wir sie kurz (Caching hilft hier):
                _trends = get_google_trends_data(keyword)
                _news = get_news_feed(keyword)
                _wiki, _ = get_wiki_data(keyword)
                # Login prüfen für Social
                _social = pd.DataFrame()
                if bsky_user and bsky_pass:
                    _social = get_bluesky_posts(keyword, bsky_user, bsky_pass)
                
                # Analyse starten
                analysis_result = analyze_with_gpt(keyword, _trends, _news, _wiki, _social)
                
                # Ergebnis anzeigen
                st.markdown(analysis_result)
                st.success("Analyse abgeschlossen.")

    # --- 3-SPALTEN LAYOUT ---
    col1, col2, col3 = st.columns(3)

    # SPALTE 1: NEWS
    with col1:
        st.header("📰 News")
        df_news = get_news_feed(keyword)
        if not df_news.empty:
            for _, row in df_news.iterrows():
                st.markdown(f"• [{row['Titel']}]({row['Link']})")
        else:
            st.info("Keine aktuellen News.")

    # SPALTE 2: WIKIPEDIA
    with col2:
        st.header("📖 Wikipedia")
        df_wiki, wiki_term = get_wiki_data(keyword)
        if not df_wiki.empty:
            total_views = df_wiki[wiki_term].sum()
            st.metric("Aufrufe (30 Tage)", f"{total_views:,}")
            st.area_chart(df_wiki[wiki_term], color="#000000")
        else:
            st.warning("Artikel nicht gefunden.")

    # SPALTE 3: SOCIAL
    with col3:
        st.header("🦋 Social")
        if bsky_user and bsky_pass:
            df_social = get_bluesky_posts(keyword, bsky_user, bsky_pass)
            if not df_social.empty:
                text = " ".join(df_social['Inhalt'].tolist())
                wc = WordCloud(width=400, height=200, background_color='white').generate(text)
                fig, ax = plt.subplots(figsize=(4, 2))
                ax.imshow(wc, interpolation='bilinear')
                ax.axis("off")
                st.pyplot(fig)
                for i, row in df_social.head(3).iterrows():
                    st.info(f"**@{row['Autor']}**: {row['Inhalt'][:100]}...")
            else:
                st.info("Keine Posts gefunden.")
        else:
            st.warning("Nicht eingeloggt.")

    # --- 5. EXPORT BUTTONS (SIDEBAR) ---
    st.sidebar.markdown("---")
    st.sidebar.header("💾 Daten-Export")
    
    if 'df_trends' in locals() and not df_trends.empty:
        st.sidebar.download_button("📈 Trends CSV", df_trends.to_csv().encode('utf-8'), f'trends_{keyword}.csv', 'text/csv')
    
    if 'df_wiki' in locals() and not df_wiki.empty:
        st.sidebar.download_button("📖 Wiki CSV", df_wiki.to_csv().encode('utf-8'), f'wiki_{keyword}.csv', 'text/csv')
        
    if 'df_social' in locals() and 'df_social' in locals() and not df_social.empty:
        st.sidebar.download_button("🦋 Social CSV", df_social.to_csv(index=False).encode('utf-8'), f'social_{keyword}.csv', 'text/csv')

        # 4. Export: PDF Report (NEU!)
    if 'df_trends' in locals() and 'df_wiki' in locals():
        st.sidebar.markdown("---")
        
        # Wir berechnen die Wiki-Summe vorher, falls vorhanden
        wiki_sum = df_wiki[wiki_term].sum() if not df_wiki.empty else 0
        
        # Button Logik
        pdf_data = create_pdf_report(keyword, df_trends, df_news, df_wiki, wiki_sum)
        
        st.sidebar.download_button(
            label="📄 PDF Report generieren",
            data=pdf_data,
            file_name=f'Report_{keyword}.pdf',
            mime='application/pdf',
        )