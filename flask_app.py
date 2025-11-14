# --- Imports ---
from flask import Flask, request, jsonify, Response
from flask_cors import CORS # For web demo
import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv
import time
import json
import string
from cerebras.cloud.sdk import Cerebras
import assemblyai as aai
from elevenlabs.client import ElevenLabs

# --- Global variable to hold our AI's "expert knowledge" ---
PROTOCOL_LIBRARY = []

# --- Setup ---
# Build Absolute Paths
project_dir = os.path.dirname(os.path.abspath(__file__))
key_path = os.path.join(project_dir, "serviceAccountKey.json")
dotenv_path = os.path.join(project_dir, ".env") 

# Load the .env file
load_dotenv(dotenv_path) 

# 1. Initialize Flask App
app = Flask(__name__)
CORS(app) # Enable CORS for our web demo

# 2. Initialize Firebase
try:
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase connection successful.")
    firebase_connected = True
except Exception as e:
    print(f"Error initializing Firebase: {e}")
    firebase_connected = False

# 3. Load API Keys & Initialize Clients
try:
    ASSEMBLYAI_API_KEY = os.environ.get('ASSEMBLYAI_API_KEY')
    CEREBRAS_API_KEY = os.environ.get('CEREBRAS_API_KEY')
    ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY')
    
    if not all([ASSEMBLYAI_API_KEY, CEREBRAS_API_KEY, ELEVENLABS_API_KEY]):
        raise KeyError("One or more API keys are missing.")
    
    aai.settings.api_key = ASSEMBLYAI_API_KEY
    cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)
    elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    
    print("All API keys loaded. Clients initialized.")
    keys_loaded = True
except Exception as e:
    print(f"Error loading API keys or initializing clients: {e}.")
    keys_loaded = False


# --- (NEW) v3.0: PROTOCOL & CONVERSATION LOGIC ---

def load_protocols_from_firebase():
    """
    Loads all protocol documents from Firebase into our global PROTOCOL_LIBRARY.
    """
    global PROTOCOL_LIBRARY
    if not firebase_connected:
        print("Error: Cannot load protocols, Firebase not connected.")
        return
    
    try:
        print("Loading protocols from Firebase...")
        docs = db.collection('protocols').stream()
        PROTOCOL_LIBRARY = [] # Clear the old library
        for doc in docs:
            protocol = doc.to_dict()
            protocol['id'] = doc.id # Store the document ID
            PROTOCOL_LIBRARY.append(protocol)
        print(f"Successfully loaded {len(PROTOCOL_LIBRARY)} protocols.")
    except Exception as e:
        print(f"Error loading protocols: {e}")

def check_for_protocol_trigger(text):
    """
    Scans the transcript for any keywords from our loaded protocols.
    """
    clean_text = text.lower().translate(str.maketrans('', '', string.punctuation))
    for protocol in PROTOCOL_LIBRARY:
        for keyword in protocol.get('keywords', []):
            if keyword in clean_text:
                print(f"Protocol trigger detected! Keyword: '{keyword}', Protocol: '{protocol.get('name')}'")
                return protocol # Return the matched protocol
    return None

def get_active_conversation():
    """
    Checks Firebase for an active conversation (e.g., one from the last 2 minutes).
    """
    try:
        # Get the most recent conversation doc
        docs_stream = db.collection('conversations') \
                        .order_by('last_update', direction=firestore.Query.DESCENDING) \
                        .limit(1) \
                        .stream()
        
        docs = list(docs_stream)
        if not docs:
            print("No active conversation found.")
            return None # No conversations found
        
        convo = docs[0].to_dict()
        convo_id = docs[0].id
        
        # Check if it's still active (e.g., within 2 minutes)
        time_since_update = time.time() - convo.get('last_update', 0)
        
        if time_since_update < 120 and convo.get('state') != 'complete':
            print(f"Active conversation found: {convo_id}")
            return docs[0] 
        else:
            print("Found an old conversation, but it has expired or is complete.")
            return None
            
    except Exception as e:
        print(f"Error getting active conversation: {e}")
        return None

def update_conversation_state(convo_id, new_state_data):
    """
    Creates or updates a conversation document in Firebase.
    """
    try:
        new_state_data['last_update'] = time.time()
        if convo_id:
            # Update existing conversation
            db.collection('conversations').document(convo_id).update(new_state_data)
            print(f"Updated conversation state for: {convo_id}")
            return convo_id
        else:
            # Create new conversation
            doc_ref = db.collection('conversations').add(new_state_data)
            convo_id = doc_ref[1].id
            print(f"Created new conversation: {convo_id}")
        return convo_id
    except Exception as e:
        print(f"Error updating conversation state: {e}")
        return None

