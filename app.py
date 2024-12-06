import streamlit as st
import requests
from bs4 import BeautifulSoup
from transformers import pipeline
from pytrends.request import TrendReq
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import os
import time

# Initialize Streamlit App
st.set_page_config(
    page_title="Trendi Search",
    page_icon="🔍",
    layout='centered',
    initial_sidebar_state='collapsed'
)


# Constants for Google Custom Search engine
API_KEY = st.secrets["API_KEY"]  # Replace with your Google Custom Search JSON API key #get it from here: https://developers.google.com/custom-search/v1/introduction #the line would be like this: API_KEY ='hfra......sbhfasjfhJ'
CSE_ID = st.secrets["CSE_ID"]  # Replace with your Google Custom Search Engine ID (CSE ID) # get it from here: https://programmablesearchengine.google.com/ #the line would be like this: CSE_IDY ='123......sbhfasjfhJ'

# Set environment variables
os.environ["GOOGLLE_JSON_API_KEY"] = API_KEY
os.environ["GOOGLE_CSE_ID"] = CSE_ID

############# PROXY RELATED FUNCTIONS #############
# Function to fetch free proxies from an online source ## to be used on google 'free API requests' if google is giving "too many requests" 429 error
def fetch_free_proxies():
    proxy_sources = [
        "https://www.proxyscan.io/api/proxy?type=https",
        "https://www.proxy-list.download/api/v1/get?type=https",
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
    ]
    proxies = []
    for url in proxy_sources:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                proxy_list = response.text.strip().split('\n')
                for proxy in proxy_list:
                    p = proxy.strip()
                    if p:
                        proxies.append({"http": f"http://{p}", "https": f"http://{p}"})
        except Exception as e:
            st.error(f"Error in fetching some free proxies. They were supposed to be used for ditching the 'exceeding limit error' on Google 'free API' requests.")
    return proxies

import time
import requests

def test_proxy(proxy, speed_threshold=2):
    """
    Test the given proxy by making a simple request to a known endpoint.
    Also measure the response time to ensure the proxy is not too slow.

    Parameters:
    - proxy (dict): A dictionary with "http" and/or "https" keys.
    - speed_threshold (int or float): Maximum acceptable response time in seconds.

    Returns:
    - bool: True if the proxy is working and fast enough, False otherwise.
    """
    test_url = "https://www.google.com"
    start_time = time.time()
    try:
        response = requests.get(test_url, proxies=proxy, timeout=speed_threshold)
        elapsed = time.time() - start_time
        # Proxy is considered reliable if response is OK and response time is below threshold
        return response.status_code == 200 and elapsed <= speed_threshold
    except Exception:
        return False


def get_pytrends_instance_with_retries(keywords, timeframe, is_region=False):
    # Try without proxy first
    pytrends = TrendReq(hl='en-US', tz=360)
    try:
        pytrends.build_payload(keywords, timeframe=timeframe)
        if is_region:
            # Just attempt to fetch region data
            data = pytrends.interest_by_region(resolution='COUNTRY', inc_low_vol=True, inc_geo_code=False)
        else:
            # Attempt to fetch interest over time data
            data = pytrends.interest_over_time()
        return pytrends
    except Exception as e:
        # Check if it's a 429 error and try proxies if so
        if "429" in str(e):
            proxies = fetch_free_proxies()
            for proxy in proxies:
                if test_proxy(proxy):
                    # Try pytrends with this proxy
                    try:
                        pytrends = TrendReq(hl='en-US', tz=360, proxies=proxy)
                        pytrends.build_payload(keywords, timeframe=timeframe)
                        if is_region:
                            data = pytrends.interest_by_region(resolution='COUNTRY', inc_low_vol=True, inc_geo_code=False)
                        else:
                            data = pytrends.interest_over_time()
                        return pytrends
                    except Exception as e2:
                        if "429" in str(e2):
                            continue  # Try next proxy
                        else:
                            # Some other error, just continue
                            continue
            # If no proxy worked
            st.error("⚠️ Too many requests have been made by this streamlit server to Google 'free API' today. I also tried to use some free proxies to ditch Google, but the free proxies didn't work. Please try the app later.")
            st.stop()
        else:
            # Some other error
            raise e


# Initialize summarization pipeline with caching to improve performance
@st.cache_resource
def load_summarizer():
    try:
        with st.spinner("Loading summarization model..."):
            return pipeline("summarization", model="facebook/bart-base")
    except Exception as e:
        st.error(f"Error loading summarization model: {e}")
        return None


