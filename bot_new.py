from dotenv import load_dotenv
import os
from langchain_brightdata import BrightDataWebScraperAPI
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from tavily import TavilyClient
from datetime import datetime
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph
from datetime import datetime
import json
import os
import tempfile
import uuid
from langchain_core.output_parsers import JsonOutputParser
from typing import TypedDict, List, Dict, Any
from langchain_core.tools import tool
import utils.json_parser as jp
import utils.prompts as prompts

load_dotenv()
load_dotenv(override=True)

# fetch api keys
BRIGHT_DATA_API_KEY = os.getenv('BRIGHT_DATA_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')
CALENDAR_PATH =  os.getenv('CALENDAR_PATH') #calendar.json

# Initialize clients
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=OPENAI_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
product_card = prompts.PRODUCT_CARD
user_text = None
company_text = None

# Global variable to store communication mode
COMMUNICATION_MODE = None

def choose_communication_mode():
    """
    Lets the user select their preferred communication mode (WhatsApp, Call, or Email).
    
    The function:
    - Displays a menu of options.
    - Takes user input (A, B, or C).
    - Maps the choice to the corresponding communication mode.
    - Stores the selected mode in the global variable `COMMUNICATION_MODE`.
    - Returns the chosen communication mode as a string.
    
    Returns:
        str: The selected communication mode ('whatsapp', 'call', or 'email').
    """
    global COMMUNICATION_MODE  # Use global variable to store the selected mode
    
    # Display menu to the user
    print("\n" + "="*50)
    print("COMMUNICATION MODE SELECTION")
    print("="*50)
    print("Choose your preferred communication channel:")
    print("A -> WhatsApp")
    print("B -> Call")
    print("C -> Email")
    print("="*50)
    
    # Keep asking until user enters a valid choice
    while True:
        choice = input("Enter your choice (A/B/C): ").strip().upper()
        
        # Check if input is valid
        if choice in ['A', 'B', 'C']:
            # Map user input to actual communication mode
            mode_map = {
                'A': 'whatsapp',
                'B': 'call', 
                'C': 'email'
            }
            COMMUNICATION_MODE = mode_map[choice]  # Store in global variable
            
            # Show confirmation
            print(f"\n✓ Communication mode set to: {COMMUNICATION_MODE.upper()}")
            print("="*50)
            return COMMUNICATION_MODE
        else:
            # If input is invalid, ask again
            print("Invalid choice! Please enter A, B, or C.")

