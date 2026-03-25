import google.generativeai as genai
import os

from dotenv import load_dotenv

# API 키 설정 (외부 파일 로드)
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    # 텍스트 파일에서도 시도
    if os.path.exists("gemini_api_key.txt"):
        with open("gemini_api_key.txt", "r", encoding="utf-8") as f:
            api_key = f.read().strip()

if api_key:
    genai.configure(api_key=api_key)
else:
    print("❌ API 키를 찾을 수 없습니다.")
    exit()

print("사용 가능한 모델 목록:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")