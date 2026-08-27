import os
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.tools.tools import web_search, scrape_url
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# ── Model Initialization ─────────────────────────────────────────────────────
# Primary: Gemini. Fallback: Grok (xAI), via the OpenAI-compatible endpoint.
# If Gemini hits a rate limit, quota error, or a deprecated/renamed model,
# the call automatically retries on Grok instead of crashing the pipeline.

primary_llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    temperature=0,
)

fallback_llm = ChatOpenAI(
    model="grok-4-fast",
    api_key=os.getenv("XAI_API_KEY"),
    base_url="https://api.x.ai/v1",
    temperature=0,
)

llm = primary_llm.with_fallbacks([fallback_llm])


# 1st Agent : Search Agent
def build_search_agent():
    return create_agent(
        model=llm,
        tools=[web_search],
    )

# 2nd Agent : Reader Agent
def build_reader_agent():
    return create_agent(
        model=llm,
        tools=[scrape_url],
    )


# writer chain

writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert research writer. Write clear, structured and insightful reports."),
    ("human", """Write a detailed research report on the topic below.

Topic: {topic}

Research Gathered:
{research}

Structure the report as:
- Introduction
- Key Findings (minimum 3 well-explained points)
- Conclusion
- Sources (list all URLs found in the research)

Be detailed, factual and professional."""),
])

writer_chain = writer_prompt | llm | StrOutputParser()


# critic_chain

critic_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a sharp and constructive research critic. Be honest and specific."),
    ("human", """Review the research report below and evaluate it strictly.

Report:
{report}

Respond in this exact format:

Score: X/10

Strengths:
- ...
- ...

Areas to Improve:
- ...
- ...

One line verdict:
..."""),
])

critic_chain = critic_prompt | llm | StrOutputParser()


# fact_checker_chain

fact_checker_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a meticulous fact-checker. You verify claims against source material with zero tolerance for unsupported statements."),
    ("human", """Compare the report below against the original source content it was based on.
For each key factual claim in the report, check whether it is directly supported by the source content.

Source Content:
{source_content}

Report:
{report}

Respond in this exact format:

Verified Claims:
- ...
- ...

Unsupported or Unclear Claims:
- ...
- ...

Fact-Check Verdict: [PASS / NEEDS REVIEW]
..."""),
])

fact_checker_chain = fact_checker_prompt | llm | StrOutputParser()