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