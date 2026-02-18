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
from fpdf import FPDF
import tempfile
from datetime import datetime
from openai import OpenAI  # <--- NEU

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="Social Radar 360°", layout="wide", page_icon="📡")

# Auto-Refresh alle 5 Minuten
count = st_autorefresh(interval=5 * 60 * 1000, key="dataframerefresh")

# --- 2. SIDEBAR & LOGIN ---
st.sidebar.header("🔐 Login Status")

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

# --- UPDATE: PDF REPORT MIT KI-TEXT ---
def create_pdf_report(keyword, df_trends, df_news, df_wiki, total_wiki_views, ai_summary=None):
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=f"Social Media Report: {keyword}", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, txt=f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10)

    # 1. Google Trends
    if not df_trends.empty:
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, txt="1. Google Suchinteresse", ln=True)
        
        plt.figure(figsize=(10, 5))
        plt.plot(df_trends.index, df_trends[keyword], color='blue', linewidth=2)
        plt.title(f"Suchvolumen für '{keyword}'")
        plt.grid(True, linestyle='--', alpha=0.5)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            plt.savefig(tmpfile.name, bbox_inches='tight')
            plt.close()
            pdf.image(tmpfile.name, x=10, w=190)
        pdf.ln(5)

    # 2. Wikipedia
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, txt="2. Wikipedia Analyse", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=f"Gesamte Aufrufe (letzte 30 Tage): {total_wiki_views:,}", ln=True)
    pdf.ln(5)

    # 3. News
    if not df_news.empty:
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, txt="3. Top Schlagzeilen", ln=True)
        pdf.set_font("Arial", size=10)
        for i, row in df_news.iterrows():
            clean_title = row['Titel'].encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 8, txt=f"- {clean_title}")
    
    # 4. KI-Analyse (NEU!)
    if ai_summary:
        pdf.add_page() # Neue Seite für die KI
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, txt="4. KI Management Summary", ln=True)
        pdf.set_font("Arial", size=11)
        
        # Markdown entfernen (Fettgedrucktes etc. mag FPDF nicht so gerne)
        clean_text = ai_summary.replace("## ", "").replace("**", "").replace("__", "")
        
        # Encoding reparieren (Emojis entfernen, Umlaute behalten soweit möglich)
        clean_text = clean_text.encode('latin-1', 'replace').decode('latin-1')
        
        pdf.multi_cell(0, 6, txt=clean_text)

    return pdf.output(dest='S').encode('latin-1')
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Social Media Report: {keyword}", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10)

    if not df_trends.empty:
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt="1. Google Suchinteresse", ln=True)
        plt.figure(figsize=(10, 5))
        plt.plot(df_trends.index, df_trends[keyword], color='blue', linewidth=2)
        plt.title(f"Suchvolumen für '{keyword}'")
        plt.grid(True, linestyle='--', alpha=0.5)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            plt.savefig(tmpfile.name, bbox_inches='tight')
            plt.close()
            pdf.image(tmpfile.name, x=10, w=190)
        pdf.ln(5)

    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="2. Wikipedia Analyse", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Gesamte Aufrufe (letzte 30 Tage): {total_wiki_views:,}", ln=True)
    pdf.ln(5)

    if not df_news.empty:
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt="3. Top Schlagzeilen", ln=True)
        pdf.set_font("Arial", size=10)
        for i, row in df_news.iterrows():
            clean_title = row['Titel'].encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 8, txt=f"- {clean_title}")
            
    return pdf.output(dest='S').encode('latin-1')

# --- NEU: KI ANALYSE FUNKTION ---
def analyze_with_gpt(keyword, df_trends, df_news, df_wiki, df_social):
    # Prompt vorbereiten
    trend_status = f"Letzter Wert: {df_trends.iloc[-1][keyword]}" if not df_trends.empty else "Keine Daten"
    wiki_stats = f"{df_wiki.sum().values[0]} Aufrufe" if not df_wiki.empty else "Keine Daten"
    news_text = "\n".join([f"- {row['Titel']}" for i, row in df_news.iterrows()]) if not df_news.empty else "Keine News"
    social_text = "\n".join([f"- {row['Inhalt']}" for i, row in df_social.head(10).iterrows()]) if not df_social.empty else "Keine Posts"

    system_prompt = "Du bist ein Senior Market Analyst. Analysiere kurz und prägnant auf Deutsch."
    user_prompt = f"""
    Thema: {keyword}
    Datenlage:
    - Google Trends: {trend_status}
    - Wikipedia: {wiki_stats}
    - News Headlines: {news_text}
    - Social Media (Bluesky): {social_text}
    
    Erstelle eine Zusammenfassung:
    1. Gesamtlage (Hype/Krise?)
    2. Stimmungslage
    3. Risikobewertung
    4. Konkrete Handlungsempfehlung für Marketing
    """
    
    # Prüfen ob Key da ist
    if "openai_api_key" not in st.secrets:
        return "⚠️ Fehler: Kein OpenAI API Key in den Secrets gefunden!"

    try:
        client = OpenAI(api_key=st.secrets["openai_api_key"])
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"KI-Fehler: {e}"

