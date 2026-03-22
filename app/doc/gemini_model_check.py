import google.generativeai as genai
import os

# API 키 설정 (기존 코드에 있는 키 사용)
os.environ["GOOGLE_API_KEY"] = "AIzaSyAquL8Mno2bGxB77WnSVXSTAVs-knk7slo"
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

print("사용 가능한 모델 목록:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")