# Function Definitions
def google_search(query, api_key, cse_id, num=10, date_restrict=None, search_type=None, domain_filter=None):
    """
    Perform a Google Custom Search with optional date range, content type, and domain filtering.
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "num": num
    }

    if date_restrict:
        params["dateRestrict"] = date_restrict

    if search_type:
        params["searchType"] = search_type

    if domain_filter:
        params["q"] += f" {domain_filter}"

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json()
        return results
    except requests.exceptions.HTTPError as http_err:
        st.error(f"HTTP error occurred: {http_err}")
    except Exception as err:
        st.error(f"An error occurred: {err}")
    return None

def summarize_text(link):
    """
    Fetch the content from the link and generate a summary.
    """
    if summarizer is None:
        return "Summarizer model is not loaded."

    try:
        page_response = requests.get(link, timeout=10)
        if page_response.status_code == 200:
            content_type = page_response.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                return "The linked content is not HTML and cannot be summarized."

            soup = BeautifulSoup(page_response.content, "html.parser")
            paragraphs = soup.find_all('p')
            text_content = " ".join([p.get_text() for p in paragraphs])[:4000]
            if not text_content:
                divs = soup.find_all('div')
                text_content = " ".join([div.get_text() for div in divs])[:4000]
            if text_content:
                summary_result = summarizer(text_content, max_length=130, min_length=30, do_sample=False)
                if summary_result and len(summary_result) > 0:
                    summary = summary_result[0].get('summary_text', "No summary available")
                    return summary
                else:
                    return "No summary available"
            else:
                return "No content to summarize."
        else:
            return "Failed to fetch the content."
    except Exception as e:
        return f"Error during summarization: {e}"

def show_trends(keywords, start_date, end_date):
    """
    Display Google Trends data for given keywords across the specified timeframe.
    """
    if len(keywords) == 0:
        st.warning("Please provide at least one keyword.")
        return

    today = datetime.now().date()
    if end_date > today:
        st.error("End Date cannot be in the future.")
        return

    if start_date > end_date:
        st.error("Start Date must be before End Date.")
        return

    timeframe = f"{start_date.strftime('%Y-%m-%d')} {end_date.strftime('%Y-%m-%d')}"

    try:
        # Attempt to get pytrends instance with retries/proxies if needed
        pytrends = get_pytrends_instance_with_retries(keywords, timeframe)
        data = pytrends.interest_over_time()

        if data.empty:
            st.warning("No trends data available for the given keywords and timeframe.")
            return

        fig = go.Figure()
        for keyword in keywords:
            if keyword in data.columns:
                fig.add_trace(go.Scatter(x=data.index, y=data[keyword], mode='lines', name=keyword))
            else:
                st.warning(f"No data found for keyword: {keyword}")

        fig.update_layout(
            title=f'Google Trends for: {", ".join(keywords)}',
            xaxis_title='Date',
            yaxis_title='Interest over time',
            legend_title='Keywords',
            template='plotly_white'
        )
        st.plotly_chart(fig)
    except Exception as e:
        st.error(f"An error occurred while fetching trends data: {e}")

def show_trending_regions(keyword, start_date, end_date):
    """
    Visualize the regions where the keyword is trending on a geographic map.
    """
    today = datetime.now().date()
    if end_date > today:
        st.error("End Date cannot be in the future.")
        return

    if start_date > end_date:
        st.error("Start Date must be before End Date.")
        return

    timeframe = f"{start_date.strftime('%Y-%m-%d')} {end_date.strftime('%Y-%m-%d')}"

    try:
        # Attempt to get pytrends instance with retries/proxies if needed
        pytrends = get_pytrends_instance_with_retries([keyword], timeframe, is_region=True)
        data = pytrends.interest_by_region(resolution='COUNTRY', inc_low_vol=True, inc_geo_code=False)

        if not data.empty:
            data.reset_index(inplace=True)
            fig = px.choropleth(
                data,
                locations='geoName',
                locationmode='country names',
                color=keyword,
                title=f'Regional Interest for "{keyword}"',
                labels={keyword: 'Interest'},
                template='plotly_white'
            )
            fig.update_layout(
                geo=dict(showframe=False, showcoastlines=False, projection_type='equirectangular')
            )
            st.plotly_chart(fig)
        else:
            st.warning("No regional data available for the given keyword and timeframe.")
    except Exception as e:
        st.error(f"An error occurred while fetching regional trends data: {e}")

# User Guide
with st.expander("📖 User Guide"):
    st.markdown("""
    ### Welcome to the Trendi Search!

    **📈 Google Trends Tab:**
    - **Number of Keywords**: Specify how many keywords you want to analyze.
    - **Keywords**: Enter the keywords you wish to explore.
    - **Timeframe**: Select the start and end dates for the trend analysis.
    - **Show Trends**: Click to generate and view the trend graphs.
    - **Trending Regions**: Click to view a geographic map of where the first keyword is trending.

    **🔍 Google Search & Summarizer Tab:**
    - **Search Query**: Enter the term you want to search on Google.
    - **Filters**:
        - **Date Range**: Select from predefined date ranges to restrict search results.
        - **Content Type**: Choose between 'All' or 'Images'. Summaries are not available for images.
        - **Domain Filter**: Include or exclude specific domains (e.g., site:wikipedia.org or -site:example.com).
    - **Search**: Click to perform the search.
    - **Summarize**: For each result (excluding images), click the "Summarize" button to generate a summary of the content.

    **Note:** Summarization uses a [**facebook/bart-base**](https://huggingface.co/facebook/bart-base) model from Hugging Face and may take a few seconds per request.

    Enjoy exploring trends and search results with ease!
    """)

st.title("📊 Trendi Search")

# Initialize session_state for search results and search_id if not already present
if 'search_results' not in st.session_state:
    st.session_state['search_results'] = None

if 'search_id' not in st.session_state:
    st.session_state['search_id'] = 0

# Tabs
tabs = st.tabs(["📈 Google Trends", "🔍 Google Search & Summarizer"])

### Google Trends Tab ###
with tabs[0]:
    st.header("Google Trends Analysis")

    # Default keywords
    default_keywords = ["LLM", "Machine Learning"]

    # Number of keywords
    num_keywords = st.number_input("Number of Keywords", min_value=1, max_value=10, value=2, step=1, help="Please enter the number of keywords you want to analyze.")

    # Keyword inputs
    keywords = []
    for i in range(num_keywords):
        if i < len(default_keywords):
            keyword = st.text_input(f"Keyword {i+1}", value=default_keywords[i], key=f"trend_keyword_{i}")
        else:
            keyword = st.text_input(f"Keyword {i+1}", key=f"trend_keyword_{i}")
        keywords.append(keyword)

    # Timeframe selection
    st.subheader("Select Timeframe")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.now().date() - timedelta(days=4*365))
    with col2:
        end_date = st.date_input("End Date", value=datetime.now().date())

    if start_date > end_date:
        st.error("Start Date must be before End Date.")
    else:
        if st.button("Show Trends"):
            with st.spinner("Fetching trends data..."):
                # Filter out empty keywords
                valid_keywords = [x for x in keywords if x.strip() != ""]
                if valid_keywords:
                    show_trends(valid_keywords, start_date, end_date)
                else:
                    st.warning("Please enter at least one valid keyword.")

    st.markdown("---")

    # Optional: Show trending regions for the first keyword
    if keywords and keywords[0].strip() != "":
        st.subheader(f"Trending Regions for '{keywords[0]}'")
        if st.button("Show Trending Regions"):
            with st.spinner("Fetching regional trends data..."):
                show_trending_regions(keywords[0], start_date, end_date)

### Google Search & Summarizer Tab ###
with tabs[1]:
    st.header("Google Custom Search")

    summarizer = load_summarizer()

    # Search Query
    query = st.text_input("Search Query", value="Persian Gulf history", help="Enter the term you want to search on Google")

    # Filters
    st.subheader("Filters")

    # Predefined Date Ranges
    date_ranges = {
        "Today": "d1",             # Last day
        "This week": "w1",         # Last week
        "This month": "m1",        # Last month
        "Last three months": "m3", # Last three months
        "This year": "y1",         # Last year
        "Last 5 years": "y5",
        "All time": None            # No restriction
    }

    col1, col2 = st.columns(2)

    with col1:
        selected_date_range = st.selectbox("Date Range", options=list(date_ranges.keys()), index=5)  # Default to "Last 5 years"
    with col2:
        # Content Type
        content_type = st.selectbox("Content Type", options=["All", "Images"])

    # Domain Filter
    domain_filter = st.text_input("Domain Filter", help="'site:wikipedia.org' to be included, '-site:example.com' to be excluded")

    # Search Button
    if st.button("Search"):
        with st.spinner("Performing search..."):
            # Increment search_id
            st.session_state['search_id'] += 1
            current_search_id = st.session_state['search_id']

            # Map selected date range to date_restrict
            date_restrict = date_ranges.get(selected_date_range)

            search_results = google_search(
                query=query,
                api_key=API_KEY,
                cse_id=CSE_ID,
                num=10,
                date_restrict=date_restrict,
                search_type="image" if content_type == "Images" else None,
                domain_filter=domain_filter
            )

            # Store search results in session_state with the current_search_id
            st.session_state['search_results'] = {
                'id': current_search_id,
                'results': search_results
            }

    # Display Search Results
    if st.session_state.get('search_results') and st.session_state['search_results']['results'] and "items" in st.session_state['search_results']['results']:
        search_id = st.session_state['search_results']['id']
        search_results = st.session_state['search_results']['results']
        st.success("Found the results.")

        for idx, item in enumerate(search_results["items"]):
            st.markdown(f"### {item.get('title')}")
            st.markdown(f"[{item.get('link')}]({item.get('link')})")
            if content_type != "Images" and "snippet" in item:
                st.markdown(f"{item.get('snippet')}")

            # Check if content type is not image to show summarize button
            if content_type != "Images":
                summarize_button_key = f"summarize_button_{search_id}_{idx}"
                summary_key = f"summary_{search_id}_{idx}"

                # Initialize the summary key in session_state if not present
                if summary_key not in st.session_state:
                    st.session_state[summary_key] = ""

                # Create a separate button key for summarization
                if st.button("📄 Summarize", key=summarize_button_key):
                    with st.spinner("Generating summary..."):
                        summary = summarize_text(item.get('link'))
                        st.session_state[summary_key] = summary

                # Display the summary if it exists
                if st.session_state[summary_key]:
                    st.markdown("**Summary:**")
                    st.write(st.session_state[summary_key])

            st.markdown("---")
    elif st.session_state.get('search_results') and "items" not in st.session_state['search_results']['results']:
        st.warning("No results found for the given search query.")
