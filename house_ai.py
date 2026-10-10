import os
import aiohttp

async def _ollama(prompt: str) -> str:
    base=os.getenv("OLLAMA_BASE_URL","http://localhost:11434").rstrip("/")
    model=os.getenv("OLLAMA_MODEL","llama3.1")
    timeout=aiohttp.ClientTimeout(total=float(os.getenv("AI_TIMEOUT_SECONDS","25")))
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(base+"/api/chat",json={"model":model,"messages":[{"role":"user","content":prompt}],"stream":False}) as r:
            r.raise_for_status()
            data=await r.json()
            answer=data.get("message",{}).get("content","").strip()
            if not answer: raise RuntimeError("Ollama lieferte eine leere Antwort")
            return answer

async def _gemini(prompt: str) -> str:
    key=os.getenv("GEMINI_API_KEY","").strip()
    if not key: raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt")
    from google import genai
    client=genai.Client(api_key=key)
    response=await client.aio.models.generate_content(
        model=os.getenv("GEMINI_MODEL","gemini-2.5-flash"),
        contents=prompt
    )
    answer=(response.text or "").strip()
    if not answer: raise RuntimeError("Gemini lieferte eine leere Antwort")
    return answer

async def ask_ai(prompt: str) -> str:
    preferred=os.getenv("AI_PROVIDER","gemini").lower()
    providers={"gemini":_gemini,"ollama":_ollama}
    order=[preferred,"ollama" if preferred=="gemini" else "gemini"]
    errors=[]
    for name in order:
        try:
            return await providers[name](prompt)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("Alle KI-Anbieter fehlgeschlagen: "+"; ".join(errors))
