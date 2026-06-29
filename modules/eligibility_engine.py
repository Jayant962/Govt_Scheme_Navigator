"""
modules/eligibility_engine.py

Deterministic Rule-Based Eligibility Engine.
NO LLM is used here. All checks are pure Python logic.

Scoring breakdown:
  Age               = 10 pts
  Income            = 20 pts
  State             = 10 pts
  District          =  5 pts
  Occupation        = 10 pts
  Education         = 10 pts
  Category          = 10 pts
  Residence         =  5 pts
  Special Conditions= 20 pts  (disability, minority, widow, ex-serviceman combined)
  ─────────────────────────
  Total             =100 pts
"""

from typing import Any, Dict, List, Tuple

# ── Education rank mapping ────────────────────────────────────────────────────

EDUCATION_RANK = {
    "illiterate": 0,
    "5th pass": 1,
    "8th pass": 2,
    "10th pass": 3,
    "12th pass": 4,
    "diploma": 5,
    "graduate": 6,
    "post graduate": 7,
    "phd": 8,
}


def _edu_rank(edu: str) -> int:
    if not edu:
        return -1
    return EDUCATION_RANK.get(edu.strip().lower(), -1)


# ── Main engine ───────────────────────────────────────────────────────────────

class EligibilityEngine:
    """
    Checks whether a user profile meets a scheme's eligibility criteria.
    Returns a score 0-100 and a list of match reasons.
    """

    MAX_SCORE = 100

    def check(
        self,
        user_profile: Dict[str, Any],
        scheme: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate eligibility for a single scheme.

        Returns:
            {
                "scheme_name": str,
                "scheme_id": int,
                "eligibility_score": int,     # 0-100
                "is_eligible": bool,          # True if score >= 60
                "match_reasons": [str, ...],
                "mismatch_reasons": [str, ...],
            }
        """
        score = 0
        match_reasons: List[str] = []
        mismatch_reasons: List[str] = []

        # ── 1. Age check (10 pts) ─────────────────────────────────────────────
        age = user_profile.get("age")
        min_age = scheme.get("min_age")
        max_age = scheme.get("max_age")

        if min_age is None and max_age is None:
            score += 10
            match_reasons.append("✅ No age restriction")
        elif age is not None:
            age_ok = True
            if min_age is not None and age < min_age:
                age_ok = False
            if max_age is not None and age > max_age:
                age_ok = False
            if age_ok:
                score += 10
                if min_age and max_age:
                    match_reasons.append(f"✅ Age {age} is within {min_age}–{max_age} years")
                elif min_age:
                    match_reasons.append(f"✅ Age {age} meets minimum age {min_age}")
                elif max_age:
                    match_reasons.append(f"✅ Age {age} is below maximum age {max_age}")
            else:
                if min_age and max_age:
                    mismatch_reasons.append(f"❌ Age {age} outside range {min_age}–{max_age}")
                elif min_age:
                    mismatch_reasons.append(f"❌ Age {age} below minimum {min_age}")
                elif max_age:
                    mismatch_reasons.append(f"❌ Age {age} exceeds maximum {max_age}")
        else:
            score += 5  # Partial: age not provided
            match_reasons.append("⚠️ Age not provided – assuming eligible")

        # ── 2. Income check (20 pts) ──────────────────────────────────────────
        income = user_profile.get("annual_income")
        income_limit = scheme.get("income_limit")

        if income_limit is None:
            score += 20
            match_reasons.append("✅ No income restriction")
        elif income is not None:
            if income <= income_limit:
                score += 20
                match_reasons.append(
                    f"✅ Income ₹{income:,} ≤ limit ₹{income_limit:,}"
                )
            else:
                mismatch_reasons.append(
                    f"❌ Income ₹{income:,} exceeds limit ₹{income_limit:,}"
                )
        else:
            score += 10
            match_reasons.append("⚠️ Income not provided – assuming eligible")

        # ── 3. State check (10 pts) ───────────────────────────────────────────
        user_state = user_profile.get("state", "")
        scheme_states = scheme.get("state", ["All"])

        if _is_all(scheme_states):
            score += 10
            match_reasons.append("✅ Open to all states")
        elif user_state and user_state in scheme_states:
            score += 10
            match_reasons.append(f"✅ State '{user_state}' matches")
        elif not user_state:
            score += 5
            match_reasons.append("⚠️ State not provided")
        else:
            mismatch_reasons.append(
                f"❌ State '{user_state}' not in eligible states: {', '.join(scheme_states)}"
            )

        # ── 4. District check (5 pts) ─────────────────────────────────────────
        user_district = user_profile.get("district", "")
        scheme_districts = scheme.get("district", ["All"])

        if _is_all(scheme_districts):
            score += 5
            match_reasons.append("✅ Open to all districts")
        elif user_district and user_district in scheme_districts:
            score += 5
            match_reasons.append(f"✅ District '{user_district}' matches")
        elif not user_district:
            score += 3
            match_reasons.append("⚠️ District not provided")
        else:
            mismatch_reasons.append(
                f"❌ District '{user_district}' not in eligible districts"
            )

        # ── 5. Occupation check (10 pts) ──────────────────────────────────────
        user_occ = user_profile.get("occupation", "")
        scheme_occs = scheme.get("occupation", ["All"])

        if _is_all(scheme_occs):
            score += 10
            match_reasons.append("✅ Open to all occupations")
        elif user_occ and any(user_occ.lower() == o.lower() for o in scheme_occs):
            score += 10
            match_reasons.append(f"✅ Occupation '{user_occ}' matches")
        elif not user_occ:
            score += 5
            match_reasons.append("⚠️ Occupation not provided")
        else:
            mismatch_reasons.append(
                f"❌ Occupation '{user_occ}' not in {', '.join(scheme_occs)}"
            )

        # ── 6. Education check (10 pts) ───────────────────────────────────────
        user_edu = user_profile.get("education", "")
        scheme_edu = scheme.get("education")

        if not scheme_edu:
            score += 10
            match_reasons.append("✅ No education requirement")
        elif user_edu:
            user_rank = _edu_rank(user_edu)
            scheme_rank = _edu_rank(scheme_edu)
            if user_rank >= scheme_rank:
                score += 10
                match_reasons.append(f"✅ Education '{user_edu}' meets requirement '{scheme_edu}'")
            else:
                mismatch_reasons.append(
                    f"❌ Education '{user_edu}' below required '{scheme_edu}'"
                )
        else:
            score += 5
            match_reasons.append("⚠️ Education not provided")

        # ── 7. Category check (10 pts) ────────────────────────────────────────
        user_cat = user_profile.get("category", "General")
        scheme_cats = scheme.get("category", ["All"])

        if _is_all(scheme_cats):
            score += 10
            match_reasons.append("✅ Open to all categories")
        elif user_cat and any(user_cat.upper() == c.upper() for c in scheme_cats):
            score += 10
            match_reasons.append(f"✅ Category '{user_cat}' is eligible")
        else:
            mismatch_reasons.append(
                f"❌ Category '{user_cat}' not in {', '.join(scheme_cats)}"
            )

        # ── 8. Residence type check (5 pts) ───────────────────────────────────
        user_res = user_profile.get("residence_type", "Both")
        scheme_res = scheme.get("residence_type", "Both")

        if scheme_res == "Both" or not scheme_res:
            score += 5
            match_reasons.append("✅ Open to rural and urban residents")
        elif user_res == scheme_res:
            score += 5
            match_reasons.append(f"✅ Residence type '{user_res}' matches")
        elif user_res == "Both":
            score += 3
            match_reasons.append(f"⚠️ Residence type unspecified")
        else:
            mismatch_reasons.append(
                f"❌ Residence '{user_res}' does not match requirement '{scheme_res}'"
            )

        # ── 9. Special conditions (20 pts combined) ───────────────────────────
        # Each condition: if scheme requires it, user must have it (hard gate)
        # If scheme does NOT require it, user still gets partial credit for matching
        special_score = 0
        MAX_SPECIAL = 20

        # Disability (5 pts)
        if scheme.get("disability_required"):
            if user_profile.get("is_disabled"):
                special_score += 5
                match_reasons.append("✅ Disability requirement met")
            else:
                mismatch_reasons.append("❌ Disability certificate required")
        else:
            special_score += 5  # No requirement → free points

        # Minority (5 pts)
        if scheme.get("minority_required"):
            if user_profile.get("is_minority"):
                special_score += 5
                match_reasons.append("✅ Minority community membership confirmed")
            else:
                mismatch_reasons.append("❌ Applicant must be from a minority community")
        else:
            special_score += 5

        # Widow (5 pts)
        if scheme.get("widow_required"):
            if user_profile.get("is_widow"):
                special_score += 5
                match_reasons.append("✅ Widow status confirmed")
            else:
                mismatch_reasons.append("❌ Scheme is only for widows")
        else:
            special_score += 5

        # Ex-Serviceman (5 pts)
        if scheme.get("ex_serviceman_required"):
            if user_profile.get("is_ex_serviceman"):
                special_score += 5
                match_reasons.append("✅ Ex-Serviceman status confirmed")
            else:
                mismatch_reasons.append("❌ Scheme is only for Ex-Servicemen")
        else:
            special_score += 5

        score += special_score

        # ── Gender check ──────────────────────────────────────────────────────
        user_gender = user_profile.get("gender", "Other")
        scheme_gender = scheme.get("gender", "Any")
        gender_hard_fail = False
        if scheme_gender not in ("Any", None, ""):
            if user_gender.lower() != scheme_gender.lower():
                mismatch_reasons.append(
                    f"❌ Scheme is for {scheme_gender} applicants only"
                )
                score = max(0, score - 20)
                gender_hard_fail = True

        # ── Final result ──────────────────────────────────────────────────────
        score = min(score, self.MAX_SCORE)
        
        # A hard gender mismatch always marks ineligible, even if score >= 60
        is_eligible = (score >= 60) and not gender_hard_fail

        # ── Final result ──────────────────────────────────────────────────────
        score = min(score, self.MAX_SCORE)

        return {
            "scheme_id": scheme.get("scheme_id"),
            "scheme_name": scheme.get("scheme_name", ""),
            "description": scheme.get("description", ""),
            "benefits": scheme.get("benefits", ""),
            "source_url": scheme.get("source_url", ""),
            "application_link": scheme.get("application_link", ""),
            "eligibility_score": score,
             "is_eligible": is_eligible,
            "match_reasons": match_reasons,
            "mismatch_reasons": mismatch_reasons,
        }

    def check_all(
        self,
        user_profile: Dict[str, Any],
        schemes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Check eligibility for all schemes and return results."""
        results = []
        for scheme in schemes:
            result = self.check(user_profile, scheme)
            results.append(result)
        return results


# ── Helper ────────────────────────────────────────────────────────────────────

def _is_all(values: List[str]) -> bool:
    """Check if a scheme field is unrestricted (contains 'All' or is empty)."""
    if not values:
        return True
    return any(v.strip().lower() == "all" for v in values)