# --- (NEW) v3.7: CEREBRAS CONVERSATIONAL AI PROMPT ---

GUIDANCE_SYSTEM_PROMPT = """
You are Virgo, an AI co-pilot for a first responder.
Your job is to be a calm, clear, and direct conversational guide.
You must follow the provided protocol.
You must guide the user one step at a time.

CRITICAL RULES:
1.  **Acknowledge and Advance:** You must *acknowledge* the user's last message before giving the *next* instruction.
2.  **Do Not Repeat:** *Do not repeat* a question if the user has already answered it. If their answer is simple (e.g., 'no,' 'yes,' 'on my leg'), acknowledge it (e.g., 'Okay, on your leg.') and proceed to the *next logical step* in the protocol.
3.  **Handle Confusion:** If the user's message is confusing or doesn't answer your question (e.g., 'what?', 'huh?', or an unrelated statement), *do not repeat* your last question. Instead, **rephrase it** to be clearer. For example, if you asked "What is your location?" and the user says "what?", you should respond with "I'm sorry, I didn't understand. Can you please confirm your location?"

---
CONTEXT: {context}
PROTOCOL NAME: {protocol_name}
PROTOCOL STEPS: {protocol_steps}
CONVERSATION HISTORY:
{history}
USER'S LATEST MESSAGE: "{user_message}"
---

Based *only* on the context and protocol, what is the *single most important next question or instruction* you should give?
Respond ONLY with your line of dialogue.
WHEN THE *ENTIRE* PROTOCOL IS FINISHED, or the user confirms the situation is resolved, you *must* end your response with the special tag: [CONVERSATION_COMPLETE]
"""

# --- (NEW) FEATURE 5 PROMPT ---
DEBRIEF_SYSTEM_PROMPT = """
You are an AI assistant for a first responder.
You will be given a list of *critical events* from the user's recent history.
Your job is to provide a brief, chronological "Tactical Debrief."
List the most important events, such as stress alerts and manual notes.
Be concise and clear.
If there are no events, just say "No critical events to debrief."
Respond ONLY with the debrief. Do not add greetings.
"""

SUMMARY_SYSTEM_PROMPT = """
You are an AI assistant for a first responder.
You will be given a list of recent radio communications.
Your job is to provide a very brief summary of *what has recently happened*, including routine check-ins.
Be concise.
Respond ONLY with the summary. Do not add greetings.
"""


# --- CEREBRAS HELPER FUNCTIONS ---

def handle_conversation_turn(protocol, transcript, convo_doc=None):
    """
    This is the new "brain" of our AI. It handles one turn of the conversation.
    """
    
    # 1. Build the context for the AI
    if convo_doc:
        convo_state = convo_doc.to_dict()
        convo_id = convo_doc.id
        context = "Continuing an active protocol."
        history = convo_state.get('history', "")
    else:
        convo_state = {}
        convo_id = None
        context = "A new protocol has just been triggered."
        history = "AI: [Conversation Started]\n"

    # 2. Create the prompt for Cerebras
    prompt = GUIDANCE_SYSTEM_PROMPT.format(
        context=context,
        protocol_name=protocol.get('name', 'N/A'),
        protocol_steps=protocol.get('steps', 'N/A'),
        history=history,
        user_message=transcript
    )
    
    print(f"Sending to Cerebras (SDK) for CONVERSATION: {transcript}")
    MODEL_ID = "llama3.1-8b"
    
    try:
        # 3. Call Cerebras
        chat_completion = cerebras_client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.3
        )
        ai_response_text = chat_completion.choices[0].message.content.strip()
        print(f"Cerebras (SDK) response: {ai_response_text}")

        # 4. Update the conversation "memory" in Firebase
        new_history = f"{history}USER: {transcript}\nAI: {ai_response_text}\n"
        
        new_state = {
            "protocol_id": protocol.get('id'),
            "protocol_name": protocol.get('name'),
            "history": new_history,
        }

        # Check if the AI wants to end the conversation
        if "[CONVERSATION_COMPLETE]" in ai_response_text:
            new_state['state'] = 'complete'
            # Clean the tag out of the response we send to the user
            ai_response_text = ai_response_text.replace("[CONVERSATION_COMPLETE]", "").strip()
            print("Conversation state set to 'complete'.")
        else:
            new_state['state'] = 'active'
        
        update_conversation_state(convo_id, new_state)
        
        # 5. Return the AI's dialogue
        return ai_response_text
        
    except Exception as e:
        print(f"Exception while calling Cerebras SDK for conversation: {e}")
        return "I'm sorry, I'm having trouble connecting."

