import base64
import datetime
import uvicorn
import os
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import Optional
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Initialize the FastAPI App and the LLM ---
app = FastAPI(title="AI-Powered Appointment Scheduler Assistant")

# Initialize the Gemini Model from LangChain
# NOTE: Corrected model name to a valid one, e.g., "gemini-1.5-flash"
# The model "gemini-2.5-flash" does not exist as of now.
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    api_key = os.getenv("GEMINI_API_KEY"),
    temperature=0,
    # The response should be JSON, so we ask the model to output it directly
    response_mime_type="application/json", 
)


# --- The Master Prompt Template ---
# This detailed prompt guides the model to produce the exact output you need.
PROMPT_TEMPLATE = """
You are an intelligent scheduling assistant. Your task is to extract, normalize, and structure appointment information from a user's request.

**Current Context:**
- Today's Date: {current_date}
- Timezone: Asia/Kolkata

**Instructions:**
1.  Analyze the user's text and/or image content. Perform OCR on the image if provided.
2.  Identify the appointment topic/department, date, and time.
3.  Normalize the date to "YYYY-MM-DD" and time to "HH:MM" (24-hour) format based on the current context.
4.  Your entire output MUST be a single, valid JSON object and nothing else.

**Guardrail:**
- If the request is ambiguous or key information (topic, date, time) is missing, you MUST return this specific JSON object:
  {{"status": "needs_clarification", "message": "Ambiguous or missing information."}}

**Success Output Structure:**
- If the information is clear, the JSON object must follow this exact structure:
  {{
    "appointment": {{
      "department": "Standardized Department Name",
      "date": "YYYY-MM-DD",
      "time": "HH:MM",
      "tz": "Asia/Kolkata"
    }},
    "status": "ok"
  }}
"""


@app.post("/parse/")
async def parse(
    input_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Parses a user request (text and/or image) to schedule an appointment
    using the correct LangChain multimodal input format.
    """
    if not input_text and not file:
        raise HTTPException(status_code=400, detail="Please provide either text or an image.")

    # Get today's date to give the model context
    current_date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    prompt = PROMPT_TEMPLATE.format(current_date=current_date_str)

    # --- This is the key change: Build a list of content parts ---
    message_content = []

    # 1. Add the system prompt/instructions as the first text part
    message_content.append({"type": "text", "text": prompt})

    # 2. Add the user's text input, if it exists
    if input_text:
        message_content.append({"type": "text", "text": f"User's request: '{input_text}'"})

    # 3. Add the user's image, if it exists
    if file:
        if not file.content_type or not file.content_type.startswith("image/"):
             raise HTTPException(status_code=400, detail="Invalid file type. Please upload an image.")
        
        # Read image bytes and encode to base64
        image_bytes = await file.read()
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")

        # Append the image as a separate dictionary in the list
        message_content.append({
            "type": "image_url",
            "image_url": f"data:{file.content_type};base64,{encoded_image}"
        })

    # Create the final HumanMessage object
    message = HumanMessage(content=message_content)

    try:
        # Call the model with the correctly structured message
        response = llm.invoke([message])
        
        # The model's response should be a JSON string. Parse it.
        # Adding a robust way to clean and parse the JSON output.
        llm_output = response.content.strip()
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:-3].strip()

        reminder_json = json.loads(llm_output)
        return reminder_json

    except json.JSONDecodeError:
        # Handle cases where the LLM output is not valid JSON
        return {
            "status": "error",
            "message": "Failed to parse the response from the AI model.",
            "raw_response": response.content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)