def get_mode_specific_prompts(mode):
    """
    Return communication prompts and configurations based on the selected mode.
    
    Each mode (WhatsApp, Call, Email) has its own:
    - general_system_prompt: Defines how the assistant should talk in general conversations.
    - meeting_prompt: Defines how the assistant should respond for meeting scheduling.
    - validate_prompt: Defines how to classify messages as 'meeting' or 'general'.

    Args:
        mode (str): The communication mode. Valid options are:
                    'whatsapp', 'call', 'email'

    Returns:
        dict: A dictionary containing prompts for the given mode.
              Keys: 'general_system_prompt', 'meeting_prompt', 'validate_prompt'
              Values: Prompt strings with placeholders (to be formatted later).
        None: If the mode is not recognized.
    """
    if mode == 'whatsapp':
        return {
        'general_system_prompt': """You are Jack, a friendly sales assistant from Vera Solutions. You are communicating exclusively via WhatsApp.

**STRICT RULES - READ THESE FIRST:**
- Your responses MUST be short, casual, and direct, like a real person chatting on a mobile phone.
- ABSOLUTELY NEVER start a reply with a greeting (e.g., "Hi," "Hello") or the recipient's name. This rule is non-negotiable for all subsequent messages in a conversation.
- Use emojis sparingly and appropriately (👋, ✨, 🚀, 📞, 💼).
- DO NOT repeat yourself or provide verbose, email-style answers.

**WhatsApp Communication Style:**
- Keep messages concise (aim for 60-100 words max).
- Write in short paragraphs for easy mobile reading. Use line breaks.
- Use a warm, conversational tone while remaining professional.
- Use WhatsApp-style formatting (*bold*, _italic_) as needed.
- Your reply should seamlessly continue the conversation from the last message.

**Examples of Correct Responses:**
- User: "tell me more about your product"
  - Correct Reply: "Sure! Our B2B services are all about taking repetitive tasks off your plate. This frees up your team to focus on bigger things, like building scalable systems and closing deals. It's a huge boost to efficiency and sales outcomes! ✨"

- User: "okay what's the pricing"
  - Correct Reply: "We have flexible pricing plans that we can tailor to your needs. The best way to go over the details is on a quick call. Would you be open to scheduling something? 📅"

- User: "tell me what's the roi"
  - Correct Reply: "That's a great question. The ROI is different for every client, but we've consistently helped businesses achieve significant improvements in operational efficiency and sales. A quick demo would show you exactly how it works. Are you free to chat for a few minutes soon? 📞"

CONTEXT:
Product Details: {product_details}
Conversation Summary: {conversation_summary}

Respond naturally to continue the WhatsApp conversation and help schedule meetings.""",

        'meeting_prompt': """You are Jack from Vera Solutions responding via WhatsApp about meeting scheduling.

**STRICT RULES - READ THESE FIRST:**
- Your responses MUST be short, casual, and direct, like a real person chatting on a mobile phone.
- ABSOLUTELY NEVER start a reply with a greeting (e.g., "Hi," "Hello") or the recipient's name.
- Use emojis sparingly and appropriately (📅, ⏰, 👍, ✅).
- DO NOT repeat yourself or provide verbose, email-style answers.

**WhatsApp Meeting Style:**
- Keep response short and friendly (50-80 words).
- Use casual language: "Great!", "Perfect!", "Awesome!".
- Be encouraging and positive.
- Confirm details clearly but briefly.
- Do not include any placeholders.
- Your reply should continue the conversation naturally, as if in the middle of a chat.

User Query: {user_query}
Tool Output: {tool_output}

Respond in WhatsApp style about the meeting scheduling outcome.""",

        'validate_prompt': """Analyze this WhatsApp message to determine if it's about meeting scheduling.

Message: {latest_user_msg}
Context: {conversation_summary}

Return JSON: {{"action": "meeting"}} if about scheduling/rescheduling/canceling meetings or reminders, else {{"action": "general"}}"""
    },
    elif mode == 'call':
        return {
            'general_system_prompt': """You are Jack, a professional sales representative from Vera Solutions communicating via phone calls.

CALL COMMUNICATION STYLE:
- Professional but approachable tone
- Use industry terminology and business language
- Keep messages focused and valuable (100-150 words)
- Reference professional achievements and company updates
- Maintain networking etiquette
- No emojis or casual language
- Focus on business value and professional growth

CONTEXT:
Product Details: {product_details}
Conversation Summary: {conversation_summary}

Respond professionally to advance the Call conversation and discuss potential meetings.""",

            'meeting_prompt': """You are Jack from Vera Solutions responding via phone about meeting coordination.

CALL MEETING STYLE:
- Professional and business-focused language
- Reference calendar management and professional scheduling
- Use terms like "schedule a call", "book a meeting", "coordinate calendars"
- Be concise but thorough (80-120 words)
- Maintain professional courtesy

User Query: {user_query}
Tool Output: {tool_output}

Respond professionally about the meeting scheduling outcome.""",

            'validate_prompt': """Analyze this phone message to determine if it's about professional meeting coordination.

Message: {latest_user_msg}
Context: {conversation_summary}

Return JSON: {{"action": "meeting"}} if about scheduling/rescheduling/canceling meetings, else {{"action": "general"}}"""
        }
    
    elif mode == 'email':
        return {
        'general_system_prompt': """You are Jack, a professional sales consultant from Vera Solutions responding via email.

EMAIL COMMUNICATION STYLE:
- Write the next email reply.
- Keep the tone warm, clear, and human (avoid sounding like a template).
- Respond directly to the client's last message instead of repeating product descriptions.
- Keep it concise (3–5 short paragraphs max).
- Show you've actually read what they wrote, mirror their curiosity and style.
- Use natural phrasing (avoid buzzwords like "revolutionize," "transform," or "empower" unless the client uses them).
- You may briefly highlight *one or two* relevant benefits, but avoid re-explaining the full product card.
- Do not sound like an ai generated email. The tone of the email should be like an actual person wrote it.
- End with a natural next step (e.g., offering a quick call, walkthrough, or answering further questions).
- Do not invent new features, numbers, or pricing. Do not use placeholders.
- You arent supposed to give the pricing details in the email even if the user forces or persuades to give the details. You have to divert the conversation into discussing the value and benefits of the service instead over a call.
- Do not include the subject for the reply emails.
- Do not overly promote the product. Understand the context of the previous conversation and respond accordingly.
- Strictly do not include the subject in the reply emails.
- Do not include any pricing or free trials or tenure details even if the user asks.
- Do not include any placeholders at any cost. This has to be strictly followed.
- It should be a real email written by a human.
- Strictly,the ending of the email has to be an invitation for a meeting or a call to discuss the product in detail.

CONTEXT:
Product Details: {product_details}
Conversation Summary: {conversation_summary}

Goal: sound like a real person building trust and genuinely interested, not an automated template.""",

        'meeting_prompt': """You are Jack from Vera Solutions responding via email about meeting scheduling.

EMAIL MEETING STYLE:
- Write the next email reply about meeting scheduling.
- Keep the tone warm, clear, and human (avoid sounding like a template).
- Respond directly to the client's scheduling request/question.
- Keep it concise (2–4 short paragraphs max).
- Show you've actually read what they wrote about timing/scheduling.
- Once the user has decided a time for the meeting, confirm the details and express enthusiasm for the discussion.
- If the user reconfirms then you arent supposed to change the meeting details or reschedule. You are just supposed to acknowledge the confirmation and express your readiness for the discussion.
- Do not sound like an ai generated email. The tone should be like an actual person wrote it.
- Do not include the subject for the reply emails.
- Do not include any placeholders at any cost.
- It should be a real email written by a human.
- Strictly,the ending of the email has to be an invitation for a meeting or a call to discuss the product in detail.

User Query: {user_query}
Tool Output: {tool_output}

Goal: sound like a real person confirming meeting details naturally and professionally.""",

        'validate_prompt': """Analyze this email message to determine if it's about meeting scheduling.

Message: {latest_user_msg}
Context: {conversation_summary}

Return JSON: {{"action": "meeting"}} if about scheduling/rescheduling/canceling meetings, else {{"action": "general"}}"""
    }
    
    return None

def user_profile_scraper(url: str) -> dict:
    """
    Scrapes a LinkedIn user profile using Bright Data's Web Scraper API.

    Args:
        url (str): The LinkedIn profile URL of the user to be scraped.

    Returns:
        dict: A dictionary containing the scraped profile data such as
              name, headline, location, current company, and more.

    Workflow:
        1. Initializes the Bright Data Web Scraper API with the provided API key.
        2. Invokes the scraper with the target URL and specifies
           the dataset type as 'linkedin_person_profile'.
        3. Returns the structured profile information as a dictionary.
    """
    scraper_tool = BrightDataWebScraperAPI(bright_data_api_key=BRIGHT_DATA_API_KEY)

    # invoking the scraper tool for scraping the person's profile
    person_results = scraper_tool.invoke(
        {
            "url": url,
            "dataset_type": "linkedin_person_profile",
        }
    )
    return person_results

