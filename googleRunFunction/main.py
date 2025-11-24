############################################
# Testing Script Used to Test Iftracer with Google Cloud Run Function
############################################

from openai import OpenAI
import os
import flask
import logging
from iftracer.sdk import Iftracer
from iftracer.sdk.instruments import Instruments
from iftracer.sdk.decorators import task

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set iftracer environment variables
os.environ["IFTRACER_BASE_URL"] = "http://52.90.56.233:4518"
os.environ["IFTRACER_APP_NAME"] = "gRunFunc"

logger.info(f"Initializing IFTracer with BASE_URL: {os.environ.get('IFTRACER_BASE_URL')}")

# Initialize IFTracer with OpenAI auto-instrumentation
Iftracer.init(
    app_name="gRunFunc",
    instruments={Instruments.OPENAI}
)

logger.info("IFTracer initialized successfully")

# Replace with your actual OpenAI API key
client = OpenAI(api_key="ENTER_YOUR_OPENAI_API_KEY")

@task(name="openai_api_call")
def call_openai(user_prompt):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # or "gpt-4" if you have access
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=100
    )
    result = response.choices[0].message.content.strip()
    return result

def call_openai_handler(request):
    """HTTP Cloud Function entry point.
    Args:
        request (flask.Request): The request object.
    Returns:
        JSON response
    """
    try:
        logger.info(f"Received request: method={request.method}")
        
        # Handle GET request with query parameter
        if request.method == "GET":
            user_prompt = request.args.get("prompt", "Hello, how are you?")
        # Handle POST request with JSON body
        else:
            request_json = request.get_json(silent=True)
            user_prompt = request_json.get("prompt", "Hello, how are you?") if request_json else "Hello, how are you?"
        
        logger.info(f"Processing prompt: {user_prompt[:50]}...")
        result = call_openai(user_prompt)
        logger.info(f"OpenAI call completed successfully")
        
        return flask.jsonify({
            "success": True,
            "prompt": user_prompt,
            "response": result
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return flask.jsonify({
            "success": False,
            "error": str(e)
        }), 500

# For local testing only
if __name__ == "__main__":
    from flask import Flask, request as flask_request
    
    app = Flask(__name__)
    
    @app.route("/", methods=["GET", "POST"])
    def local_handler():
        return call_openai_handler(flask_request)
    
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting local server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)