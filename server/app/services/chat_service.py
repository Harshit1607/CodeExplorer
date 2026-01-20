import os
from groq import Groq
from fastapi import HTTPException

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Chat feature is not configured. GROQ_API_KEY is missing."
        )
    return Groq(api_key=api_key)

def build_context(analysis_data: dict, max_files: int = 10) -> str:
    """Build a context string from the analysis data for the LLM."""
    context_parts = []

    structure = analysis_data.get("structure_analysis", {})

    # Repository overview
    repo_url = analysis_data.get("repository_url", "Unknown")
    context_parts.append(f"Repository: {repo_url}")

    # Languages
    languages = structure.get("languages", {})
    if languages:
        lang_summary = ", ".join([f"{lang} ({info.get('count', 0)} files)" for lang, info in languages.items()])
        context_parts.append(f"Languages: {lang_summary}")

    # Frameworks
    frameworks = structure.get("frameworks", {})
    if frameworks:
        frontend = frameworks.get("frontend", [])
        backend = frameworks.get("backend", [])
        if frontend:
            context_parts.append(f"Frontend frameworks: {', '.join(frontend)}")
        if backend:
            context_parts.append(f"Backend frameworks: {', '.join(backend)}")

    # Entry points
    entry_points = structure.get("entry_points", [])
    if entry_points:
        context_parts.append(f"Entry points: {', '.join(entry_points[:5])}")

    # Key files
    key_files = structure.get("key_files", [])
    if key_files:
        context_parts.append(f"Key files: {', '.join(key_files[:10])}")

    # File structure with functions and classes
    files = structure.get("files", {})
    if files:
        context_parts.append("\nFile details:")
        file_count = 0
        for file_path, info in files.items():
            if file_count >= max_files:
                context_parts.append(f"... and {len(files) - max_files} more files")
                break

            file_info = [f"  - {file_path}"]

            functions = info.get("functions", [])
            if functions:
                file_info.append(f"    Functions: {', '.join(functions[:10])}")

            classes = info.get("classes", [])
            if classes:
                file_info.append(f"    Classes: {', '.join(classes[:10])}")

            imports = info.get("imports", [])
            if imports:
                file_info.append(f"    Imports: {', '.join(imports[:10])}")

            context_parts.append("\n".join(file_info))
            file_count += 1

    # Dependencies
    dependencies = structure.get("dependencies", {})
    if dependencies:
        context_parts.append("\nDependencies:")
        for dep_type, deps in dependencies.items():
            if isinstance(deps, dict) and deps:
                dep_list = list(deps.keys())[:15]
                context_parts.append(f"  {dep_type}: {', '.join(dep_list)}")

    return "\n".join(context_parts)

def chat_about_repo(question: str, analysis_data: dict, chat_history: list = None) -> str:
    """Chat with the LLM about the repository."""
    client = get_groq_client()

    # Build context from analysis
    context = build_context(analysis_data)

    # System prompt
    system_prompt = f"""You are a helpful coding assistant that answers questions about a GitHub repository.
You have access to the following analysis of the repository:

{context}

Guidelines:
- Answer questions based on the repository structure and code analysis provided
- Be concise but helpful
- If you don't have enough information to answer, say so
- Reference specific files, functions, or classes when relevant
- Help users understand how the codebase is organized and how different parts work together
"""

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]

    # Add chat history if provided
    if chat_history:
        for msg in chat_history[-10:]:  # Limit to last 10 messages
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

    # Add current question
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Better quality, still free tier friendly
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except Exception as e:
        error_msg = str(e).lower()

        # Rate limit error
        if "rate_limit" in error_msg or "rate limit" in error_msg or "429" in error_msg:
            raise HTTPException(
                status_code=429,
                detail="Rate limit reached. Please wait a moment and try again."
            )
        # API key issues
        elif "invalid_api_key" in error_msg or "authentication" in error_msg or "401" in error_msg:
            raise HTTPException(
                status_code=401,
                detail="AI service authentication failed. Please contact support."
            )
        # Model not available
        elif "model_not_found" in error_msg or "model not found" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="AI model temporarily unavailable. Please try again later."
            )
        # Context too long
        elif "context_length" in error_msg or "too long" in error_msg or "token" in error_msg:
            raise HTTPException(
                status_code=400,
                detail="The repository is too large to analyze in chat. Try asking about specific files."
            )
        # Service unavailable
        elif "service_unavailable" in error_msg or "503" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="AI service is temporarily unavailable. Please try again later."
            )
        # Generic error
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to get AI response. Please try again."
            )
