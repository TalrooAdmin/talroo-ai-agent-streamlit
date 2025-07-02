import streamlit as st
import uuid
import html
import requests
import json
import os
from datetime import datetime
from streamlit_extras.streaming_write import write as stream_write
from streamlit_extras.let_it_rain import rain
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Disable verbose logging from HTTP libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

# Import the necessary schemas from local schema.py
from schema import ChatMessage, TextPayload, UIComponentPayload, UserActionPayload

DEFAULT_PROFILE_ID = "adf2b2d4-d59f-4e6e-8382-24062ca88f72"

# Get API URL from Streamlit secrets (for Streamlit Cloud) or environment variables (for local)
try:
    API_GATEWAY_URL = st.secrets.get('API_ENDPOINT', os.getenv('API_ENDPOINT', ''))
    API_KEY = st.secrets.get('API_KEY', os.getenv('API_KEY', ''))
except:
    # Fallback to environment variables if secrets are not available
    API_GATEWAY_URL = os.getenv('API_ENDPOINT', '')
    API_KEY = os.getenv('API_KEY', '') 
# --- API Helper Functions ---
def call_ai_response_api(interact_profile_id: str, user_message: dict) -> dict:
    """Call the API Gateway Lambda function for AI response generation."""
    try:
        # Convert datetime objects to strings to match the working example format
        clean_user_message = user_message.copy()
        if 'timestamp' in clean_user_message and hasattr(clean_user_message['timestamp'], 'isoformat'):
            clean_user_message['timestamp'] = clean_user_message['timestamp'].isoformat()
        
        # Only send the required parameters - the Lambda function loads state from DB
        payload = {
            "interact_profile_id": interact_profile_id,
            "current_user_message": clean_user_message
        }
        
        # Debug: Print what we're sending
        print(f"🔄 API Gateway Input:")
        print(f"   URL: {API_GATEWAY_URL}")
        print(f"   Payload: {json.dumps(payload, indent=2)}")
        
        # Make the API call - POST with JSON body and API Key
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": API_KEY
        }
        
        # Validate API Key
        if not API_KEY:
            st.error("🔑 API_KEY is required! Please check your .env file.")
            return {"ai_responses": [], "updated_state": {}}
        
        response = requests.post(
            API_GATEWAY_URL, 
            data=json.dumps(payload),
            headers=headers,
            timeout=30
        )
        
        # Check for API Key authentication errors
        if response.status_code == 403:
            st.error("🔑 API Key authentication failed! Please check your API_KEY in .env file.")
            return {"ai_responses": [], "updated_state": {}}
        
        response.raise_for_status()
        
        # Debug: Print what we got back
        print(f"📥 API Gateway Response:")
        print(f"   Status Code: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")
        print(f"   Raw Response: {response.text}")
        
        # Parse the response - API Gateway returns the data in 'body' field
        result = response.json()
        if 'body' in result:
            # Parse the body content which contains the actual data
            body_data = json.loads(result['body'])
            return body_data
        else:
            # Fallback for direct response format
            return result
        
    except requests.exceptions.Timeout:
        st.error("⏰ Request timed out. Please try again.")
        return {"ai_responses": [], "updated_state": {}}
    except requests.exceptions.RequestException as e:
        st.error(f"🌐 Network error: {str(e)}")
        return {"ai_responses": [], "updated_state": {}}
    except json.JSONDecodeError as e:
        st.error(f"🔧 Failed to parse API response: {str(e)}")
        return {"ai_responses": [], "updated_state": {}}
    except Exception as e:
        st.error(f"❌ Unexpected error: {str(e)}")
        return {"ai_responses": [], "updated_state": {}}

# --- Application Initialization ---
def initialize_app():
    """Initialize the application with proper error handling."""
    # No initialization needed for frontend - all keys are handled by API Gateway
    pass