# --- 4. HAUPT-DASHBOARD UI ---
st.title("📡 Social Radar 360° AI Edition")
st.caption("Live-Monitoring & KI-Analyse")

keyword = st.text_input("Thema eingeben (z.B. Bitcoin, KI, Angela Merkel):", "Bitcoin")

if keyword:
    # Daten laden (für KI und Charts)
    df_trends = get_google_trends_data(keyword)
    df_news = get_news_feed(keyword)
    df_wiki, wiki_term = get_wiki_data(keyword)
    
    df_social = pd.DataFrame()
    if bsky_user and bsky_pass:
        df_social = get_bluesky_posts(keyword, bsky_user, bsky_pass)

    # --- KI SECTION ---
    st.markdown("### 🤖 KI-Marktanalyse")
    with st.expander("✨ Klicke hier für die KI-Einschätzung", expanded=False):
        if st.button("Analyse generieren"):
            with st.spinner("KI analysiert Datenquellen..."):
                # Analyse durchführen
                analysis_text = analyze_with_gpt(keyword, df_trends, df_news, df_wiki, df_social)
                
                # WICHTIG: Im Session State speichern für später!
                st.session_state['ai_result'] = analysis_text
                
                # Anzeigen
                st.markdown(analysis_text)
        
        # Falls schon eine Analyse da ist (vom vorherigen Klick), zeige sie wieder an
        elif 'ai_result' in st.session_state:
            st.markdown(st.session_state['ai_result'])

    # --- CHARTS SECTION ---
    st.subheader(f"📈 Such-Interesse: {keyword}")
    if not df_trends.empty:
        st.line_chart(df_trends[keyword], color="#4285F4")
    else:
        st.warning("Keine Google-Daten.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.header("📰 News")
        if not df_news.empty:
            for _, row in df_news.iterrows():
                st.markdown(f"• [{row['Titel']}]({row['Link']})")
        else:
            st.info("Keine aktuellen News.")

    with col2:
        st.header("📖 Wikipedia")
        if not df_wiki.empty:
            total_views = df_wiki[wiki_term].sum()
            st.metric("Aufrufe (30 Tage)", f"{total_views:,}")
            st.area_chart(df_wiki[wiki_term], color="#000000")
        else:
            st.warning("Artikel nicht gefunden.")

    with col3:
        st.header("🦋 Social")
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
            st.info("Keine Posts oder nicht eingeloggt.")

    # --- 5. EXPORT BUTTONS ---
    st.sidebar.markdown("---")
    st.sidebar.header("💾 Daten-Export")
    
    if not df_trends.empty:
        st.sidebar.download_button("📈 Trends CSV", df_trends.to_csv().encode('utf-8'), f'trends_{keyword}.csv', 'text/csv')
    
    if not df_wiki.empty:
        st.sidebar.download_button("📖 Wiki CSV", df_wiki.to_csv().encode('utf-8'), f'wiki_{keyword}.csv', 'text/csv')
        
        # Prüfen, ob wir eine KI-Analyse im Speicher haben
        ai_text_for_pdf = st.session_state.get('ai_result', None)
        
        # PDF Button mit KI-Text
        pdf_data = create_pdf_report(keyword, df_trends, df_news, df_wiki, df_wiki[wiki_term].sum(), ai_text_for_pdf)
        
        st.sidebar.download_button("📄 PDF Report", pdf_data, f'Report_{keyword}.pdf', 'application/pdf')

    if not df_social.empty:
        st.sidebar.download_button("🦋 Social CSV", df_social.to_csv(index=False).encode('utf-8'), f'social_{keyword}.csv', 'text/csv')