def summarize_text(text_to_summarize, prompt_template):
    """
    A generic function to call Cerebras for summarization or debriefing.
    """
    print(f"Sending to Cerebras (SDK) for SUMMARY/DEBRIEF: {text_to_summarize[:50]}...")
    MODEL_ID = "llama3.1-8b" 
    try:
        chat_completion = cerebras_client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": prompt_template},
                {"role": "user", "content": text_to_summarize} # Send the logs as the user message
            ],
            temperature=0.3 
        )
        summary = chat_completion.choices[0].message.content.strip()
        print(f"Cerebras (SDK) summary/debrief complete: {summary}")
        return summary
    except Exception as e:
        print(f"Exception while calling Cerebras SDK for summary: {e}")
        return f"Error during summary: {e}"


# --- ELEVENLABS & SIMPLE STRESS CHECK FUNCTIONS ---

def generate_voice_audio(text_to_speak):
    print(f"Sending to ElevenLabs for voice generation: {text_to_speak}")
    try:
        audio_stream = elevenlabs_client.text_to_speech.convert(
            text=text_to_speak,
            voice_id="JBFqnCBsd6RMkjVDRZzb",
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        audio_bytes = b"".join(chunk for chunk in audio_stream)
        print("ElevenLabs audio generated and assembled successfully.")
        return audio_bytes
    except Exception as e:
        print(f"Error calling ElevenLabs: {e}")
        return None

STRESS_SYSTEM_PROMPT = """
You are an AI analysis tool... Respond ONLY with a valid JSON object...
{"is_stressed": true, "reason": "High urgency and panic detected in tone."}
OR
{"is_stressed": false, "reason": "Calm and procedural."}
"""
def analyze_for_stress_simple(text_to_analyze):
    print(f"Sending to Cerebras (SDK) for SIMPLE STRESS analysis: {text_to_analyze}")
    MODEL_ID = "llama3.1-8b" 
    try:
        chat_completion = cerebras_client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": STRESS_SYSTEM_PROMPT},
                {"role": "user", "content": text_to_analyze}
            ],
            temperature=0.1
        )
        content = chat_completion.choices[0].message.content
        analysis_json = json.loads(content)
        return analysis_json
    except Exception as e:
        return {"error": f"Exception calling SDK: {e}"}

# --- MAIN API ENDPOINT (The "Router") ---

# Load the protocols when the server first starts
if firebase_connected:
    load_protocols_from_firebase()
else:
    print("CRITICAL: Firebase not connected. Protocols will not be loaded.")


@app.route('/')
def home():
    return f"""Virgo's Whisper AI (v3.8) is online.
    {len(PROTOCOL_LIBRARY)} protocols loaded.
    <form action="/reload-protocols" method="post">
        <button type="submit">Reload Protocols from Firebase</button>
    </form>
    """

@app.route('/reload-protocols', methods=['POST'])
def reload_protocols():
    """Endpoint to manually reload protocols without restarting the server."""
    load_protocols_from_firebase()
    return f"Reloaded. {len(PROTOCOL_LIBRARY)} protocols now loaded."

