"""
data_pipeline/extractor.py

AI Extraction Engine:
Converts messy eligibility text into structured JSON fields using
Google Gemini 2.0 Flash + LangChain LCEL.
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PROCESSED_PATH = Path("data/processed")
PROCESSED_PATH.mkdir(parents=True, exist_ok=True)

# ── Extraction prompt ─────────────────────────────────────────────────────────

ELIGIBILITY_EXTRACTION_PROMPT_TEXT = """You are a government scheme eligibility extraction expert.

Extract structured eligibility criteria from the given text and return ONLY a valid JSON object.
Do NOT include any explanation, markdown formatting, or code fences. Return raw JSON only.

Scheme Name: {scheme_name}

Eligibility Text:
{eligibility_text}

Extract the following fields:
- min_age: minimum age in years (integer or null)
- max_age: maximum age in years (integer or null)
- income_limit: maximum annual family income in INR rupees as an integer (e.g., 250000 for ₹2.5 lakh), or null if no limit
- category: list of eligible categories from ["SC", "ST", "OBC", "General", "EWS", "Minority"] or ["All"] if no restriction
- occupation: list of eligible occupations such as ["Farmer", "Street Vendor", "Student", "Business Owner", "Government Employee", "Private Employee", "Self-Employed", "Unemployed", "Labourer"] or ["All"] if no restriction
- education: minimum education qualification as a string (e.g., "10th Pass", "12th Pass", "Graduate", "Post Graduate") or null
- state: list of eligible states (e.g., ["Punjab", "Haryana"]) or ["All"] if no restriction
- district: list of eligible districts or ["All"] if no restriction
- disability_required: true if applicant must be disabled, false otherwise
- minority_required: true if applicant must be from a minority community, false otherwise
- widow_required: true if applicant must be a widow, false otherwise
- ex_serviceman_required: true if applicant must be an ex-serviceman, false otherwise
- residence_type: "Rural" or "Urban" or "Both" (default "Both" if not specified)
- gender: "Male" or "Female" or "Any" (default "Any" if not specified)

Rules:
- Use null for numeric fields when not specified
- Use ["All"] for list fields when there is no restriction
- Convert income amounts to integer rupees (e.g., "₹2.5 lakh" = 250000, "₹3 lakh" = 300000)
- Be conservative: if in doubt, use null or ["All"]

