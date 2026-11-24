import os
import json
from groq import AsyncGroq
from fastapi import HTTPException
from typing import Dict, Any, List, Optional

from app.core import config
from app.services.llm import completion_kwargs, groq_api_key, map_llm_error
from app.services.report_grounding import ReportGrounding, check_citations

def get_groq_client():
    api_key = groq_api_key()
    if not api_key:
        return None
    return AsyncGroq(api_key=api_key)

class AIAnalyzer:
    def __init__(self, analysis_data: Dict[str, Any], grounding: Optional[ReportGrounding] = None):
        self.data = analysis_data
        self.client = get_groq_client()
        # Code excerpts (with path/line headers) retrieved from the repository; see report_grounding.py
        self.grounding = grounding or ReportGrounding("")

    async def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive AI report about the repository."""
        if not self.client:
            return {"error": "AI service not configured (GROQ_API_KEY missing)"}

        # Build a condensed context for the report
        context = self._build_condensed_context()
        prompt = self._build_prompt(context)

        try:
            response = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a senior software architect. Explain codebases using only the repository data you are given, citing the code you rely on."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                **completion_kwargs(max_tokens=2500, temperature=0.2),
            )
            
            report = json.loads(response.choices[0].message.content)
            if not isinstance(report, dict):
                raise ValueError("the model did not return a JSON object")
            return self._attach_grounding(report)
        except Exception as e:
            print(f"AI Analysis Error: {e!r}")
            return {"error": f"Failed to generate AI report: {map_llm_error(e).detail}"}

    def _build_prompt(self, context: str) -> str:
        code = self.grounding.context
        if code:
            code_block = ("CODE EXCERPTS (retrieved from the repository; each header gives the file path and its line range):\n"
                          f"{code}")
            grounding_rules = """- Base every claim on the metadata and code excerpts above. Do not describe files, functions or behaviour that appear in neither.
- Cite the code you rely on as `path:start-end` (or `path:line`), using the exact paths and line numbers from the excerpt headers. Every section must contain at least one such citation.
- The excerpts are a selection, not the whole repository. If a section needs code that is not shown (for example the next step of a call chain), say which file or symbol is missing instead of guessing."""
        else:
            code_block = "CODE EXCERPTS: none were available for this repository, so only the metadata above is known."
            grounding_rules = """- Base every claim on the metadata above only. Do not describe code you have not been shown; say plainly where the metadata is not enough.
- Do not invent line numbers or file:line citations."""

        return f"""You are a world-class senior software architect. Write an architectural report about this repository from the repository metadata and code excerpts below. Use general engineering knowledge only to explain what this data shows, never to fill in what it does not show.

METADATA:
{context}

{code_block}

GOAL:
Provide insights that help a developer actually understand the system. Avoid generic corporate speak. Be technical and specific. Reference actual file names and directory paths.

FORMAT YOUR RESPONSE AS JSON with these keys:
1. "architecture_summary": A deep-dive into the system's design. How do the components interact? What are the core patterns (e.g., MVC, Layered, Hexagonal)? Mention specific entry point files.
2. "module_breakdown": An array of strings. Each string must be a concise explanation of a major directory and its responsibility. Example: ["server/api: Handles HTTP routing and validation using FastAPI", "client/src/hooks: Shared React state logic"].
3. "tech_stack_rationale": Analyze the combination of languages and libraries found. Why was this mix used? (e.g., "Python for heavy ML processing paired with a React frontend for visualization").
4. "entry_point_deep_dive": Trace the flow from the main entry points as far as the excerpts show. Which file initializes the system? What is the next step in the execution chain?
5. "onboarding_advice": A list of 3-5 concrete steps a new developer should take to set up their environment and make their first change in THIS specific codebase.

STRICT REQUIREMENTS:
- Values must be strings or arrays of strings. 
- NO nested objects.
- NO placeholders like "[object Object]".
{grounding_rules}
"""

    def _attach_grounding(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Add the excerpts the report was written from and which of its citations point into them."""
        sources = self.grounding.sources
        report["sources"] = sources
        report["grounding"] = {**self.grounding.info(), "model": config.GROQ_MODEL,
                               **check_citations(report, sources)}
        return report

    def _build_condensed_context(self) -> str:
        """Build a high-quality summary of the repo for the LLM."""
        repo_meta = self.data.get("repoMeta", {})
        languages = self.data.get("languages", {})
        frameworks = self.data.get("frameworks", {})
        databases = self.data.get("databases", [])
        entry_points = self.data.get("entryPoints", [])
        
        # Get top files by complexity
        file_list = self.data.get("complexity", {}).get("fileList", [])
        top_files = sorted(file_list, key=lambda x: x.get("lines", 0), reverse=True)[:20]
        
        # Get dependency summary (who depends on whom)
        file_deps = self.data.get("file_dependencies", {})
        dep_summary = []
        for file, deps in list(file_deps.items())[:15]:
            resolved = deps.get("resolved", [])
            if resolved:
                dep_summary.append(f"{file} -> {', '.join(resolved[:5])}")

        context = {
            "name": repo_meta.get("name"),
            "languages": list(languages.keys()),
            "frameworks": frameworks,
            "databases": databases,
            "entry_points": entry_points,
            "architecture_hints": dep_summary,
            "core_files": [
                {
                    "path": f["file"],
                    "exports": f.get("functions", [])[:5] + f.get("classes", [])[:3]
                } for f in top_files
            ]
        }
        
        # Safely extract readme content (more of it)
        readme = self.data.get("quickstart", {}).get("readme")
        readme_text = ""
        if isinstance(readme, dict):
            readme_text = readme.get("content", "")
        elif isinstance(readme, str):
            readme_text = readme
            
        context["readme_preview"] = readme_text[:3000] # Increased for better context
        
        return json.dumps(context, indent=2)
