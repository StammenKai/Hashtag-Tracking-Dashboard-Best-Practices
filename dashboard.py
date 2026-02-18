import streamlit as st
import pandas as pd
import feedparser
from pytrends.request import TrendReq

# --- KONFIGURATION ---
st.set_page_config(page_title="Trend Radar (Free Data)", layout="wide")

# --- FUNKTION 1: GOOGLE TRENDS (Interesse) ---
@st.cache_data(ttl=3600) # Cache für 1 Stunde, um Google nicht zu nerven
def get_google_trends_data(keyword):
    try:
        pytrends = TrendReq(hl='de-DE', tz=60)
        # Wir bauen den Request
        pytrends.build_payload([keyword], cat=0, timeframe='today 1-m', geo='DE')
        
        # Daten abholen
        data = pytrends.interest_over_time()
        
        if data.empty:
            return pd.DataFrame() # Leeres DF zurückgeben falls Fehler
            
        data = data.reset_index()
        return data
    except Exception as e:
        st.error(f"Fehler bei Google Trends: {e}")
        return pd.DataFrame()

# --- FUNKTION 2: GOOGLE NEWS RSS (Schlagzeilen) ---
def get_news_feed(keyword):
    # Der Trick: Wir nutzen die RSS URL von Google News
    encoded_keyword = keyword.replace("#", "").replace(" ", "%20")
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=de&gl=DE&ceid=DE:de"
    
    feed = feedparser.parse(rss_url)
    
    news_items = []
    for entry in feed.entries[:10]: # Nur die neuesten 10
        news_items.append({
            "Titel": entry.title,
            "Veröffentlicht": entry.published,
            "Link": entry.link
        })
    
    return pd.DataFrame(news_items)

# --- DASHBOARD UI ---
st.title("📡 Trend Radar (Kostenlose Live-Daten)")

keyword = st.text_input("Thema oder Hashtag eingeben:", "Bitcoin")

if keyword:
    col1, col2 = st.columns([2, 1])

    # --- LINKER BEREICH: CHART ---
    with col1:
        st.subheader(f"Suchinteresse in Deutschland: {keyword}")
        st.caption("Datenquelle: Google Trends (Letzte 30 Tage)")
        
        df_trends = get_google_trends_data(keyword)
        
        if not df_trends.empty:
            # Chart zeichnen
            st.line_chart(df_trends.set_index('date')[keyword], color="#FF4B4B")
            
            # Aktueller Score
            current_score = df_trends.iloc[-1][keyword]
            st.metric("Aktueller Interesse-Score (0-100)", str(current_score))
        else:
            st.warning("Keine Trend-Daten gefunden oder Google blockt Anfragen.")

    # --- RECHTER BEREICH: NEWS ---
    with col2:
        st.subheader("Neueste Schlagzeilen")
        st.caption("Datenquelle: Google News RSS")
        
        df_news = get_news_feed(keyword)
        
        if not df_news.empty:
            for index, row in df_news.iterrows():
                # Schöne Darstellung der News als klickbare Links
                st.markdown(f"**[{row['Titel']}]({row['Link']})**")
                st.caption(f"🕒 {row['Veröffentlicht']}")
                st.markdown("---")
        else:
            st.info("Keine Nachrichten gefunden.")