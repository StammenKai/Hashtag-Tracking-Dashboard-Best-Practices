
import streamlit as st
import pandas as pd
import feedparser
import matplotlib.pyplot as plt
from pytrends.request import TrendReq
from atproto import Client
from wordcloud import WordCloud
from mwviews.api import PageviewsClient  # <--- NEU: Wikipedia
from streamlit_autorefresh import st_autorefresh
import urllib.parse

# --- KONFIGURATION ---
st.set_page_config(page_title="Social Radar 360°", layout="wide", page_icon="📡")
# Aktualisiere alle 5 Minuten (300.000 Millisekunden)
count = st_autorefresh(interval=5 * 60 * 1000, key="dataframerefresh")

# --- SIDEBAR ---
st.sidebar.header("🔐 Bluesky Login")
bsky_user = st.sidebar.text_input("Bluesky Handle")
bsky_pass = st.sidebar.text_input("App Password", type="password")

# --- FUNKTION 1: WIKIPEDIA (NEU!) ---
@st.cache_data(ttl=3600)
def get_wiki_data(keyword):
    p = PageviewsClient(user_agent="Dashboard-User")
    try:
        # Wir versuchen, den Begriff direkt zu finden (Großschreibung beachten!)
        # Leerzeichen durch Unterstriche ersetzen für Wiki-URLs
        wiki_term = keyword.replace(" ", "_").title() 
        
        # Hole Daten der letzten 30 Tage
        data = p.article_views('de.wikipedia', [wiki_term], granularity='daily')
        
        # Das Datenformat ist etwas komplex, wir vereinfachen es:
        # data ist ein Dict: {date: {article: views}} -> wir brauchen ein DataFrame
        df = pd.DataFrame.from_dict(data, orient='index')
        
        # Index in echtes Datumsformat umwandeln
        df.index = pd.to_datetime(df.index)
        return df, wiki_term
        
    except Exception as e:
        return pd.DataFrame(), ""

# --- FUNKTION 2: BLUESKY ---
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

# --- FUNKTION 3: GOOGLE TRENDS ---
@st.cache_data(ttl=3600)
def get_google_trends_data(keyword):
    try:
        pytrends = TrendReq(hl='de-DE', tz=60)
        pytrends.build_payload([keyword], cat=0, timeframe='today 1-m', geo='DE')
        data = pytrends.interest_over_time()
        return data if not data.empty else pd.DataFrame()
    except Exception: return pd.DataFrame()
    
# --- FUNKTION 4: NEWS (Korrigiert) ---
def get_news_feed(keyword):
    # Schritt 1: Suchbegriff "URL-sicher" machen (z.B. Leerzeichen -> %20)
    encoded_keyword = urllib.parse.quote(keyword)
    
    # Schritt 2: URL bauen
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=de&gl=DE&ceid=DE:de"
    
    # Schritt 3: Abrufen
    feed = feedparser.parse(rss_url)
    
    # Schritt 4: Daten verarbeiten
    if not feed.entries:
        return pd.DataFrame()
        
    return pd.DataFrame([{"Titel": e.title, "Link": e.link} for e in feed.entries[:5]])

# --- DASHBOARD LAYOUT ---
st.title("📡 Social Radar 360°")
st.caption("Datenquellen: Google Trends, Google News, Wikipedia & Bluesky")

keyword = st.text_input("Thema eingeben (z.B. Bitcoin, KI, Angela Merkel):", "Bitcoin")

if keyword:
    # 1. GOOGLE TRENDS CHART (Ganz oben)
    st.subheader(f"📈 Such-Interesse: {keyword}")
    df_trends = get_google_trends_data(keyword)
    if not df_trends.empty:
        st.line_chart(df_trends[keyword], color="#4285F4") # Google Blau
    else:
        st.warning("Keine Google-Daten.")

    st.markdown("---")

    # 2. DREI-SPALTEN-LAYOUT (News | Wikipedia | Bluesky)
    col1, col2, col3 = st.columns(3)

    # --- SPALTE 1: NEWS ---
    with col1:
        st.header("📰 News")
        df_news = get_news_feed(keyword)
        if not df_news.empty:
            for _, row in df_news.iterrows():
                st.markdown(f"• [{row['Titel']}]({row['Link']})")
        else:
            st.info("Keine aktuellen News.")

    # --- SPALTE 2: WIKIPEDIA (NEU) ---
    with col2:
        st.header("📖 Wikipedia")
        df_wiki, wiki_term = get_wiki_data(keyword)
        
        if not df_wiki.empty:
            # Zeige die Gesamtzahl der Aufrufe
            total_views = df_wiki[wiki_term].sum()
            st.metric("Aufrufe (letzte 30 Tage)", f"{total_views:,}")
            
            # Zeige den Verlauf als Flächendiagramm
            st.area_chart(df_wiki[wiki_term], color="#000000")
            st.caption(f"Artikel: {wiki_term}")
        else:
            st.warning(f"Artikel '{keyword}' nicht gefunden. Achte auf Großschreibung!")

    # --- SPALTE 3: SOCIAL (BLUESKY) ---
    with col3:
        st.header("🦋 Social")
        if bsky_user and bsky_pass:
            df_social = get_bluesky_posts(keyword, bsky_user, bsky_pass)
            if not df_social.empty:
                # Wordcloud
                text = " ".join(df_social['Inhalt'].tolist())
                wc = WordCloud(width=400, height=200, background_color='white').generate(text)
                fig, ax = plt.subplots(figsize=(4, 2))
                ax.imshow(wc, interpolation='bilinear')
                ax.axis("off")
                st.pyplot(fig)
                
                # Letzte 3 Posts
                for i, row in df_social.head(3).iterrows():
                    st.info(f"**@{row['Autor']}**: {row['Inhalt'][:100]}...")
            else:
                st.info("Keine Posts gefunden.")
        else:
            st.warning("Login erforderlich.")