"""
modules/explanation_chain.py

LangChain LCEL Explanation Chain.
Generates human-readable explanations for scheme recommendations using:
  - PromptTemplate
  - RunnableParallel
  - RunnablePassthrough
  - LCEL (|) composition
  - StrOutputParser
  - Gemini 2.0 Flash
"""

import os
import logging
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ── Prompt templates ──────────────────────────────────────────────────────────

ELIGIBILITY_PROMPT_TEMPLATE = """
You are a helpful government scheme advisor for Indian citizens.

A citizen has been matched with a government scheme. Your task is to explain in clear, 
simple language (suitable for rural citizens) why they are eligible and how to benefit.

CITIZEN PROFILE:
- Name: {user_name}
- Age: {age} years
- State: {state}
- Annual Income: ₹{annual_income:,}
- Category: {category}
- Occupation: {occupation}
- Special Status: {special_status}

SCHEME DETAILS:
- Scheme Name: {scheme_name}
- Benefits: {benefits}

ELIGIBILITY SCORE: {eligibility_score}/100

MATCH REASONS:
{match_reasons}

Please provide:

1. WHY ELIGIBLE (2-3 sentences explaining why this citizen qualifies):

2. BENEFITS SUMMARY (2-3 sentences describing what the citizen will receive in simple terms):

3. RECOMMENDATION (1-2 sentences encouraging the citizen to apply and what documents to keep ready):

Keep the language simple, warm, and encouraging. Write as if speaking to the citizen directly.
"""

BULK_EXPLANATION_PROMPT = """
You are a senior government scheme advisor.

Summarize why the following schemes are top recommendations for this citizen profile in 1 sentence each.

Citizen: {user_name}, Age {age}, {category} category, ₹{annual_income:,} income, {state}

Top Schemes:
{scheme_list}

Provide a 1-sentence recommendation for each scheme. Format:
SCHEME NAME: Recommendation sentence.
"""


