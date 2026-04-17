import re
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import quote
from difflib import SequenceMatcher

st.set_page_config(page_title="eBay Last Sold Researcher", page_icon="📦", layout="wide")
st.title("📦 eBay Last Sold Researcher")
st.markdown("**Real-time recently sold items + suggested list prices** (scraping-only)")

# ====================== SIMILARITY HELPERS ======================
STOPWORDS = {"the", "a", "an", "of", "and", "or", "to", "for", "with",
             "in", "on", "new", "nwt", "rare"}

def _normalize_title(s: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", s.lower())
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) >= 2]
    return " ".join(sorted(tokens))

def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio()

# ====================== SCRAPE ======================
@st.cache_data(ttl=600)
def scrape_sold_listings(query: str, max_items: int = 40):
    clean_query = query.replace("/", " ").strip()
    encoded_query = quote(clean_query)
    search_url = (
        f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}"
        "&_sacat=0&LH_Sold=1&LH_Complete=1&rt=nc&_ipg=240"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/134.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
    }

    diag = {"status": None, "len": 0, "layout": None, "raw": 0, "blocked": False}

    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        diag["status"] = resp.status_code
        diag["len"] = len(resp.text)
        resp.raise_for_status()

        low = resp.text.lower()
        if "pardon our interruption" in low or "are you a robot" in low or "captcha" in low:
            diag["blocked"] = True
            return pd.DataFrame(), search_url, diag

        soup = BeautifulSoup(resp.text, "html.parser")

        raw = soup.select("li.s-card")
        if raw:
            diag["layout"] = "s-card"
        else:
            raw = soup.select("li.s-item")
            diag["layout"] = "s-item"
        diag["raw"] = len(raw)

        items = []
        for it in raw:
            try:
                title_el = (it.select_one(".s-card__title")
                            or it.select_one(".su-styled-text.primary.default")
                            or it.select_one(".s-item__title"))
                title = title_el.get_text(strip=True) if title_el else ""
                if not title or title.lower().startswith("shop on ebay"):
                    continue

                link_el = (it.select_one("a.s-card__link")
                           or it.select_one("a.su-link")
                           or it.select_one(".s-item__link"))
                link = link_el.get("href") if link_el else "#"

                price_el = (it.select_one(".s-card__price")
                            or it.select_one(".su-styled-text.positive.bold")
                            or it.select_one(".s-item__price"))
                price_str = price_el.get_text(strip=True) if price_el else ""
                price_str = price_str.split(" to ")[0].split(" - ")[0]
                price_clean = price_str.replace("$", "").replace(",", "").strip()
                try:
                    sold_price = float(price_clean)
                except ValueError:
                    sold_price = 0.0
                if sold_price <= 0:
                    continue

                date_el = (it.select_one(".s-card__caption")
                           or it.select_one(".s-item__caption--signal.POSITIVE")
                           or it.select_one(".s-item__title--tag")
                           or it.select_one(".s-item__ended-date"))
                date_sold = date_el.get_text(strip=True) if date_el else "Unknown"

                img_el = it.select_one("img")
                image = None
                if img_el:
                    src = img_el.get("src") or img_el.get("data-src") or ""
                    if src.startswith("http"):
                        image = src

                items.append({
                    "title": title,
                    "sold_price": sold_price,
                    "date_sold": date_sold,
                    "link": link,
                    "image": image,
                })
                if len(items) >= max_items:
                    break
            except Exception:
                continue

        return pd.DataFrame(items), search_url, diag

    except Exception as e:
        st.error(f"Could not reach eBay: {e}")
        return pd.DataFrame(), search_url, diag

# ====================== UI ======================
if "sold_df" not in st.session_state:
    st.session_state.sold_df = None
    st.session_state.search_url = None
    st.session_state.diag = None
    st.session_state.last_query = None

query = st.text_input("🔍 Enter product description or keywords",
                      placeholder="arda guler topps chrome /99",
                      value="arda guler topps chrome /99")

if st.button("🔎 Search Recently Sold Items", type="primary", use_container_width=True):
    with st.spinner("Fetching latest sold listings from eBay..."):
        sold_df, search_url, diag = scrape_sold_listings(query)
    st.session_state.sold_df = sold_df
    st.session_state.search_url = search_url
    st.session_state.diag = diag
    st.session_state.last_query = query
    if "selected_item" in st.session_state:
        del st.session_state.selected_item

if st.session_state.sold_df is not None:
    sold_df = st.session_state.sold_df
    search_url = st.session_state.search_url
    diag = st.session_state.diag

    st.caption(f"🔗 Searched: [View on eBay]({search_url})")

    if sold_df.empty:
        st.warning("**No sold listings found.**")
        with st.expander("🔧 Diagnostics"):
            st.json(diag)
        if diag.get("blocked"):
            st.error("eBay served a bot-challenge page. Streamlit Cloud's IP is likely blocked.")
        elif diag.get("raw", 0) == 0:
            st.info("eBay returned HTML but no listing cards. Layout may have changed again.")
        else:
            st.info("Listings found but no parseable prices. Try a broader query.")
    else:
        st.success(f"✅ Found {len(sold_df)} recently sold items")

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

        # Sidebar — comps filtered by similarity to the selected card
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

                st.divider()
                st.subheader("🎯 Comps for this card")

                # Score every result by similarity to the selected title
                scored = sold_df.copy()
                scored["similarity"] = scored["title"].apply(
                    lambda t: title_similarity(row["title"], t)
                )
                scored = scored.sort_values("similarity", ascending=False)

                threshold = st.slider(
                    "Match strictness",
                    min_value=0.30, max_value=0.95, value=0.60, step=0.05,
                    help="Higher = only very similar listings. Lower = looser matching."
                )
                comps = scored[scored["similarity"] >= threshold]

                if comps.empty:
                    st.info(f"No comps at ≥{threshold:.2f} — showing top 10 closest matches.")
                    comps = scored.head(10)

                st.caption(f"Using **{len(comps)} comps** for pricing")

                avg_sold = comps["sold_price"].mean()
                median_sold = comps["sold_price"].median()
                suggested_price = round(avg_sold * 1.12, 2)

                st.metric("**Suggested List Price**", f"${suggested_price}",
                          delta="Recommended today")
                st.caption("Calculated as: Avg of matching comps × 1.12")
                st.metric("Average Sold Price", f"${avg_sold:.2f}")
                st.metric("Median Sold Price", f"${median_sold:.2f}")

                st.subheader("Matching Comps")
                display_df = comps[["date_sold", "sold_price", "similarity", "title"]].head(15).copy()
                display_df["similarity"] = display_df["similarity"].round(2)
                display_df["sold_price"] = display_df["sold_price"].apply(lambda x: f"${x:.2f}")
                st.dataframe(display_df, use_container_width=True, hide_index=True)

                csv = comps.to_csv(index=False)
                safe_name = re.sub(r"[^A-Za-z0-9]+", "_", row["title"])[:40]
                st.download_button("📥 Export matching comps to CSV", csv,
                                   f"ebay_comps_{safe_name}.csv", "text/csv")

        st.caption("💡 Tip: Move the slider up for stricter comps (same parallel/grade), "
                   "down to include broader matches.")