@app.route('/analyze-audio-file', methods=['POST'])
def analyze_audio_file():
    print("Received a request on /analyze-audio-file...")
    if 'audio_file' not in request.files:
        return jsonify({"error": "No 'audio_file' key in request"}), 400
    
    audio_file = request.files['audio_file']
    if audio_file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # 1. Save and 2. Transcribe
    temp_file_path = os.path.join(project_dir, audio_file.filename)
    transcript_text = ""
    try:
        audio_file.save(temp_file_path)
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(temp_file_path)
        if transcript.status == aai.TranscriptStatus.error:
            return jsonify({"error": f"AssemblyAI Error: {transcript.error}"}), 500
        transcript_text = transcript.text
        if not transcript_text:
            return jsonify({"error": "Transcription returned no text"}), 500
    except Exception as e:
        return jsonify({"error": f"Server error: {e}"}), 500
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

    # 3. CONVERSATION ROUTING
    try:
        ai_response_text = None
        
        # Define clean_text here for all checks
        clean_text = transcript_text.lower().translate(str.maketrans('', '', string.punctuation))

        # Check for "over and out" first as a master override
        if "over and out" in clean_text:
            print("'Over and out' detected. Ending conversation.")
            active_convo_doc = get_active_conversation()
            if active_convo_doc:
                update_conversation_state(active_convo_doc.id, {"state": "complete"})
            
            audio_data = generate_voice_audio("Roger that. Virgo out.")
            return Response(audio_data, mimetype="audio/mpeg")

        # Check for an active conversation
        active_convo_doc = get_active_conversation()
        
        if active_convo_doc:
            convo_state = active_convo_doc.to_dict()
            protocol = next((p for p in PROTOCOL_LIBRARY if p['id'] == convo_state.get('protocol_id')), None)
            if protocol:
                ai_response_text = handle_conversation_turn(protocol, transcript_text, active_convo_doc)
            else:
                print(f"Error: Active convo {active_convo_doc.id} has a missing protocol ID. Treating as new.")
        
        if not ai_response_text:
            # No active convo. Check for our non-protocol commands.
            
            if "virgo take a note" in clean_text:
                print("Command detected: 'virgo take a note'")
                try:
                    note = transcript_text.lower().split("take a note", 1)[1].strip()
                except IndexError:
                    note = "" 
                
                if note:
                    log_data = { 'text': note, 'original_command': transcript_text, 'timestamp': time.time(), 'type': 'manual_log' }
                    db.collection('transcripts').add(log_data)
                    print(f"Successfully logged manual note: {note}")
                    ai_response_text = f"Note taken: {note}"
                else:
                    ai_response_text = "I heard the 'take a note' command, but didn't catch the note. Please try again."

            elif "virgo summarize" in clean_text:
                print("Command detected: 'virgo summarize'")
                docs_stream = db.collection('transcripts').where('type', '==', 'general_comm').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10).stream()
                recent_comms = [doc.to_dict().get('text', '') for doc in docs_stream]
                recent_comms.reverse()
                
                if not recent_comms:
                    ai_response_text = "No recent communications to summarize."
                else:
                    comms_for_prompt = "\n- ".join(recent_comms)
                    ai_response_text = summarize_text(comms_for_prompt, SUMMARY_SYSTEM_PROMPT)
            
            # --- (THIS IS THE FIX) ---
            # Changed 'clean_' to 'clean_text' and added the missing ':'
            elif "virgo debrief me" in clean_text:
                print("Command detected: 'virgo debrief me'")
                docs_stream = db.collection('transcripts') \
                                .order_by('timestamp', direction=firestore.Query.DESCENDING) \
                                .limit(20) \
                                .stream()
                
                critical_events = []
                for doc in docs_stream:
                    event = doc.to_dict()
                    event_type = event.get('type')
                    if event_type == 'stress_detected':
                        critical_events.append(f"Stress detected: {event.get('text', '')}")
                    elif event_type == 'manual_log':
                        critical_events.append(f"Manual log: {event.get('text', '')}")
                
                critical_events.reverse() # Put in chronological order

                if not critical_events:
                    ai_response_text = "No critical events to debrief."
                else:
                    events_for_prompt = "\n- ".join(critical_events)
                    ai_response_text = summarize_text(events_for_prompt, DEBRIEF_SYSTEM_PROMPT)
            # --- (END OF FIX) ---
            
            # Check for a *new* protocol trigger.
            if not ai_response_text:
                triggered_protocol = check_for_protocol_trigger(transcript_text)
                if triggered_protocol:
                    ai_response_text = handle_conversation_turn(triggered_protocol, transcript_text, None)
        
        if ai_response_text:
            # We have a conversational response! Generate audio and return it.
            print(f"CONVERSATIONAL RESPONSE: {ai_response_text}")
            audio_data = generate_voice_audio(ai_response_text)
            if audio_data:
                return Response(audio_data, mimetype="audio/mpeg")
            else:
                return jsonify({"error": "Failed to generate voice"}), 500
        
        # Step 3c: No convo, no trigger. Do a simple stress check (v2.0 logic).
        print("No conversation or trigger. Running simple stress check.")
        analysis_result = analyze_for_stress_simple(transcript_text)
        
        log_data = { 'text': transcript_text, 'original_filename': audio_file.filename, 'timestamp': time.time(), 'type': 'general_comm', 'cerebras_analysis': analysis_result }
        
        if analysis_result.get("is_stressed") == True:
            log_data['type'] = 'stress_detected'
            db.collection('transcripts').add(log_data) # Log the stress event
            audio_data = generate_voice_audio("Deep breath. Focus.")
            if audio_data:
                return Response(audio_data, mimetype="audio/mpeg")
            else:
                return jsonify({"error": "Failed to generate voice"}), 500
        else:
            db.collection('transcripts').add(log_data) # Log the general_comm event
            return "OK", 204 # 204 means "No Content"

    except Exception as e:
        print(f"Error in main analysis loop: {e}")
        return jsonify({"error": f"Server error: {e}"}), 500