def setup_page():
    """Configure the Streamlit page."""
    st.set_page_config(
        page_title="AI Job Agent (Dev)", 
        page_icon="🏭",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    st.title("🏭 AI Recruiting Manager (Dev Ver.)")
    st.markdown("*Start your job search based on real data.*")

def initialize_session_state():
    """Initialize session state variables."""

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.profile_id_submitted = False
        st.session_state.show_confetti = False
        
        # Initialize graph state variables
        st.session_state.interact_profile_id = None
        st.session_state.profile = None
        st.session_state.top_jobs = None
        st.session_state.has_job_list = False
        st.session_state.last_intent = None
        st.session_state.profile_was_updated = False
        st.session_state.last_profile_update = None
        
        # Initialize job selection state
        st.session_state.selected_jobs = []

# --- UI Component Renderers ---
def render_job_cards_css():
    """Inject CSS for beautiful, scrollable job cards."""
    st.markdown("""
    <style>
    .job-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        border: 2px solid #e3f2fd;
        border-radius: 16px;
        padding: 1.5rem;
        margin: 0;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
        height: 320px;
        width: 100%;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    
    .job-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    
    .job-card:hover {
        transform: translateY(-4px) scale(1.01);
        box-shadow: 0 16px 48px rgba(0,0,0,0.15);
        border-color: #667eea;
    }
    
    .job-card:hover::before {
        opacity: 1;
    }
    
    .job-title {
        font-size: 1.2rem;
        font-weight: 700;
        color: #2c3e50;
        margin-bottom: 0.5rem;
        line-height: 1.3;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        flex-shrink: 0;
        min-height: 2.6rem;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    
    .job-company {
        font-size: 1rem;
        color: #5a6c7d;
        margin-bottom: 0.3rem;
        font-weight: 600;
        flex-shrink: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    .job-location {
        color: #7b8794;
        font-size: 0.9rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.3rem;
        flex-shrink: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    .job-card-content {
        flex: 1;
        display: flex;
        flex-direction: column;
    }
    
    .job-card-footer {
        flex-shrink: 0;
        margin-top: auto;
    }
    

    
    /* Interaction columns below job cards - ensure they align with cards above */
    .st-emotion-cache-ocqkz7 {
        gap: 1rem !important;
    }
    
    /* Individual interaction column styling - match card width */
    [data-testid="column"] {
        width: 320px !important;
        max-width: 320px !important;
        min-width: 320px !important;
    }
    
    [data-testid="column"] > div {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 12px;
        border: 1px solid #dee2e6;
        padding: 1rem;
        min-height: 180px;
        max-height: 180px;
        overflow-y: auto;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        width: 100%;
        box-sizing: border-box;
    }
    
    [data-testid="column"] > div:hover {
        border-color: #667eea;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
    }
    
    /* Ensure columns container doesn't have flex-wrap */
    .st-emotion-cache-ocqkz7 {
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
    }
    
    .match-score {
        background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
        color: white;
        padding: 0.4rem 0.8rem;
        border-radius: 25px;
        font-weight: 700;
        font-size: 0.9rem;
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(40, 167, 69, 0.3);
    }
    
    /* Streamlit expander styling for match reasons */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%) !important;
        border-radius: 8px !important;
        border: 1px solid #667eea !important;
    }
    
    .streamlit-expanderContent {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%) !important;
        border-radius: 0 0 8px 8px !important;
        padding: 1rem !important;
    }
    
    .scroll-hint {
        text-align: center;
        color: #6c757d;
        font-size: 0.9rem;
        margin: 1rem 0;
        font-style: italic;
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
        padding: 0.5rem;
        border-radius: 8px;
        border: 1px solid #667eea;
    }
    
    /* Horizontal scrollable job cards container */
    .job-cards-container {
        margin: 1rem 0 2rem 0;
        width: 100%;
        overflow-x: auto;
        overflow-y: hidden;
        padding: 1rem 0;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: thin;
        scrollbar-color: #667eea #e3f2fd;
    }
    
    /* Custom scrollbar for webkit browsers */
    .job-cards-container::-webkit-scrollbar {
        height: 8px;
    }
    
    .job-cards-container::-webkit-scrollbar-track {
        background: #e3f2fd;
        border-radius: 4px;
    }
    
    .job-cards-container::-webkit-scrollbar-thumb {
        background: #667eea;
        border-radius: 4px;
    }
    
    .job-cards-container::-webkit-scrollbar-thumb:hover {
        background: #5a6fd8;
    }
    
    /* Horizontal flex layout for job cards */
    .job-cards-row {
        display: flex;
        flex-direction: row;
        gap: 1rem;
        width: max-content;
        min-width: 100%;
        align-items: stretch;
    }
    
    /* Individual job card in horizontal layout */
    .job-cards-row .job-card-wrapper {
        flex: 0 0 auto;
        width: 320px;
        min-width: 320px;
        max-width: 320px;
    }
    
    .form-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px;
        padding: 2rem;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        border: 2px solid rgba(255, 255, 255, 0.2);
        margin: 1rem 0;
        color: #ffffff;
    }
    
    .form-container h3 {
        color: #ffffff !important;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        margin-bottom: 1rem;
    }
    
    .form-container p {
        color: #f8f9fa !important;
        opacity: 0.95;
    }
    
    /* Enhanced form field styling */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div > select,
    .stNumberInput > div > div > input {
        border-radius: 8px !important;
        border: 2px solid #ced4da !important;
        transition: all 0.3s ease !important;
        background-color: #ffffff !important;
        color: #495057 !important;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stSelectbox > div > div > select:focus,
    .stNumberInput > div > div > input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2) !important;
    }
    
    /* Form labels for better readability */
    .stTextInput > label,
    .stTextArea > label,
    .stSelectbox > label,
    .stNumberInput > label,
    .stRadio > label,
    .stCheckbox > label,
    .stDateInput > label,
    .stFileUploader > label {
        color: #ffffff !important;
        font-weight: 600 !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3) !important;
    }
    
    /* Form radio and checkbox text */
    .stRadio > div > div > div > label,
    .stCheckbox > div > div > div > label {
        color: #ffffff !important;
        font-weight: 500 !important;
    }
    
    /* Form help text */
    .stTextInput > div > small,
    .stTextArea > div > small,
    .stSelectbox > div > small,
    .stNumberInput > div > small,
    .stRadio > div > small,
    .stCheckbox > div > small,
    .stDateInput > div > small,
    .stFileUploader > div > small {
        color: #e9ecef !important;
    }
    
    /* Form validation messages */
    .stAlert > div {
        color: #ffffff !important;
    }
    
    /* Form markdown content */
    .form-container .stMarkdown {
        color: #ffffff !important;
    }
    
    /* Ensure all text in form containers is white */
    .form-container * {
        color: inherit !important;
    }
    
    /* Override any dark text in forms */
    .stForm {
        color: #ffffff !important;
    }
    
    .stForm * {
        color: inherit !important;
    }
    
    /* File uploader styling */
    .stFileUploader > div {
        border: 2px dashed rgba(255, 255, 255, 0.6) !important;
        border-radius: 12px !important;
        background: rgba(255, 255, 255, 0.1) !important;
        padding: 1rem !important;
        color: #ffffff !important;
    }
    
    .stFileUploader > div > div {
        color: #ffffff !important;
    }
    
    .stFileUploader button {
        background: rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
    }
    
    /* Pre-filled field indicator */
    .pre-filled-label {
        color: #28a745 !important;
        font-weight: 600 !important;
    }
    
    /* Required field indicator */
    .required-asterisk {
        color: #dc3545 !important;
        font-weight: bold !important;
    }
    
    .success-container {
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border-radius: 16px;
        padding: 2rem;
        box-shadow: 0 8px 32px rgba(40, 167, 69, 0.1);
        border: 2px solid #28a745;
        margin: 1rem 0;
        color: #155724;
    }
    
    /* Job selection styles */
    .job-card.selected {
        border-color: #28a745 !important;
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important;
        transform: scale(1.02);
    }
    
    .job-card.selected::before {
        background: linear-gradient(90deg, #28a745 0%, #20c997 100%) !important;
        opacity: 1 !important;
    }
    
    .selection-indicator {
        position: absolute;
        top: 1rem;
        right: 1rem;
        background: #28a745;
        color: white;
        border-radius: 50%;
        width: 30px;
        height: 30px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 1.2rem;
        box-shadow: 0 2px 8px rgba(40, 167, 69, 0.4);
    }
    
    .apply-all-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px;
        padding: 2rem;
        margin: 2rem 0;
        text-align: center;
        color: white;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
        border: 2px solid rgba(255, 255, 255, 0.2);
    }
    
    .apply-all-container h3 {
        margin-top: 0;
        font-size: 1.5rem;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
    }
    
    .apply-all-container p {
        margin-bottom: 0;
        font-size: 1.1rem;
        opacity: 0.95;
    }
    
    /* Confetti animation */
    @keyframes confetti-fall {
        0% { transform: translateY(-100vh) rotate(0deg); }
        100% { transform: translateY(100vh) rotate(720deg); }
    }
    
    .confetti-piece {
        position: fixed;
        width: 10px;
        height: 10px;
        background: #667eea;
        animation: confetti-fall 3s linear infinite;
        z-index: 9999;
    }
    
    /* Recommended Actions Styling */
    .recommended-actions-container {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 16px;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 2px solid #e3f2fd;
        box-shadow: 0 4px 16px rgba(0,0,0,0.05);
    }
    
    .recommended-actions-container h3 {
        color: #2c3e50 !important;
        margin-top: 0 !important;
        margin-bottom: 0.5rem !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .recommended-actions-container p {
        color: #6c757d !important;
        margin-bottom: 1rem !important;
        font-style: italic;
    }
    
    /* Enhanced button styling for quick actions */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        border: none !important;
        border-radius: 12px !important;
        color: white !important;
        font-weight: 600 !important;
        padding: 0.75rem 1.25rem !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3) !important;
        min-height: 3rem !important;
        text-align: left !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4) !important;
    }
    
    .stButton > button[kind="secondary"] {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%) !important;
        border: 2px solid #e3f2fd !important;
        border-radius: 12px !important;
        color: #495057 !important;
        font-weight: 500 !important;
        padding: 0.75rem 1.25rem !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        min-height: 3rem !important;
        text-align: left !important;
    }
    
    .stButton > button[kind="secondary"]:hover {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%) !important;
        border-color: #667eea !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2) !important;
    }
    
    /* Ensure button text wraps nicely */
    .stButton > button {
        white-space: normal !important;
        word-wrap: break-word !important;
        text-align: left !important;
    }
    </style>
    """, unsafe_allow_html=True)

def render_scrollable_job_list(jobs, search_criteria, total_matches, message="", unique_key=""):
    """Render job cards with selection checkboxes and a batch apply button."""
    if not jobs:
        # Create more specific message with search details
        query = search_criteria.get('query', 'your search') if search_criteria else 'your search'
        location = search_criteria.get('location', 'your location') if search_criteria else 'your location'
        
        st.warning(f"No jobs found matching **'{query}'** in **{location}**. Try searching with different keywords or a broader location!")
        return
    
    # Display header info
    header_message = message if message else 'Here are the top job matches I found for you:'
    st.markdown(f"### 🎯 {header_message}")
    
    if search_criteria:
        st.info(f"🔍 Found **{total_matches}** jobs matching **'{search_criteria.get('query', 'N/A')}'** in **{search_criteria.get('location', 'N/A')}**")
    else:
        st.info(f"🔍 Found **{total_matches}** job matches")
    
    # Selection controls
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown("**Select jobs to apply to:**")
    with col2:
        if st.button("✅ Select All", key=f"select_all_{unique_key}"):
            st.session_state.selected_jobs = [job.get('id') for job in jobs if job.get('id')]
            st.rerun()
    with col3:
        if st.button("❌ Clear All", key=f"clear_all_{unique_key}"):
            st.session_state.selected_jobs = []
            st.rerun()
    
    # Create hint
    st.markdown('<div class="scroll-hint">⬅️ Scroll horizontally to browse job matches • Check boxes below cards to select multiple positions ➡️</div>', unsafe_allow_html=True)
    
    # Job cards container wrapper for horizontal scrolling
    st.markdown('<div class="job-cards-container">', unsafe_allow_html=True)
    
    # Create horizontal row of job cards
    job_cards_html = '<div class="job-cards-row">'
    
    for job_idx, job in enumerate(jobs):
        job_card_html = render_job_card_html(job, job_idx, unique_key)
        job_cards_html += f'<div class="job-card-wrapper">{job_card_html}</div>'
    
    job_cards_html += '</div>'
    
    # Render all job cards at once for smooth horizontal scrolling
    st.markdown(job_cards_html, unsafe_allow_html=True)
    
    # Close job cards container
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Render interactive elements using columns that align with the cards
    interaction_cols = st.columns(len(jobs))
    
    for job_idx, job in enumerate(jobs):
        with interaction_cols[job_idx]:
            render_job_interactions(job, job_idx, unique_key)
    
    # Apply to selected jobs button
    if st.session_state.selected_jobs:
        selected_count = len(st.session_state.selected_jobs)
        
        st.markdown(f"""
        <div class="apply-all-container">
            <h3>🚀 Ready to Apply!</h3>
            <p>You have selected <strong>{selected_count}</strong> job{('s' if selected_count > 1 else '')} for application.</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(
            f"🎯 Apply to {selected_count} Selected Job{'s' if selected_count > 1 else ''}", 
            key=f"apply_selected_{unique_key}",
            type="primary",
            use_container_width=True
        ):
            # Collect selected job data
            selected_job_data = []
            for job in jobs:
                if job.get('id') in st.session_state.selected_jobs:
                    selected_job_data.append({
                        "jobId": job.get('id'),
                        "jobTitle": job.get('title', 'Unknown Title'),
                        "company": job.get('company', 'Unknown Company')
                    })
            
            send_user_action("CLICKED_JOB_APPLY", {
                "selectedJobs": selected_job_data,
                "jobCount": len(selected_job_data)
            })
    else:
        st.info("💡 Select one or more jobs above to apply to multiple positions at once!")

def render_job_card_html(job, job_idx, unique_key):
    """Generate HTML for a single job card without interactive elements."""
    job_id = job.get('id')
    is_selected = job_id in st.session_state.selected_jobs if job_id else False
    
    # Prepare job data with safe escaping
    job_title = html.escape(str(job.get('title', 'Unknown Title')))
    job_company = html.escape(str(job.get('company', 'Unknown Company')))
    job_location = html.escape(str(job.get('location', 'Location not specified')))
    match_score = job.get('matchScore', 0)
    
    # Remove match reasons display from job card - will be shown below
    
    # Create job card with proper structure for horizontal scrolling
    card_class = "job-card selected" if is_selected else "job-card"
    selection_indicator = '<div class="selection-indicator">✓</div>' if is_selected else ''
    match_score_html = f"<div class='match-score'>🎯 {match_score}% Match</div>" if match_score else ""
    
    # Create the job card HTML with flexbox layout
    job_card_html = f"""<div class="{card_class}">
{selection_indicator}
<div class="job-card-content">
<div class="job-title">🏢 {job_title}</div>
<div class="job-company">{job_company}</div>
<div class="job-location">📍 {job_location}</div>
</div>
<div class="job-card-footer">
{match_score_html}
</div>
</div>"""
    
    return job_card_html

def render_job_interactions(job, job_idx, unique_key):
    """Render interactive checkbox and match reasons for job selection."""
    job_id = job.get('id')
    is_selected = job_id in st.session_state.selected_jobs if job_id else False
    
    if job_id:
        checkbox_key = f"select_{job_id}_{unique_key}_{job_idx}"
        
        # Compact checkbox label
        if st.checkbox(
            "✅ Select for application",
            value=is_selected,
            key=checkbox_key,
            help=f"Select {job.get('title', 'Unknown Title')} for batch application"
        ):
            if job_id not in st.session_state.selected_jobs:
                st.session_state.selected_jobs.append(job_id)
                st.rerun()
        else:
            if job_id in st.session_state.selected_jobs:
                st.session_state.selected_jobs.remove(job_id)
                st.rerun()
        
        # Show match reasons with full text
        match_reasons = job.get('matchReasons', [])
        if match_reasons:
            st.markdown("**🎯 Why this matches:**")
            # Show all reasons with full text
            for reason in match_reasons:
                if reason and str(reason).strip():
                    reason_text = str(reason).strip()
                    st.markdown(f"• {reason_text}")
        else:
            st.markdown("*No match reasons available*")
    else:
        st.warning("⚠️ Job ID missing")

def render_application_form(form_props, form_key=""):
    """Render a beautiful application form."""
    # Handle both single and multiple job applications
    selected_jobs = form_props.get('selectedJobs', [])
    
    if selected_jobs:
        # Multiple job application form
        job_titles = form_props.get('jobTitles', [])
        companies = form_props.get('companies', [])
        
        if len(job_titles) == 2:
            title_text = f"{job_titles[0]} and {job_titles[1]}"
        elif len(job_titles) > 2:
            title_text = f"{len(job_titles)} positions"
        else:
            title_text = job_titles[0] if job_titles else "Multiple Positions"
            
        company_text = ", ".join(list(set(companies))) if len(companies) <= 3 else f"{len(set(companies))} companies"
        
        # Safely escape HTML content
        safe_title_text = html.escape(title_text)
        safe_company_text = html.escape(company_text)
        safe_message = html.escape(form_props.get('message', 'Please complete the application form.'))
        
        st.markdown(f"""
        <div class="form-container">
            <h3>📝 Combined Application for {safe_title_text}</h3>
            <p><strong>Companies:</strong> {safe_company_text}</p>
            <p>{safe_message}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Single job application form (backward compatibility)
        job_title = form_props.get('jobTitle', 'Unknown Position')
        company = form_props.get('company', 'Unknown Company')
        message = form_props.get('message', 'Please complete the application form.')
        
        # Safely escape HTML content
        safe_job_title = html.escape(job_title)
        safe_company = html.escape(company)
        safe_message = html.escape(message)
        
        st.markdown(f"""
        <div class="form-container">
            <h3>📝 Application for {safe_job_title} at {safe_company}</h3>
            <p>{safe_message}</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Create form
    form_fields = form_props.get('formFields', [])
    form_submit_key = f"application_form_{form_props.get('jobId')}_{form_key}"
    
    with st.form(key=form_submit_key):
        form_data = {}
        
        for field in form_fields:
            field_id = field.get('id')
            field_text = field.get('text')
            field_type = field.get('type', 'text')
            field_value = field.get('value')
            field_required = field.get('required', False)
            field_source = field.get('source')
            unique_key = f"{form_key}_{field_id}_{field_type}"
            
            # Add required indicator and pre-filled indicator to label
            label = field_text
            if field_required:
                label += " *"
            if field.get('preFilled') and field_source:
                label += f" ✅ (Pre-filled from {field_source})"
            
            # Add help text if available
            help_text = field.get('helpText')
            
            if field_type == 'yesno':
                form_data[field_id] = st.radio(
                    label,
                    ["Yes", "No"],
                    index=0 if field_value == "yes" else 1 if field_value == "no" else 0,
                    key=unique_key,
                    help=help_text
                )
                
            elif field_type == 'select':
                options = field.get('options', [])
                default_index = 0
                if field_value and field_value in options:
                    default_index = options.index(field_value)
                form_data[field_id] = st.selectbox(
                    label,
                    options,
                    index=default_index,
                    key=unique_key,
                    help=help_text
                )
                
            elif field_type == 'date':
                min_date = None
                if field.get('minDate'):
                    from datetime import datetime
                    min_date = datetime.strptime(field['minDate'], '%Y-%m-%d').date()
                
                form_data[field_id] = st.date_input(
                    label,
                    min_value=min_date,
                    key=unique_key,
                    help=help_text
                )
                
            elif field_type == 'textarea':
                max_chars = field.get('maxLength')
                form_data[field_id] = st.text_area(
                    label,
                    value=field_value or "",
                    placeholder=field.get('placeholder', ''),
                    max_chars=max_chars,
                    key=unique_key,
                    help=help_text
                )
                
            elif field_type == 'email':
                form_data[field_id] = st.text_input(
                    label,
                    value=field_value or "",
                    placeholder=field.get('placeholder', 'your.email@example.com'),
                    key=unique_key,
                    help=help_text or "Please enter a valid email address"
                )
                
            elif field_type == 'tel':
                form_data[field_id] = st.text_input(
                    label,
                    value=field_value or "",
                    placeholder=field.get('placeholder', '(555) 123-4567'),
                    key=unique_key,
                    help=help_text or "Please enter your phone number"
                )
                
            elif field_type == 'number':
                min_val = field.get('min', 0)
                step = field.get('step', 1)
                suffix = field.get('suffix', '')
                
                form_data[field_id] = st.number_input(
                    label + (f" ({suffix})" if suffix else ""),
                    min_value=min_val,
                    step=step,
                    value=field_value if field_value is not None else min_val,
                    key=unique_key,
                    help=help_text
                )
                
            elif field_type == 'file':
                accepted_types = field.get('acceptedTypes', ['pdf', 'doc', 'docx'])
                max_size = field.get('maxSize', '5MB')
                
                # Convert MIME types to file extensions for Streamlit
                type_mapping = {
                    'application/pdf': 'pdf',
                    'application/msword': 'doc', 
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
                    'text/plain': 'txt',
                    'image/jpeg': 'jpg',
                    'image/png': 'png'
                }
                
                streamlit_types = []
                for mime_type in accepted_types:
                    if mime_type in type_mapping:
                        streamlit_types.append(type_mapping[mime_type])
                    else:
                        # Fallback: extract extension from MIME type
                        if '/' in mime_type:
                            streamlit_types.append(mime_type.split('/')[-1])
                
                uploaded_file = st.file_uploader(
                    label,
                    type=streamlit_types,
                    key=unique_key,
                    help=help_text or f"Accepted formats: {', '.join(streamlit_types).upper()}, Max size: {max_size}"
                )
                
                if uploaded_file is not None:
                    # Format file data for backend
                    form_data[field_id] = {
                        "fileName": uploaded_file.name,
                        "fileSize": f"{uploaded_file.size / 1024:.0f}KB",
                        "fileType": uploaded_file.type,
                        "uploadId": f"upload_{field_id}_{st.session_state.session_id}"
                    }
                else:
                    form_data[field_id] = None
                    
            else:  # Default to text input
                max_chars = field.get('maxLength')
                form_data[field_id] = st.text_input(
                    label,
                    value=field_value or "",
                    placeholder=field.get('placeholder', ''),
                    max_chars=max_chars,
                    key=unique_key,
                    help=help_text
                )
        
        # Submit button
        if st.form_submit_button("🎉 Submit Application", type="primary"):
            # Validate required fields
            validation_errors = []
            for field in form_fields:
                field_id = field.get('id')
                field_text = field.get('text')
                field_required = field.get('required', False)
                field_type = field.get('type', 'text')
                
                if field_required:
                    value = form_data.get(field_id)
                    if field_type == 'file':
                        if value is None:
                            validation_errors.append(f"Please upload {field_text}")
                    elif not value or (isinstance(value, str) and not value.strip()):
                        validation_errors.append(f"Please fill in {field_text}")
            
            if validation_errors:
                for error in validation_errors:
                    st.error(f"❌ {error}")
                return
            
            # Trigger confetti
            st.session_state.show_confetti = True
            
            # Clear selected jobs from session state
            st.session_state.selected_jobs = []
            
            # Clean up form data - convert dates to strings and handle different types
            clean_form_data = {}
            for key, value in form_data.items():
                if hasattr(value, 'isoformat'):  # Date object
                    clean_form_data[key] = value.isoformat()
                elif isinstance(value, dict):  # File upload object
                    clean_form_data[key] = value  # Keep file object as-is
                elif value is None:
                    clean_form_data[key] = ""
                else:
                    clean_form_data[key] = str(value)
            
            # Handle both single and multiple job submissions
            if selected_jobs:
                # Multiple job submission
                send_user_action("FORM_SUBMISSION", {
                    "selectedJobs": selected_jobs,
                    "formData": clean_form_data
                })
            else:
                # Single job submission (backward compatibility)
                send_user_action("FORM_SUBMISSION", {
                    "jobId": form_props.get('jobId'),
                    "jobTitle": job_title,
                    "company": company,
                    "formData": clean_form_data
                })

def render_profile_form(form_props, form_key=""):
    """Render a beautiful profile update form."""
    message = form_props.get('message', 'Please update your profile information.')
    safe_message = html.escape(message)
    
    st.markdown(f"""
    <div class="form-container">
        <h3>👤 Update Your Profile</h3>
        <p>{safe_message}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Create form
    form_fields = form_props.get('formFields', [])
    sections = form_props.get('sections', {})
    form_submit_key = f"profile_form_{form_key}"
    
    with st.form(key=form_submit_key):
        form_data = {}
        original_values = {}  # Track original values to detect changes
        
        # Group fields by section
        fields_by_section = {}
        for field in form_fields:
            section = field.get('section', 'general')
            if section not in fields_by_section:
                fields_by_section[section] = []
            fields_by_section[section].append(field)
        
        # Render each section
        for section_key, section_fields in fields_by_section.items():
            section_title = sections.get(section_key, section_key.title())
            st.markdown(f"### {section_title}")
            
            # Create columns for better layout
            if len(section_fields) > 1:
                cols = st.columns(min(len(section_fields), 2))  # Max 2 columns
            else:
                cols = [st]  # Single column
            
            for i, field in enumerate(section_fields):
                col = cols[i % len(cols)] if len(cols) > 1 else st
                
                with col:
                    field_id = field.get('id')
                    field_text = field.get('text')
                    field_type = field.get('type', 'text')
                    field_value = field.get('value')
                    field_required = field.get('required', False)
                    unique_key = f"{form_key}_{field_id}_{field_type}"
                    
                    # Store original value for change detection
                    original_values[field_id] = field_value
                    
                    # Add required indicator to label
                    label = field_text
                    if field_required:
                        label += " *"
                    
                    # Add help text if available
                    help_text = field.get('helpText')
                    placeholder = field.get('placeholder', '')
                    
                    if field_type == 'textarea':
                        max_chars = field.get('maxLength')
                        form_data[field_id] = st.text_area(
                            label,
                            value=field_value or "",
                            placeholder=placeholder,
                            max_chars=max_chars,
                            key=unique_key,
                            help=help_text,
                            height=100
                        )
                        
                    elif field_type == 'email':
                        form_data[field_id] = st.text_input(
                            label,
                            value=field_value or "",
                            placeholder=placeholder,
                            key=unique_key,
                            help=help_text or "Please enter a valid email address"
                        )
                        
                    elif field_type == 'tel':
                        form_data[field_id] = st.text_input(
                            label,
                            value=field_value or "",
                            placeholder=placeholder,
                            key=unique_key,
                            help=help_text or "Please enter your phone number"
                        )
                        
                    elif field_type == 'number':
                        min_val = field.get('min', 0)
                        max_val = field.get('max', 100)
                        step = field.get('step', 1)
                        
                        form_data[field_id] = st.number_input(
                            label,
                            min_value=min_val,
                            max_value=max_val,
                            step=step,
                            value=field_value if field_value is not None else min_val,
                            key=unique_key,
                            help=help_text
                        )
                        
                    else:  # Default to text input
                        max_chars = field.get('maxLength')
                        form_data[field_id] = st.text_input(
                            label,
                            value=field_value or "",
                            placeholder=placeholder,
                            max_chars=max_chars,
                            key=unique_key,
                            help=help_text
                        )
        
        # Submit button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.form_submit_button("💾 Update Profile", type="primary", use_container_width=True):
                # Validate required fields
                validation_errors = []
                for field in form_fields:
                    field_id = field.get('id')
                    field_text = field.get('text')
                    field_required = field.get('required', False)
                    
                    if field_required:
                        value = form_data.get(field_id)
                        if not value or (isinstance(value, str) and not value.strip()):
                            validation_errors.append(f"Please fill in {field_text}")
                
                if validation_errors:
                    for error in validation_errors:
                        st.error(f"❌ {error}")
                    return
                
                # Only include fields that have actually changed
                changed_fields = {}
                for key, new_value in form_data.items():
                    original_value = original_values.get(key)
                    
                    # Normalize values for comparison
                    original_str = str(original_value).strip() if original_value is not None else ""
                    new_str = str(new_value).strip() if new_value is not None else ""
                    
                    # Check if the field has actually changed
                    if original_str != new_str:
                        # Only include non-empty changed values
                        if new_str:  # Field has a new non-empty value
                            changed_fields[key] = new_str
                        elif original_str:  # Field was cleared (had value, now empty)
                            changed_fields[key] = ""  # Explicitly set to empty to clear the field
                
                if not changed_fields:
                    st.info("💡 No changes detected. Please modify the fields you want to update.")
                    return
                
                # Show what's being updated
                st.success(f"✅ Updating {len(changed_fields)} field(s): {', '.join(changed_fields.keys())}")
                
                # Send profile form submission with only changed fields
                send_user_action("PROFILE_FORM_SUBMISSION", {
                    "formData": changed_fields
                })

def render_profile_success(success_props, action_key=""):
    """Render a beautiful profile update success confirmation."""
    message = success_props.get('message', 'Profile updated successfully!')
    safe_message = html.escape(message)
    
    updated_fields = success_props.get('updatedFields', [])
    updated_count = success_props.get('updatedCount', len(updated_fields))
    
    st.markdown(f"""
    <div class="success-container">
        <h2>{safe_message}</h2>
        <h3>Update Details</h3>
        <p><strong>Fields Updated:</strong> {updated_count}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Show updated fields with better formatting
    if updated_fields:
        st.markdown("**Fields Successfully Updated:**")
        for field in updated_fields:
            # Fields are already in display format from backend
            st.markdown(f"✅ {field}")
    
    # Additional actions
    next_actions = success_props.get('nextActions', [])
    if next_actions:
        st.markdown("### 🎯 What would you like to do next?")
        cols = st.columns(len(next_actions))
        
        for i, action in enumerate(next_actions):
            if action.get('enabled', True):
                with cols[i]:
                    button_key = f"{action_key}_action_{action.get('actionType')}"
                    if st.button(action.get('label', 'Action'), key=button_key, use_container_width=True):
                        if action.get('actionType') == 'SEARCH_JOBS':
                            # Trigger a job search by sending a text message
                            process_user_text_input("find me jobs")
                        elif action.get('actionType') == 'UPDATE_PROFILE_AGAIN':
                            # Trigger another profile update
                            process_user_text_input("update my profile")

def render_application_success(success_props, action_key=""):
    """Render a beautiful success confirmation."""
    message = success_props.get('message', 'Application submitted!')
    safe_message = html.escape(message)
    
    # Handle both single and multiple job applications
    selected_jobs = success_props.get('selectedJobs', [])
    
    if selected_jobs:
        # Multiple job applications success
        job_count = success_props.get('jobCount', len(selected_jobs))
        application_ids = success_props.get('applicationIds', [])
        
        st.markdown(f"""
        <div class="success-container">
            <h2>✅ {safe_message}</h2>
            <h3>Application Details</h3>
            <p><strong>Number of Applications:</strong> {job_count}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # List each application
        st.markdown("**Applications Submitted:**")
        for i, job in enumerate(selected_jobs):
            job_title = html.escape(job.get('jobTitle', 'Unknown Position'))
            company = html.escape(job.get('company', 'Unknown Company'))
            app_id = html.escape(str(application_ids[i] if i < len(application_ids) else 'N/A'))
            st.markdown(f"• **{job_title}** at **{company}** (ID: {app_id})")
        
    else:
        # Single job application success (backward compatibility)
        job_title = html.escape(success_props.get('jobTitle', 'Unknown Position'))
        company = html.escape(success_props.get('company', 'Unknown Company'))
        app_id = html.escape(str(success_props.get('applicationId', 'N/A')))
        
        st.markdown(f"""
        <div class="success-container">
            <h2>✅ {safe_message}</h2>
            <h3>Application Details</h3>
            <p><strong>Position:</strong> {job_title}</p>
            <p><strong>Company:</strong> {company}</p>
            <p><strong>Application ID:</strong> {app_id}</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Show next steps
    next_steps = success_props.get('nextSteps', [])
    if next_steps:
        st.markdown("### 📋 What happens next:")
        for i, step in enumerate(next_steps, 1):
            st.write(f"**{i}. {step.get('step')}** ({step.get('expectedTime')})")
            st.write(f"   {step.get('description')}")
    
    # Contact info
    contact_info = success_props.get('contactInfo', {})
    if contact_info:
        st.markdown("### 📞 Contact Information")
        if contact_info.get('email'):
            st.write(f"**Email:** {contact_info['email']}")
        if contact_info.get('phone'):
            st.write(f"**Phone:** {contact_info['phone']}")
    
    # Additional actions
    additional_actions = success_props.get('additionalActions', [])
    if additional_actions:
        st.markdown("### 🎯 What would you like to do next?")
        for action in additional_actions:
            if action.get('enabled', True):
                button_key = f"{action_key}_action_{action.get('actionType')}"
                if st.button(action.get('label', 'Action'), key=button_key):
                    if action.get('actionType') == 'SEARCH_SIMILAR_JOBS':
                        st.info("🔄 Similar job search feature coming soon!")
                    elif action.get('actionType') == 'EDIT_PROFILE':
                        st.info("👤 Profile editing feature coming soon!")

def render_error_display(error_props, error_key=""):
    """Render an error display component."""
    title = error_props.get('title', 'Error')
    message = error_props.get('message', 'An error occurred.')
    error_code = error_props.get('errorCode', 'UNKNOWN_ERROR')
    is_retryable = error_props.get('isRetryable', False)
    retry_action = error_props.get('retryAction', {})
    
    # Safely escape HTML content
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    safe_error_code = html.escape(error_code)
    
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
        border: 2px solid #dc2626;
        border-radius: 16px;
        padding: 2rem;
        margin: 1rem 0;
        color: #7f1d1d;
    ">
        <h3 style="color: #dc2626 !important; margin-top: 0; font-size: 1.5rem;">
            ❌ {safe_title}
        </h3>
        <p style="color: #991b1b !important; font-size: 1.1rem; margin-bottom: 1rem;">
            {safe_message}
        </p>
        <p style="color: #7f1d1d !important; font-size: 0.9rem; font-family: monospace;">
            Error Code: {safe_error_code}
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Show retry button if retryable
    if is_retryable and retry_action:
        retry_label = retry_action.get('label', 'Try Again')
        retry_action_type = retry_action.get('actionType', 'RETRY')
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(
                f"🔄 {retry_label}",
                key=f"retry_button_{error_key}_{retry_action_type}",
                type="primary",
                use_container_width=True
            ):
                send_user_action(retry_action_type, {})

def render_ui_component(msg, message_index):
    """Render different UI components based on component name."""
    component_name = msg.payload.componentName
    component_props = msg.payload.componentProps
    unique_key = f"{component_name}_{message_index}"
    
    if component_name == 'JobList':
        message = component_props.get('message', 'Here are the top job matches I found for you:')
        jobs = component_props.get('jobs', [])
        total_matches = component_props.get('totalMatches', len(jobs))
        search_criteria = component_props.get('searchCriteria', {})
        
        render_scrollable_job_list(jobs, search_criteria, total_matches, message, unique_key)
        
    elif component_name == 'ApplicationForm':
        render_application_form(component_props, unique_key)
        
    elif component_name == 'ApplicationSuccess':
        render_application_success(component_props, unique_key)
        
    elif component_name == 'ProfileForm':
        render_profile_form(component_props, unique_key)
        
    elif component_name == 'ProfileSuccess':
        render_profile_success(component_props, unique_key)
        
    elif component_name == 'ErrorDisplay':
        render_error_display(component_props, unique_key)
        
    else:
        # Fallback for any other components
        st.write(f"Displaying UI Component: **{component_name}**")
        with st.expander("Component Data", expanded=False):
            st.json(component_props)

# --- Helper Functions ---
def get_last_ai_message_id() -> str:
    """Helper function to find the last AI message ID for threading."""
    for msg in reversed(st.session_state.messages):
        if msg.get('sender') == 'ai':
            return msg.get('id')
    return None

def create_user_context(in_response_to: str = None) -> dict:
    """Helper function to create consistent user message context."""
    context = {
        'interact_profile_id': st.session_state.interact_profile_id,
        'sessionId': st.session_state.session_id
    }
    if in_response_to:
        context['in_response_to'] = in_response_to
    return context

def send_user_action(action_type: str, action_data: dict):
    """Send a user action to the backend and process the response."""
    # Create user context with proper threading
    last_ai_message_id = get_last_ai_message_id()
    context = create_user_context(last_ai_message_id)
    
    user_message = ChatMessage(
        sender='user',
        type='user_action',
        payload=UserActionPayload(actionType=action_type, actionData=action_data),
        context=context
    )
    
    # Add user message to chat history
    st.session_state.messages.append(user_message.model_dump())
    
    with st.spinner("🤖 Processing your request..."):
        # Extract past AI responses - AI responses after the previous user message
        past_ai_responses = []
        messages = st.session_state.messages
        
        # Find the previous user message (excluding the one we just added)
        # and collect AI responses after it up to now
        user_message_count = 0
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.get('sender') == 'user':
                user_message_count += 1
                # Skip the first user message (current one), find the previous one
                if user_message_count == 2:
                    # Found the previous user message, collect AI responses after it
                    past_ai_responses = messages[i+1:-1]  # Exclude current user message
                    break
        
        # If this is the first user message, past_ai_responses stays empty []
        
        # Build complete state for the graph
        complete_state = {
            'interact_profile_id': st.session_state.interact_profile_id,
            'profile': st.session_state.profile,
            'top_jobs': st.session_state.top_jobs,
            'has_job_list': st.session_state.has_job_list,
            'last_intent': st.session_state.last_intent,
            'profile_was_updated': st.session_state.profile_was_updated,
            'last_profile_update': st.session_state.last_profile_update,
            'ai_responses': [],  # Initialize empty list for accumulating AI responses
            'current_user_message': user_message.model_dump(),  # Include the current message
            'past_ai_responses': past_ai_responses  # AI responses after previous user message
        }
        
        # Process through API Gateway and get response
        result = call_ai_response_api(complete_state['interact_profile_id'], user_message.model_dump())
        ai_responses = result.get("ai_responses", [])
        updated_state = result.get("updated_state", {})
        
        # Update session state with new values
        for key, value in updated_state.items():
            if hasattr(st.session_state, key):
                setattr(st.session_state, key, value)
        
        # Add AI responses to chat history
        if ai_responses:
            for ai_response in ai_responses:
                if isinstance(ai_response, dict):
                    st.session_state.messages.append(ai_response)
                else:
                    st.session_state.messages.append(ai_response.model_dump())
            st.rerun()

def process_user_text_input(prompt: str):
    """Process user text input and get AI response."""
    # Create user context with proper threading
    last_ai_message_id = get_last_ai_message_id()
    context = create_user_context(last_ai_message_id)
    
    user_message = ChatMessage(
        sender='user',
        type='text',
        payload=TextPayload(content=prompt),
        context=context
    )
    
    # Add user message to chat history
    st.session_state.messages.append(user_message.model_dump())
    
    with st.spinner("🧠 AI is thinking..."):
        # Extract past AI responses - AI responses after the previous user message
        past_ai_responses = []
        messages = st.session_state.messages
        
        # Find the previous user message (excluding the one we just added)
        # and collect AI responses after it up to now
        user_message_count = 0
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.get('sender') == 'user':
                user_message_count += 1
                # Skip the first user message (current one), find the previous one
                if user_message_count == 2:
                    # Found the previous user message, collect AI responses after it
                    past_ai_responses = messages[i+1:-1]  # Exclude current user message
                    break
        
        # If this is the first user message, past_ai_responses stays empty []
        
        # Build complete state for the graph
        complete_state = {
            'interact_profile_id': st.session_state.interact_profile_id,
            'profile': st.session_state.profile,
            'top_jobs': st.session_state.top_jobs,
            'has_job_list': st.session_state.has_job_list,
            'last_intent': st.session_state.last_intent,
            'profile_was_updated': st.session_state.profile_was_updated,
            'last_profile_update': st.session_state.last_profile_update,
            'ai_responses': [],  # Initialize empty list for accumulating AI responses
            'current_user_message': user_message.model_dump(),  # Include the current message
            'past_ai_responses': past_ai_responses  # AI responses after previous user message
        }
        
        # Process through API Gateway and get response
        result = call_ai_response_api(complete_state['interact_profile_id'], user_message.model_dump())
        ai_responses = result.get("ai_responses", [])
        updated_state = result.get("updated_state", {})
        
        # Update session state with new values
        for key, value in updated_state.items():
            if hasattr(st.session_state, key):
                setattr(st.session_state, key, value)
        
        # Add AI responses to chat history
        if ai_responses:
            for ai_response in ai_responses:
                if isinstance(ai_response, dict):
                    st.session_state.messages.append(ai_response)
                else:
                    st.session_state.messages.append(ai_response.model_dump())
            st.rerun()
        else:
            st.error("The AI did not return a valid response. Please try again.")

def display_chat_history():
    """Display the entire conversation history."""
    for i, msg_data in enumerate(st.session_state.messages):
        msg = ChatMessage.model_validate(msg_data)
        with st.chat_message(msg.sender):
            if msg.type == 'text':
                st.write(msg.payload.content)
            elif msg.type == 'ui_component':
                render_ui_component(msg, i)

def render_profile_input_section():
    """Render the profile ID input section."""
    st.markdown("### 🔑 Enter Your Profile ID")
    st.markdown("*Please enter your Interact Profile ID to get started with personalized job recommendations.*")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        profile_id = st.text_input(
            "Profile ID", 
            value=DEFAULT_PROFILE_ID,
            placeholder="Enter your Interact Profile ID...",
            help="This is used to load your profile and find matching jobs."
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)  # Add some spacing
        start_clicked = st.button("🚀 Start Agent", type="primary", use_container_width=True)
    
    if start_clicked:
        if profile_id:
            st.session_state.interact_profile_id = profile_id
            st.session_state.profile_id_submitted = True
            
            # Add welcome message to Streamlit chat history only
            initial_message = ChatMessage(
                sender='ai',
                type='text',
                payload=TextPayload(content="Hello! I am your AI Recruiting Manager. To get started, please tell me what you're looking for, or ask me to check your profile."),
                context={'interact_profile_id': profile_id, 'sessionId': st.session_state.session_id}
            )
            st.session_state.messages.append(initial_message.model_dump())
            st.rerun()
        else:
            st.error("❌ Please enter a Profile ID to continue.")

def render_recommended_actions():
    """Render recommended action buttons based on current state."""
    # Determine which actions to show based on current state
    recommended_actions = []
    
    # Always show profile-related actions
    recommended_actions.append({
        "label": "👤 Show My Profile",
        "message": "show my profile",
        "description": "View your current profile information",
        "type": "info"
    })
    
    recommended_actions.append({
        "label": "✏️ Update My Profile", 
        "message": "update my profile",
        "description": "Modify your profile details",
        "type": "profile"
    })
    
    # Job search actions
    if st.session_state.get('has_job_list', False):
        recommended_actions.append({
            "label": "🔄 Find More Jobs",
            "message": "find me more jobs",
            "description": "Search for additional job opportunities",
            "type": "search"
        })
    else:
        recommended_actions.append({
            "label": "🔍 Find Me Jobs",
            "message": "find me jobs",
            "description": "Search for job opportunities",
            "type": "search"
        })
    
    # Context-aware suggestions
    # if st.session_state.get('profile_was_updated', False):
    #     recommended_actions.append({
    #         "label": "🎯 Search with Updated Profile",
    #         "message": "search for jobs with my updated profile",
    #         "description": "Find jobs using your latest profile information",
    #         "type": "search"
    #     })
    
    if recommended_actions:
        st.markdown("""
        <div class="recommended-actions-container">
            <h3>💡 Quick Actions</h3>
            <p>Click any button below to get started quickly:</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Create a responsive grid layout
        cols_per_row = 2
        for i in range(0, len(recommended_actions), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, action in enumerate(recommended_actions[i:i+cols_per_row]):
                with cols[j]:
                    # Style buttons based on type
                    button_type = "primary" if action["type"] in ["search", "profile"] else "secondary"
                    
                    if st.button(
                        action["label"],
                        key=f"quick_action_{i}_{j}_{action['type']}",
                        help=action["description"],
                        type=button_type,
                        use_container_width=True
                    ):
                        # Process the predefined message
                        process_user_text_input(action["message"])

def render_chat_interface():
    """Render the main chat interface."""
    st.markdown(f"### 👤 Active Profile: `{st.session_state.interact_profile_id}`")
    
    # Display chat history
    display_chat_history()
    
    # Always show recommended actions when expecting user input
    # Add a toggle to show/hide recommendations for experienced users
    user_message_count = len([m for m in st.session_state.messages if m.get('sender') == 'user'])
    show_recommendations = True  # Always show by default
    
    if user_message_count > 3:  # Only show toggle after some interaction
        col1, col2 = st.columns([1, 4])
        with col1:
            show_recommendations = st.checkbox("💡 Show Quick Actions", value=True, key="toggle_recommendations")
    
    if show_recommendations:
        render_recommended_actions()
        st.markdown("---")  # Add a separator
    
    # Handle confetti
    if st.session_state.get('show_confetti', False):
        rain(
            emoji="🎉",
            font_size=54,
            falling_speed=5,
            animation_length="infinite",
        )
        # Reset confetti after showing
        st.session_state.show_confetti = False
    
    # Chat input
    if prompt := st.chat_input("💬 Enter your message..."):
        # Display user message immediately
        with st.chat_message("user"):
            st.write(prompt)
        
        # Process the input
        process_user_text_input(prompt)

# --- Main Application Flow ---
def main():
    """Main application entry point."""
    # Initialize everything
    initialize_app()
    setup_page()
    initialize_session_state()
    
    # Inject CSS
    render_job_cards_css()
    
    # Show profile input or chat interface
    if not st.session_state.profile_id_submitted:
        render_profile_input_section()
    else:
        render_chat_interface()

if __name__ == "__main__":
    main()
