import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="eBay Last Sold Researcher", page_icon="📦", layout="wide")
st.title("📦 eBay Last Sold Researcher")
st.markdown("**Real-time recently sold items + suggested list prices** (100% scraping version)")

# ====================== SCRAPE SOLD LISTINGS ======================
@st.cache_data(ttl=600)  # cache for 10 minutes
def scrape_sold_listings(query: str, max_items: int = 40):
    # Build eBay sold/completed search URL
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={query.replace(' ', '+')}&_sacat=0&LH_Sold=1&LH_Complete=1&rt=nc&_ipg=240"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        items = []
        for item in soup.select("li.s-item")[:max_items]:
            try:
                # Title
                title_tag = item.select_one(".s-item__title")
                title = title_tag.get_text(strip=True) if title_tag else "N/A"
                
                # Link
                link_tag = item.select_one(".s-item__link")
                link = link_tag["href"] if link_tag else "#"
                
                # Price
                price_tag = item.select_one(".s-item__price")
                price_str = price_tag.get_text(strip=True).replace("$", "").replace(",", "") if price_tag else "0"
                sold_price = float(price_str) if price_str.replace(".", "").isdigit() else 0.0
                
                # Sold date
                date_tag = item.select_one(".s-item__ended-date, .s-item__title--tag, span.s-item__ended")
                date_sold = date_tag.get_text(strip=True) if date_tag else "Unknown"
                
                # Image
                img_tag = item.select_one("img.s-item__image-img")
                image = img_tag["src"] if img_tag and img_tag.get("src", "").startswith("http") else None
                
                items.append({
                    "title": title,
                    "sold_price": sold_price,
                    "date_sold": date_sold,
                    "link": link,
                    "image": image
                })
            except:
                continue
                
        return pd.DataFrame(items)
        
    except Exception as e:
        st.error(f"Could not reach eBay right now: {e}")
        return pd.DataFrame()

# ====================== UI ======================
query = st.text_input("🔍 Enter product description or keywords", 
                     placeholder="iPhone 13 128GB black", 
                     value="iPhone 13 128GB black")

if st.button("🔎 Search Recently Sold Items", type="primary", use_container_width=True):
    with st.spinner("Scraping latest sold listings from eBay..."):
        sold_df = scrape_sold_listings(query)
        
        if sold_df.empty:
            st.warning("No sold items found. Try a more specific search or wait a minute and try again.")
        else:
            st.success(f"✅ Found {len(sold_df)} recently sold items")
            
            # Display as nice cards
            st.subheader("Recently Sold Items")
            cols = st.columns(4)
            for i, row in sold_df.iterrows():
                with cols[i % 4]:
                    if row["image"]:
                        st.image(row["image"], use_column_width=True)
                    st.caption(row["date_sold"])
                    st.markdown(f"**{row['title'][:55]}...**")
                    st.markdown(f"**${row['sold_price']:.2f}**")
                    if st.button("View details →", key=f"btn_{i}"):
                        st.session_state.selected_item = row
                        st.rerun()

            # Sidebar when an item is clicked
            if "selected_item" in st.session_state:
                row = st.session_state.selected_item
                with st.sidebar:
                    st.header("📌 Selected Item")
                    if row["image"]:
                        st.image(row["image"], use_column_width=True)
                    st.subheader(row["title"])
                    st.markdown(f"**Sold for:** ${row['sold_price']:.2f}")
                    st.caption(f"Date sold: {row['date_sold']}")
                    st.markdown(f"[Open original eBay listing]({row['link']})")
                    
                    # Calculate stats
                    avg_sold = sold_df["sold_price"].mean()
                    median_sold = sold_df["sold_price"].median()
                    suggested_price = round(avg_sold * 1.12, 2)  # 12% buffer for profit/listing
                    
                    st.divider()
                    st.metric("**Suggested List Price**", f"${suggested_price}", delta="Recommended today")
                    st.caption("Calculated as: Average sold price × 1.12")
                    
                    st.metric("Average Sold Price", f"${avg_sold:.2f}")
                    st.metric("Median Sold Price", f"${median_sold:.2f}")
                    
                    st.subheader("Last 15 Sold Comps")
                    comps = sold_df.head(15)[["date_sold", "sold_price", "title"]]
                    st.dataframe(comps, use_container_width=True, hide_index=True)
                    
                    # Export button
                    csv = sold_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Export all sold data to CSV",
                        data=csv,
                        file_name=f"ebay_sold_{query.replace(' ', '_')}.csv",
                        mime="text/csv"
                    )

st.caption("💡 This version works instantly with no API keys. Scraping is cached for 10 minutes so eBay doesn't get overloaded.")
