import os
import json
from groq import AsyncGroq
from fastapi import HTTPException
from typing import Dict, Any, List

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    return AsyncGroq(api_key=api_key)

class AIAnalyzer:
    def __init__(self, analysis_data: Dict[str, Any]):
        self.data = analysis_data
        self.client = get_groq_client()

    async def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive AI report about the repository."""
        if not self.client:
            return {"error": "AI service not configured (GROQ_API_KEY missing)"}

        # Build a condensed context for the report
        context = self._build_condensed_context()
        
        prompt = f"""You are a world-class senior software architect. Analyze the following repository metadata and provide a deep, actionable architectural report.

CONTEXT:
{context}

GOAL:
Provide insights that help a developer actually understand the system. Avoid generic corporate speak. Be technical and specific. Reference actual file names and directory paths from the context.

FORMAT YOUR RESPONSE AS JSON with these keys:
1. "architecture_summary": A deep-dive into the system's design. How do the components interact? What are the core patterns (e.g., MVC, Layered, Hexagonal)? Mention specific entry point files.
2. "module_breakdown": An array of strings. Each string must be a concise explanation of a major directory and its responsibility. Example: ["server/api: Handles HTTP routing and validation using FastAPI", "client/src/hooks: Shared React state logic"].
3. "tech_stack_rationale": Analyze the combination of languages and libraries found. Why was this mix used? (e.g., "Python for heavy ML processing paired with a React frontend for visualization").
4. "entry_point_deep_dive": Trace the flow from the main entry points. Which file initializes the system? What is the next step in the execution chain?
5. "onboarding_advice": A list of 3-5 concrete steps a new developer should take to set up their environment and make their first change in THIS specific codebase.

STRICT REQUIREMENTS:
- Values must be strings or arrays of strings. 
- NO nested objects.
- NO placeholders like "[object Object]".
- Reference real filenames from the context.
"""

        try:
            response = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a senior software architect. Provide a technical, objective, and insightful analysis of codebases."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, # Lower temperature for more factual output
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"AI Analysis Error: {e}")
            return {"error": f"Failed to generate AI report: {str(e)}"}

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
