import os
import requests
from groq import Groq
from fastapi import HTTPException
from typing import List

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Chat feature is not configured. GROQ_API_KEY is missing."
        )
    return Groq(api_key=api_key)

# Maximum context size (in characters) - Groq free tier has 12k TPM limit
# ~4 chars per token, leaving room for response = ~28k chars max
MAX_CONTEXT_CHARS = 28000

def extract_mentioned_files(question: str, available_files: List[str]) -> List[str]:
    """Extract file names mentioned in the user's question."""
    mentioned = []
    question_lower = question.lower()

    for file_path in available_files:
        file_name = file_path.split('/')[-1].lower()
        file_stem = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name

        # Check if file name or stem is mentioned
        if file_name in question_lower or file_stem in question_lower:
            mentioned.append(file_path)
        # Also check for partial path matches
        elif any(part.lower() in question_lower for part in file_path.split('/')):
            mentioned.append(file_path)

    return mentioned

def prioritize_files(files: dict, key_files: List[str], entry_points: List[str], mentioned: List[str]) -> List[str]:
    """Prioritize files for inclusion in context."""
    priority_order = []
    seen = set()

    # 1. First add mentioned files (highest priority)
    for f in mentioned:
        if f not in seen and f in files:
            priority_order.append(f)
            seen.add(f)

    # 2. Add entry points
    for f in entry_points:
        if f not in seen and f in files:
            priority_order.append(f)
            seen.add(f)

    # 3. Add key files
    for f in key_files:
        if f not in seen and f in files:
            priority_order.append(f)
            seen.add(f)

    # 4. Add remaining files sorted by importance (classes + functions count)
    remaining = []
    for path, info in files.items():
        if path not in seen:
            score = len(info.get('functions', [])) + len(info.get('classes', [])) * 2
            remaining.append((path, score))

    remaining.sort(key=lambda x: x[1], reverse=True)
    for path, _ in remaining:
        priority_order.append(path)

    return priority_order

def fetch_file_content(repo_url: str, default_branch: str, file_path: str) -> str:
    """Fetch file content directly from GitHub."""
    if not repo_url or not repo_url.startswith("https://github.com/"):
        return ""
        
    parts = repo_url.rstrip('/').split('/')
    if len(parts) < 2:
        return ""
        
    owner, repo = parts[-2], parts[-1]
    if repo.endswith('.git'):
        repo = repo[:-4]
        
    branch = default_branch or "main"
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
    
    try:
        resp = requests.get(raw_url, timeout=5.0)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"Failed to fetch {file_path}: {e}")
        
    return ""

