import re

with open("api/routes.py", "r") as f:
    content = f.read()

# 1. Imports
content = content.replace(
    "from fastapi import APIRouter, HTTPException",
    "import collections\nfrom fastapi import APIRouter, HTTPException, Header"
)

# 2. History & Settings
old_history = """HISTORY_FILE = "data/history.json"
_analyses: dict[str, AnalysisResponse] = {}

def _load_history():
    global _analyses
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    _analyses[k] = AnalysisResponse(**v)
        except Exception as e:
            logger.error(f"Failed to load history: {e}")

def _save_history():
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w") as f:
            json.dump({k: v.model_dump(mode="json") for k, v in _analyses.items()}, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")

_load_history()"""

new_history = """_analyses: dict[str, dict[str, AnalysisResponse]] = collections.defaultdict(dict)

def _get_history_file(user_id: str) -> str:
    safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_") or "default"
    return f"data/history_{safe_id}.json"

def _load_history(user_id: str):
    file_path = _get_history_file(user_id)
    if os.path.exists(file_path) and not _analyses.get(user_id):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    _analyses[user_id][k] = AnalysisResponse(**v)
        except Exception as e:
            logger.error(f"Failed to load history for {user_id}: {e}")

def _save_history(user_id: str):
    try:
        os.makedirs("data", exist_ok=True)
        file_path = _get_history_file(user_id)
        with open(file_path, "w") as f:
            json.dump({k: v.model_dump(mode="json") for k, v in _analyses[user_id].items()}, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save history for {user_id}: {e}")

def _get_settings_file(user_id: str) -> str:
    safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_") or "default"
    return f"data/settings_{safe_id}.json"

def _get_user_settings(user_id: str) -> dict:
    file_path = _get_settings_file(user_id)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_user_settings(user_id: str, settings: dict):
    os.makedirs("data", exist_ok=True)
    with open(_get_settings_file(user_id), "w") as f:
        json.dump(settings, f, indent=2)"""

content = content.replace(old_history, new_history)

# 3. submit_analysis
old_submit = """@router.post("/analyze", response_model=AnalysisResponse)
async def submit_analysis(request: AnalyzeRequest):"""
new_submit = """@router.post("/analyze", response_model=AnalysisResponse)
async def submit_analysis(request: AnalyzeRequest, x_user_id: str = Header(default="anonymous")):
    _load_history(x_user_id)"""
content = content.replace(old_submit, new_submit)

content = content.replace("_analyses[analysis_id] = response\n    _save_history()", "_analyses[x_user_id][analysis_id] = response\n    _save_history(x_user_id)")
content = content.replace("asyncio.create_task(_run_analysis(analysis_id, request.pr_url))", "asyncio.create_task(_run_analysis(x_user_id, analysis_id, request.pr_url))")


# 4. get_analysis
old_get = """@router.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: str):
    \"\"\"Get the status and results of an analysis.\"\"\"
    if analysis_id not in _analyses:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _analyses[analysis_id]"""

new_get = """@router.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: str, x_user_id: str = Header(default="anonymous")):
    \"\"\"Get the status and results of an analysis.\"\"\"
    _load_history(x_user_id)
    if analysis_id not in _analyses[x_user_id]:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _analyses[x_user_id][analysis_id]"""
content = content.replace(old_get, new_get)

# 5. list_analyses
old_list = """@router.get("/analyses", response_model=list[AnalysisResponse])
async def list_analyses():
    \"\"\"List all analyses, most recent first.\"\"\"
    return sorted(
        _analyses.values(),
        key=lambda a: a.created_at,
        reverse=True,
    )"""
new_list = """@router.get("/analyses", response_model=list[AnalysisResponse])
async def list_analyses(x_user_id: str = Header(default="anonymous")):
    \"\"\"List all analyses, most recent first.\"\"\"
    _load_history(x_user_id)
    return sorted(
        _analyses[x_user_id].values(),
        key=lambda a: a.created_at,
        reverse=True,
    )"""
content = content.replace(old_list, new_list)


# 6. health check
content = content.replace("len(_analyses),", "sum(len(user_analyses) for user_analyses in _analyses.values()),")


