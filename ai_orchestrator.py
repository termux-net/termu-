import google.generativeai as genai
from typing import List, Optional
import asyncio

class AIOrchestrator:
    def __init__(self, api_key: str, system_prompt: str, thinking_budget: int = 0):
        genai.configure(api_key=api_key)
        self.system_prompt = system_prompt
        self.thinking_budget = thinking_budget
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')

    def build_prompt(self, user_message: str, file_info: Optional[dict] = None) -> str:
        prompt = f"[SYSTÈME] {self.system_prompt}\n\n"
        
        if file_info:
            if file_info["type"] == "text":
                prompt += f"[FICHIER: {file_info['filename']}]\n{file_info['content']}\n\n"
            elif file_info["type"] == "image":
                prompt += f"[IMAGE REÇUE: {file_info['filename']}]\n"
        
        prompt += f"[UTILISATEUR] {user_message}"
        return prompt

    async def stream_response(self, prompt: str, file_info: Optional[dict] = None):
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 24048,
        }
        
        if self.thinking_budget > 0:
            generation_config["thinking_config"] = {"thinking_budget": self.thinking_budget}

        contents = [prompt]
        
        if file_info and file_info["type"] in ["image", "pdf"]:
            contents.append({
                "mime_type": file_info["mime_type"] if "mime_type" in file_info else "application/pdf",
                "data": file_info["data"]
            })

        response = self.model.generate_content(
            contents,
            generation_config=generation_config,
            stream=True
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text
                await asyncio.sleep(0.01)