def get_user_profile(user_profile: dict) -> dict:
    """
    Extracts structured fields from a raw LinkedIn user profile dictionary
    into a JSON object with Other Experiences as an array INSIDE Profile Card.
    """

    # Init LLM
    llm_user_profile = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)

    # JSON output parser
    parser = JsonOutputParser()

    # JSON-structured prompt
    prompt = ChatPromptTemplate.from_template("""
    You are given a LinkedIn user profile dictionary:
    {profile}

    Extract the following fields in valid JSON format:

    {{
      "Profile Card":
      {{
        "user_id": "<linkedin user id>",
        "Name": "<full name>",
        "City": "<city/location>",
        "Linkedin URL": "<linkedin profile url>",
        "Linkedin Description": "<about/bio section>",
        "Current Company": "<current company name>",
        "Current Company Url": "<current company url>",
        "Current Position": "<current position title>",
        "Previous Company": "<previous company name>",
        "Previous Position": "<previous position title>",
        "Other Experiences": [
          {{
            "company": "<company name>",
            "title": "<job title>",
            "duration": "<duration>",
            "date": "<start - end date>",
            "location": "<location>",
            "description": "<description>"
          }}
        ]
        "Professional Summary": "<120–180 word narrative summary>"
      }},

    }}

    Important rules:
    - Do NOT invent or guess missing details.
    - If a field is missing, return "Not available".
    - For Current Company Url:
        * If a valid URL exists, return it as-is.
        * If no company URL exists, return "Not available".
        * Never output placeholders like "https://linkedin.com/company/Not available".
    - In Other Experiences:
        * Exclude the Current Company and Previous Company.
        * Keep only the remaining experiences in JSON array format.
        * If no other experiences exist, return [].
    - The Professional Summary must:
        * Mention domain/industry.
        * Explain nature of work and key responsibilities.
        * Highlight skills, talents, and areas of expertise.
        * Mention career interests/passions if available.
        * Point out achievements or leadership if available.
        * Use professional, concise, recruiter-friendly tone.
    """)

    # Run chain
    chain = prompt | llm_user_profile | parser
    output = chain.invoke({"profile": user_profile})
    return jp.parse_json_response(output)


def get_company_profile(user_profile: dict) -> dict:
    """
    Extracts the current company URL from a LinkedIn user profile dictionary,
    scrapes the company profile using BrightData, and returns the results.

    Args:
        user_profile (dict): The LinkedIn user profile dictionary.

    Returns:
        dict: The scraped company profile data, or {"error": "..."} if unavailable.
    """
    try:
        company_url = (
            user_profile
            .get("Profile Card", {})
            .get("Current Company Url", None)
        )
    except (IndexError, AttributeError):
        company_url = None

    if not company_url:
        return {"error": "Company URL not available"}

    scraper_tool = BrightDataWebScraperAPI(bright_data_api_key=BRIGHT_DATA_API_KEY)
    company_profile = scraper_tool.invoke(
        {
            "url": company_url,
            "dataset_type": "linkedin_company_profile",
        }
    )
    comp_profile = jp.parse_json_response(company_profile)
    return comp_profile


def fetch_web_news(company_name: str, max_results: int = 10) -> list[str]:
    """
    Fetch recent company news using Tavily search.
    Returns a list of "<title>: <snippet>" strings.
    """
    results = tavily_client.search(f"{company_name} recent news 2025")
    news_items = []
    for item in results.get("results", [])[:max_results]:
        title = item.get("title")
        snippet = item.get("content")
        if title and snippet:
            news_items.append(f"{title}: {snippet}")
    return news_items


def get_company_profile_text(company_profile: dict, company_name: str) -> dict:
    """
    Extracts structured company details from LinkedIn data,
    enriches with Tavily web news, and outputs valid JSON.
    """
    # Prefer company_name from LinkedIn profile if available
    profile_company_name = company_profile.get("name", company_name or "Unknown Company")
    print("COMPANY NAME:", profile_company_name)

    # Fetch Tavily news
    company_news = fetch_web_news(profile_company_name, max_results=5)

    # JSON parser
    parser = JsonOutputParser()

    # Build JSON-structured prompt
    prompt = ChatPromptTemplate.from_template("""
    You are given structured LinkedIn company profile data:
    {profile}

    You are also given recent external web news about the company:
    {company_news}

    Extract the following fields in valid JSON format:

    {{
      "Company Profile": {{
        "Company Id": "<id>",
        "Company Name": "<company name>",
        "Company Website": "<company website>",
        "Company Linkedin Url": "<linkedin url>",
        "Company Headquarters": "<headquarters>",
        "About the company": "<about>",
        "Company Speciality": "<specialties>",
        "Company Industry": "<industries>",
        "Company Size": "<company_size>",
        "Company Funding": "<funding>",
        "News Coverage": [
          {{
            "headline": "<news headline>",
            "summary": "<~70 words about the news>"
          }}
        ],
        "Summary": "<500-700 word narrative merging LinkedIn info + news>"
      }}
    }}

    Rules:
    - Do NOT invent details. Only use LinkedIn data and news provided.
    - company id is not <company_id> which is present in the company profile. It is the <id> field from the company profile.
    - If a field is missing, return "Not available".
    - Always include at least 5 items in "News Coverage" (from provided news).
    - The "Summary" must ALWAYS be present (500-700 words).
        - The Summary must merge LinkedIn information + recent news into a single professional narrative.
        - The Summary should highlight industry, mission, vision, values, products, services, innovations,
          clients, funding, partnerships, and recent achievements if available.
        - Include the recent news headlines and a 70 words about that headline.
        - Strictly include minimum of 5 headlines and 5 summaries about those headlines since these tell a lot about the company.
        - Keep the tone professional and research-style.

    """)

    # Run the chain with parser
    chain = prompt | llm | parser
    return chain.invoke({
        "profile": company_profile,
        "company_news": "\n".join(company_news) if company_news else "No recent news found."
    })