Return ONLY the JSON object:"""


class EligibilityExtractor:
    """
    Uses Gemini 2.0 Flash via LangChain to extract structured eligibility fields
    from unstructured government scheme eligibility text.
    """

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        self.llm = None
        self.chain = None
        self.parser = None

        if not api_key or api_key == "your_gemini_api_key_here":
            logger.warning("GOOGLE_API_KEY not set. Using rule-based fallback extractor.")
        else:
            try:
                from langchain_core.output_parsers import StrOutputParser
                from langchain_core.prompts import PromptTemplate
                from langchain_google_genai import ChatGoogleGenerativeAI

                self.llm = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    google_api_key=api_key,
                    temperature=0.0,
                )
                prompt = PromptTemplate(
                    input_variables=["scheme_name", "eligibility_text"],
                    template=ELIGIBILITY_EXTRACTION_PROMPT_TEXT,
                )
                self.parser = StrOutputParser()
                self.chain = prompt | self.llm | self.parser
            except (ImportError, ModuleNotFoundError) as exc:
                logger.warning(
                    f"LangChain dependencies unavailable: {exc}. "
                    "Using rule-based fallback extractor."
                )
            except Exception as exc:
                logger.warning(
                    f"Could not initialize Gemini extractor: {exc}. "
                    "Using rule-based fallback extractor."
                )

    # ── Default empty structure ───────────────────────────────────────────────

    @staticmethod
    def _empty_eligibility() -> Dict[str, Any]:
        return {
            "min_age": None,
            "max_age": None,
            "income_limit": None,
            "category": ["All"],
            "occupation": ["All"],
            "education": None,
            "state": ["All"],
            "district": ["All"],
            "disability_required": False,
            "minority_required": False,
            "widow_required": False,
            "ex_serviceman_required": False,
            "residence_type": "Both",
            "gender": "Any",
        }

    # ── Rule-based fallback (no API key needed) ───────────────────────────────

    @staticmethod
    def _rule_based_extract(scheme_name: str, text: str) -> Dict[str, Any]:
        """
        Fast, offline extraction using regex-like keyword matching.
        Not as accurate as LLM but functional without API key.
        """
        result = EligibilityExtractor._empty_eligibility()
        text_lower = text.lower()

        # Age
        import re
        age_min = re.search(r'(?:age|aged)\s+(?:must be\s+)?(\d+)\s*(?:years?|yr)?(?:\s*or\s*above|\s*and\s*above|\s*minimum)?', text_lower)
        age_max = re.search(r'(?:age|aged)\s+(?:must\s+not\s+exceed|below|under|upto|up to)\s+(\d+)', text_lower)
        age_between = re.search(r'between\s+(\d+)\s+and\s+(\d+)\s+years?', text_lower)

        if age_between:
            result["min_age"] = int(age_between.group(1))
            result["max_age"] = int(age_between.group(2))
        else:
            if age_min:
                result["min_age"] = int(age_min.group(1))
            if age_max:
                result["max_age"] = int(age_max.group(1))

        # Income
        income_patterns = [
            r'₹\s*(\d+(?:\.\d+)?)\s*lakh',
            r'rs\.?\s*(\d+(?:\.\d+)?)\s*lakh',
            r'rupees?\s*(\d+(?:\.\d+)?)\s*lakh',
        ]
        for pat in income_patterns:
            m = re.search(pat, text_lower)
            if m:
                result["income_limit"] = int(float(m.group(1)) * 100000)
                break

        # Category
        cats = []
        if "scheduled caste" in text_lower or " sc " in text_lower or "(sc)" in text_lower:
            cats.append("SC")
        if "scheduled tribe" in text_lower or " st " in text_lower or "(st)" in text_lower:
            cats.append("ST")
        if "other backward" in text_lower or " obc " in text_lower:
            cats.append("OBC")
        if "minority" in text_lower:
            cats.append("Minority")
            result["minority_required"] = True
        if "economically weaker" in text_lower or " ews " in text_lower:
            cats.append("EWS")
        result["category"] = cats if cats else ["All"]

        # Occupation
        occs = []
        occ_map = {
            "farmer": "Farmer",
            "agricultur": "Farmer",
            "street vendor": "Street Vendor",
            "hawker": "Street Vendor",
            "student": "Student",
            "business": "Business Owner",
            "entrepreneur": "Business Owner",
            "self-employ": "Self-Employed",
            "labourer": "Labourer",
            "labor": "Labourer",
        }
        for kw, occ in occ_map.items():
            if kw in text_lower and occ not in occs:
                occs.append(occ)
        result["occupation"] = occs if occs else ["All"]

        # State
        states = [
            "Punjab", "Haryana", "Delhi", "Maharashtra", "Gujarat", "Rajasthan",
            "Uttar Pradesh", "Bihar", "West Bengal", "Tamil Nadu", "Karnataka",
            "Andhra Pradesh", "Telangana", "Madhya Pradesh", "Kerala",
        ]
        found_states = [s for s in states if s.lower() in text_lower]
        result["state"] = found_states if found_states else ["All"]

        # Special conditions
        if "widow" in text_lower:
            result["widow_required"] = True
        if "ex-serviceman" in text_lower or "ex serviceman" in text_lower or "exserviceman" in text_lower:
            result["ex_serviceman_required"] = True
        if "disab" in text_lower or "handicap" in text_lower:
            result["disability_required"] = True

        # Residence
        if "rural" in text_lower and "urban" not in text_lower:
            result["residence_type"] = "Rural"
        elif "urban" in text_lower and "rural" not in text_lower:
            result["residence_type"] = "Urban"

        # Gender: word boundaries avoid false matches such as "government"
        # and "management". Deliberately avoid bare "man"/"men".
        if re.search(r"\b(woman|women|girl|female)\b", text_lower):
            result["gender"] = "Female"
        elif re.search(r"\b(male|ex-serviceman|serviceman)\b", text_lower):
            result["gender"] = "Male"

        return result

    # ── LLM extraction ────────────────────────────────────────────────────────

    def _llm_extract(self, scheme_name: str, eligibility_text: str) -> Dict[str, Any]:
        """Call Gemini via LangChain and parse the JSON response."""
        try:
            raw = self.chain.invoke({
                "scheme_name": scheme_name,
                "eligibility_text": eligibility_text,
            })
            # Strip any accidental markdown fences
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            data = json.loads(raw)
            # Ensure all required keys exist
            defaults = self._empty_eligibility()
            for k, v in defaults.items():
                if k not in data:
                    data[k] = v
            return data
        except json.JSONDecodeError as exc:
            logger.error(f"JSON parse error for scheme '{scheme_name}': {exc}")
            return self._empty_eligibility()
        except Exception as exc:
            logger.error(f"LLM extraction error for '{scheme_name}': {exc}")
            return self._empty_eligibility()

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(self, scheme: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured eligibility from a single raw scheme dict.
        Returns the original scheme merged with extracted fields.
        """
        eligibility_text = scheme.get("eligibility_text", "")
        scheme_name = scheme.get("scheme_name", "Unknown")

        if not eligibility_text.strip():
            logger.warning(f"Empty eligibility text for: {scheme_name}")
            extracted = self._empty_eligibility()
        elif self.chain:
            logger.info(f"LLM extracting: {scheme_name}")
            extracted = self._llm_extract(scheme_name, eligibility_text)
            time.sleep(1)  # Rate limiting
        else:
            logger.info(f"Rule-based extracting: {scheme_name}")
            extracted = self._rule_based_extract(scheme_name, eligibility_text)

        return {**scheme, **extracted}

    def extract_all(self, raw_schemes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract eligibility for a list of raw schemes and save to processed/."""
        processed = []
        total = len(raw_schemes)

        for i, scheme in enumerate(raw_schemes, 1):
            logger.info(f"Processing {i}/{total}: {scheme.get('scheme_name', 'Unknown')}")
            result = self.extract(scheme)
            processed.append(result)

        self._save(processed)
        return processed

    def _save(self, schemes: List[Dict[str, Any]]):
        out_path = PROCESSED_PATH / "schemes.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(schemes, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(schemes)} processed schemes → {out_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    raw_path = Path("data/raw/latest.json")
    if not raw_path.exists():
        print("❌ No raw data found. Run scraper.py first.")
        sys.exit(1)

    with open(raw_path, encoding="utf-8") as f:
        raw_schemes = json.load(f)

    extractor = EligibilityExtractor()
    processed = extractor.extract_all(raw_schemes)
    print(f"\n✅ Extracted eligibility for {len(processed)} schemes")
    print("\nSample output:")
    sample = processed[0]
    print(json.dumps({k: sample[k] for k in list(sample.keys())[:8]}, indent=2))