# 7. settings
old_settings = """@router.get("/settings")
async def get_settings():
    \"\"\"Get non-sensitive parts of settings.\"\"\"
    return {
        "github_token_set": bool(os.getenv("GITHUB_TOKEN")),
        "llm_api_key_set": bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")),
        "llm_model": os.getenv("LLM_MODEL", "gemini-2.5-flash"),
    }


@router.post("/settings")
async def update_settings(settings: SettingsUpdate):
    \"\"\"Update settings in .env file (very simple implementation).\"\"\"
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    
    # Read current
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
            
    # Helper to update
    def update_key(key: str, val: str):
        if not val:
            return
        os.environ[key] = val
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={val}\\n"
                return
        lines.append(f"{key}={val}\\n")

    update_key("GITHUB_TOKEN", settings.github_token)
    update_key("LLM_API_KEY", settings.llm_api_key)
    update_key("LLM_MODEL", settings.llm_model)

    with open(env_path, "w") as f:
        f.writelines(lines)

    return {"status": "success"}"""

new_settings = """@router.get("/settings")
async def get_settings(x_user_id: str = Header(default="anonymous")):
    \"\"\"Get non-sensitive parts of settings.\"\"\"
    user_settings = _get_user_settings(x_user_id)
    return {
        "github_token_set": bool(user_settings.get("github_token") or os.getenv("GITHUB_TOKEN")),
        "llm_api_key_set": bool(user_settings.get("llm_api_key") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")),
        "llm_model": user_settings.get("llm_model") or os.getenv("LLM_MODEL", "gemini-2.5-flash"),
    }


@router.post("/settings")
async def update_settings(settings: SettingsUpdate, x_user_id: str = Header(default="anonymous")):
    \"\"\"Update user-specific settings.\"\"\"
    current = _get_user_settings(x_user_id)
    if settings.github_token is not None:
        current["github_token"] = settings.github_token
    if settings.llm_api_key is not None:
        current["llm_api_key"] = settings.llm_api_key
    if settings.llm_model is not None:
        current["llm_model"] = settings.llm_model
        
    _save_user_settings(x_user_id, current)
    return {"status": "success"}"""
content = content.replace(old_settings, new_settings)


# 8. _run_analysis
old_run = """async def _run_analysis(analysis_id: str, pr_url: str):
    \"\"\"Background task: fetch data, run agents, aggregate verdict.\"\"\"
    orchestrator = _get_orchestrator()
    start_time = time.time()

    try:
        # Step 1: Fetch GitHub data
        _analyses[analysis_id].status = AnalysisStatus.FETCHING
        logger.info(f"[{analysis_id}] Fetching PR data from GitHub...")

        github = GitHubService()"""

new_run = """async def _run_analysis(user_id: str, analysis_id: str, pr_url: str):
    \"\"\"Background task: fetch data, run agents, aggregate verdict.\"\"\"
    orchestrator = _get_orchestrator()
    start_time = time.time()
    
    settings = _get_user_settings(user_id)
    github_token = settings.get("github_token") or os.getenv("GITHUB_TOKEN", "")

    try:
        # Step 1: Fetch GitHub data
        _analyses[user_id][analysis_id].status = AnalysisStatus.FETCHING
        logger.info(f"[{analysis_id}] Fetching PR data from GitHub for user {user_id}...")

        github = GitHubService(token=github_token)"""

content = content.replace(old_run, new_run)

# Replace all remaining `_analyses[analysis_id]` with `_analyses[user_id][analysis_id]` in _run_analysis
def replace_analyses(match):
    return match.group(0).replace("_analyses[analysis_id]", "_analyses[user_id][analysis_id]")

# Since we only want to replace inside _run_analysis, let's just do a string replace after the point where _run_analysis starts.
start_idx = content.find("def _run_analysis")
if start_idx != -1:
    before = content[:start_idx]
    after = content[start_idx:]
    after = after.replace("_analyses[analysis_id]", "_analyses[user_id][analysis_id]")
    after = after.replace("_save_history()", "_save_history(user_id)")
    content = before + after

with open("api/routes.py", "w") as f:
    f.write(content)

