from google import genai
from google.genai import types


class GeminiClient:
    def __init__(self, llm_model, tools, api_key):
        self.llm_model = llm_model
        self.tools = tools
        self.client = genai.Client(api_key=api_key)

    async def generate(self, contents, available_tools, temperature, system_prompt):
        config = types.GenerateContentConfig(
            temperature=temperature, tools=available_tools, system_instruction=system_prompt)
        try:
            response = self.client.aio.models.generate_content(
                model=self.llm_model, contents=contents,
                config=config)
            return response
        except Exception as e:
            print("The error is: ", e)
            raise