def build_context(analysis_data: dict, question: str = "", max_code_files: int = 6) -> str:
    """Build a comprehensive context string including actual code for the LLM."""
    if not analysis_data:
        return "No analysis data available. The user should analyze the repository first."

    context_parts = []
    current_size = 0

    # Determine format (streaming vs old)
    is_streaming = isinstance(analysis_data, dict) and "repoMeta" in analysis_data
    
    if is_streaming:
        repo_meta = analysis_data.get("repoMeta") or {}
        repo_url = repo_meta.get("url", "Unknown")
        default_branch = repo_meta.get("default_branch", "main")
        
        quickstart = analysis_data.get("quickstart") or {}
        readme_raw = quickstart.get("readme", "")
        # readme can be a dict {content, filename} or a plain string
        if isinstance(readme_raw, dict):
            readme = readme_raw.get("content", "")
        else:
            readme = readme_raw or ""
        
        languages = analysis_data.get("languages") or {}
        frameworks_dict = analysis_data.get("frameworks") or {}
        frontend = frameworks_dict.get("frontend", []) if isinstance(frameworks_dict, dict) else []
        backend = frameworks_dict.get("backend", []) if isinstance(frameworks_dict, dict) else []
        databases = analysis_data.get("databases") or []
        entry_points = analysis_data.get("entryPoints") or []
        key_files = analysis_data.get("keyFiles") or []
        dependencies = analysis_data.get("dependencies") or {}
        
        # files mapping
        files = {}
        complexity = analysis_data.get("complexity") or {}
        for f in complexity.get("fileList", []):
            files[f["file"]] = {
                "functions": f.get("functions", []),
                "classes": f.get("classes", [])
            }
    else:
        structure = analysis_data.get("structure_analysis", {})
        repo_url = analysis_data.get("repository_url", "Unknown")
        default_branch = "main"
        readme = structure.get("readme", {}).get("content", "")
        languages = structure.get("languages", {})
        frameworks_dict = structure.get("frameworks", {})
        frontend = frameworks_dict.get("frontend", []) if isinstance(frameworks_dict, dict) else []
        backend = frameworks_dict.get("backend", []) if isinstance(frameworks_dict, dict) else []
        databases = structure.get("databases", [])
        entry_points = structure.get("entry_points", [])
        key_files = structure.get("key_files", [])
        dependencies = structure.get("dependencies", {})
        files = structure.get("files", {})

    # Repository overview
    context_parts.append(f"# Repository: {repo_url}\n")

    # README content (very important for understanding the project)
    if readme and isinstance(readme, str):
        readme_content = readme[:5000]  # Limit README size
        context_parts.append(f"## README\n```\n{readme_content}\n```\n")

    # Languages
    if languages:
        lang_summary = ", ".join([f"{lang} ({info.get('count', 0)} files)" for lang, info in languages.items()])
        context_parts.append(f"## Languages\n{lang_summary}\n")

    # Frameworks
    if frontend or backend:
        if frontend:
            context_parts.append(f"**Frontend:** {', '.join(frontend)}")
        if backend:
            context_parts.append(f"**Backend:** {', '.join(backend)}")
        context_parts.append("")

    # Databases
    if databases:
        context_parts.append(f"**Databases:** {', '.join(databases)}\n")

    # Dependencies summary
    if dependencies:
        context_parts.append("## Dependencies")
        for dep_type, deps in dependencies.items():
            if isinstance(deps, dict) and deps:
                for source, dep_list in deps.items():
                    if dep_list:
                        context_parts.append(f"**{source}:** {', '.join(dep_list[:20])}")
        context_parts.append("")

    if not files:
        return "\n".join(context_parts)

    # Determine which files to include with full code
    mentioned_files = extract_mentioned_files(question, list(files.keys()))
    prioritized = prioritize_files(files, key_files, entry_points, mentioned_files)

    # Calculate current context size
    current_size = sum(len(p) for p in context_parts)

    # Add file structure overview first
    context_parts.append("## File Structure Overview")
    for file_path, info in list(files.items())[:50]:  # Show up to 50 files
        functions = info.get("functions", [])
        classes = info.get("classes", [])
        summary = []
        if classes:
            summary.append(f"classes: {', '.join(classes[:5])}")
        if functions:
            summary.append(f"functions: {', '.join(functions[:8])}")
        if summary:
            context_parts.append(f"- **{file_path}**: {'; '.join(summary)}")
        else:
            context_parts.append(f"- {file_path}")

    if len(files) > 50:
        context_parts.append(f"- ... and {len(files) - 50} more files")
    context_parts.append("")

    # Now include actual source code for prioritized files
    context_parts.append("## Source Code\n")

    files_included = 0
    for file_path in prioritized:
        if files_included >= max_code_files:
            break

        info = files.get(file_path, {})
        content = info.get("content", "")
        
        if not content and is_streaming:
            content = fetch_file_content(repo_url, default_branch, file_path)

        if not content:
            continue

        # Check if we have room for this file
        file_header = f"### {file_path}\n"
        language = info.get('language', '').lower().split()[0] if info.get('language') else ''
        file_block = f"```{language}\n{content}\n```\n\n"

        new_size = current_size + len(file_header) + len(file_block)
        if new_size > MAX_CONTEXT_CHARS:
            # Try with truncated content
            max_content = MAX_CONTEXT_CHARS - current_size - len(file_header) - 100
            if max_content > 500:  # Only include if we can show at least 500 chars
                truncated = content[:max_content] + "\n... [truncated]"
                file_block = f"```{language}\n{truncated}\n```\n\n"
                context_parts.append(file_header)
                context_parts.append(file_block)
                files_included += 1
            break

        context_parts.append(file_header)
        context_parts.append(file_block)
        current_size = new_size
        files_included += 1

    if files_included < len(prioritized):
        remaining = len(prioritized) - files_included
        context_parts.append(f"*({remaining} more files not shown due to context limits)*\n")

    return "\n".join(context_parts)

