"""
modules/ranking_engine.py

Ranking Engine:
Sorts eligibility results by score (descending) and returns top-N.
Supports secondary sort by benefit richness (description length proxy).
"""

from typing import Any, Dict, List, Optional


class RankingEngine:
    """
    Takes a list of eligibility results (from EligibilityEngine) and ranks them.

    Primary sort  : eligibility_score descending
    Secondary sort: description + benefits text length (richer scheme = higher rank on tie)
    """

    def rank(
        self,
        eligibility_results: List[Dict[str, Any]],
        top_n: Optional[int] = None,
        eligible_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Rank and optionally filter eligibility results.

        Args:
            eligibility_results: Output from EligibilityEngine.check_all()
            top_n: Return only the top-N results (None = all)
            eligible_only: If True, filter out schemes with is_eligible=False

        Returns:
            Sorted list of result dicts with added 'rank' field.
        """
        results = list(eligibility_results)

        if eligible_only:
            results = [r for r in results if r.get("is_eligible", False)]

        # Primary: score DESC; secondary: text richness DESC
        results.sort(
            key=lambda r: (
                r.get("eligibility_score", 0),
                len(r.get("description", "")) + len(r.get("benefits", "")),
            ),
            reverse=True,
        )

        # Add rank field
        for i, result in enumerate(results, 1):
            result["rank"] = i

        if top_n is not None:
            results = results[:top_n]

        return results

    def get_top_n(
        self,
        eligibility_results: List[Dict[str, Any]],
        n: int = 10,
    ) -> List[Dict[str, Any]]:
        """Convenience: return top-N eligible schemes."""
        return self.rank(eligibility_results, top_n=n, eligible_only=False)

    def get_stats(self, eligibility_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute summary statistics over eligibility results."""
        if not eligibility_results:
            return {
                "total_schemes": 0,
                "eligible_count": 0,
                "highest_score": 0,
                "average_score": 0.0,
                "score_distribution": {},
            }

        scores = [r.get("eligibility_score", 0) for r in eligibility_results]
        eligible = [r for r in eligibility_results if r.get("is_eligible", False)]

        # Score bands
        distribution = {
            "90-100": sum(1 for s in scores if s >= 90),
            "70-89":  sum(1 for s in scores if 70 <= s < 90),
            "50-69":  sum(1 for s in scores if 50 <= s < 70),
            "Below 50": sum(1 for s in scores if s < 50),
        }

        return {
            "total_schemes": len(eligibility_results),
            "eligible_count": len(eligible),
            "highest_score": max(scores),
            "average_score": round(sum(scores) / len(scores), 1),
            "score_distribution": distribution,
        }
