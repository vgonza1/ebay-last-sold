import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import time
import base64

st.set_page_config(page_title="eBay Last Sold Researcher", page_icon="📦", layout="wide")
st.title("📦 eBay Last Sold Researcher")
st.markdown("**Real-time sold data + suggested list prices** — powered by official eBay API + scraping")

# ====================== CONFIG ======================
EBAY_API_BASE = "https://api.ebay.com/buy/browse/v1/item_summary/search"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"

# Load secrets
@st.cache_data(ttl=3600)
def get_ebay_token():
    if not st.secrets.get("EBAY_CLIENT_ID") or not st.secrets.get("EBAY_CLIENT_SECRET"):
        st.error("Missing eBay API credentials in .streamlit/secrets.toml")
        st.stop()
    
    credentials = f"{st.secrets.EBAY_CLIENT_ID}:{st.secrets.EBAY_CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded}"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope/buy.item.bulk"
    }
    
    resp = requests.post(TOKEN_URL, headers=headers, data=data)
    if resp.status_code != 200:
        st.error(f"Token error: {resp.text}")
        st.stop()
    return resp.json()["access_token"]

# ====================== SCRAPE SOLD LISTINGS ======================
@st.cache_data(ttl=600)  # 10 min cache
def scrape_sold_listings(query: str, max_items: int = 30):
    url = f"https://www.ebay.com/sch/i.html?_nkw={query.replace(' ', '+')}&_sacat=0&LH_Sold=1&LH_Complete=1&rt=nc&_ipg=240"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        items = []
        for item in soup.select("li.s-item")[:max_items]:
            try:
                title_tag = item.select_one(".s-item__title")
                title = title_tag.get_text(strip=True) if title_tag else "N/A"
                
                link_tag = item.select_one(".s-item__link")
                link = link_tag["href"] if link_tag else "#"
                
                price_tag = item.select_one(".s-item__price")
                price_str = price_tag.get_text(strip=True).replace("$", "").replace(",", "") if price_tag else "0"
                try:
                    price = float(price_str)
                except:
                    price = 0.0
                
                # Sold date (common 2025/2026 structure)
                date_tag = item.select_one(".s-item__title--tag, .s-item__ended, span.s-item__ended-date")
                date_str = date_tag.get_text(strip=True) if date_tag else "Unknown"
                
                img_tag = item.select_one("img.s-item__image-img")
                img = img_tag["src"] if img_tag and img_tag.get("src", "").startswith("http") else None
                
                items.append({
                    "title": title,
                    "sold_price": price,
                    "date_sold": date_str,
                    "link": link,
                    "image": img
                })
            except:
                continue
        return pd.DataFrame(items)
    except Exception as e:
        st.warning(f"Scraping issue: {e} — eBay may have changed layout.")
        return pd.DataFrame()

# ====================== ACTIVE LISTINGS FROM API ======================
@st.cache_data(ttl=300)
def get_active_listings(query: str, token: str, limit: int = 50):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
    }
    params = {
        "q": query,
        "limit": str(limit),
        "filter": "buyingOptions:{FIXED_PRICE|AUCTION}",
        "fieldgroups": "MATCHING_ITEMS,EXTENDED"
    }
    try:
        resp = requests.get(EBAY_API_BASE, headers=headers, params=params)
        if resp.status_code != 200:
            return pd.DataFrame()
        data = resp.json()
        items = []
        for item in data.get("itemSummaries", []):
            price = float(item["price"]["value"]) if "price" in item and "value" in item["price"] else 0
            img = item.get("image", {}).get("imageUrl") or item.get("thumbnailImages", [{}])[0].get("imageUrl")
            items.append({
                "title": item.get("title", "N/A"),
                "active_price": price,
                "link": item.get("itemWebUrl", "#"),
                "image": img
            })
        return pd.DataFrame(items)
    except:
        return pd.DataFrame()

# ====================== UI ======================
query = st.text_input("🔍 Enter product description or keywords", placeholder="iPhone 13 128GB black", value="iPhone 13 128GB black")

if st.button("🔎 Search eBay", type="primary"):
    with st.spinner("Fetching sold data + active listings..."):
        token = get_ebay_token()
        
        sold_df = scrape_sold_listings(query, max_items=40)
        active_df = get_active_listings(query, token)
        
        if sold_df.empty:
            st.error("No sold listings found or scraping temporarily blocked. Try a different query.")
        else:
            st.success(f"✅ Found {len(sold_df)} recently sold items")
            
            # Display sold list as nice cards
            st.subheader("Recently Sold Items")
            cols = st.columns(4)
            for i, row in sold_df.iterrows():
                with cols[i % 4]:
                    if row["image"]:
                        st.image(row["image"], use_column_width=True)
                    st.caption(row["date_sold"])
                    st.markdown(f"**{row['title'][:60]}...**")
                    st.markdown(f"**${row['sold_price']:.2f}**")
                    if st.button("View details →", key=f"btn_{i}"):
                        st.session_state.selected = row
                        st.rerun()
            
            # Sidebar details when item clicked
            if "selected" in st.session_state:
                row = st.session_state.selected
                with st.sidebar:
                    st.header("📌 Item Details")
                    if row["image"]:
                        st.image(row["image"], use_column_width=True)
                    st.subheader(row["title"])
                    st.markdown(f"**Sold for:** ${row['sold_price']:.2f}")
                    st.caption(f"Sold: {row['date_sold']}")
                    st.markdown(f"[View original listing]({row['link']})")
                    
                    # Calculate stats from all sold items
                    avg_sold = sold_df["sold_price"].mean()
                    median_sold = sold_df["sold_price"].median()
                    
                    # Suggested price logic
                    if not active_df.empty:
                        avg_active = active_df["active_price"].mean()
                        suggested = max(avg_sold * 1.12, avg_active * 1.05)
                        method = "Average sold × 1.12 (or current active listings)"
                    else:
                        suggested = avg_sold * 1.12
                        method = "Average sold × 1.12"
                    
                    st.divider()
                    st.metric("**Suggested List Price**", f"${suggested:.2f}", delta=None)
                    st.caption(method)
                    
                    st.metric("Average Sold", f"${avg_sold:.2f}")
                    st.metric("Median Sold", f"${median_sold:.2f}")
                    
                    st.subheader("Last 15 Sold Comps")
                    display_df = sold_df.head(15)[["date_sold", "sold_price", "title"]]
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    if st.button("Export all sold data to CSV"):
                        csv = sold_df.to_csv(index=False)
                        st.download_button("Download CSV", csv, f"ebay_sold_{query}.csv", "text/csv")
            
            # Show active listings summary
            if not active_df.empty:
                st.divider()
                st.subheader("Current Active Listings (for pricing context)")
                st.dataframe(active_df[["title", "active_price"]].head(10), use_container_width=True, hide_index=True)

st.caption("💡 Tip: Run locally with `streamlit run ebay_last_sold.py`. Scraping may need occasional selector updates if eBay changes their site.")

# ====================== SETUP INSTRUCTIONS ======================
st.sidebar.header("Setup Instructions")
st.sidebar.markdown("""
1. **Get eBay API keys** (free):
   - Go to [developer.ebay.com](https://developer.ebay.com)
   - Create app → Production keys
2. Create folder `.streamlit` and file `secrets.toml` with:
```toml
EBAY_CLIENT_ID = "your_client_id_here"
EBAY_CLIENT_SECRET = "your_client_secret_here"