def chat_about_repo(question: str, analysis_data: dict, chat_history: list = None) -> str:
    """Chat with the LLM about the repository."""
    client = get_groq_client()

    # Build context from analysis, including the question for better file prioritization
    context = build_context(analysis_data, question=question)

    # System prompt
    system_prompt = f"""You are an expert code analyst helping users understand a GitHub repository. You have access to the repository's actual source code, structure, and documentation.

{context}

## Your Capabilities
- You can see and analyze the actual source code of key files in this repository
- You understand the project structure, frameworks, and dependencies
- You can explain how specific functions, classes, and modules work
- You can answer questions about syntax, implementation details, and code patterns
- You can trace how different parts of the code interact with each other

## Guidelines
1. **Be specific**: Reference exact file names, function names, and line-level details when relevant
2. **Show code snippets**: When explaining code, quote relevant portions to illustrate your points
3. **Explain the "why"**: Don't just describe what code does, explain design decisions when apparent
4. **Be honest about limitations**: If a file's content wasn't included or was truncated, say so
5. **Connect the dots**: Help users understand how different parts of the codebase work together
6. **Answer authoritatively**: You have the actual code - use it to give definitive answers, not guesses

If a user asks about a specific file that isn't shown in the source code section above, let them know that file's content wasn't included in the current context, but offer to describe what you can infer from the file structure and imports.
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
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except Exception as e:
        error_msg = str(e)
        error_lower = error_msg.lower()

        # Log the actual error for debugging
        print(f"Chat API Error: {error_msg}")

        # Check for specific Groq error attributes first
        status_code = getattr(e, 'status_code', None)

        # Request too large (413) - context exceeds token limit
        if status_code == 413 or "request too large" in error_lower or "reduce your message size" in error_lower:
            raise HTTPException(
                status_code=400,
                detail="The repository context is too large. Try asking about specific files."
            )
        # Rate limit error - too many requests
        elif status_code == 429 or ("rate_limit" in error_lower and "request too large" not in error_lower):
            raise HTTPException(
                status_code=429,
                detail="Rate limit reached. Please wait a moment and try again."
            )
        # API key issues
        elif status_code == 401 or "invalid_api_key" in error_lower or "invalid api key" in error_lower:
            raise HTTPException(
                status_code=401,
                detail="AI service authentication failed. Please check the API key."
            )
        # Model not available
        elif "model_not_found" in error_lower or "model not found" in error_lower or "does not exist" in error_lower:
            raise HTTPException(
                status_code=503,
                detail="AI model temporarily unavailable. Please try again later."
            )
        # Context too long - be more specific
        elif "context_length_exceeded" in error_lower or "maximum context length" in error_lower or "too many tokens" in error_lower:
            raise HTTPException(
                status_code=400,
                detail="The repository is too large to analyze in chat. Try asking about specific files."
            )
        # Service unavailable
        elif status_code == 503 or "service_unavailable" in error_lower or "service unavailable" in error_lower:
            raise HTTPException(
                status_code=503,
                detail="AI service is temporarily unavailable. Please try again later."
            )
        # Generic error - include actual message for debugging
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Chat failed: {error_msg[:200]}"
            )