def profile_to_human_text(user_text: dict) -> str:
    llm_profile_to_human_text = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=OPENAI_API_KEY)

    prompt = ChatPromptTemplate.from_template("""
    You are given a structured LinkedIn profile JSON:
    {user_text}

    Task: Convert this into a clean, human-readable professional profile text.
    - Write in a recruiter-friendly, narrative style.
    - Highlight the person's background, current and previous roles, and notable experiences.
    - Do not give any heading for the paragraph
    - Summarize "Other Experiences" without listing every detail verbatim (group them logically).
    - End with the "Professional Summary" as a conclusion.
    - Do not invent new information. Make the paragraph with the user profile passed.
    - Do not skip any information given in the user_text. Include everything without fail.
    - Keep it 400-500 words, professional but engaging.
    """)

    chain = prompt | llm_profile_to_human_text
    return chain.invoke({"user_text": user_text}).content


def company_profile_to_human_text(company_text: dict) -> str:
    llm_company_profile_to_human_text = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=OPENAI_API_KEY)

    prompt = ChatPromptTemplate.from_template("""
    You are given a structured JSON about the company:
    {company_text}

    Task: Convert this into a clean, human-readable professional profile text.
    - Write in a recruiter-friendly, narrative style.
    - Highlight the company's background, current and previous roles, and notable experiences.
    - Summarize "Other Experiences" without listing every detail verbatim (group them logically).
    - End with the "Professional Summary" as a conclusion.
    - Do not invent new information. Make the paragraph with the company profile passed.
    - Do not skip any details given in the company profile. You have to include everything without fail.
    - Keep it 400-500 words, professional but engaging.
    """)

    chain = prompt | llm_company_profile_to_human_text
    return chain.invoke({"company_text": company_text}).content

def generate_email_script(user_profile: str, company_profile: str, product_card: str) -> dict:
    """
    Generates a personalized outreach Email script with subject + body.
    """
    parser = JsonOutputParser()

    prompt = ChatPromptTemplate.from_template("""
    You are a persuasive sales assistant named Jack working at Vera Solutions.
    You are given three inputs:
    - User profile: {user_profile}
    - Company profile: {company_profile}
    - Product information: {product_info}

    Task: Create an ATTRACTIVE, SALES-FOCUSED, personalized outreach email script in JSON format:

    {{
      "Outreach Scripts": {{
        "Email": {{
          "Subject": "<catchy and professional subject line>",
          "Body": "<200-250 word persuasive email body>"
        }}
      }}
    }}

    CRITICAL RULES FOR EMAIL BODY:
    - Start with "Dear [Name from user profile]," using the ACTUAL name from the profile
    - Your signature must be exactly: "Best regards,\nJack"
    - NO PLACEHOLDERS anywhere in the email - use real information from the profiles
    - NO brackets like [Recipient's Name], [Your Position], [Company Name], etc.
    - Use SPECIFIC company details, recent news, and user's actual role/experience
    - Personalize deeply using the user profile, company profile, and product information
    - Do not invent or assume new facts; strictly use only the provided data
    - Subject must be concise and engaging
    - Body must start with a hook, acknowledge company's mission/updates, show ROI alignment.
    - Keep it formal, polished, and compelling
    - The email should sound like an actual person writing to a specific person at a specific company. It shouldnt sound like an ai generated email.
    - You aren't allowed to give out pricing and product free trials at any cost
    - Output MUST be valid JSON only
    - You must surely end the email with a clear call-to-action (e.g., quick call/demo).
    
    """)

    chain = prompt | llm | parser
    return chain.invoke({
        "user_profile": user_profile,
        "company_profile": company_profile,
        "product_info": product_card
    })

def generate_whatsapp_script(user_profile: str, company_profile: str, product_card: str) -> dict:
    """
    Generates a short and engaging WhatsApp outreach script.
    """
    parser = JsonOutputParser()

    prompt = ChatPromptTemplate.from_template("""
    You are a persuasive sales assistant.
    Inputs:
    - User profile: {user_profile}
    - Company profile: {company_profile}
    - Product information: {product_info}

    Task: Create a WHATSAPP outreach script in JSON format:

    {{
      "Outreach Scripts": {{
        "WhatsApp": "<60-80 word conversational and engaging message>"
      }}
    }}

    RULES:
    - Your name is Jack, You work in Vera Solutions.
    - Be warm, concise, and engaging in WhatsApp style.
    - Since this message will be sent only after the user doesn't respond to emails, make it more engaging.
    - Personalize with the company's recent updates or mission.
    - Message must feel natural, not like a copy-paste email.
    - End with a clear call-to-action (e.g., quick call/demo).
    - The message has to be short and impactful. It should not be more than 100 words.
    - Output MUST be valid JSON only.
    """)

    chain = prompt | llm | parser
    return chain.invoke({
        "user_profile": user_profile,
        "company_profile": company_profile,
        "product_info": product_card
    })


