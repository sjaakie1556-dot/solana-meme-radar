import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

st.set_page_config(page_title="Solana Meme Radar", page_icon="🚀", layout="wide")
st.title("🚀 Solana Meme Radar V2")
st.caption("Nieuwe Solana-paren · momentum-indicatie · risicowaarschuwingen · geen automatische trades")

with st.sidebar:
    st.header("Filters")
    max_age = st.slider("Maximale leeftijd (minuten)", 5, 180, 30, 5)
    min_liq = st.number_input("Min. liquiditeit ($)", 0, 10000000, 3000, 1000)
    min_vol = st.number_input("Min. volume 5m ($)", 0, 10000000, 500, 100)
    min_buys = st.number_input("Min. buys 5m", 0, 100000, 5, 1)
    include_all = st.checkbox("Toon ook lage liquiditeit / weinig activiteit", False)

@st.cache_data(ttl=20, show_spinner=False)
def profiles():
    r = requests.get("https://api.dexscreener.com/token-profiles/latest/v1", timeout=15)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []

@st.cache_data(ttl=15, show_spinner=False)
def pairs_for(address):
    r = requests.get(f"https://api.dexscreener.com/token-pairs/v1/solana/{address}", timeout=12)
    if r.status_code != 200:
        return []
    data = r.json()
    return data if isinstance(data, list) else []

def val(x):
    try:
        return float(x or 0)
    except (ValueError, TypeError):
        return 0.0

def age_m(p):
    t = p.get("pairCreatedAt")
    if not t:
        return None
    return max(0, (datetime.now(timezone.utc).timestamp()*1000 - val(t))/60000)

def analyze(p, age):
    tx = (p.get("txns") or {}).get("m5") or {}
    buys, sells = int(val(tx.get("buys"))), int(val(tx.get("sells")))
    vol = val((p.get("volume") or {}).get("m5"))
    liq = val((p.get("liquidity") or {}).get("usd"))
    change = val((p.get("priceChange") or {}).get("m5"))
    # Heuristische score, geen voorspelling.
    score = min(25, (buys+sells)*0.5) + min(20, max(0, buys-sells)*1.5)
    score += min(20, vol/250) + min(15, liq/1000) + max(0, 20-age/3)
    score += 10 if change > 0 else (3 if change == 0 else 0)
    flags = []
    if liq < 3000: flags.append("lage liquiditeit")
    info = p.get("info") or {}
    if not info.get("websites") and not info.get("socials"): flags.append("weinig socials/info")
    return round(min(100, score)), buys, sells, vol, liq, change, (", ".join(flags) if flags else "geen eenvoudige rode vlag gevonden; geen veiligheidsgarantie")

if st.button("🔄 Scan opnieuw", type="primary"):
    st.cache_data.clear()

try:
    with st.spinner("Nieuwe tokenprofielen en paren ophalen…"):
        prof = profiles()
        addresses, seen = [], set()
        for item in prof:
            if str(item.get("chainId", "")).lower() == "solana":
                addr = item.get("tokenAddress")
                if addr and addr not in seen:
                    seen.add(addr); addresses.append(addr)
        rows = []
        bar = st.progress(0) if addresses else None
        for i, addr in enumerate(addresses[:60]):
            for p in pairs_for(addr):
                if str(p.get("chainId", "")).lower() != "solana":
                    continue
                age = age_m(p)
                if age is None or age > max_age:
                    continue
                base = p.get("baseToken") or {}
                score, buys, sells, vol, liq, change, risk = analyze(p, age)
                rows.append({
                    "Naam": base.get("name") or "Onbekend",
                    "Ticker": base.get("symbol") or "?",
                    "Leeftijd (min)": round(age, 1),
                    "Momentum": score,
                    "Liquiditeit ($)": liq,
                    "Volume 5m ($)": vol,
                    "Buys 5m": buys,
                    "Sells 5m": sells,
                    "Prijs 5m (%)": change,
                    "Risico-opmerking": risk,
                    "DEX": p.get("dexId", "—"),
                    "Pair": p.get("pairAddress", ""),
                    "Tokenadres": base.get("address", addr),
                    "Chart": p.get("url", "")
                })
            if bar: bar.progress((i+1)/min(len(addresses),60))
        if bar: bar.empty()

    if not rows:
        st.warning("Geen paren gevonden binnen deze leeftijdsfilter. De DexScreener-profielenfeed is niet compleet voor elke nieuwe lancering. Probeer later opnieuw of verhoog de maximale leeftijd.")
    else:
        df = pd.DataFrame(rows).drop_duplicates(subset=["Pair"])
        if not include_all:
            df = df[(df["Liquiditeit ($)"] >= min_liq) & (df["Volume 5m ($)"] >= min_vol) & (df["Buys 5m"] >= min_buys)]
        df = df.sort_values(["Leeftijd (min)", "Momentum"], ascending=[True, False])
        x, y, z = st.columns(3)
        x.metric("Paren gevonden", len(df))
        y.metric("Scanmoment", datetime.now().strftime("%H:%M:%S"))
        z.metric("Max. leeftijd", f"{max_age} min")
        st.info("Sorteert eerst op jongste paar en daarna op momentum. De score is een simpele heuristiek, geen voorspelling. Risicodata is beperkt; een lage risicoscore bewijst niet dat een coin veilig is.")
        if df.empty:
            st.warning("Geen paren voldoen aan je filters. Verlaag de minimumwaarden of vink 'Toon ook lage liquiditeit / weinig activiteit' aan.")
        for _, r in df.head(40).iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3,1])
                c1.subheader(f"{r['Naam']} (${r['Ticker']})")
                c1.caption(f"{r['Leeftijd (min)']} min · DEX: {r['DEX']} · {r['Risico-opmerking']}")
                c2.metric("Momentum", f"{r['Momentum']}/100")
                a,b,c,d = st.columns(4)
                a.metric("Liquiditeit", f"${r['Liquiditeit ($)']:,.0f}")
                b.metric("Volume 5m", f"${r['Volume 5m ($)']:,.0f}")
                c.metric("Buys / sells", f"{int(r['Buys 5m'])} / {int(r['Sells 5m'])}")
                d.metric("Prijs 5m", f"{r['Prijs 5m (%)']:+.2f}%")
                links = []
                if r["Chart"]: links.append(f"[Chart openen]({r['Chart']})")
                if r["Tokenadres"]: links.append(f"[RugCheck](https://rugcheck.xyz/tokens/{r['Tokenadres']})")
                st.markdown(" · ".join(links))
        with st.expander("Tabel en CSV-export"):
            cols = ["Naam","Ticker","Leeftijd (min)","Momentum","Liquiditeit ($)","Volume 5m ($)","Buys 5m","Sells 5m","Prijs 5m (%)","Risico-opmerking","DEX"]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)
            st.download_button("Download CSV", df[cols].to_csv(index=False).encode("utf-8"), "solana_meme_radar.csv", "text/csv")
except requests.RequestException as e:
    st.error(f"API/netwerkfout: {e}. Tik op Scan opnieuw.")
except Exception as e:
    st.error(f"Fout tijdens scannen: {e}")

st.divider()
st.caption("Databron: DexScreener publieke API. De feed kan vertraagd/onvolledig zijn. Geen financieel advies; meme coins kunnen snel naar nul gaan.")