class ExplanationChain:
    """
    LCEL-based chain that generates personalized explanations for scheme recommendations.
    Falls back to rule-based templates if Gemini API is unavailable.
    """

    def __init__(self):
        self._llm = None
        self._chain = None
        self._initialized = False

    def _ensure_init(self):
        """Lazy initialization to avoid import errors at module load time."""
        if self._initialized:
            return

        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key or api_key == "your_gemini_api_key_here":
            logger.warning("GOOGLE_API_KEY not set. Using template-based explanations.")
            self._initialized = True
            return

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.prompts import PromptTemplate
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.runnables import RunnableParallel, RunnablePassthrough

            self._llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=api_key,
                temperature=0.4,
            )

            prompt = PromptTemplate(
                input_variables=[
                    "user_name", "age", "state", "annual_income", "category",
                    "occupation", "special_status", "scheme_name", "benefits",
                    "eligibility_score", "match_reasons",
                ],
                template=ELIGIBILITY_PROMPT_TEMPLATE,
            )

            parser = StrOutputParser()

            # LCEL composition with RunnablePassthrough to preserve input context
            self._chain = (
                RunnablePassthrough()
                | prompt
                | self._llm
                | parser
            )

            logger.info("ExplanationChain initialized with Gemini 2.0 Flash")
        except Exception as exc:
            logger.error(f"Failed to initialize LLM chain: {exc}")
            self._llm = None
            self._chain = None

        self._initialized = True

    # ── Template fallback ─────────────────────────────────────────────────────

    @staticmethod
    def _template_explanation(
        user_profile: Dict[str, Any],
        scheme: Dict[str, Any],
        match_reasons: List[str],
    ) -> str:
        """Rule-based explanation when Gemini is not available."""
        name = user_profile.get("user_name", "Applicant")
        score = scheme.get("eligibility_score", 0)
        scheme_name = scheme.get("scheme_name", "this scheme")
        benefits = scheme.get("benefits", "various benefits")

        positive_reasons = [r for r in match_reasons if r.startswith("✅")]
        reason_text = (
            ", ".join(r.replace("✅ ", "") for r in positive_reasons[:3])
            if positive_reasons
            else "meeting the basic eligibility criteria"
        )

        explanation = f"""1. WHY ELIGIBLE:
Dear {name}, you qualify for {scheme_name} because of {reason_text}. \
Your eligibility score is {score}/100, which indicates a strong match with this scheme's requirements.

2. BENEFITS SUMMARY:
Under this scheme, you can avail: {benefits}. \
This financial assistance is provided directly by the Government of India/State Government \
to help citizens like you improve their quality of life.

3. RECOMMENDATION:
We strongly encourage you to apply at the earliest. Keep your Aadhaar card, income certificate, \
caste certificate (if applicable), bank passbook, and passport-size photographs ready before applying. \
Visit the official portal link provided to start your application today!"""

        return explanation

    # ── Public API ────────────────────────────────────────────────────────────

    def explain(
        self,
        user_profile: Dict[str, Any],
        scheme_result: Dict[str, Any],
    ) -> str:
        """
        Generate a personalized explanation for a single scheme recommendation.

        Args:
            user_profile: User's demographic and eligibility data
            scheme_result: Result dict from EligibilityEngine (includes score + reasons)

        Returns:
            Human-readable explanation string
        """
        self._ensure_init()

        match_reasons = scheme_result.get("match_reasons", [])

        if self._chain is None:
            return self._template_explanation(user_profile, scheme_result, match_reasons)

        special_status_parts = []
        if user_profile.get("is_disabled"):
            special_status_parts.append("Person with Disability")
        if user_profile.get("is_minority"):
            special_status_parts.append("Minority Community")
        if user_profile.get("is_widow"):
            special_status_parts.append("Widow")
        if user_profile.get("is_ex_serviceman"):
            special_status_parts.append("Ex-Serviceman")
        special_status = ", ".join(special_status_parts) or "None"

        input_data = {
            "user_name": user_profile.get("user_name", "Applicant"),
            "age": user_profile.get("age", "N/A"),
            "state": user_profile.get("state", "N/A"),
            "annual_income": user_profile.get("annual_income", 0),
            "category": user_profile.get("category", "General"),
            "occupation": user_profile.get("occupation", "N/A"),
            "special_status": special_status,
            "scheme_name": scheme_result.get("scheme_name", ""),
            "benefits": scheme_result.get("benefits", ""),
            "eligibility_score": scheme_result.get("eligibility_score", 0),
            "match_reasons": "\n".join(match_reasons),
        }

        try:
            return self._chain.invoke(input_data)
        except Exception as exc:
            logger.error(f"Chain invocation failed: {exc}")
            return self._template_explanation(user_profile, scheme_result, match_reasons)

    def explain_batch(
        self,
        user_profile: Dict[str, Any],
        scheme_results: List[Dict[str, Any]],
        top_n: int = 5,
    ) -> Dict[str, str]:
        """
        Generate explanations for the top-N schemes.

        Returns:
            Dict mapping scheme_name → explanation string
        """
        explanations = {}
        for result in scheme_results[:top_n]:
            name = result.get("scheme_name", "")
            explanations[name] = self.explain(user_profile, result)

        return explanations

    def quick_summary(
        self,
        user_profile: Dict[str, Any],
        scheme_results: List[Dict[str, Any]],
    ) -> str:
        """
        Generate a short one-line summary for each top scheme.
        Used in dashboard overview cards.
        """
        self._ensure_init()

        if not scheme_results:
            return "No matching schemes found."

        if self._llm is None:
            lines = []
            for r in scheme_results[:5]:
                lines.append(
                    f"• **{r['scheme_name']}** (Score: {r['eligibility_score']}/100): "
                    f"{r.get('benefits', '')[:100]}…"
                )
            return "\n".join(lines)

        try:
            from langchain_core.prompts import PromptTemplate
            from langchain_core.output_parsers import StrOutputParser

            scheme_list = "\n".join(
                f"- {r['scheme_name']} (score {r['eligibility_score']}/100)"
                for r in scheme_results[:5]
            )
            prompt = PromptTemplate(
                input_variables=["user_name", "age", "category", "annual_income", "state", "scheme_list"],
                template=BULK_EXPLANATION_PROMPT,
            )
            chain = prompt | self._llm | StrOutputParser()
            return chain.invoke({
                "user_name": user_profile.get("user_name", "Applicant"),
                "age": user_profile.get("age", "N/A"),
                "category": user_profile.get("category", "General"),
                "annual_income": user_profile.get("annual_income", 0),
                "state": user_profile.get("state", "N/A"),
                "scheme_list": scheme_list,
            })
        except Exception as exc:
            logger.error(f"Quick summary failed: {exc}")
            return "See individual scheme details below."