def generate_call_script(user_profile: str, company_profile: str, product_card: str) -> dict:
    """
    Generates a Phone Call script for outreach.
    """
    parser = JsonOutputParser()

    prompt = ChatPromptTemplate.from_template("""
    You are a persuasive sales assistant.
    Inputs:
    - User profile: {user_profile}
    - Company profile: {company_profile}
    - Product information: {product_info}

    Task: Create a PHONE CALL outreach script in JSON format:

    {{
      "Outreach Scripts": {{
        "Phone Call": "<Script of 5-7 sentences guiding a conversation>"
      }}
    }}

    RULES:
    - Your name is Jack, You work in Vera Solutions.
    - Start with a polite greeting and quick intro.
    - Mention company's recent updates or mission.
    - Highlight the product's ROI quickly.
    - Ask engaging questions to keep the conversation flowing.
    - End with a proposal to schedule a follow-up/demo.
    - Output MUST be valid JSON only.
    """)

    chain = prompt | llm | parser
    return chain.invoke({
        "user_profile": user_profile,
        "company_profile": company_profile,
        "product_info": product_card
    })


# --- Define the state structure ---
class ConversationState(TypedDict):
    conversation_id: str
    log: List[Dict[str, Any]]
    latest_user_message: str
    communication_mode: str

# --- Node: Generate outreach scripts and initialize log ---
def outreach_node(state: ConversationState) -> ConversationState:
    # Call each generator separately
    email_script = generate_email_script(user_text, company_text, product_card)
    whatsapp_script = generate_whatsapp_script(user_text, company_text, product_card)
    call_script = generate_call_script(user_text, company_text, product_card)

    # Append Email (separate subject + body)
    state["log"].append({
        "id": str(uuid.uuid4().hex),
        "role": "assistant",
        "type": "outreach_email",
        "timestamp": datetime.now().isoformat(),
        "content": {
            "subject": email_script["Outreach Scripts"]["Email"]["Subject"],
            "body": email_script["Outreach Scripts"]["Email"]["Body"]
        }
    })

    # Append WhatsApp
    state["log"].append({
        "id": str(uuid.uuid4().hex),
        "role": "assistant",
        "type": "outreach_whatsapp",
        "timestamp": datetime.now().isoformat(),
        "content": whatsapp_script["Outreach Scripts"]["WhatsApp"]
    })

    # Append Phone Call
    state["log"].append({
        "id": str(uuid.uuid4().hex),
        "role": "assistant",
        "type": "outreach_call",
        "timestamp": datetime.now().isoformat(),
        "content": call_script["Outreach Scripts"]["Phone Call"]
    })

    # Save to JSON each time
    with open(f"conversation_{state['conversation_id']}.json", "w") as f:
        json.dump(state, f, indent=2)

    return state


def load_calendar(path: str = CALENDAR_PATH):
    """
    Tries to open and parse calendar.json.

    If the file doesn't exist -- returns an empty dict (no calendar yet).

    If the file exists but is broken JSON -- raises an error.
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise RuntimeError(f"calendar.json has some problem: {e}")

# --- Node: summarization ---
def _get_summary_chain():
    summary_prompt_txt = prompts.SUMMARY_PROMPT
    summary_prompt = ChatPromptTemplate.from_template(summary_prompt_txt)
    summary_chain = summary_prompt | llm | StrOutputParser()
    return summary_chain

def format_conversation_log(log: list) -> str:
    formatted = []
    for entry in log:
        role = entry["role"].capitalize()
        content = entry["content"]
        reply_to = entry.get("reply_to")
        if reply_to:
            formatted.append(f"{role} (reply to {reply_to}): {content}")
        else:
            formatted.append(f"{role}: {content}")
    return "\n".join(formatted)


def summarize_node(state: dict) -> dict:
    conversation_log = format_conversation_log(state["log"])
    summary_chain = _get_summary_chain()
    summary = summary_chain.invoke({"conversation_log": conversation_log})

    # Keep the summary only at the top level (do NOT append an assistant log entry)
    state["conversation_summary"] = summary

    # Persist state so the saved conversation file contains the top-level conversation_summary
    with open(f"conversation_{state['conversation_id']}.json", "w") as f:
        json.dump(state, f, indent=2)

    return state


def _save_calendar(calendar):
    print('saving calendar...')
    print(calendar)
    with open(CALENDAR_PATH, 'w') as f:
        json.dump(calendar, f, indent = 2)



def _check_availablility(calendar, sch_response):
    msg_str = ""
    dt_avail = sch_response['date'] in calendar
    tm_avail = False
    
    if dt_avail:
        tm_avail = sch_response['time'] in calendar[sch_response['date']]
    
    if not dt_avail:
        available_dates = "Dates available are: \n"
        for key in calendar.keys():
            if key != 'bookings' and key != 'reminders':  # Exclude non-date keys
                try:
                    dt = datetime.strptime(key, '%Y-%m-%d')
                    asked_dt = datetime.strptime(sch_response['date'], '%Y-%m-%d')
                    if dt >= asked_dt:  # Include today and future dates
                        available_dates += f"{key}:\n"
                        for time_slot in calendar[key]:
                            available_dates += f"  - {time_slot}\n"
                        available_dates += "\n"
                except ValueError:
                    continue  # Skip invalid date formats
        msg_str = available_dates

    elif dt_avail and not tm_avail:
        available_slots = f"Slots available on {sch_response['date']} are:\n"
        for slot in calendar[sch_response['date']]:
            available_slots += f"  - {slot}\n"
        msg_str = available_slots
    
    return {
        "avail_date": dt_avail,
        "avail_time": tm_avail,
        "message": msg_str
    }


def _scheduler(id, sch_response, communication_mode):
    print('Scheduling the event...')
    print(sch_response)
    
    calendar = load_calendar()
    if sch_response['action'].lower() == 'reminder':
        if 'reminder' in calendar:
            calendar['reminder'].append({
                "id": id,
                "date": sch_response['date'],
                "time": sch_response['time'],
                "type": communication_mode
            })
        
        else:
            calendar['remainder'] = [{
                "id": id,
                "date": sch_response['date'],
                "time": sch_response['time'],
                "type": communication_mode
            }]
    
        _save_calendar(calendar)
        return {
                "success": True,
                "message": f"Reminder Scheduled at {sch_response['date']} {sch_response['time']}"
            }
    
    
    if sch_response['intent'].lower() == 'schedule':
        avail_msg = _check_availablility(calendar, sch_response)
        is_available = True if avail_msg['avail_date'] and avail_msg['avail_time'] else False

        # if sch_response['date'] in calendar:
        #     schedules = calendar[sch_response['date']]
        #     for sch in schedules:
        #         if sch.lower() == sch_response['time'].lower():  # Added .lower() for case-insensitive comparison
        #             is_available = True
        #             schedules.remove(sch)
        #             break  # Added break to exit loop once found
        
        if is_available:
            print('booking the date...')
            # Initialize bookings list if it doesn't exist
            if 'bookings' not in calendar:
                calendar['bookings'] = []
            
            calendar['bookings'].append({
                "id": id,
                "date": sch_response['date'],
                "time": sch_response['time'],
                "type": sch_response['action']
            })
            calendar[sch_response['date']].remove(sch_response['time'])

            _save_calendar(calendar)
            return {
                "success": True,
                "message": f"Booking Scheduled at {sch_response['date']} {sch_response['time']}"
            }
        
        
        
        return {
            "success": False,
            "message": f"Meeting not scheduled.\n {avail_msg['message']}"
        }
    
    if sch_response['intent'].lower() == 'reschedule':  # Fixed typo: 'reschule' -> 'reschedule'
        # Check if the new time slot is available
        avail = _check_availablility(calendar, sch_response)
        print("Availability check result:", avail)
        
        if avail['avail_date'] and avail['avail_time']:
            # Find and remove the existing booking
            old_bookings = []
            updated_bookings = []
            
            # Initialize bookings list if it doesn't exist
            if 'bookings' not in calendar:
                calendar['bookings'] = []
            
            for booking in calendar['bookings']:
                if booking['id'] == id:
                    old_bookings.append({
                        'date': booking['date'],
                        'time': booking['time']
                    })
                else:
                    updated_bookings.append(booking)  # Keep bookings that don't match the ID
            
            # Update the bookings list (remove old booking)
            calendar['bookings'] = updated_bookings
            
            # Add the new booking
            calendar['bookings'].append({
                "id": id,
                "date": sch_response['date'],
                "time": sch_response['time'],
                "type": sch_response['action']
            })

            # Remove the new slot from available slots (since it's now booked)
            if sch_response['date'] in calendar and sch_response['time'] in calendar[sch_response['date']]:
                calendar[sch_response['date']].remove(sch_response['time'])
            
            # Add the old time slots back to available slots
            for old_slot in old_bookings:
                if old_slot['date'] in calendar:
                    if old_slot['time'] not in calendar[old_slot['date']]:  # Avoid duplicates
                        calendar[old_slot['date']].append(old_slot['time'])
                else:
                    calendar[old_slot['date']] = [old_slot['time']]
            
            _save_calendar(calendar)
            return {
                "success": True,
                "message": f"Rescheduling successful for {sch_response['date']} {sch_response['time']}"
            }
        
        else:
            return {
                "success": False,
                "message": f"Meeting not rescheduled.\n {avail['message']}"
            }
    
    return {
        "success": False,
        "message": "Invalid Input Please Retry"
    }


def _cancel_event(id, sch_response):
    try:
        calendar = load_calendar()
        for booking in calendar['bookings']:
            if booking['id'] == id:
                if booking['date'] == sch_response['date'] and booking['time'] == sch_response['time']:
                    calendar['bookings'].remove(booking)
                    _save_calendar(calendar)
                    calendar[sch_response['date']].append(sch_response['time'])
                    break
        
        return {
            "success": True,
            "message": "Event cancelled successfully"
        }
    except Exception as e:
        print(e)
        return {
            "success": False,
            "message": "Cancellation Failed"
        }
    
def _get_parse_chain():
    parse_prompt = ChatPromptTemplate.from_template(prompts.PARSE_PROMPT)
    parse_chain = parse_prompt | llm | StrOutputParser()
    return parse_chain

def detect_and_schedule_node(state: dict) -> dict:
    latest_user_msg = next((entry for entry in reversed(state["log"]) if entry["role"] == "user"), None)
    if not latest_user_msg:
        return state
    
    latest_text = latest_user_msg["content"]
    now_time = datetime.now()
    today = now_time.strftime("%Y-%m-%d")
    today_day = now_time.strftime("%A")
    max_time = datetime.now()
    
    calendar = load_calendar()
    if 'bookings' in calendar:
        for booking in calendar['bookings']:
            if 'id' in booking and booking['id'] == state['conversation_id']:
                str_date_time = booking['date'] + " " + booking['time']
                dt_dt = datetime.strptime(str_date_time, '%Y-%m-%d %H:%M')
                if dt_dt > max_time:
                    max_time = dt_dt
    
    parse_chain = _get_parse_chain()
    schedule_resp = parse_chain.invoke(
        {
            "today_date_str": today,
            "today_day": today_day,
            "curr_sch_dt_time": max_time.strftime('%Y-%m-%d %H:%M:%S'),
            "user_query": latest_text
        }
    )

    sch_response = jp.parse_json_response(schedule_resp)
    print(sch_response)
    if sch_response:
        # Fixed typo: 'reschule' -> 'reschedule'
        if sch_response['intent'].lower() == 'schedule' or sch_response['intent'].lower() == 'reschedule':
            sch_resp = _scheduler(state['conversation_id'], sch_response, state['communication_mode'])
            state['log'].append(
                {
                    "id": state['conversation_id'],
                    "role": 'tool',
                    "type": sch_response['action'],
                    "timestamp": datetime.now().isoformat(),
                    "content": sch_resp['message']
                }
            )
        
        if sch_response['intent'].lower() == 'cancel':
            cancel_resp = _cancel_event(state['conversation_id'], sch_response)
            c = 0
            while c < 5:
                if cancel_resp['success']:
                    state['log'].append(
                        {
                            "id": state['conversation_id'],
                            "role": 'tool',
                            "type": sch_response['action'],
                            "timestamp": datetime.now().isoformat(),
                            "content": cancel_resp['message']
                        }
                    )
                    c = 6
                else:
                    print('Retrying...')
                    cancel_resp = _cancel_event(state['conversation_id'], sch_response)
                    c += 1
            
            if not cancel_resp['success']:
                state['log'].append(
                        {
                            "id": state['conversation_id'],
                            "role": 'tool',
                            "type": sch_response['action'],
                            "timestamp": datetime.now().isoformat(),
                            "content": cancel_resp['message']
                        }
                    )

        if sch_response['action'] == 'reminder':
            # Initialize reminders if it doesn't exist
            if 'reminders' not in state:
                state['reminders'] = []
            state['reminders'].append({
                "id": state['conversation_id'],
                "context": sch_response['context'],
                "date": sch_response['date'],
                "time": sch_response['time']
            })
    
    state = summarize_node(state)
    return state

def _check_product_reminder(state, user_msg):
    prompt = prompts.PRODUCT_REMINDER_PROMPT.format(
        user_profile = str(user_text),
        communication_mode = state['communication_mode'],
        product_details = prompts.PRODUCT_CARD,
        conversation_summary = state['conversation_summary'],
        user_msg = user_msg)

    response = llm.invoke(prompt).content
    resp = jp.parse_json_response(response)
    
    if resp['valid'] == 'yes':
        return {
            "success": True,
            "type": resp['type'],
            "message": resp['message']
        }
    return {
        "success": False,
        "message": resp['message']
    }


def _validate_and_generate_response(state, latest_user_msg):
    mode_prompts = get_mode_specific_prompts(state.get('communication_mode', 'email'))
    meet_resp = _check_product_reminder(state, latest_user_msg)
    if meet_resp['success'] and meet_resp['type'].lower() != 'reminder':
        return {
            "type": "general",
            "message": meet_resp['message']
        }
    elif meet_resp['success'] and meet_resp['type'].lower() == 'reminder':
        meeting_prompt_text = mode_prompts['meeting_prompt'].format(
            user_query = latest_user_msg['content'],
            tool_output = state['conversation_summary']
        )
        output = llm.invoke(meeting_prompt_text).content
        return {
            "type": 'meeting',
            "message": output
        }
    
    validate_prompt_text = mode_prompts['validate_prompt'].format(
        conversation_summary = state.get('conversation_summary', ''),
        latest_user_msg = latest_user_msg['content']
    )

    response = llm.invoke(validate_prompt_text)
    print('[VALIDATE BLOCK]Response...')
    print(response.content)
    resp = jp.parse_json_response(response.content)
    
    if resp['action'] == 'meeting':
        meeting_prompt_text = mode_prompts['meeting_prompt'].format(
            user_query = latest_user_msg['content'],
            tool_output = state['conversation_summary']
        )
        output = llm.invoke(meeting_prompt_text).content
        return {
            "type": 'meeting',
            "message": output
        }
    else:
        system_prompt = mode_prompts['general_system_prompt']
        system_prompt_template = SystemMessagePromptTemplate.from_template(system_prompt)
        latest_user_prompt_template = HumanMessagePromptTemplate.from_template("""Latest client message:
        {latest_message}
        """)
        reply_prompt = ChatPromptTemplate.from_messages([
            system_prompt_template,
            latest_user_prompt_template
        ])
        reply_chain = reply_prompt | llm | StrOutputParser()
        assistant_reply = reply_chain.invoke({
            "conversation_summary": state.get("conversation_summary", ""),
            "latest_message": latest_user_msg["content"],
            "product_details": product_card
        })

        validate_product_pricing_output = llm.invoke(prompts.VALIDATE_PRODUCT_PRICING_PROMPT.format(output = assistant_reply)).content
        

        return {
            "type": "general",
            "message": validate_product_pricing_output
        }
    

def reply_node(state: dict) -> dict:
    latest_user_msg = next(
        (entry for entry in reversed(state["log"]) if entry["role"] == "user"),
        None
    )
    if not latest_user_msg:
        raise ValueError("No user message found in the log.")
    
    response = _validate_and_generate_response(state, latest_user_msg)
    
    if response['type'] == 'meeting':
        state = detect_and_schedule_node(state)
        response = _validate_and_generate_response(state, latest_user_msg)
    
    # Get the communication mode for proper response type
    comm_mode = state.get('communication_mode', 'email')
    response_type_map = {
        'whatsapp': 'reply_whatsapp',
        'call': 'reply_call', 
        'email': 'reply_email'
    }
    
    state["log"].append({
        "id": str(uuid.uuid4().hex),
        "role": "assistant",
        "type": response_type_map[comm_mode],
        "reply_to": latest_user_msg["id"],
        "timestamp": datetime.now().isoformat(),
        "content": response['message']
    })

    # Save JSON
    with open(f"conversation_{state['conversation_id']}.json", "w") as f:
        json.dump(state, f, indent=2)

    return state


def initialization_and_scrapping():
    print('fetching user profile')
    user_profile = user_profile_scraper("https://www.linkedin.com/in/kriti-rohilla/")
    user_text = get_user_profile(user_profile)
    print('fetching company profile...')
    company_profile = get_company_profile(user_text)
    company_name = company_profile.get("name")
    company_text = get_company_profile_text(company_profile, company_name)

    user_profile= profile_to_human_text(user_text)
    company_profile = company_profile_to_human_text(company_text)
    print("created a company profile")
    graph = StateGraph(ConversationState)

    graph.add_node("outreach", outreach_node)
    graph.set_entry_point("outreach")
    graph.set_finish_point("outreach")  # ends after outreach for now

    # --- Compile graph ---
    app = graph.compile()

    # --- Run initial conversation ---
    initial_state: ConversationState = {
        "conversation_id": user_text["Profile Card"]["user_id"],
        "log": [],
        "latest_user_message": "",  # initialize empty
        "communication_mode": COMMUNICATION_MODE
    }

    final_state = app.invoke(initial_state)
    conversation_id = final_state["conversation_id"]
    
    user_text = jp.parse_json_response(user_text)
    company_text = jp.parse_json_response(company_text)

    return user_text, company_text


def display_initial_outreach_scripts(conversation_file):
    """
    Display the initial outreach scripts based on selected communication mode
    """
    with open(conversation_file, "r") as f:
        state = json.load(f)
    
    mode = state.get("communication_mode", "email")
    
    print(f"\n{'='*60}")
    print(f"INITIAL {mode.upper()} OUTREACH SCRIPTS")
    print('='*60)
    
    # Display the relevant outreach script based on mode
    for entry in state["log"]:
        if entry["role"] == "assistant":
            if mode == "email" and entry["type"] == "outreach_email":
                print(f"\n📧 EMAIL SCRIPT:")
                print(f"Subject: {entry['content']['subject']}")
                print(f"\nBody:\n{entry['content']['body']}")
                break
            elif mode == "whatsapp" and entry["type"] == "outreach_whatsapp":
                print(f"\n💬 WHATSAPP SCRIPT:")
                print(entry['content'])
                break
            elif mode == "call" and entry["type"] == "outreach_call":
                print(f"\n💼 CALL SCRIPT:")
                print(entry['content'])
                break
    
    print(f"\n{'='*60}")
    print(f"Now you can simulate {mode.upper()} conversation...")
    print('='*60)


if __name__ == '__main__':
    # Choose communication mode first
    communication_mode = choose_communication_mode()
    
    # Load or initialize user and company data
    try:
        with open('user_text.json', 'r') as f:
            user_text = json.load(f)
        
        with open('company_text.json', 'r') as f:
            company_text = json.load(f)
        
        print("✓ Loaded existing user and company profiles")
    except FileNotFoundError:
        print("Profiles not found. Initializing and scraping...")
        user_text, company_text = initialization_and_scrapping()
        
        if user_text and company_text and type(user_text) == dict and type(company_text) == dict:
            with open('user_text.json', 'w') as f:
                json.dump(user_text, f, indent = 2)
            
            with open('company_text.json', 'w') as f:
                json.dump(company_text, f, indent = 2)
            print("✓ Saved user and company profiles")

    # Check for existing conversation or create new one
    conversation_file = "conversation_kriti-rohilla.json"
    
    try:
        with open(conversation_file, "r") as f:
            existing_state = json.load(f)
        
        # Update communication mode if it's different
        existing_state["communication_mode"] = communication_mode
        
        with open(conversation_file, "w") as f:
            json.dump(existing_state, f, indent=2)
            
        print("✓ Loaded existing conversation")
        
    except FileNotFoundError:
        print("Creating new conversation...")
        # Run initial outreach generation
        user_text, company_text = initialization_and_scrapping()
        
        with open(conversation_file, "r") as f:
            existing_state = json.load(f)
        
        print("✓ Created new conversation with outreach scripts")

    # Display initial scripts
    display_initial_outreach_scripts(conversation_file)
    
    # Main conversation loop
    while True:
        print(f"\n[{communication_mode.upper()} MODE]")
        new_user_message = input(f"Enter client's {communication_mode} message (or 'quit' to exit): ")
        
        if new_user_message.lower() == 'quit':
            print("Conversation ended.")
            break
            
        if new_user_message.lower() == 'switch':
            print("\nSwitching communication mode...")
            communication_mode = choose_communication_mode()
            existing_state["communication_mode"] = communication_mode
            
            with open(conversation_file, "w") as f:
                json.dump(existing_state, f, indent=2)
            continue
        
        # Find the last assistant message to reply to
        last_assistant_msg = next(
            (
                entry for entry in reversed(existing_state["log"])
                if entry["role"] == "assistant" and entry["type"] in [
                    "outreach_email", "outreach_whatsapp", "outreach_call",
                    "reply_email", "reply_whatsapp", "reply_call"
                ]
            ),
            None
        )

        # Add user message to log
        existing_state["log"].append({
            "id": str(uuid.uuid4().hex),
            "role": "user",
            "type": f"reply_{communication_mode}",
            "reply_to": last_assistant_msg["id"] if last_assistant_msg else None,
            "timestamp": datetime.now().isoformat(),
            "content": new_user_message
        })

        existing_state["latest_user_message"] = new_user_message
        
        # Create conversation graph for reply processing
        graph = StateGraph(dict)
        graph.add_node("summarize", summarize_node)
        graph.add_node("reply", reply_node)
        graph.set_entry_point("summarize")
        graph.add_edge("summarize", "reply")
        graph.set_finish_point("reply")
        app = graph.compile()

        # Process the response
        try:
            updated_state = app.invoke(existing_state)
            
            # Display the assistant's response
            last_response = updated_state["log"][-1]
            print(f"\nJack's {communication_mode.upper()} Response:")
            print("-" * 50)
            print(last_response["content"])
            print("-" * 50)
            
        except Exception as e:
            print(f"Error processing message: {e}")
            continue